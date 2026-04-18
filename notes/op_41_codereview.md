# SN41 — Almanac (Sportstensor): Code Review Operacional

**Repo:** https://github.com/sportstensor/sn41
**Data da analise:** 2026-04-12

---

## Resumo

Almanac/Sportstensor e um subnet de prediction market descentralizado. Miners geram "sinais de informacao" fazendo trades reais na plataforma Almanac (que roteia ordens para o Polymarket CLOB). O scoring e baseado em performance de trading: ROI, volume, consistencia. NAO requer modelos ML — e puramente baseado em resultados de trades.

O "mining" aqui e literalmente **fazer apostas em mercados de predicao (Polymarket)** e ser avaliado pela qualidade dessas apostas. Voce precisa de capital real para apostar e de habilidade para fazer predicoes lucrativas.

---

## TAREFA OPERACIONAL DETALHADA

### O que o miner.py faz:
1. Setup interativo: coleta wallet name, hotkey, network
2. Valida carteira e registro no subnet 41
3. Pede um endereco Ethereum/Polygon (EOA) — seu endereco Almanac/Polymarket
4. Submete os primeiros 5 caracteres do EOA na chain como metadata (privacidade)
5. **NAO roda um loop continuo** — e um script de configuracao one-time

### Fluxo real do miner:
```
[Voce] --> [Almanac dApp (beta.almanac.market)] --> [Trades no Polymarket]
                                                         |
[Validator] <-- [API Almanac] <-- [Historico de trades] --+
                    |
              [Scoring (ROI, volume, consistencia)]
                    |
              [Weights on-chain] --> [Alpha emissions para voce]
```

### O que voce realmente faz como miner:
1. Cria conta no Almanac + conecta ao Polymarket
2. Deposita USDC no safe wallet do Almanac
3. Faz trades manualmente no dApp OU usa api_trading.py programaticamente
4. Validators buscam seu historico de trades automaticamente
5. Scoring roda a cada hora, baseado nos ultimos 30 dias de trades

### api_trading.py (136KB!):
- Cliente interativo completo para trading via API
- Gera credenciais Polymarket API
- Busca mercados, coloca ordens assinadas (EIP-712)
- Gerencia multiplas carteiras
- Suporta operacoes CLOB completas

---

## Hardware Requirements

| Componente | Requisito |
|---|---|
| CPU | Qualquer — sem processamento pesado |
| RAM | Minimo (256MB suficiente) |
| Disco | Minimo |
| GPU | NAO necessario |
| VPS $8/mo | **SUFICIENTE** para rodar o script de setup e api_trading.py |
| **CAPITAL PARA TRADING** | **OBRIGATORIO: USDC para fazer trades no Polymarket** |

### Infraestrutura real:
- VPS: Opcional, so se quiser rodar api_trading.py 24/7
- Pode operar 100% do navegador (Almanac dApp)
- NAO precisa rodar nenhum processo continuo como miner

---

## ECONOMIA REAL

### Dados do subnet:
- Emissao: 29.42 TAO/dia
- TAO_USD: $270
- Emissao diaria em USD: ~$7,943/dia (~$238,290/mo total)
- Miners scoring: **34**
- Mediana mensal: $6,454/mo
- Gini: 0.489
- TOTAL_MINER_ALPHA_PER_DAY: 2,952 alpha (41% das emissoes do subnet)

### Constantes criticas do scoring:
- **ROLLING_HISTORY_IN_DAYS = 30** — janela de 30 dias de trades
- **ROI_MIN = 0.0** — precisa ter ROI positivo (lucrativo)
- **VOLUME_MIN = 1** — volume minimo baixo (1 USDC)
- **VOLUME_FEE = 0.01** — 1% de fee sobre volume
- **VOLUME_DECAY = 0.9** — atividade recente pesa mais
- **MIN_EPOCHS_FOR_ELIGIBILITY = 0** — sem periodo minimo de espera!
- **MIN_PREDICTIONS_FOR_ELIGIBILITY = 1** — apenas 1 predicao necessaria
- **RHO_CAP = 0.1** — cap de 10% max por trader (diversidade)
- **MINER_POOL_WEIGHT_BOOST_PERCENTAGE = 3** — miners registrados tem 3x boost nos pesos

