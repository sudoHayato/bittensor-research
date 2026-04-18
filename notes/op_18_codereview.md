# SN18 Zeus - Code Review Operacional
## Environmental Forecasting (Weather Prediction)
**Repo:** https://github.com/Orpheus-AI/Zeus
**Data:** 2026-04-12 | TAO = $270 | Emission = 38.02 TAO/dia

---

## Resumo

SN18 Zeus e uma subnet de **previsao meteorologica global** baseada em dados ERA5 (Copernicus/ECMWF). Miners devem prever variaveis ambientais (temperatura a 2m, componentes de vento a 100m, radiacao solar) para a Terra inteira em grid de 0.25 graus (721x1440 pontos) em horizontes de 48h e 15 dias. O protocolo usa commit-reveal: miners enviam hash da previsao, depois revelam, e sao pontuados quando ground truth ERA5 fica disponivel (ate 7 dias depois).

**CRITICO: O miner default envia dados ALEATORIOS (np.random.rand).** Isso e um placeholder. Para competir de verdade, voce precisa implementar um modelo de previsao meteorologica real ou usar uma API como Open-Meteo.

---

## TAREFA OPERACIONAL DETALHADA

### O que o miner FAZ de fato:

1. **A cada 6 horas (00:30, 06:30, 12:30, 18:30 UTC):** Recebe pedido de hash de previsao
2. **1 hora depois:** Pode receber pedido da previsao completa (reveal)
3. **~7 dias depois:** Recebe pedido final para scoring contra ground truth ERA5

### Variaveis avaliadas (com pesos):
- `2m_temperature` - peso 0.2
- `100m_u_component_of_wind` - peso 0.3
- `100m_v_component_of_wind` - peso 0.3
- `surface_solar_radiation_downwards` - peso 0.2

### Horizontes de previsao:
- **Curto prazo (SHORT_CHALLENGE):** 49 timesteps horarios (0 a +48h) - peso 0.2
- **Longo prazo (LONG_CHALLENGE):** 361 timesteps horarios (0 a +360h/15 dias) - peso 0.8

### Formato de saida:
- Tensor float16 shape `(requested_hours, 721, 1440)` comprimido com blosc2
- Short: ~49 x 721 x 1440 x 2 bytes = ~102 MB descomprimido
- Long: ~361 x 721 x 1440 x 2 bytes = ~749 MB descomprimido

### Scoring:
- RMSE + MAE ponderados por latitude (cosseno) e com peso extra para Europa (1.5x) e Alemanha (2.5x)
- Score final = (RMSE + MAE) / 2
- Competition ranking: rank 1 = melhor, penalizados vao para ultimo

### Sistema de pesos (PERCENTAGE_GOING_TO_WINNER = 0.95):
- **95% do peso de cada challenge vai para o rank 1**
- Restantes 5% distribuidos logaritmicamente entre os demais
- Pesos finais = media ponderada dos pesos de cada challenge (variable x horizon)

---

## Por que Gini e 0.167 (baixo) com 9 miners?

**CONTRADIZ o codigo.** O mecanismo de scoring e extremamente winner-take-all:
- `PERCENTAGE_GOING_TO_WINNER = 0.95` -- 95% vai para o primeiro lugar
- Com 8 challenges (4 variaveis x 2 horizontes), a media ponderada pode diluir um pouco
- Mas se 1 miner domina todas, ele levaria ~95% de tudo

**Explicacao provavel do Gini baixo:**
1. Diferentes miners podem ser melhores em diferentes variaveis/horizontes
2. O sistema de rank usa janela historica (window_size), entao lideranca pode alternar
3. Collusion detection remove miners muito similares (threshold RMSE < 0.002 para short, < 0.00002 para long)
4. Poucos miners ativos (9) com performance parecida usando modelos similares (possivelmente todos usando Open-Meteo ou similar)
5. O mecanismo de "burn" (uid 56) distribui parte para queima de TAO

**Na pratica, o Gini baixo provavelmente reflete que os miners existentes tem performance similar, nao que o sistema e egalitario por design. O design e fortemente winner-take-all.**

---

## Hardware Requirements

### Oficial (min_compute.yml):
- CPU: 4 cores min, 8 recomendado, 2.5 GHz+
- RAM: 16 GB min
- GPU: **NAO NECESSARIO** (required: False)
- Storage: 10 GB min, 100 GB recomendado (SSD)
- Rede: 100 Mbps download, 20 Mbps upload

### Analise real:
- O miner default gera arrays de ~750 MB em memoria (15 dias x 721 x 1440 x float16)
- Compressao blosc2 reduz significativamente para transmissao
- **16 GB RAM e necessario** -- o CX23 da Hetzner tem apenas 4 GB RAM
- Bandwidth importante: payloads comprimidos do long challenge podem chegar a ~780 MB

### Hetzner CX23 ($8/mo) - INSUFICIENTE:
- 2 vCPU, 4 GB RAM, 40 GB disk
- **4 GB RAM e insuficiente** para arrays de ~750 MB em memoria
- Seria necessario no minimo um **CX32 (8 GB RAM, ~$14/mo)** ou idealmente **CX41 (16 GB RAM, ~$22/mo)**

