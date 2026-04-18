# SN73 (MetaHash) - Operational Code Review

**Repo**: https://github.com/fx-integral/metahash  
**Date**: 2026-04-12  
**Commit**: f6b50dc (main)  
**TAO_USD**: $270 | **VPS**: $8/mo (Hetzner CX23)

---

## Resumo

MetaHash SN73 e um **subnet de tesouraria/treasury** -- NAO e um subnet de compute, oracle, ou storage apesar das categorias listadas. E um mecanismo financeiro on-chain: miners participam de **leiloes de alpha tokens** de outros subnets, compram esses tokens com desconto, e transferem para a tesouraria do validador. O scoring e baseado no VALOR (em TAO) do alpha entregue.

**O miner NAO faz nenhum compute util.** Ele:
1. Recebe broadcast de leilao do validador (`AuctionStartSynapse`)
2. Envia bids (subnet_id, quantidade alpha, desconto em bps)
3. Se ganhar, recebe `WinSynapse` com invoice
4. Faz `transfer_stake` on-chain para pagar alpha ao treasury coldkey do validador

E essencialmente um **market maker de alpha tokens** -- compra alpha de subnets com desconto e entrega ao validador treasury.

---

## TAREFA OPERACIONAL DETALHADA

### O que o miner FAZ:

```
Validator broadcasts AuctionStartSynapse (epoch e)
  -> Miner responde com bids: [{subnet_id: 30, alpha: 1000, discount_bps: 500}]
  -> Validator faz clearing (greedy TAO-budget allocator com reputation caps)
  -> Winners recebem WinSynapse com invoice

Epoch e+1: Payment Window
  -> Miner executa transfer_stake on-chain (alpha do subnet -> treasury coldkey)
  -> Background payment loop com retries

Epoch e+2: Settlement
  -> Validator escaneia transfers on-chain
  -> Se miner pagou >= required_rao: credita VALUE (TAO) como score
  -> Se nao pagou: score = 0, possivel jail (2-12 epochs)
```

### Configuracao de bids (CLI):
```bash
python neurons/miner.py \
  --netuid 73 \
  --wallet.name <COLD> \
  --wallet.hotkey <HOT> \
  --subtensor.chain_endpoint <ENDPOINT> \
  --miner.bids.netuids 30 12 348 \
  --miner.bids.amounts 1000 500 200 \
  --miner.bids.discounts 10 5 1000bps
```

### O miner precisa:
- **Alpha tokens nos subnets alvo** para pagar os invoices
- **Coldkey desbloqueada** (via WALLET_PASSWORD env var)
- **Stake minimo**: `S_MIN_ALPHA_MINER = 0` (default, sem barreira de stake!)
- Registro no netuid 73

---

## POR QUE GINI = 0.000 (A Grande Questao)

### Analise do codigo de scoring:

O gini=0.000 com exatamente 6 miners **NAO e por scoring binario**. O scoring e baseado em VALUE (TAO):

```python
# settlement.py line 722-723
if fully_paid and value_sum > 0:
    scores_by_uid[uid] += value_sum
    credited_total_tao += value_sum
```

A igualdade perfeita acontece por uma combinacao de fatores:

1. **Ha apenas 1 validador master** (treasury): `VALIDATOR_TREASURIES` tem apenas 1 hotkey hardcoded
2. **AUCTION_BUDGET_ALPHA = 148.0** por epoch -- budget fixo
3. **Reputation caps** limitam cada coldkey a max 30% do budget (`REPUTATION_MAX_CAP_FRAC = 0.30`)
4. **Com 6 miners e reputation gamma=0.7**, se todos tem reputation similar, o budget e dividido quase igualmente
5. **Se todos os 6 miners fazem bids similares** (mesmos subnets, mesmos descontos) e **todos pagam integralmente**, o VALUE creditado e identico

### O mecanismo real:
- Com `REPUTATION_BASELINE_CAP_FRAC = 0.02` e `REPUTATION_MAX_CAP_FRAC = 0.30`
- Quotas por coldkey: `q = (1-gamma)/N + gamma * normalized_reputation`
- Com gamma=0.7 e reputation similar: cada um recebe ~1/6 = 16.7% do budget
- **Se todos pagam** e tem bids identicos -> VALUE identico -> gini = 0.000

