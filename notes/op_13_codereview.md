# SN13 — Data Universe — Operational Deep Dive

## Resumo

SN13 (Data Universe) e um subnet de coleta de dados sociais: miners fazem scraping de Reddit e Twitter/X, armazenam os dados em SQLite local, servem esses dados para validators via P2P (axon), fazem upload para S3, e respondem a "on-demand jobs" (scraping sob demanda da API central). Nao requer GPU -- e essencialmente um pipeline de web scraping + storage + upload. **POREM: 70% das emissoes sao redirecionadas ao subnet owner via mecanismo de burn, o que muda drasticamente a economia.**

## TAREFA OPERACIONAL DETALHADA

O miner executa as seguintes operacoes em paralelo (threads):

### 1. Scraping Continuo (ScraperCoordinator)
- Roda em background thread com 5 workers async
- Configuracao default (`scraping_config.json`):
  - **X/Twitter via Apidojo (Apify actor)**: a cada 300s, busca 75 tweets sobre crypto (#bitcoin, #bittensor, #crypto, etc.)
  - **Reddit via JSON API**: a cada 10s, busca 100 posts de subreddits crypto (r/bitcoin, r/Cryptocurrency, r/WallstreetBets, etc.)
  - **YouTube transcripts**: a cada 100s, busca 50 transcricoes de canais especificos
- Cada scrape escolhe um label aleatorio da lista, seleciona um TimeBucket (hora) usando distribuicao triangular favorecendo dados recentes
- Dados sao armazenados em SQLite local (`SqliteMinerStorage.sqlite`, default 250GB max)

### 2. Servindo Index P2P (Axon)
- Expoe 3 endpoints via axon (protocolo Bittensor):
  - `GetMinerIndex`: retorna indice comprimido de todos os dados que o miner tem
  - `GetDataEntityBucket`: retorna dados de um bucket especifico
  - `GetContentsByBuckets`: retorna conteudos de multiplos buckets
- Validators consultam periodicamente para avaliar o miner

### 3. Upload S3 (S3PartitionedUploader)
- A cada 2 horas, faz upload dos dados para S3 via presigned URLs
- Dados organizados por hotkey e job_id
- Primeira execucao espera 30 minutos

### 4. On-Demand Jobs
- Polls a API central (`data-universe-api.api.macrocosmos.ai`) a cada 5s
- Recebe jobs de scraping sob demanda (ex: "busque tweets do @usuario sobre X")
- Executa o scrape, formata os dados, e submete de volta via API
- CRITICO para scoring: S3 boost e capped a 2x do on-demand component -- sem on-demand, S3 boost = 0

### 5. Dynamic Desirability (Gravity)
- Opcional (`--gravity` flag), atualiza a cada 20 minutos
- Busca lista dinamica de dados mais desejados pela API central

### 6. Index Refresh
- A cada ~21 minutos, refresha o indice comprimido em cache

## Hardware Requirements

- **CPU**: Qualquer CPU moderno serve. Scraping e I/O bound, nao compute bound
- **RAM**: 2-4GB suficiente para operacao normal. O SQLite e o maior consumidor
- **Storage**: O default e 250GB (!), mas isso e configuravel via `--neuron.max_database_size_gb_hint`. Pode ser reduzido significativamente para comecar. 20-50GB recomendado para operacao minima
- **GPU**: NAO necessario. Zero dependencia de GPU. Torch esta nas dependencias mas e usado apenas para tensores de scoring (float32)
- **Bandwidth**: Moderado. Scraping constante (Reddit a cada 10s, X a cada 5min) + upload S3 a cada 2h + polling on-demand a cada 5s
- **VPS Hetzner CX23**: 2 vCPU, 4GB RAM, 40GB disk -- **disk insuficiente para operacao plena**. Precisaria de storage adicional ou CX32+ (80GB) ou volume externo

## ECONOMIA REAL

### Calculo ANTES do burn (numeros brutos)
- Emissao diaria: 44.08 TAO/dia
- Miners scoring: 241
- Median miner: $1,367/mes

### Calculo COM o burn de 70%
```
EMISSION_CONTROL_PERCENTAGE = 0.70  # constants.py linha 52
```
**70% de TODAS as emissoes vao para o subnet owner!** Isso esta hardcoded no codigo:
- `validator.py` aplica `apply_burn_to_weights()` com 70% para o owner UID
- Efetivamente, miners dividem apenas 30% das emissoes

**Economia real ajustada:**
- Emissao efetiva para miners: 44.08 * 0.30 = 13.22 TAO/dia
- Por miner (median): 13.22 / 241 = 0.0549 TAO/dia = ~$14.82/dia = ~$444/mes
- Contra VPS de $8/mo: ainda positivo em TAO puro
- **MAS**: custos adicionais de Apify nao incluidos (ver Barreiras)
- Break-even contra $8/mo VPS: ~0.53 dias (se median)
- Revenue como 242o miner: provavelmente abaixo do median, estimativa ~$200-300/mes

### Custos Operacionais Adicionais
- **Apify**: Scrapers X/Twitter usam Apify actors. Free tier = 25 actor runs/dia (muito limitado). Plano pago ~$49/mes para uso razoavel
- **Reddit API**: JSON scraper e gratuito (sem auth), mas custom scraper precisa Reddit app credentials (gratuito)
- **Storage**: Se usar volume adicional no Hetzner, +$4-8/mes

## SETUP ESTIMADO

**Tempo: 2-8 horas** (categoria intermediaria)

1. **Setup bittensor + wallet** (~30min se ja tem experiencia)
2. **Registro no SN13** (~10min + custo de registro ~0.1 TAO)
3. **Clone repo + install deps** (~15min)
4. **Configurar .env**:
   - Apify API token (conta + setup ~15min)
   - Reddit credentials (criar app OAuth2 ~15min)
5. **Ajustar scraping_config.json** para seu caso (~30min)
6. **Primeiro run + debug** (~1-2h)
7. **Esperar dados acumularem** (~24-48h para ter scoring relevante)

## CURVA DE APRENDIZAGEM

### Skills necessarios alem de Python:
- **Web scraping**: entender rate limits, headers, APIs REST
- **Bittensor basics**: wallets, axon, subtensor, netuid
- **SQLite**: debug de storage, queries de verificacao
- **API OAuth2**: configurar Reddit app
- **Apify platform**: criar conta, entender actors, gerenciar billing
- **Systemd/PM2**: manter processo rodando 24/7
- **Networking**: abrir portas para axon (validators precisam conectar)

### Complexidade: MODERADA
- O codigo e bem escrito e organizado
- Scraping config e JSON simples
- Mas a interacao entre P2P + S3 + OnDemand e complexa de debugar

## MANUTENCAO DIARIA

- **Tempo**: ~15-30 minutos/dia
- **Monitoramento**: verificar se scraping esta rodando, checar logs de erros
- **Disco**: monitorar uso de storage (SQLite cresce constantemente)
- **Apify**: monitorar credits/billing
- **Updates**: repo recebe updates frequentes (nota: STATE_VERSION ja esta em 7, com resets frequentes de scoring)
- **Credibility**: monitorar credibility scores -- erros de validacao reduzem credibilidade via EMA

## BARREIRAS REAIS

### 1. Apify API Token (OBRIGATORIO para X/Twitter)
- Scrapers de Twitter (ApiDojo, Microworlds, Quacker) TODOS usam Apify
- Free tier e muito limitado para operacao competitiva
- Custo real: ~$49/mes para plano adequado

### 2. Storage Significativo
- Default 250GB. Mesmo reduzido, precisa de dezenas de GB
- CX23 tem apenas 40GB -- insuficiente sem ajustes

### 3. On-Demand Participation e CRITICA
- Scoring formula: `score = P2P + S3 + OD`
- S3 e capped a 2x de OD component
- Se OD = 0, entao S3 = 0 tambem!
- P2P e capped ao valor de (S3 + OD)
- Ou seja: sem participacao em on-demand, score efetivo e ZERO
- On-demand requer scraping rapido e funcional

### 4. Porta Aberta para Axon
- Validators precisam conectar via axon
- Requer porta publica e IP acessivel

### 5. Credibility System e Punitivo
- Comeca com credibility 0 (STARTING_CREDIBILITY = 0)
- Precisa passar validacoes para subir
- Credibility elevada a 2.5 (CREDIBILITY_EXP) -- penaliza fortemente baixa credibilidade
- Erros de validacao (dados incorretos, timeout Apify) reduzem credibilidade

### 6. Custo de Registro
- ~0.1 TAO para registrar no subnet ($27 ao preco atual)

## Red Flags

### FLAG CRITICA: 70% Burn para Subnet Owner
```python
EMISSION_CONTROL_PERCENTAGE = 0.70  # 70% of emissions redirected to subnet owner
```
Isto e um **team tax brutal**. 70% de todas as emissoes vao para o hotkey do owner do subnet. Miners efetivamente competem por apenas 30% das emissoes. Isso esta hardcoded em `common/constants.py` e aplicado em `neurons/validator.py:773-779` via `apply_burn_to_weights()`.

### FLAG: State Resets Frequentes
O `MinerScorer.STATE_VERSION` esta em 7. Cada bump reseta scores de todos os miners. Historico:
- v2: Reset por exploit de tamanhos inflados
- v3: Reset por exploit em on-demand
- v4: Reset por bug em Reddit
- v5: Full reset por exploit de engagement/uniqueness
- v6: Reset S3 por bypass de sampling
- v7: Reset OD por mudanca de scoring

Isso indica um sistema instavel onde exploits sao frequentes e resets penalizam miners honestos.

### FLAG: Dependencia Centralizada
- API central (`data-universe-api.api.macrocosmos.ai`) e single point of failure
- On-demand jobs vem dessa API
- S3 upload usa essa API para presigned URLs
- Se API cair, scoring para

### FLAG: Apify como Dependencia Paga
- Validacao de tweets pela equipe usa Apify (validators tambem)
- Miners que nao pagam Apify ficam limitados a Reddit JSON (gratuito)
- Cria vantagem para quem pode pagar mais

## PROBABILIDADE DE PRIMEIROS REWARDS EM 7 DIAS: MED

**Justificativa:**
- Setup tecnico e factivel em 4-8 horas
- Reddit JSON scraper funciona sem API keys pagas
- Mas credibility comeca em 0 e demora para subir
- On-demand participation e obrigatoria para score > 0
- Primeiros TAO provavelmente em 3-5 dias se tudo configurado corretamente
- Porem os rewards serao BAIXOS inicialmente (credibility^2.5 com credibility baixa)

## VEREDICTO: MARGINAL

**Razoes:**
1. **70% burn e devastador** -- transforma $1,367/mes median em ~$410/mes efetivo
2. **Custos operacionais reais** (Apify ~$49/mo + storage extra ~$4-8/mo) comem parte do lucro
3. **Lucro liquido estimado**: ~$410 - $49 (Apify) - $8 (VPS) - $5 (storage) = ~$348/mes
4. **Ainda positivo**, mas com risco significativo:
   - State resets frequentes podem zerar seu progresso
   - Sistema de credibility e punitivo
   - Dependencia de API centralizada
5. **CX23 e insuficiente** em disco -- precisa de VPS maior ou volume addon
6. **Complexidade operacional moderada** -- nao e trivial mas e factivel para dev Python
7. O Gini de 0.241 e bom (distribuicao justa), o que e positivo

**Para viabilizar**: usar Reddit JSON scraper (gratuito) como base, investir em Apify para X/Twitter, e participar ativamente em on-demand jobs. Monitorar de perto os state resets e updates do repo. O 70% burn e o maior problema -- em qualquer outro subnet com emissoes similares, o retorno seria 3x maior.
