# SN22 — Desearch — Deep Dive v3

## Resumo

Desearch (SN22) e um subnet de busca descentralizada que agrega resultados de Twitter/X, Web, Reddit, HackerNews, ArXiv, YouTube e Wikipedia. Miners recebem queries dos validators, buscam conteudo nestas fontes e retornam resultados + summaries. Validators scoring e baseado em LLM (GPT-4o-mini via OpenAI API ou Chutes) que avalia relevancia do conteudo, mais performance/latencia.

**ALERTA CRITICO: O codigo contem um mecanismo de "emission control" hardcoded que redireciona 80% de TODAS as emissoes para um unico hotkey do team.**

## Codigo (validator/reward)

### Arquitetura do Validator
- **3 tipos de validacao**: `AdvancedScraperValidator` (AI search com Twitter+Web+summary), `XScraperValidator` (Twitter search puro), `WebScraperValidator` (Web search puro)
- **QueryScheduler**: Polls um utility API centralizado (https://utility-api.desearch.ai) para obter questions. Scoring e feito por hora (epoch = 1 hora UTC)
- **Utility API**: Centralizado, com whitelist de 13 hotkeys hardcoded em `utility-api/app/auth.py` -- apenas validators autorizados recebem questions

### Reward Pipeline
1. **Reward Functions** (weighted sum):
   - AI Search: Twitter content (0.45) + Web search relevance (0.30) + Summary relevance (0.20) + Performance/latency (0.05)
   - X Search: Twitter content (0.70) + Performance (0.30)
   - Web Search: Web content (0.70) + Performance (0.30)

2. **Normalization** (`BaseRewardModel.normalize_rewards`):
   - Min-max normalization entre non-zero rewards
   - **Exaggeration factor = 4**: `rewards = pow(rewards * 4, 4)` -- isto e equivalente a `rewards^4 * 256`, amplificando dramaticamente diferencias pequenas. O top scorer recebe quase tudo.

3. **Penalty Functions**:
   - `ExponentialTimePenaltyModel`: Penaliza respostas lentas com `1 - exp(-delay)`
   - `StreamingPenaltyModel`: Penaliza falhas de streaming
   - `SummaryRulePenaltyModel`: Penaliza summaries que nao seguem regras
   - `MinerScorePenaltyModel`: Compara link relevance scores do miner vs validator
   - `ChatHistoryPenaltyModel`: Penaliza inconsistencias no chat history
   - `TwitterCountPenaltyModel`: Penaliza contagens incorretas de tweets

4. **Moving Average**: alpha=0.2, scores acumulam via `alpha * new + (1-alpha) * old`, persistidos em Redis

5. **Weight Setting**: L1-normalized, depois passa por `burn_weights()`, depois `process_weights()` do bittensor

### Scoring LLM
- Usa GPT-4o-mini (OpenAI) ou modelos via Chutes como alternativa
- Temperature = 0.0001 (near-deterministic)
- Validator precisa de OPENAI_API_KEY (custo operacional adicional)

## Red Flags Adversariais

### CRITICO: Emission Control (burn_weights) -- HARDCODED HOTKEY COM 80% DAS EMISSOES

```python
ENABLE_EMISSION_CONTROL = True
EMISSION_CONTROL_HOTKEY = "5CUu1QhvrfyMDBELUPJLt4c7uJFbi7TKqDHkS1Zz41oD4dyP"
EMISSION_CONTROL_PERC = 0.8
```

**Localizacao**: `neurons/validators/weights.py` linhas 30-32

A funcao `burn_weights()` (linha 134) redistribui os pesos ANTES de submeter on-chain:
- 80% do peso total vai para o UID associado ao hotkey hardcoded
- Os 20% restantes sao distribuidos proporcionalmente entre todos os outros miners
- Este mecanismo e ATIVADO por default (`ENABLE_EMISSION_CONTROL = True`)
- O hotkey beneficiado e EXCLUIDO de queries organicas via `UIDManager.resync()` (nao precisa nem fazer trabalho real)

**Impacto**: Com emission_tao_day = 26.83 TAO:
- ~21.46 TAO/dia (~$6,868/dia) vao automaticamente para este unico hotkey
- Isto explica o top1_share de 81% e Gini de 0.831
- Os restantes 139 miners competem por apenas ~5.37 TAO/dia (~$1,718/dia total)

### MEDIO: Utility API Centralizado com Whitelist

- `utility-api/app/auth.py`: 13 hotkeys hardcoded na whitelist
- Apenas validators na whitelist recebem questions para scoring
- O team controla completamente quais queries sao feitas e para quais UIDs
- Nao ha descentralizacao real na selecao de queries

### MEDIO: Exaggeration Factor Extremo na Normalizacao

- `normalize_rewards()` em `reward/reward.py` aplica `pow(reward * 4, 4)` 
- Isto e uma transformacao de potencia^4 com multiplicador, criando winner-take-all dynamics
- Pequenas diferencas de qualidade resultam em diferencas enormes de reward

### BAIXO: Auto-updater em run.sh

- `run.sh` contem auto-updater que faz `git pull` e `pip install -e .` automaticamente
- Verifica versao via GitHub API a cada 20 minutos
- Pode potencialmente instalar codigo nao auditado, mas requer apenas incremento de 1 versao
- Muda o remote origin URL para `Desearch-ai/subnet-22` dinamicamente

### AUSENTES (positivo):
- Nenhum `trust_remote_code=True`
- Nenhum softmax com temperature alta (temperature LLM = 0.0001, adequado para scoring)
- Sem `subprocess` ou `os.system` calls no codigo Python principal
- Sem kill switches obvios alem do emission control

## Hardware Requirements

### Miner
- **CPU**: 4 cores min, 8 recommended (x86_64)
- **RAM**: 8 GB min
- **Storage**: 48 GB SSD min
- **GPU**: NAO NECESSARIA
- **APIs necessarias**: OPENAI_API_KEY, TWITTER_BEARER_TOKEN, SERPAPI_API_KEY, WANDB_API_KEY
- **Custos API estimados**: OpenAI (~$5-20/mes), Twitter API (Basic $100/mes ou Pro $5000/mes), SerpAPI ($50/mes)
- **Software**: Redis

### Validator
- **Hardware**: Igual ao miner
- **APIs necessarias**: OPENAI_API_KEY, EXPECTED_ACCESS_KEY, WANDB_API_KEY, APIFY_API_KEY, SCRAPINGDOG_API_KEY ($90/mes)
- **Nota**: Validator precisa estar na whitelist do utility API para funcionar

## ECONOMIA REAL

Parametros base:
- emission_tao_day: 26.83 TAO
- TAO_USD: $320
- miners_scoring: 139
- Gini: 0.831

**NOTA CRITICA**: 80% das emissoes vao para o hotkey do team via burn_weights. Os calculos abaixo refletem isso.

### Emissoes efetivas
- Total emissao/dia: 26.83 TAO = $8,585.60/dia
- Emission control (80%): 21.46 TAO = $6,868.48/dia para hotkey do team
- Disponivel para miners reais (20%): 5.37 TAO = $1,717.12/dia

### Receitas mensais

- **Top 1 receita mensal real**: $208,629 (hotkey do emission control)
- **Top 10 mediana**: ~$1,200 (estimado, dos miners reais competindo pelos 20%)
- **Miner mediano**: $366

### Custos mensais do miner
- Compute (Vast.ai RTX 4090): $180/mes (mas GPU NAO e necessaria, entao possivel rodar mais barato ~$30-50/mes em CPU-only)
- Compute (Hetzner): EUR 184/mes
- APIs obrigatorias (OpenAI + Twitter + SerpAPI): ~$155-5,070/mes dependendo do tier Twitter
  - Minimo viavel: OpenAI $10 + Twitter Basic $100 + SerpAPI $50 = ~$160/mes
- **Custo total minimo**: $180 + $160 = $340/mes (Vast.ai) ou EUR 184 + $160 = ~$345/mes (Hetzner)

### Break-even

Com custo total ~$340/mes e receita mediana de $366/mes:
- **Break-even Vast.ai ($180/mes compute + $160 APIs)**: ~28 dias (marginalmente viavel, margem de ~$26/mes)
- **Break-even Hetzner (EUR 184/mes compute + $160 APIs)**: ~28 dias (margem similar)

**POREM**: Estes calculos assumem receita mediana estavel, que e improvavel dado o Gini de 0.831 e o exaggeration_factor^4.

Considerando que 80% das emissoes sao capturadas pelo team:
- Miner no percentil 25: provavelmente recebe < $100/mes = **NUNCA break-even**
- Miner no percentil 50 (mediano): $366/mes, margem de ~$26/mes = **MARGINAL**
- Miner no top 10 (excluindo emission control): ~$1,200/mes = **VIAVEL**

## VEREDICTO ECONOMICO: IMPOSSIBLE

**Justificativa**: O mecanismo de `burn_weights` hardcoded que redireciona 80% de TODAS as emissoes para um unico hotkey do team torna este subnet economicamente inviavel para novos miners. Apenas ~$1,717/dia ($51,513/mes) sao distribuidos entre 139 miners. Combinado com o exaggeration_factor^4 que cria winner-take-all dynamics, custos de API obrigatorios (Twitter, OpenAI, SerpAPI), e o controle centralizado do utility API, a grande maioria dos miners opera em prejuizo. O subnet funciona essencialmente como um mecanismo de extracao de renda para o team, disfarçado de rede descentralizada de busca.

**Red flag principal**: Emission control hardcoded = 80% para 1 hotkey. Isto e a definicao de rent-seeking num subnet Bittensor.