### CONCLUSAO: A igualdade e porque:
- Poucos miners (6), todos coordenados/cooperativos
- Reputation system normaliza as quotas
- Todos fazem bids parecidos e pagam integralmente
- Provavel que sao todos do mesmo grupo/operador (MetaHash Group)

---

## Pode um 7o Miner Entrar e Ganhar Igual?

**Tecnicamente sim**, mas com ressalvas CRITICAS:

1. **S_MIN_ALPHA_MINER = 0** -- sem barreira de stake para bid acceptance
2. **Porem**: precisa de alpha tokens nos subnets alvo para pagar invoices
3. **Reputation system**: novo miner comeca com reputation 0, recebe `REPUTATION_BASELINE_CAP_FRAC = 0.02` (2%) do budget
4. **Com 7 miners**: seu cap seria ~2-4% do budget vs ~14-16% dos incumbentes
5. **Jail risk**: se nao pagar um invoice, jail por 2-12 epochs

**Na pratica**: um novo miner receberia MUITO MENOS que os 6 existentes ate construir reputation. O gini deixaria de ser 0.000.

### Calculo para novo miner:
- Budget total: 148 alpha/epoch
- Novo miner cap: ~2% = ~2.96 alpha/epoch
- Incumbentes: ~16% cada = ~23.7 alpha/epoch
- Ratio novo/incumbente: ~1:8 inicialmente

---

## Hardware Requirements

```
CPU: 1-2 cores (MINIMO)
RAM: 2-4 GB
Disco: 10 GB
GPU: NAO NECESSARIO
Network: Porta aberta para Axon (8091 default)
```

O miner e um processo Python leve que:
- Roda um Axon server (recebe synapses)
- Faz RPC calls ao Bittensor chain
- Executa transfer_stake on-chain
- Zero ML, zero GPU, zero heavy compute

**CX23 Hetzner ($8/mo) e MAIS que suficiente.**

---

## ECONOMIA REAL

```
Emission diaria: 25.69 TAO
Miners scoring: 6 (gini=0.000)
Mediana mensal: $34,676 (por miner)

POR MINER (se igualmente dividido):
  Diario:  25.69 / 6 = 4.28 TAO = $1,155/dia
  Mensal:  128.4 TAO = $34,668/mes

CUSTOS:
  VPS: $8/mo
  Alpha tokens para bids: VARIAVEL (este e o CUSTO REAL)
  Registro SN73: ~1 TAO recycled

LUCRO APARENTE: ~$34,660/mes

POREM -- CUSTO OCULTO CRITICO:
  O miner PAGA alpha tokens a cada epoch como "pagamento" ao treasury.
  AUCTION_BUDGET_ALPHA = 148 alpha POR EPOCH POR MASTER VALIDATOR.
  
  Se compra alpha a preco de mercado e entrega com desconto ao treasury,
  o miner esta essencialmente COMPRANDO rewards com capital.
  
  O "lucro" real depende do spread entre:
  - Custo de aquisicao dos alpha tokens
  - Rewards recebidos em TAO de emissao
  - Desconto oferecido nos bids

  ISTO E FUNDAMENTALMENTE DIFERENTE de mining compute.
  E mais parecido com yield farming/market making.
```

---

## SETUP ESTIMADO

### Tempo total: 4-8 horas (se tiver capital)

```
1. Registro no SN73 (30 min)
   - btcli subnet register --netuid 73

2. Adquirir alpha tokens (TEMPO VARIAVEL - HORAS/DIAS)
   - Precisa de alpha nos subnets que vai bidar
   - Ex: stake em SN30, SN12, etc
   - Conversao TAO -> Alpha stake

3. Setup do miner (1-2 horas)
   - git clone, pip install
   - Configurar .env (WALLET_PASSWORD, BITTENSOR_NETWORK)
   - Configurar bids (netuids, amounts, discounts)
   - Abrir porta Axon

4. Primeiro bid aceito (1-4 epochs = 1-5 horas)
   - Epoch = ~360 blocks = ~72 min
   - Pipeline: bid(e) -> pay(e+1) -> settle(e+2) -> weight(e+3)
   - Mínimo 3 epochs para primeiro reward

5. Deploy com PM2 (30 min)
   pm2 start neurons/miner.py --name sn73-miner -- \
     --netuid 73 --wallet.name X --wallet.hotkey Y \
     --subtensor.chain_endpoint wss://... \
     --miner.bids.netuids 30 12 \
     --miner.bids.amounts 500 500 \
     --miner.bids.discounts 5 5
```

