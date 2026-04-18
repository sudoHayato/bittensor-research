# CAMINHO A v3 REFRAMED — Mining Operacional (Non-ML)
## Perfil: Python + automação + 4h/dia + VPS ($8-50/mês)
**Data:** 2026-04-12 | **TAO/USD:** $270 | **Infra ref:** Hetzner CX23 $8/mês

---

## Pipeline Summary

| Fase | Filtro | Input | Passed | Failed |
|------|--------|-------|--------|--------|
| Fase 0 | README keyword match (scraping/storage/oracle/data) | 116 | 36 | 80 |
| Fase 1 | Económico (top10 >= $80/mês) | 36 | 36 | 0 |
| Fase 2 | Grep (burn/math flags) + Hardware (CPU_ONLY/LIGHT_ML) | 36 | 25 | 11 |
| Fase 3 | Deep dive operacional (top 6) | 6 | 1 viable, 1 marginal | 4 |

---

## Fase 0 — Descoberta por Categoria

116 subnets scanned. Contagem por categoria de keyword match:
- oracle: 15
- monitoring: 14
- data_collection: 13
- networking: 12
- storage: 12
- indexing: 12
- api_service: 11
- compute_light: 9
- scraping: 6

**36 subnets** tiveram pelo menos 1 keyword match + emission >= 0.05 TAO/dia + active_miners >= 3.

## Fase 1 — Económico por Tier

**Resultado surpreendente: TODAS as 36 passaram** com top10 >= $80/mês (VIABLE_STORAGE). Isto acontece porque mesmo subnets com poucos miners têm emissões suficientes para os tiers baratos ($8-50/mês).

## Fase 2 — Hardware + Grep

| Rejeitadas | Motivo |
|------------|--------|
| SN1 Apex | GPU_REQUIRED |
| SN34 BitMind | GPU_REQUIRED |
| SN45 Talisman AI | GPU_REQUIRED |
| SN123 MANTIS | GPU_REQUIRED |
| SN54 Yanez MIID | GPU_REQUIRED |
| SN33 ReadyAI | GPU_REQUIRED |
| SN72 StreetVision | GPU_REQUIRED |
| SN85 Vidaio | GPU_REQUIRED |
| SN57 Sparket.AI | Burn flags |
| SN50 Synth | Burn flags |
| SN105 Beam | Clone failed (org URL) |

**25 sobreviventes**: 15 CPU_ONLY + 10 LIGHT_ML

---

## Fase 3 — Deep Dive Operacional

### Tabela Final — Top 6 Deep Dived

| SN | Name | med$/mo | gini | hw | TAREFA REAL | veredicto |
|----|------|---------|------|-----|-------------|-----------|
| 13 | Data Universe | $1,367* | 0.241 | LIGHT_ML | Scraping Reddit/X + upload S3 | **MARGINAL** |
| 73 | MetaHash | $34,676 | 0.000 | CPU_ONLY | Alpha token auctions (DeFi insider) | SKIP |
| 18 | Zeus | $37,538 | 0.167 | LIGHT_ML | Global weather forecasting | SKIP |
| 116 | TaoLend | $36,905 | 0.060 | CPU_ONLY | DeFi lending protocol (no miner code) | SKIP |
| 14 | TAOHash | $48,966 | 0.458 | CPU_ONLY | SHA-256 BTC mining proxy | SKIP |
| 41 | Almanac | $6,454 | 0.489 | CPU_ONLY | Polymarket prediction betting | **CONDITIONAL** |

*SN13: Revenue real ~$410/mês após 70% emission burn tax

---

## Análise Detalhada por Subnet

### SN13 Data Universe — MARGINAL (5/10)
**O que o miner faz:** Scraping de Reddit (JSON API, sem auth) e Twitter/X (via Apify, $49/mês). Armazena em SQLite, serve dados via axon, upload para S3, responde a jobs on-demand de API central.

