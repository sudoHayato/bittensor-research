# SN34 — BitMind — Deep Dive v3

## Resumo

BitMind (SN34) e um subnet focado em deteccao de deepfakes e media sintetica. O subnet opera com dois tipos de miners:
- **Generators**: geram imagens/videos sinteticos a pedido dos validators
- **Discriminators**: detectam se media e real ou sintetica (benchmarked via API externa)

A arquitetura v3 introduziu um modelo de "escrow" onde 93% do peso de emissoes vai para enderecos especiais (burn 40%, video escrow 23.5%, image escrow 28.5%, audio escrow 1%), deixando apenas **7% das emissoes para generators ativos**. Isto altera drasticamente a economia para miners.

## Codigo (validator/reward)

### Fluxo de Scoring (Generators)

1. **Base Rewards** (`get_generator_base_rewards`): Calculados a partir de `verification_stats` das ultimas 4h. Usa `pass_rate * min(verified_count, 10)` — volume bonus capped a 10 submissions.

2. **Reward Multipliers** (`get_generator_reward_multipliers`): Baseados em `fool_rate` (taxa de enganar discriminators) com bonus logaritmico por sample size:
   - `fool_rate * sample_size_multiplier` (max 2.0)
   - Reference count = 20, abaixo disso penalizacao
   - Dados vem de API externa `gas.bitmind.ai` (ultimos 7 dias)

3. **Score Update**: EMA com alpha=0.5 (decay agressivo). Generators inativos >24h sao zerados.

4. **Weight Distribution** (validator.py L219-271):
   ```
   burn_pct      = 0.40   (40%)
   video_pct     = 0.235  (23.5%)
   image_pct     = 0.285  (28.5%)
   audio_pct     = 0.01   (1%)
   generator_pct = 0.07   (7%)
   ```
   Generators recebem apenas 7% do total de emissoes, normalized via L1 norm.

5. **set_weights**: Usa `process_weights_for_netuid` standard do bittensor, sem manipulacao adicional.

### Fluxo de Scoring (Discriminators)
- Benchmarked via API externa (`gas.bitmind.ai`)
- Weighted por binary MCC e multiclass MCC
- Pesos: image 60%, video 40%; binary 75%, multiclass 25%

### Verificacao de Conteudo Gerado
- CLIP consensus scoring (3 modelos) com threshold 0.25
- C2PA verification obrigatoria (trusted issuer required)
- Duplicate detection via perceptual hashing
- Corrupted media detection

## Red Flags Adversariais

### trust_remote_code=True
**ENCONTRADO** em `gas/generation/util/model.py` (L223, L234) - usado para carregar Janus model. Isto e no lado da **geracao de conteudo sintetico** (GAS pipeline do validator), nao no miner diretamente. Risco moderado — modelo e carregado de HuggingFace com `trust_remote_code=True`, poderia executar codigo arbitrario se o repo HF fosse comprometido.

### Auto-updater
**ENCONTRADO** em `gas/utils/autoupdater.py`. O updater:
- Fetch VERSION de `raw.githubusercontent.com/BitMind-AI/bitmind-subnet/main/VERSION`
- Compara versoes e faz `git pull` + `pm2 restart`
- Usa `os.system(f"cd {base_path} && git pull")` (L182) — command injection risk se `base_path` fosse manipulavel (improvavel mas ma pratica)
- Pode executar `gascli install-py-deps --clear-venv` que reinstala dependencias
- **Risco**: Updates automaticos do branch main podem introduzir codigo malicioso sem revisao

### Dependencia de API Externa
**FLAG SIGNIFICATIVA**: Escrow addresses sao fetched dinamicamente de `gas.bitmind.ai/api/v1/validator/escrow-addresses` (L186-199). Se a API retornar enderecos maliciosos, 93% das emissoes poderiam ser redirecionadas. Fallback para hardcoded defaults mitiga parcialmente.

### Benchmark results de API externa
Generator rewards dependem de `gas.bitmind.ai/api/v1/validator/generator-results`. Se esta API for comprometida ou manipulada, os multipliers de reward seriam afetados. A equipa BitMind controla esta API.

### Pickle deserialization
**ENCONTRADO** em `generative_challenge_manager.py` (L570, L581). Loads pickle files do disco local para state recovery. Risco baixo (ficheiros locais), mas pickle e inerentemente inseguro.

### Softmax/Temperature
Nenhuma manipulacao encontrada. Temperature 1.0 usada normalmente em geracao de texto para prompts (nao afeta scoring).

### Hardcoded UIDs
Nenhum UID hardcoded favorecendo miners especificos. `MAINNET_UID = 34` e apenas o netuid do subnet.

### Kill Switches
Nenhum encontrado.

### Lambda/Weight Manipulation
Nenhuma manipulacao de pesos antes de `set_weights`. A normalizacao e standard (L1 norm, `process_weights_for_netuid`).

### Resumo Red Flags
| Flag | Status | Severidade |
|------|--------|-----------|
| Softmax temp >10 | NAO ENCONTRADO | - |
| Lambda manipulation | NAO ENCONTRADO | - |
| Hardcoded UIDs favorecidos | NAO ENCONTRADO | - |
| Kill switch | NAO ENCONTRADO | - |
| trust_remote_code=True | ENCONTRADO (Janus model) | MEDIA |
| Auto-updater sem verificacao | ENCONTRADO (git pull + pm2 restart) | MEDIA-ALTA |
| API externa controla 93% das emissoes (escrow addresses) | ENCONTRADO | ALTA |
| API externa controla reward multipliers | ENCONTRADO | ALTA |
| Pickle deserialization | ENCONTRADO (local files) | BAIXA |

