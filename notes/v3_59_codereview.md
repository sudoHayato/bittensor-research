# SN59 — Babelbit — Deep Dive v3

## Resumo

Babelbit e um subnet de traducao preditiva de baixa latencia ("interpretacao em tempo real"). Miners recebem tokens de fala um a um e devem prever o restante da frase antes de ser totalmente revelada. O scoring usa similaridade semantica (cosine via sentence-transformers `mxbai-embed-large-v1`) calibrada contra baseline + earliness bonus (`U_step = similarity * 1/(step+1)`). A media de U_best por dialogo determina o score do miner.

**O sistema de pesos e WINNER-TAKE-ALL**: 95% das emissoes vao para o melhor miner (main winner), com apenas 5% distribuidos proporcionalmente entre miners trailing. Isto explica diretamente o Gini de 0.953.

## Codigo (validator/reward)

### Arquitetura
- **Utterance Engine** (servico externo em `api.babelbit.ai`): gera os desafios/dialogos, revela tokens palavra a palavra
- **Runner** (`runner.py`): orquestra as rondas - busca miners do registry (commitments on-chain + axons), envia tokens para todos os miners em paralelo, coleta predicoes, faz scoring local via `score_dialogue.py`
- **Score Dialogue** (`score_dialogue.py`): scoring local usando SentenceTransformer para embeddings, calcula cosine similarity calibrada contra baseline random, pondera por earliness
- **Validator** (`validate.py`): busca scores da API centralizada (`scoring.babelbit.ai`), seleciona winner, define pesos on-chain
- **Submit API** (servico externo): recebe logs/scores dos validators, agrega, retorna scores consolidados

### Fluxo de Scoring
1. Runner envia tokens para miners, coleta predicoes
2. `score_jsonl()` calcula score: `U_step = calibrated_semantic(cos, baseline) * (1/(step+1))`
3. Calibracao: `s = clamp01((cos_raw - baseline_b) / (1 - baseline_b))` onde baseline e media de cosine de pares aleatorios de ground truth
4. Score do dialogo = media dos best U_step por utterance
5. Scores sao submetidos para a API centralizada (`scoring.babelbit.ai`)
6. Validator busca scores da API e faz `max()` para selecionar winner

### Sistema de Pesos (`compute_weights`)
- **Winner principal (main)**: recebe `(1 - TRAILING_INCENTIVE_FRACTION) * (1 - arena_fraction)` = ~95% (com arena_fraction=0 por default)
- **Winner arena**: recebe `(1 - TRAILING) * arena_fraction` (0% por default, configuravel via env)
- **Trailing miners**: 5% total dividido proporcionalmente entre todos os outros com score > 0
- **Fallback UID 248**: recebe peso quando nao ha winner ou arena winner (burn_uid)
- Quando nao ha scores por 12 rondas consecutivas, 100% vai para UID 248

### Scoring Centralizado
O scoring final NAO e feito localmente pelo validator - e buscado de `scoring.babelbit.ai/v1/get_scores`. Embora o runner faca scoring local e submeta resultados, a decisao final de quem ganha vem da API centralizada. Isto e um ponto critico de centralizacao.

## Red Flags Adversariais

### CRITICO: UID 248 Hardcoded como Fallback
```python
DEFAULT_FALLBACK_UID = _get_int_env("BB_DEFAULT_FALLBACK_UID", 248)
```
Quando nao ha scores disponiveis por 12+ rondas, ou quando nao ha winner/arena_winner, UID 248 recebe 100% do peso. Tambem e usado como `burn_uid` para absorver a fracao de arena quando nao ha arena winner. Este UID pode pertencer ao team - configurable via env var mas o default de 248 e suspeito.

### CRITICO: Scoring Centralizado (Opaco)
Scores finais vem de `scoring.babelbit.ai` - um servico controlado pelo team. Os validators fazem scoring local mas submetem para a API, e depois buscam o resultado consolidado da mesma API. O team tem controle total sobre quais scores sao retornados, podendo favorecer qualquer miner.

### MEDIO: Winner-Take-All Design Explica Gini = 0.953
O design intencional de 95% para o winner e 5% trailing e a causa direta da concentracao extrema. Nao e um bug - e uma escolha de design que torna o subnet extremamente concentrado por natureza.

