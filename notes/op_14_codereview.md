# SN14 — TAOHash: Code Review Operacional

**Repo:** https://github.com/latent-to/taohash
**Versao:** 0.4.1
**Data da analise:** 2026-04-12

---

## Resumo

TAOHash e um subnet de mineracao BTC/BCH descentralizada. Miners contribuem hashrate real (SHA-256) para um pool coletivo operado pelo subnet. O "miner" no contexto Bittensor e apenas um script Python leve que busca credenciais do pool e sincroniza configuracao — a mineracao real acontece em hardware ASIC ou hashrate alugado (NiceHash, MiningRigRentals). O miner ganha de duas formas: BTC direto via protocolo TIDES e alpha tokens (+5% do valor do hashpower) via Bittensor.

**IMPORTANTE: Este subnet NAO e "CPU only" no sentido de rodar mineracao em CPU. O script Python do miner e leve, mas voce PRECISA de hashrate BTC real (ASICs ou aluguel de hashrate). Sem hashrate = zero rewards.**

---

## TAREFA OPERACIONAL DETALHADA

### O que o miner.py faz:
1. Conecta ao Bittensor, verifica registro no subnet 14
2. Busca informacoes do pool (IP, porta, credenciais) da chain
3. Gera um worker name no formato `BTC_ADDRESS.HOTKEY_PREFIX`
4. Exibe as configuracoes para voce apontar seu hardware de mineracao

### O que o miner_with_proxy.py faz:
1. Loop principal que sincroniza metagraph periodicamente
2. Busca pool info e atualiza configuracao do proxy (Taohash Proxy ou Braiins)
3. Salva dados do pool em storage (JSON ou Redis)
4. Aguarda blocos e re-sincroniza em intervalos regulares ou epoch boundaries

### Fluxo real do miner:
```
[Seu ASIC/NiceHash] --> [Pool TAOHash (btc.taohash.com:3331)] --> [Shares validados]
[Script Python] --> [Busca credenciais] --> [Configura proxy se usado]
```

O script Python e um "coordinator" — quem faz o trabalho real e o hardware de mineracao BTC.

---

## Hardware Requirements

| Componente | Requisito |
|---|---|
| CPU | Qualquer (script Python leve) |
| RAM | 512MB suficiente para o script |
| Disco | Minimo, logs e JSON storage |
| GPU | NAO necessario para o script |
| **HARDWARE DE MINERACAO BTC** | **OBRIGATORIO: ASICs (ex: Antminer S19) OU aluguel de hashrate** |
| Rede | Conexao estavel para stratum protocol |

### Custo Real do Hardware de Mineracao:
- **ASIC Antminer S19 Pro**: ~$2,000-4,000 + eletricidade (~$200-400/mes)
- **NiceHash aluguel**: ~$50-200/dia para hashrate competitivo
- **MiningRigRentals**: Variavel, similar ao NiceHash
- **VPS $8/mo**: Suficiente APENAS para rodar o script Python, NAO para minerar

---

## ECONOMIA REAL

### Dados do subnet:
- Emissao: 48.36 TAO/dia
- TAO_USD: $270
- Emissao diaria em USD: ~$13,057/dia
- Miners scoring: **4** (MUITO poucos!)
- Mediana mensal: $48,966/mo
- Gini: 0.458

### Analise critica:
- Apenas 4 miners recebendo score = mercado altamente concentrado
- Mediana alta ($48,966/mo) mas ENGANOSA: isso reflete miners com hashrate MASSIVO
- PAYOUT_FACTOR = 0.015 (1.5%) — o subnet paga 5% do valor do hashpower em alpha
- OWNER_TAKE = 0.18 (18%) — owner leva 18% das emissoes
- SPLIT_WITH_MINERS = 0.5 (50%) — metade das emissoes vai para miners

### Calculo para miner pequeno:
- Se voce aluga 1 TH/s no NiceHash: custo ~$5-10/dia
- Share value seria infimo comparado aos 4 miners existentes (provavelmente operacoes industriais)
- Retorno provavel em alpha: centavos por dia
- **ROI negativo quase certo para minerador pequeno**

---

## SETUP ESTIMADO

| Etapa | Tempo |
|---|---|
| Criar wallet Bittensor + registrar SN14 | 30 min |
| Clonar repo + pip install -e . | 10 min |
| Rodar miner.py para pegar credenciais do pool | 5 min |
| Configurar fonte de hashrate (NiceHash/ASIC) | 1-4 horas |
| Configurar proxy (opcional, Docker) | 30 min |
| **Total** | **2-5 horas** |