## Hardware Requirements

### Validator (min_compute.yml)
- GPU: **NVIDIA A100 80GB** (min 80GB VRAM, compute capability 8.0)
- RAM: 32GB
- Storage: 1TB SSD
- CPU: 8 cores @ 3.5GHz

### Miner (Generator)
- **CUDA obrigatorio** (`LocalService` requer CUDA)
- Modelos carregados: SDXL, FLUX.1-dev, HunyuanVideo, CogVideoX, Wan, Chroma, AnimateDiff
- FLUX.1-dev sozinho precisa ~24GB VRAM
- Video models (HunyuanVideo, CogVideoX) precisam 24-48GB VRAM
- **Minimo pratico: RTX 4090 (24GB) para imagem-only, A100 para video**
- Miners podem usar APIs externas (OpenAI, StabilityAI, OpenRouter) em vez de local, mas precisam de C2PA verification

### Miner (Discriminator)
- Operado pela equipa BitMind (benchmarked via API)
- Nao e claro se miners independentes podem operar discriminators

## ECONOMIA REAL

### Parametros Base
- Emissao diaria: 77.76 TAO/dia
- TAO/USD: $320
- Emissao diaria USD: $24,883.20/dia = $746,496/mês

### Distribuicao Real de Emissoes
Com 93% a ir para burn/escrow:
- **Burn (40%)**: $298,598/mes — destruido
- **Video Escrow (23.5%)**: $175,427/mes
- **Image Escrow (28.5%)**: $212,752/mes
- **Audio Escrow (1%)**: $7,465/mes
- **Generators (7%)**: $52,255/mes — pool total para TODOS os generators

### Calculo para Generators (7% pool = $52,255/mes)
- Top 1 receita mensal real: **$359,872** (dado fornecido, inclui provavelmente escrow UIDs)
- Top 1 generator real (7% pool, share 48.2% do pool generator): ~$25,187/mes
- Top 10 mediana generator: ~$2,000-3,000/mes (estimado)
- Miner mediano: **$1,708/mes** (dado fornecido, mas se isto e sobre o pool total, miner mediano do pool generator 7% seria ~$120/mes)

### Nota Critica sobre Economia
Os dados fornecidos (top1=$359,872, median=$1,708) provavelmente incluem os UIDs de escrow como "miners". Se o top1 e um escrow UID recebendo 28.5% das emissoes, a economia real para generators e dramaticamente diferente:

**Cenario A** (dados incluem escrow UIDs):
- Top 1 receita mensal real: $359,872 (escrow UID, nao um generator real)
- Miner mediano real (generator): ~$120/mes
- Break-even Vast.ai ($180/mes): **NUNCA** (mediano nao cobre custos)
- Break-even Hetzner (€184/mes ≈ $200/mes): **NUNCA**

**Cenario B** (dados ja excluem escrow, improvavel):
- Top 1 receita mensal real: $359,872
- Miner mediano: $1,708/mes
- Break-even Vast.ai ($180/mes): **1 dia** (lucro desde dia 1)
- Break-even Hetzner (€184/mes ≈ $200/mes): **1 dia**

### Calculo Mais Provavel (Cenario A)
Pool generator = 7% de $746,496 = **$52,255/mes**
Com 50 miners scoring e Gini 0.872:
- Top 1 generator: ~$25,187/mes
- Top 5 generator: ~$5,000-10,000/mes
- Top 10 generator: ~$2,000-4,000/mes
- Miner mediano (#25): ~$200-400/mes
- Bottom 50%: <$100/mes

- Break-even Vast.ai ($180/mes): Possivel para top ~25 miners
- Break-even Hetzner (€184/mes ≈ $200/mes): Possivel para top ~20-25 miners
- **Metade dos miners opera em prejuizo**

## VEREDICTO ECONOMICO: MARGINAL

### Justificacao
1. **93% das emissoes nao vao para miners** — burn (40%) + escrow (53%) deixa apenas 7% para generators
2. **Pool de $52K/mes para ~50 generators** — media seria ~$1,045/mes, mas Gini 0.872 significa concentracao extrema
3. **Hardware pesado** — RTX 4090 ($180/mes Vast.ai) ou melhor e obrigatorio, A100 para ser competitivo em video
4. **Dependencia critica de API externa** — `gas.bitmind.ai` controla escrow addresses e benchmark results, risco de centralizacao
5. **Top miners podem ser lucrativos** ($5K-25K/mes), mas mediano esta no limiar do break-even
6. **Miners API-dependent** podem usar OpenAI/StabilityAI/OpenRouter em vez de GPU local, alterando o calculo de custos (mas precisam pagar por API calls + C2PA verification)
7. **C2PA requirement** limita quais modelos/APIs podem ser usados, criando barreira de entrada

### Risco Adicional
A equipa BitMind controla a API que determina tanto os enderecos de escrow (93% das emissoes) como os benchmark results (multiplicadores de reward). Isto cria um ponto unico de falha e potencial de manipulacao que e incomum entre subnets.