### NAO ENCONTRADO: Softmax manipulation, temperature hacking, trust_remote_code, auto-updaters
- Nenhum softmax com temperatura alta
- Nenhum `trust_remote_code=True`
- Nenhum auto-updater (sem git pull, sem self-update)
- Nenhum `exec()` ou `eval()` no codigo de producao
- `subprocess` usado apenas para info de git (branch/commit) em logs de boot
- Temperature parametros existem apenas em dev_scripts (phrase_completion.py) para chamadas OpenAI, nao no scoring

### NOTA: Arena System
Arena challenge e opcional (BB_ENABLE_ARENA_CHALLENGE=true por default), com cadencia configuravel. Arena incentive fraction e 0% por default (env BB_ARENA_INCENTIVE_PERCENT). O split entre main/arena e configuravel mas por default tudo vai para main.

## Hardware Requirements

Segundo `min_compute.yml`:
- **Minimo**: 2 CPU, 4GB RAM, sem GPU, 50GB storage
- **Recomendado**: 4 CPU, 16GB RAM, 1 GPU (T4 ou equiv), 200GB NVMe

O scorer usa `sentence-transformers` com device CPU por default (`BB_SCORER_DEVICE=cpu`). O miner precisa de um modelo de ML para predicao - referencia ao repo separado `babelbit_miner`. O modelo base referenciado e `babelbit-ai/base-miner` no HuggingFace.

Para mining, hardware GPU e provavelmente necessario para inference competitiva, mas o subnet nao exige GPU especifica. Uma RTX 4090 seria mais que suficiente.

**hardware_heavy: False** - Confirmado. CPU pode funcionar para mining basico, GPU recomendada para competitividade.

## ECONOMIA REAL

### Parametros
- emission_tao_day: 22.19 TAO
- TAO_USD: $320
- Emissao diaria USD: 22.19 * 320 = $7,100.80/dia = $213,024/mes

### Distribuicao Real (Gini = 0.953)
- **Top 1 receita mensal real**: $202,774 (95.2% share)
- **Top 10 mediana**: Estimada ~$62-200 (trailing miners recebem migalhas do pool de 5%)
- **Miner mediano (rank 87 de 174)**: $62/mes

### Analise do Winner-Take-All
Com 95% para o winner e 5% para trailing:
- Winner: ~$202,374/mes
- Pool trailing: ~$10,651/mes dividido entre ~173 miners
- Media trailing: ~$61.5/mes

### Break-even

**Para o winner (top 1):**
- Break-even Vast.ai ($180/mes): **< 1 dia** (receita de $6,759/dia)
- Break-even Hetzner (EUR 184/mes): **< 1 dia**

**Para miner mediano ($62/mes):**
- Break-even Vast.ai ($180/mes): **NUNCA** (receita < custo)
- Break-even Hetzner (EUR 184/mes): **NUNCA** (receita < custo)

**Para miner trailing top 10 (~$150-200/mes estimado):**
- Break-even Vast.ai ($180/mes): **Marginal a impossivel**
- Break-even Hetzner (EUR 184/mes): **Marginal a impossivel**

## VEREDICTO ECONOMICO: IMPOSSIBLE

O subnet SN59 tem o Gini mais alto do dataset inteiro (0.953) por design: 95% das emissoes vao para UM unico miner winner. Isto torna mining viavel APENAS para quem consegue ser consistentemente o melhor - para todos os outros 173 miners, o retorno mediano de $62/mes nao cobre sequer os custos de infraestrutura mais basicos ($180/mes Vast.ai).

**Riscos adicionais:**
1. **Centralizacao critica**: Scores vem de API do team (scoring.babelbit.ai), nao verificaveis on-chain
2. **UID 248 hardcoded**: Fallback UID que recebe 100% quando nao ha scores - potencial insider advantage
3. **Winner-take-all extremo**: Estruturalmente impossivel para a maioria dos miners ter ROI positivo
4. **Opacidade**: O scoring final e feito off-chain num servico proprietario

**Recomendacao**: Evitar mining neste subnet a menos que tenha um modelo superior comprovado e esteja confiante em manter a posicao #1 consistentemente. Para os restantes 99.4% dos miners, o retorno e inferior ao custo operacional.