### Registro no subnet:
```bash
btcli subnet register --netuid 14 --wallet.name WALLET --wallet.hotkey HOTKEY --network finney
```
Custo de registro: ~0.1 TAO (burn) atualmente

---

## CURVA DE APRENDIZAGEM

| Nivel | Descricao |
|---|---|
| Python | Baixa — script simples, so configuracao |
| Bittensor | Media — wallet, registro, conceitos basicos |
| Mineracao BTC | **ALTA** — precisa entender stratum protocol, hashrate, dificuldade, ASICs |
| Operacional | Media-Alta — gerenciar hardware/aluguel de hashrate |

---

## MANUTENCAO DIARIA

- **Script Python**: Quase zero manutencao. Loop automatico com sync periodico
- **Hardware/Hashrate**: Monitoramento constante necessario
  - Verificar hashrate no taohash.com/leaderboard
  - Monitorar aceitacao de shares
  - Ajustar dificuldade minima se necessario (`x;md=100000;`)
- **Atualizacoes**: Pull do repo + restart ocasional
- **Tempo estimado**: 15-30 min/dia (se tudo funcionar)

---

## BARREIRAS REAIS

1. **BARREIRA FATAL: Necessidade de hashrate BTC real**
   - NAO e possivel minerar com CPU/GPU de forma competitiva
   - Precisa de ASICs ($2,000+) ou aluguel de hashrate ($50-200/dia)
   - Competindo com 4 miners que provavelmente sao operacoes industriais

2. **Barreira economica**: Investimento minimo alto para ser competitivo
   - Os 4 miners existentes provavelmente tem dezenas/centenas de TH/s
   - Entrar com 1 TH/s = fração insignificante do pool

3. **Barreira tecnica**: Conhecimento de mineracao BTC
   - Stratum protocol, configuracao de ASICs, otimizacao de hashrate

4. **Concentracao extrema**: 4 miners = oligopolio
   - Dificil entrar e competir por share significativo das emissoes

---

## Red Flags

1. **CRITICO: "CPU_ONLY" e ENGANOSO** — O script Python e leve, mas o miner PRECISA de hashrate BTC real. Isso NAO e mineravel com um VPS de $8/mo.

2. **OWNER_TAKE = 18%** — Owner leva fatia significativa. Combinado com SPLIT_WITH_MINERS = 50%, miners efetivamente recebem ~41% das emissoes totais.

3. **Apenas 4 miners scoring** — Mercado extremamente concentrado. Provavelmente operacoes com capital significativo.

4. **BAD_COLDKEYS hardcoded** no validator (`5CS96ckqKnd2snQ4rQKAvUpMh2pikRmCHb4H7TDzEt2AM9ZB`) — Indica que houve problemas com mineradores especificos.

5. **Dependencia de pool centralizado** — Todo hashrate vai para btc.taohash.com, controlado pelo time do subnet.

6. **PAYOUT_FACTOR = 0.015** — Factor de pagamento baixo. Alpha tokens valem apenas 1.5% do score calculado.

7. **Codigo do miner e essencialmente um "configurador"** — NAO faz trabalho computacional. A complexidade e toda externa (hardware de mineracao).

---

## PROBABILIDADE DE PRIMEIROS REWARDS EM 7 DIAS

**5% — Extremamente Improvavel**

- Precisa adquirir/alugar hashrate BTC significativo (custo alto)
- Competindo com 4 miners estabelecidos com hashrate massivo
- TIDES rewards requerem contribuicao proporcional ao pool
- Alpha rewards sao 5% do valor do hashpower — retorno marginal para miners pequenos
- Investimento minimo para resultados visiveis: provavelmente >$1,000/mes em hashrate

---

## VEREDICTO

**NAO RECOMENDADO para o perfil descrito (Python dev, 4h/dia, sem GPU, VPS $8/mo).**

Este subnet e fundamentalmente um pool de mineracao BTC com incentivos Bittensor. A classificacao "CPU_ONLY, compute_light" refere-se apenas ao script Python de coordenacao — o trabalho real exige ASICs ou aluguel de hashrate, que e capital-intensivo.

Com apenas 4 miners scoring e mediana de $48,966/mo, este e um jogo para operadores de mineracao BTC com infraestrutura existente. Um developer Python com VPS de $8/mo nao consegue competir de forma alguma.

O unico cenario viavel seria usar NiceHash/MiningRigRentals com um orcamento de $500+/mes, mas mesmo assim o retorno provavel seria inferior ao custo do hashrate. A economia so fecha para quem ja tem ASICs pagos ou eletricidade muito barata.

**Score: 1/10 para este perfil**
- Setup do script: Facil
- Competitividade: Impossivel sem capital significativo
- ROI: Negativo para miners pequenos
