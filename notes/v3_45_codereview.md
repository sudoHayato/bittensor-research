# SN45 — Talisman AI — Deep Dive v3

## Resumo

Talisman AI e um subnet de analise de sentimento e relevancia de posts X/Twitter e Telegram para o ecossistema Bittensor. Miners recebem batches de tweets/mensagens de validators, classificam com LLM (via OpenAI API, temperature=0), e devolvem resultados. Validators re-executam a classificacao numa amostra e comparam resultados exactos. O sistema usa um modelo push-based: validator envia batch ao miner, miner processa em background e envia resultados de volta ao validator axon.

**ALERTA CRITICO**: Top1 share = 99.8% e um monopolio quase total. A causa raiz e o mecanismo de BURN: a funcao `calculate_weights()` em `burn.py` aloca TODO o peso nao atribuido a miners ao `BURN_UID=189`. Com apenas 6 miners scoring e recompensas pequenas por ponto, a vasta maioria do peso (~90%+) vai para UID 189 (burn address). Isto significa que o UID 189 captura quase toda a emissao. Nao e um miner a dominar -- e o sistema de burn que absorve quase tudo.

## Codigo (validator/reward)

### Fluxo de Validacao
1. `ValidationClient.run()` poll a API central por tweets/mensagens nao processados
2. Tweets sao distribuidos a miners via `_on_tweets()` -> `_dispatch_miner_batch()`
3. Miner recebe `TweetBatch` synapse, classifica cada tweet com LLM (`SubnetRelevanceAnalyzer.classify_post()`), devolve ao validator
4. Validator valida amostras (`validate_miner_batch()`, sample_size=1): re-classifica e compara 6 campos (subnet_id, sentiment, content_type, technical_quality, market_analysis, impact_potential) com match exacto case-insensitive
5. Se valido: +1 reward por tweet. Se invalido: +1 penalty por batch

### Sistema de Pesos
- `calculate_weights()` em `burn.py` e o core:
  - Converte pontos (rewards) em percentagem de alpha necessario via `get_percent_needed_to_equal_points()`
  - Cada ponto vale `USD_PRICE_PER_POINT = $0.040`
  - `alpha_per_point = alpha_price / USD_PRICE_PER_POINT`
  - O peso restante (1 - total_percent_miners) vai para `BURN_UID=189`
  - Linha critica: `weights[config.BURN_UID] = (1 - (min(total_percent_needed, 100) / 100))`
- `update_scores()` em `base/validator.py` faz replacement directo (NAO EMA): `self.scores = scattered_rewards`
- `set_weights()` normaliza via L1 norm e aplica `process_weights_for_netuid()`

### Epochs
- `BLOCK_LENGTH=100` blocks por epoch (~8.3 min)
- Rewards broadcast para outros validators com delay de 1 epoch
- Pesos calculados com base em epoch E-2 (2 epochs atras)
- Penalties requerem 2+ validators a penalizar o mesmo UID

## Red Flags Adversariais

### 1. BURN_UID Hardcoded = 189 -- FLAG AMARELA
- `config.py` linha 118: `BURN_UID = int(os.getenv("BURN_UID", "189"))`
- `burn.py` linha 238: todo o peso nao alocado a miners vai para este UID
- Burn modifier antigo comentado em `base/validator.py` (linhas 578-582) com `burn_modifier: float = 0.9`
- **Risco**: Se UID 189 for controlado pelo team e nao for genuinamente um burn address, isto e extraccao directa de valor. Com 99.8% do peso a ir para este UID, isto e potencialmente $226k/mes para uma unica entidade
- **Mitigacao**: E configuravel via env var, mas o default e 189

### 2. API Central Opaca -- FLAG VERMELHA
- O validator depende de `MINER_API_URL` (API central do team) para:
  - Obter tweets nao processados (`get_unscored_tweets`)
  - Submeter resultados (`submit_completed_tweets`)
  - Obter preco TAO (`/price/tao-usd`)
  - Verificar axon reachability (`check_axon`)
- Esta API controla QUE tweets sao distribuidos, a QUEM, e com que frequencia
- **Risco**: O team pode manipular a distribuicao de trabalho para favorecer os seus proprios miners
- Codigo da API NAO e open-source -- caixa preta total

### 3. Auto-Updater -- FLAG AMARELA
- `scripts/start_validator.py`: `git pull --rebase` + `pip install` automatico a cada 1 minuto
- Codigo arbitrario pode ser injectado via commits ao repo
- **Mitigacao**: Usa o branch actual, nao um branch especifico. Standard para subnets Bittensor mas continua a ser um vector de ataque