---

## CURVA DE APRENDIZAGEM

```
Dificuldade: 7/10

NAO e dificil tecnicamente (Python puro, sem ML).
A complexidade esta em:
  1. Entender o mecanismo de auction/clearing/settlement (3 epochs pipeline)
  2. Estrategia de bidding (quais subnets, quanto alpha, qual desconto)
  3. Gestao de capital (alpha tokens nos subnets certos)
  4. Reputation building (comecar com cap baixo)
  5. Evitar jail (sempre pagar invoices)
  6. Entender valuation com slippage (effective_value_tao)

Para um Python dev: a barreira NAO e tecnica, e FINANCEIRA.
```

---

## MANUTENCAO DIARIA

```
Tempo: 30 min/dia (monitoramento)

Tasks:
  - Verificar se miner esta online e respondendo
  - Verificar se payments estao sendo feitos
  - Monitorar balance de alpha tokens (precisa reabastecer)
  - Ajustar bids se precos de alpha mudarem
  - Verificar se nao caiu em jail
  - Monitorar reputation score

Automacao possivel:
  - autosell.enabled (auto-venda de alpha SN73 recebido)
  - bidding.max_total_alpha (limitar gasto total)
  - bidding.min_stake_alpha (parar se stake cair)
```

---

## BARREIRAS REAIS

### 1. CAPITAL NECESSARIO (BARREIRA PRINCIPAL)
- Precisa de alpha tokens nos subnets alvo ANTES de bidar
- Se bidar 500 alpha no SN30, precisa TER 500 alpha staked em SN30
- Aquisicao de alpha = conversao de TAO, com slippage
- **Estimativa minima: 5-20 TAO de capital de giro**

### 2. REPUTATION COLD START
- Novo miner: cap = 2% do budget = ~3 alpha/epoch
- Incumbentes: ~16% cada
- Precisa de MUITAS epochs para construir reputation
- `REPUTATION_BETA = 0.5` (EMA decay)

### 3. GRUPO FECHADO IMPLÍCITO
- Apenas 1 treasury coldkey hardcoded em VALIDATOR_TREASURIES
- Apenas 1 validador master (precisa S_MIN_MASTER_VALIDATOR = 10,000 stake)
- Os 6 miners provavelmente sao do MetaHash Group
- Nao ha incentivo claro para aceitar outsiders

### 4. JAIL RISK
- Se falhar pagamento: jail 2-12 epochs (2.4-14.4 horas)
- Durante jail, zero rewards
- Partial payment: jail 2 epochs
- No payment: jail 12 epochs

### 5. WALLET COLDKEY EXPOSTA
- Miner precisa de WALLET_PASSWORD em env var
- Coldkey e desbloqueada para fazer transfer_stake
- Risco de seguranca se VPS for comprometida

---

## Red Flags

### FLAG CRITICA: ECONOMIA CIRCULAR / INSIDER OPERATION
- **1 unico validador master** (hardcoded treasury coldkey)
- **6 miners com gini=0.000** = claramente coordenados
- MetaHash Group controla validador E provavelmente todos os miners
- O subnet funciona como **auto-treasury**: emissao TAO vai para o grupo via miners controlados
- Outsiders recebem cap de 2% e enfrentam reputation cold start

### FLAG ALTA: MODELO ECONOMICO NAO-SUSTENTAVEL PARA OUTSIDERS
- Miners PAGAM alpha para receber TAO
- O spread e o lucro -- mas se o grupo controla o validador, eles definem os termos
- Desconto nos bids reduz o "custo" aparente mas o valor real depende de precos de mercado
- Para outsider: comprar alpha, entregar com desconto, receber 2% do budget = NEGATIVO