---

## Precisa de ML? (Classificado LIGHT_ML)

### Analise do requirements.txt:
```
torch>=2.4.0          # NECESSARIO - usado no protocolo, compression, miner
numpy>=2.0.0          # NECESSARIO
blosc2==4.0.0         # NECESSARIO - compressao de predicoes
openmeteo-requests    # "miners only" - API de previsao meteorologica
```

### Veredicto sobre ML:
- **torch e necessario como dependencia**, mas e usado apenas para manipulacao de tensores (serialize/deserialize), NAO para inferencia de modelo
- **O miner default NAO usa nenhum modelo ML** - gera dados aleatorios
- **Para competir**, voce pode usar:
  - **Open-Meteo API** (gratis, ja tem loader no codigo) - sem ML
  - **Modelo ML proprio** (ex: Pangu-Weather, GraphCast, FourCastNet) - requer GPU para treino
  - **Ensemble de APIs meteorologicas** - sem ML
- **Classificacao LIGHT_ML e correta**: torch como dependencia mas nao precisa de GPU para mining

### Setup.sh confirma: instala CPU-only torch
```bash
pip install --extra-index-url https://download.pytorch.org/whl/cpu -e .
```

---

## ECONOMIA REAL

| Metrica | Valor |
|---------|-------|
| Emissao diaria | 38.02 TAO |
| Emissao mensal | ~1,140 TAO |
| Mediana USD/mes | $37,538 |
| Miners scoring | 9 |
| Mediana por miner | ~$4,171/mes (se igual) |
| Custo VPS (minimo viavel) | ~$22/mo (CX41 16GB) |
| Custo registro | ~0.1 TAO = ~$27 |
| ROI potencial | **Excelente se conseguir top 3** |

### Realidade economica:
- Com PERCENTAGE_GOING_TO_WINNER = 0.95, o rank 1 leva a maioria
- Se voce NAO for top 1-3, seus ganhos serao minimos
- A mediana alta ($37k) e inflada pelo winner-take-all com poucos miners
- **Risco real: entrar como 10o miner com previsoes ruins = quase zero reward**

---

## SETUP ESTIMADO

### Tempo total: 4-8 horas (setup basico) + dias/semanas (modelo competitivo)

### Passos:
1. **VPS setup (30 min):** Provisionar VPS com 16 GB+ RAM
2. **Instalacao (30 min):**
   ```bash
   git clone https://github.com/Orpheus-AI/Zeus.git && cd Zeus
   conda create -y -n zeus python=3.11
   conda activate zeus
   ./setup.sh
   ```
3. **Wallet e registro (30 min):** Criar wallet, registrar no netuid 18
4. **Configurar miner.env (10 min)**
5. **CRITICO - Implementar modelo de previsao (horas a semanas):**
   - Opcao rapida: integrar Open-Meteo API (horas)
   - Opcao competitiva: treinar/fine-tune modelo ML (semanas, requer GPU)
6. **Launch (10 min):** `./start_miner.sh`
7. **Aguardar scoring (~7 dias):** Ground truth ERA5 tem delay

---

## CURVA DE APRENDIZAGEM

### Para dev Python sem ML:
- **Entender o protocolo commit-reveal:** 2-3 horas lendo codigo
- **Integrar Open-Meteo API:** 1-2 dias (loader ja existe no codigo como referencia)
- **Entender ERA5/meteorologia:** 1-2 dias para unidades, variaveis, coordenadas
- **Produzir previsao global 721x1440:** Complexo - Open-Meteo nao retorna grid global facilmente
- **Competir com miners existentes:** Semanas de iteracao

### Complexidades nao-obvias:
1. O grid e GLOBAL (721x1440 = 1,038,240 pontos por timestep)
2. Open-Meteo API tem limites de rate/tamanho de request - impossivel pegar grid global inteiro de uma vez
3. Precisaria interpolar/agregar dados de multiplas fontes
4. O peso extra para Europa/Alemanha significa que erros la custam mais caro
5. O challenge de 15 dias (peso 0.8!) e MUITO mais importante que o de 48h
6. Previsao meteorologica a 15 dias e inerentemente dificil

---

## MANUTENCAO DIARIA

- **Monitoramento:** Verificar que miner esta respondendo (pm2 logs)
- **Previsoes:** Se usando API, garantir que calls funcionam 4x/dia
- **Storage:** Miner deve manter previsoes ate scoring (~7-10 dias)
- **Updates:** Acompanhar repo para mudancas no protocolo
- **Estimativa:** 30-60 min/dia inicialmente, 15 min/dia depois de estavel

---

## BARREIRAS REAIS

### 1. BARREIRA TECNICA ALTA
O miner default e um placeholder que envia dados aleatorios. Voce PRECISA implementar um modelo de previsao real. Isso nao e trivial:
- Grid global 0.25 graus e enorme
- 4 variaveis diferentes com unidades ERA5 especificas
- Horizonte de 15 dias (peso 80%) e extremamente dificil