### Calculo para miner novo:
- Volume minimo: 1 USDC (trivial)
- Precisa ser lucrativo (ROI > 0) para receber rewards
- Com 34 miners scoring e RHO_CAP de 10%, distribuicao e razoavelmente justa
- **Custo real: capital de trading + fees do Polymarket (~1-2% por trade)**
- Se voce trade $100/dia com ROI de 5%, score seria modesto mas presente
- ENABLE_ES_MINER_INCENTIVES = True + ESM_MIN_MULTIPLIER = 1.2 = bonus de 120% para miners iniciais

### Economia do trading:
- Fee Almanac/Polymarket: ~1-2% por trade
- Se trade $1000/mes com 5% ROI: lucro = $50, fees = ~$15, liquido = ~$35 em trades
- Alpha rewards adicionais baseados no score
- Com mediana de $6,454/mo em 34 miners: media de ~$190/dia por miner scoring

---

## SETUP ESTIMADO

| Etapa | Tempo |
|---|---|
| Criar wallet Bittensor + registrar SN41 | 30 min |
| Criar conta Almanac (beta.almanac.market) | 15 min |
| Deploy safe wallet + sign approvals | 20 min |
| Instalar extensao Bittensor wallet + linkar coldkey | 15 min |
| Depositar USDC no safe wallet | 10 min (+ tempo de bridge se necessario) |
| Clonar repo + pip install requirements | 10 min |
| Rodar miner.py (registrar metadata) | 5 min |
| Primeiro trade no Almanac | 5 min |
| **Total** | **~2 horas** |

### Registro no subnet:
```bash
btcli subnet register --netuid 41 --wallet.name WALLET --wallet.hotkey HOTKEY --network finney
```

### Setup do miner:
```bash
git clone https://github.com/sportstensor/sn41/
cd sn41
pip install -r requirements.txt
python miner.py  # interativo
```

---

## CURVA DE APRENDIZAGEM

| Nivel | Descricao |
|---|---|
| Python | Baixa — script de setup simples |
| Bittensor | Media — wallet, registro |
| Polymarket/DeFi | Media-Alta — precisa entender prediction markets, CLOB, safe wallets |
| Trading/Predicoes | **ALTA** — precisa fazer predicoes LUCRATIVAS consistentemente |
| API Trading | Media — se quiser automatizar com api_trading.py |

---

## MANUTENCAO DIARIA

- **Processo tecnico**: ZERO — nao ha processo rodando 24/7
- **Trading ativo**: 1-4 horas/dia dependendo da estrategia
  - Analisar mercados disponives
  - Colocar trades no Almanac
  - Monitorar posicoes abertas
  - Ajustar estrategia baseado em resultados
- **Monitoramento**: Verificar scores/weights periodicamente
- **Tempo estimado**: 1-4 horas/dia (alinhado com o perfil de 4h/dia)

---

## BARREIRAS REAIS

1. **Capital de trading necessario**
   - Precisa de USDC para fazer trades no Polymarket
   - Minimo tecnico: $1, mas para ser competitivo: $100-500+ em capital ativo
   - Risco de perda do capital investido em trades

2. **Habilidade de predicao**
   - ROI > 0 e OBRIGATORIO para receber rewards (ROI_MIN = 0.0)
   - Se suas predicoes sao ruins, voce perde capital E nao recebe alpha
   - Nao basta volume — precisa ser lucrativo

3. **Conhecimento de DeFi/Polygon**
   - Safe wallet, USDC bridging, gas fees
   - Entender order books (CLOB)

4. **Risco regulatorio**
   - Polymarket tem restricoes em algumas jurisdicoes
   - Prediction markets podem ter implicacoes legais