### 4. LLM como Oraculo Deterministico -- FLAG AMARELA
- Classificacao usa `temperature=0` com OpenAI API para reprodutibilidade
- Mas LLMs nao sao 100% deterministicos mesmo com temperature=0 (known issue da OpenAI)
- Validacao por sample_size=1: uma unica amostra errada = penalidade total do batch
- **Risco**: Miners podem ser penalizados por non-determinismo do LLM, nao por desonestidade

### 5. Sem softmax manipulation, sem kill switch, sem trust_remote_code
- Temperature = 0 (nao >10)
- Sem `exec()` ou `eval()` 
- Sem hardcoded UIDs em reward logic (excepto BURN_UID)
- Sem lambda manipulation antes de set_weights
- Normalizacao standard (L1 norm + process_weights_for_netuid)

### 6. Reward Broadcast Trust Model -- FLAG AMARELA
- Validators broadcast rewards/penalties entre si
- `RewardBroadcastStore` aceita dados de qualquer validator com permit
- Aggregacao simples: soma de pontos de todos os validators
- **Risco**: Um validator malicioso com alto stake pode inflacionar rewards para miners aliados

## Hardware Requirements

### Miner
- GPU: Obrigatorio (min 8GB VRAM, recomendado 24GB / A100)
- CPU: 4-8 cores
- RAM: 16GB
- Storage: 10-100GB SSD
- **Nota**: Miner precisa de API key OpenAI (`API_KEY`, `LLM_BASE`, `MODEL`) e paga custos de inferencia LLM por tweet. Requer tambem X API bearer token
- **Custo real miner**: Hardware + custo API OpenAI por tweet processado

### Validator
- Mesmos requisitos que miner (GPU required)
- Precisa de axon publicamente acessivel
- Precisa de API keys: OpenAI + X API + MINER_API_URL (API do team)

## ECONOMIA REAL

### Calculo de receitas
- emission_tao_day: 23.62 TAO
- TAO_USD: $320
- Emissao diaria USD: 23.62 * 320 = $7,558/dia = $226,752/mes

### Distribuicao
- Top 1 receita mensal real (UID 189 / BURN): **$226,291** (99.8% share)
- Top 10 mediana: ~$100 (restos divididos entre ~6 miners activos)
- Miner mediano: **$100/mes**

### Break-even Analysis (para miner mediano com $100/mes receita)
- **Atencao**: Alem de hardware, miner paga custos API OpenAI por cada tweet classificado
- Receita miner mediano: ~$100/mes (estimativa optimista)
- Break-even Vast.ai ($180/mes): **NUNCA** (receita < custo hardware, sem contar API costs)
- Break-even Hetzner (EUR184/mes ~= $200/mes): **NUNCA** (receita < custo hardware)

### Nota sobre o BURN
- O mecanismo `calculate_weights()` aloca peso residual ao BURN_UID
- Com `USD_PRICE_PER_POINT = $0.040` e poucos miners/pontos, quase todo o peso vai para burn
- Isto e by design para "queimar" emissoes nao utilizadas, mas na pratica significa que 99.8% da emissao vai para UID 189
- Se UID 189 e genuinamente um burn address, os miners dividem apenas ~0.2% da emissao (~$453/mes total para todos os miners)
- Se UID 189 NAO e burn, alguem esta a capturar $226k/mes

## VEREDICTO ECONOMICO: IMPOSSIBLE

### Razoes
1. **Monopolio pelo BURN**: 99.8% da emissao vai para BURN_UID=189. Os miners reais dividem migalhas
2. **Receita miner < custos**: Com ~$100/mes de receita mediana e custos de $180-200/mes so em hardware (+ custos API OpenAI), e matematicamente impossivel ser lucrativo
3. **API Central opaca**: A distribuicao de trabalho e controlada por uma API closed-source do team, criando assimetria de informacao
4. **Barreira de entrada alta**: GPU obrigatoria + API keys pagas (OpenAI + X API) + axon publico
5. **6 miners activos**: Subnet essencialmente morto em termos de participacao competitiva
6. **Risco de manipulacao**: Se o BURN_UID nao for genuinamente burn, o team extrai ~$226k/mes
7. **LLM non-determinism**: Penalizacoes por falsos negativos na validacao sample-of-1 aumentam o risco

### Conclusao
SN45 e um subnet onde a quase totalidade da emissao e capturada pelo mecanismo de burn (UID 189). Para um miner individual, a receita esperada e inferior aos custos operacionais. O modelo economico e fundamentalmente quebrado para participantes externos. A dependencia de uma API central closed-source e a concentracao extrema de emissoes (Gini=0.831) tornam este subnet **economicamente impossivel** para novos mineradores.