### 2. RAM INSUFICIENTE NO CX23
16 GB minimo recomendado. O CX23 com 4 GB nao suporta os arrays de 750 MB+ em memoria.

### 3. SCORING DELAY DE 7+ DIAS
Ground truth ERA5 demora ~7 dias. Voce nao sabe se seu modelo esta funcionando ate la.

### 4. WINNER-TAKE-ALL EXTREMO
95% vai para rank 1. Se voce nao esta entre os top 3, os ganhos sao desprezaveis.

### 5. COLLUSION DETECTION
Se suas previsoes forem muito parecidas com outro miner (threshold RMSE < 0.002), o miner mais novo e penalizado. Usar a mesma API que outros pode triggerar isso.

### 6. BANDWIDTH
Long challenge pode exigir transmissao de ~780 MB comprimidos. Timeout de 55 segundos.

---

## Red Flags

1. **MINER DEFAULT E RANDOM** -- O codigo de referencia gera `np.random.rand(...)`. Nenhum modelo real e fornecido. Isso significa que a barreira real de entrada e construir um forecaster meteorologico global, nao apenas rodar o codigo.

2. **WINNER-TAKE-ALL EXTREMO (95%)** -- Gini de 0.167 e enganoso. O mecanismo favorece massivamente o rank 1. A baixa desigualdade atual provavelmente reflete miners com performance similar, nao um design egalitario.

3. **PESO 80% NO CHALLENGE DE 15 DIAS** -- Previsao meteorologica a 15 dias e um problema de pesquisa ativa. Modelos state-of-the-art (ECMWF) mal conseguem habilidade alem de 10 dias. Competir nisso sem ML expertise e muito dificil.

4. **RAM REQUIREMENT NAO BATE COM VPS BARATO** -- 16 GB RAM necessario, CX23 tem 4 GB. Custo real e 3x maior.

5. **OPEN-METEO NAO RESOLVE O PROBLEMA** -- Open-Meteo e otimo para pontos especificos mas nao fornece grid global 721x1440 facilmente. Rate limits tornam impratico para cobertura global 4x/dia.

6. **SEM MODELO BASE COMPETITIVO** -- Diferente de outras subnets que fornecem um baseline funcional, aqui o miner e deliberadamente um placeholder. A complexidade de implementacao e alta.

---

## PROBABILIDADE DE PRIMEIROS REWARDS EM 7 DIAS

### 15% -- BAIXA

**Justificativa:**
- Dia 1-2: Setup e entender o protocolo
- Dia 2-4: Implementar algum modelo de previsao (Open-Meteo parcial?)
- Dia 4-5: Deploy e primeiras respostas ao validator
- Dia 5-12: Aguardar ground truth ERA5 para scoring (~7 dias)
- **Matematicamente impossivel receber rewards em 7 dias** -- o scoring delay sozinho e ~7 dias
- Mesmo com setup perfeito no dia 1, primeiro scoring seria ~dia 8-14
- E mesmo recebendo score, com dados de Open-Meteo parcial vs miners estabelecidos, provavelmente ficaria em ultimo lugar
- 95% vai pro rank 1, entao "receber rewards" != "receber rewards significativos"

---

## VEREDICTO

**NAO RECOMENDADO para o perfil atual.**

### Razoes:
1. **Complexidade tecnica altissima:** Construir um forecaster meteorologico global nao e tarefa para 4h/dia sem expertise em ML/meteorologia. O miner default e um placeholder inutil.

2. **Hardware incompativel:** CX23 (4 GB RAM) e insuficiente. Precisaria no minimo $22/mo (CX41), e idealmente mais para processar os grids.

3. **Winner-take-all torna entrada arriscada:** Com 95% indo para rank 1 e 9 miners estabelecidos, um 10o miner precisaria superar pelo menos metade deles para ganhar algo relevante.

4. **Sem ML = sem competitividade:** Apesar de torch ser so dependencia de serialization, competir de verdade requer modelos de weather prediction (Pangu-Weather, FourCastNet, etc.) que precisam GPU para treino e ML expertise para operar.

5. **Delay de scoring impossibilita rewards em 7 dias:** O ground truth ERA5 leva ~7 dias. Primeiro scoring seria no dia 14+.

### Quando faria sentido:
- Se voce tiver acesso a um modelo de weather prediction pre-treinado
- Se tiver experiencia com dados ERA5/meteorologicos
- Se tiver budget para VPS com 16+ GB RAM
- Se aceitar ROI apenas apos 2-4 semanas de iteracao
- A recompensa mediana ($4k+/mes se top 3) e atraente, mas a barreira de entrada e uma das mais altas entre subnets "light"

### Score: 3/10 (para este perfil)
- Oportunidade economica: 7/10 (mediana alta, poucos miners)
- Viabilidade tecnica: 2/10 (requer forecaster global sem base fornecida)
- Fit com perfil: 2/10 (sem ML, sem GPU, VPS fraco, 4h/dia insuficiente)