### FLAG MEDIA: SINGLE POINT OF FAILURE
- 1 validador master = 1 ponto de falha
- Se validador cair, todo o subnet para
- `S_MIN_MASTER_VALIDATOR = 10,000` limita quem pode ser master

### FLAG MEDIA: FORBIDDEN_ALPHA_SUBNETS = [73]
- Nao pode bidar alpha do proprio subnet (anti-circular)
- Porem o mecanismo permite qualquer outro subnet

### FLAG BAIXA: COMPLEXIDADE DESNECESSARIA
- ~3,300 linhas de codigo para engines (auction/clearing/settlement)
- Mecanismo sofisticado de reputation, slippage, partial fills
- Para uma operacao de 6 miners identicos, isto e overengineering

---

## PROBABILIDADE DE PRIMEIROS REWARDS EM 7 DIAS

```
Probabilidade: 25-35%

Razoes CONTRA:
  - Reputation cold start (2% cap)
  - Capital necessario para alpha tokens
  - Pipeline de 3 epochs ate primeiro reward
  - Insiders podem nao querer competicao
  - Entender o mecanismo de bidding leva tempo

Razoes A FAVOR:
  - Setup tecnico e simples (Python puro, sem ML)
  - CX23 e mais que suficiente
  - S_MIN_ALPHA_MINER = 0 (sem barreira de stake)
  - Codigo funcional e bem estruturado
  - Auto-sell feature para reciclar earnings
```

---

## VEREDICTO

```
RECOMENDACAO: NAO ENTRAR (para outsider individual)

Score: 3/10

JUSTIFICATIVA:
  Este NAO e um subnet de mineracao no sentido tradicional.
  E uma operacao de tesouraria/market-making controlada por um grupo.

  Os numeros sao atrativos ($34k/mes/miner) mas sao ILUSORIOS para
  um outsider porque:

  1. Gini=0.000 com 6 miners = operacao interna coordenada
  2. Reputation cold start = 2% do budget para novos
  3. Capital de giro necessario (alpha tokens)
  4. 1 validador master = decide quem ganha
  5. Modelo economico favorece insiders

  MESMO SE conseguir entrar e ganhar rewards:
  - Receita esperada como novo: ~2% de 25.69 TAO/dia = 0.51 TAO/dia = $138/dia
  - Custos: $8/mo VPS + capital de giro em alpha
  - Parece ok, MAS:
    - Precisou investir TAO em alpha tokens (custo de oportunidade)
    - Reputation demora epochs para crescer
    - Incumbentes podem ajustar bids para squeeze outsiders
    - Risco de jail se pagamento falhar

  PARA QUEM E BOM:
  - Se voce CONHECE o MetaHash Group e pode negociar entrada
  - Se tem capital significativo (50+ TAO) para alpha de vários subnets
  - Se entende market making e esta disposto a otimizar bids

  PARA VOCE (Python dev, 4h/dia, VPS, sem ML):
  - O codigo e Python puro, entendivel
  - Mas o modelo economico nao favorece outsiders
  - Existem subnets com melhor risk/reward para seu perfil
```

---

## Notas Tecnicas Adicionais

### Epoch Pipeline
```
e:   Auction + Clearing (bids aceitos, winners notificados)
e+1: Payment Window (miner faz transfer_stake on-chain)
e+2: Settlement (validator verifica pagamentos, aplica weights)
```

### Arquivos Chave
```
neurons/miner.py          - Entry point do miner (548 linhas)
neurons/validator.py      - Entry point do validador (305 linhas)
metahash/config.py        - Constantes globais (todas as configs)
metahash/treasuries.py    - Treasury coldkeys hardcoded (1 producao)
metahash/protocol.py      - AuctionStartSynapse, WinSynapse
metahash/validator/engines/auction.py    - Bid acceptance + broadcast
metahash/validator/engines/clearing.py   - TAO-budget greedy allocator
metahash/validator/engines/settlement.py - Score via VALUE, set_weights
metahash/miner/runtime.py   - Config -> bid lines, auction handling
metahash/miner/payments.py  - Background payment loop + transfer_stake
```

### Dependencias
- bittensor==9.9.0
- substrate-interface==1.7.11
- Sem ML frameworks, sem GPU libs
- Python puro com async/await