5. **Dependencies externas**
   - Almanac API (https://api.almanac.market) deve estar online
   - Polymarket CLOB deve estar funcionando
   - Se qualquer um cair, trades param

---

## Red Flags

1. **RISCO DE CAPITAL: Voce esta literalmente apostando dinheiro real.** Se suas predicoes forem ruins, voce perde o capital E nao recebe alpha rewards. Double loss.

2. **Scoring complexo (68KB scoring.py)** — Sistema de scoring muito complexo com duas fases de otimizacao (CVXPY). Dificil prever exatamente como seus trades serao scored.

3. **Dependencia centralizada no Almanac API** — Validators buscam trading history de `api.almanac.market`. Se o backend cair ou mudar, todo o subnet para.

4. **BURN_UID = 210** — Subnet tem UID de burn para "excess" weights. Owner pode redirecionar peso nao alocado.

5. **Polymarket dependency** — Todo o subnet depende de uma plataforma centralizada (Polymarket) que pode mudar termos, bloquear contas, ou ser regulada.

6. **api_trading.py tem 136KB** — Arquivo monolitico gigante. Qualidade de codigo questionavel para producao. Inclui debug flags e endpoints comentados de localhost.

7. **Scoring muda frequentemente** — Muitas constantes com comentarios "originally X" indicando ajustes frequentes. Regras podem mudar a qualquer momento.

8. **ENABLE_ES_MINER_LOSS_COMPENSATION = True com 100%** — Fee compensation para miners com profit positivo mas sem score. Indica que o sistema de scoring pode ser instavel.

9. **Credenciais sensiveis** — api_trading.env requer private keys (EOA_WALLET_PK). Risco de seguranca se mal gerenciado.

---

## PROBABILIDADE DE PRIMEIROS REWARDS EM 7 DIAS

**40% — Moderadamente Possivel**

Pontos positivos:
- MIN_EPOCHS_FOR_ELIGIBILITY = 0 (sem espera)
- MIN_PREDICTIONS_FOR_ELIGIBILITY = 1 (apenas 1 trade)
- 34 miners ja scoring = mercado nao saturado
- MINER_POOL_WEIGHT_BOOST_PERCENTAGE = 3x para miners registrados
- ENABLE_ES_MINER_INCENTIVES = True (bonus para novos miners)
- Setup rapido (~2 horas)

Pontos negativos:
- Precisa ser LUCRATIVO (ROI > 0) — se suas predicoes forem ruins, zero rewards
- Scoring roda por rolling window de 30 dias — peso pleno leva tempo
- VOLUME_DECAY = 0.9 — precisa volume consistente
- Capital de trading necessario
- Competindo com traders potencialmente mais experientes

**Se voce depositar $200+ USDC e fizer trades lucrativos nos primeiros dias, e possivel ver alpha rewards na primeira semana.**

---

## VEREDICTO

**PARCIALMENTE VIAVEL para o perfil descrito, mas com RISCOS SIGNIFICATIVOS.**

### Pros:
- NAO precisa de GPU ou hardware especial
- VPS de $8/mo e suficiente (ou nem precisa de VPS)
- 4h/dia e suficiente para trading manual
- Setup rapido (~2 horas)
- Barreira de entrada tecnica baixa
- Comunidade ativa (34 miners scoring)
- Mediana de $6,454/mo e atrativa

### Contras:
- **E essencialmente gambling com camada de Bittensor** — voce esta apostando dinheiro real
- Precisa de capital de trading ($100-500+ em USDC)
- Precisa ser BOM em predicoes (ROI positivo obrigatorio)
- Risco de perder capital + nao receber rewards
- Dependencia total em plataformas centralizadas (Almanac, Polymarket)
- Scoring complexo e opaco

### Recomendacao:
- **Se voce tem experiencia com prediction markets/trading**: 6/10 — vale experimentar com capital limitado ($200-500)
- **Se voce NAO tem experiencia com trading**: 3/10 — alto risco de perder capital
- **Como "mining passivo"**: 1/10 — NAO funciona, precisa de decisoes ativas de trading

### Estrategia sugerida se decidir entrar:
1. Comece com $100-200 USDC
2. Foque em mercados que voce entende (esportes, politica)
3. Faca trades pequenos ($5-20) para entender o scoring
4. Monitore seus scores apos 24-48h
5. Escale apenas se ROI for positivo consistentemente
6. Considere automatizar com api_trading.py apos entender o sistema

**Score: 5/10 para este perfil** (com capital e experiencia de trading)
**Score: 2/10 para este perfil** (sem experiencia de trading)