**Por que MARGINAL:**
- 70% emission burn tax (`EMISSION_CONTROL_PERCENTAGE = 0.70`) — reduz mediana real de $1,367 para ~$410/mês
- Custo real: VPS $8 + Apify $49 + storage extra ~$5 = ~$62/mês
- Lucro líquido: ~$348/mês — positivo mas modesto
- Setup: 2-8h (straightforward Python)
- Manutenção: passiva (set and forget)
- 241 miners ativos = competição real mas gini baixo
- **PROB REWARDS 7 DIAS: MED** — precisa configurar axon + S3 + Apify, depois é automático

### SN73 MetaHash — SKIP (3/10)
**O que "o miner" faz:** Participa em leilões de alpha tokens — operação financeira pura, não computação.

**Por que SKIP:**
- 6 miners, TODOS do mesmo owner (insider coordenado)
- Gini=0.000 porque é literalmente a mesma pessoa controlando tudo
- Novos miners começam com 2% allocation vs 16.7% dos incumbentes
- Requer capital em alpha tokens para participar
- **NÃO É MINING OPERACIONAL**

### SN18 Zeus — SKIP (3/10)
**O que o miner faz:** Previsão meteorológica global (grid 721x1440) para 15 dias.

**Por que SKIP:**
- Miner default é `np.random.rand()` — placeholder
- Precisa construir modelo de previsão meteorológica DO ZERO
- 95% winner-take-all (`PERCENTAGE_GOING_TO_WINNER = 0.95`)
- Requer 16GB RAM mínimo (CX23 tem 4GB)
- Primeiros rewards só após 14+ dias (delay do ERA5 ground truth)
- **REQUER ML EXPERTISE que o perfil não tem**

### SN116 TaoLend — SKIP (0/10)
**O que "o miner" faz:** NADA. Não existe código de miner no repo.

**Por que SKIP:**
- É um protocolo DeFi de lending, não uma subnet de mining
- 4 "miners" = todos do mesmo owner
- Weights vindos de API centralizada (`api.taolend.io/v1/weights`)
- Participação externa = depositar TAO no protocolo (decisão financeira, não operacional)
- **FALSO POSITIVO TOTAL**

### SN14 TAOHash — SKIP (1/10)
**O que o miner faz:** Proxy para mining de Bitcoin (SHA-256). O script Python é apenas um configurador de pool credentials.

**Por que SKIP:**
- Mining real requer ASICs ou hashrate alugado ($500+/mês)
- VPS a $8/mês é completamente inútil
- 4 miners = operações industriais
- 18% owner take + 50% split with miners
- **REQUER HARDWARE ENTERPRISE que o perfil não tem**

### SN41 Almanac — CONDITIONAL (5/10 com trading experience, 2/10 sem)
**O que o miner faz:** Faz apostas reais no Polymarket. Validators avaliam P&L e distribuem rewards proporcionalmente.

**Por que CONDITIONAL:**
- CPU_ONLY: sim, VPS suficiente
- Setup: <2h (registo + wallet Polygon)
- Requer capital real ($100-500 USDC) para apostar
- Requer RENTABILIDADE — perder apostas = 0 rewards + capital perdido
- 34 miners ativos, cap de 10% por trader
- **PROB REWARDS 7 DIAS: MED-HIGH** se souberes o que estás a fazer

---

## Meta-observações REFRAMED

### 1. A maioria das "subnets operacionais" são falsas
Das 6 analisadas:
- 2 são protocolos DeFi disfarçados de subnets (SN73, SN116)
- 1 é proxy de BTC mining industrial (SN14)
- 1 requer expertise ML que o perfil não tem (SN18)
- Apenas 2 são genuinamente operacionais (SN13, SN41)

### 2. Subnets com poucos miners (< 10) e mediana alta são quase sempre armadilhas
O padrão é: poucos miners = insider group, gini baixo por coordenação, não por fairness. SN73 (gini=0.000), SN116 (gini=0.060), SN14 (gini=0.458 com 4 miners) — todos insiders.

### 3. A "mediana" é enganadora para subnets com < 10 miners
Com 4 miners, a "mediana" é literalmente o 2º miner. Adicionar 1 miner dilui tudo. Confiar apenas em subnets com 20+ miners para medianas significativas.

### 4. Emission burns são universais
SN13: 70% burn. SN22: 80% burn. SN45: 99.8% burn. A receita real é SEMPRE muito inferior à emisão teórica.

---

## Subnets NÃO deep-dived que merecem atenção futura

| SN | Name | med$/mo | gini | miners | hw | Nota |
|----|------|---------|------|--------|-----|------|
| 126 | Poker44 | $1,291 | 0.155 | 240 | CPU_ONLY | Grande, gini baixo, data/oracle. **Candidato #1 para next deep dive.** |
| 103 | Djinn | $1,076 | 0.029 | 246 | LIGHT_ML | Quase perfeita igualdade, grande subnet. **Candidato #2.** |
| 82 | Hermes | $579 | 0.069 | 246 | CPU_ONLY | Grande, gini baixíssimo. Pode ser viável com VPS a $8. |
| 111 | oneoneone | $687 | 0.152 | 249 | LIGHT_ML | Grande, gini baixo. |
| 128 | ByteLeap | $3,498 | 0.206 | 42 | CPU_ONLY | Mediana decente, tamanho médio. |
| 77 | Liquidity | $6,631 | 0.576 | 9 | CPU_ONLY | Poucos miners mas revenue boa. |

---

## TOP 3 RECOMENDAÇÕES

### 1. SN13 Data Universe — ACÇÃO: setup dentro de 1 semana
- **Lucro líquido:** ~$348/mês (após burn + custos)
- **Setup:** 2-8 horas, Python puro
- **Custo:** $62/mês (VPS + Apify + storage)
- **Risco:** burn tax pode aumentar; 241 miners = competição real
- **Próximo passo:** criar conta Apify, provisionar VPS com 100GB disk, seguir guia miner

### 2. SN41 Almanac/Sportstensor — ACÇÃO: só se tiveres trading edge
- **Lucro potencial:** $6,454/mês mediana (mas requer apostas rentáveis)
- **Setup:** <2 horas
- **Custo:** $8/mês VPS + capital de apostas ($100-500 USDC)
- **Risco:** perda de capital se apostas forem más
- **Próximo passo:** criar conta Polymarket, experimentar com $50-100 primeiro

### 3. Deep dive SN126 Poker44 + SN103 Djinn — INVESTIGAR
- Ambas têm 240+ miners, gini < 0.16, CPU_ONLY/LIGHT_ML
- Medianas de $1,076-$1,291 contra $8/mês de VPS = ROI potencial de 130-160x
- **PRECISA deep dive para verificar se não há burn tax escondida**

---

## Conclusão Brutal

O ecossistema Bittensor para mining operacional (não-ML, não-GPU) é **extremamente pobre em opções genuínas**:

- Das 116 subnets analisadas, apenas **2** são genuinamente mineable com o perfil Python+VPS
- A maioria das subnets "operacionais" são DeFi protocols, proxy mining, ou insider groups disfarçados
- O melhor caso (SN13) rende ~$348/mês líquido — viável mas não transformador
- O caminho mais promissor requer research adicional (SN126, SN103) para confirmar que não há armadilhas

**A realidade: Bittensor mining em 2026 é dominado por insiders com burn mechanisms que capturam 70-99% das emissões. O espaço para outsiders individuais em VPS barato existe mas é estreito.**

---

*Gerado por pipeline_reframed_fase0.py + pipeline_reframed_fase1.py + deep dives manuais*
*Ficheiros: data/operacional_candidates.csv, data/reframed_fase1_all.csv, data/reframed_fase2_survivors.json*
*Deep dives: notes/op_{13,73,18,116,14,41}_codereview.md*
