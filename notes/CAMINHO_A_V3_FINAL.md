# CAMINHO A v3 — Relatório Final
## Mining External em Subnets Bittensor
**Data:** 2026-04-12 | **TAO/USD:** $320 | **Infra ref:** Vast.ai RTX 4090 $180/mês

---

## Pipeline Summary

| Fase | Filtro | Input | Passed | Failed |
|------|--------|-------|--------|--------|
| Pre-filter | active_miners >= 5, emission > 0 | 116 | 38 | 78 |
| Fase 0 | top1 >= $300/mo, uniform >= $50/mo, scoring >= 5 | 38 | 34 | 4 |
| Fase 1 | flow_30d > -1000 TAO, github != null | 34 | 29 | 5 |
| Fase 2 | Grep: burn=0, math=0, central<=2 | 29 | 27 | 2 |
| Fase 3 | Deep dive top 6 | 6 | 1 GO | 5 |

**Taxa de sobrevivência total: 1/116 = 0.86%**

---

## Fase 0 — Filtro Económico HARD

78 subnets eliminadas no pre-filtro (active_miners < 5). Isto é o dado mais revelador: **67% das subnets têm menos de 5 miners activos**. A maioria do ecossistema Bittensor é ocupada por subnets-fantasma ou monopólios de 1-2 miners.

Dos 38 que passaram ao query de neurons:
- 4 FAILED por scoring < 5 (SN14 TAOHash, SN44 Score, SN48 Quantum Compute, SN80 dogelayer)
- 34 PASSED

## Fase 1 — Filtro Flow + GitHub

5 rejeitadas por outflow severo (> 1000 TAO/30d):
- SN8 Vanta: -4538 TAO/30d (apesar de $752k top1)
- SN6 Numinous: -3434 TAO/30d
- SN13 Data Universe: -1800 TAO/30d
- SN33 ReadyAI: -1181 TAO/30d
- SN78 Loosh: -1330 TAO/30d

## Fase 2 — Grep Automático

2 rejeitadas:
- **SN74 Gittensor**: TREASURY_UID hardcoded (insider capture)
- **SN71 Leadpoet**: 18 external API calls (centralização extrema)

## Fase 3 — Deep Dive (Top 6)

### Tabela Cruzada Final

| SN | Name | top1$/mo | med$/mo | break_even_vast | red_flags | veredicto |
|----|------|----------|---------|-----------------|-----------|-----------|
| 56 | Gradients | $373,937 | $11,117 | <1 dia | Nenhuma significativa | **GO** |
| 34 | BitMind | $359,872 | $1,708 | ~3 dias (top25) | API-controlled escrow (93% emission); trust_remote_code | MARGINAL |
| 12 | Compute Horde | $339,441 | $1,737 | ~3 dias (top25) | Burn mechanism 100% runtime; Pylon intermediary | MARGINAL/IMPOSSIBLE |
| 45 | Talisman AI | $226,291 | $100 | NUNCA | BURN_UID=189 captura 99.8%; sample_size=1 validation | IMPOSSIBLE |
| 22 | Desearch | $208,629 | $366 | NUNCA | 80% emission tax to team hotkey; pow(r*4,4) exaggeration | IMPOSSIBLE |
| 59 | Babelbit | $202,774 | $62 | NUNCA | 95% winner-take-all by design; centralized scoring API; fallback UID 248 | IMPOSSIBLE |

---

## Análise Detalhada por Veredicto

### GO: SN56 Gradients

**Por que funciona:**
- Miners NÃO precisam de GPU — submetem scripts de AutoML, validators executam
- Custo real de mining: ~$350/mês (participation fees + servidor mínimo)
- Mediana real: $11,117/mês — ROI de 31x
- Sem burn traps, sem emission tax, sem insider UIDs
- Scoring baseado em competição de modelos (torneios)
- Gini 0.667 é moderado — não é winner-take-all extremo

**Riscos:**
- trust_remote_code=True em datasets (mitigado por curadoria)
- Auto-updater sem verificação criptográfica
- Barreira de entrada técnica alta (AutoML/ML expertise)

**Break-even Vast.ai:** < 1 dia (custo mínimo, revenue alto)
**Break-even Hetzner:** < 1 dia

### MARGINAL: SN34 BitMind

- API-controlled escrow recebe 93% das emissões — só 7% para generators
- Hardware pesado (>= 24GB VRAM)
- Top 25 miners podem ser viáveis, mas mediana é marginal
- Risco de centralização via API do team

### MARGINAL/IMPOSSIBLE: SN12 Compute Horde

- Monopoly natural: 97.5% vai para 1 miner
- Burn mechanism pode redirecionar 100% das emissões a runtime
- Pylon intermediary centraliza weight-setting
- Novos miners não conseguem competir por organic jobs

### IMPOSSIBLE: SN45, SN22, SN59

Todas partilham o mesmo padrão: **burn/tax mechanism que desvia 80-99% das emissões para o team/burn address**, deixando migalhas para miners genuínos. A mediana de revenue não cobre sequer os custos de infraestrutura.

---

## Subnets NÃO deep-dived mas economicamente interessantes

Da lista de 27 survivors Fase 2, além do top 6, estas merecem atenção futura:

| SN | Name | med$/mo | gini | Nota |
|----|------|---------|------|------|
| 105 | Beam | $47,332 | 0.377 | Mediana MUITO alta, gini baixo. Não clonável (org page). |
| 18 | Zeus | $44,489 | 0.167 | Mediana alta, gini muito baixo (egalitário). 9 miners. |
| 73 | MetaHash | $41,097 | 0.000 | Gini ZERO — perfeitamente igual. 6 miners. |
| 57 | Sparket.AI | $20,332 | 0.031 | Quase perfeita igualdade. 8 miners. |
| 77 | Liquidity | $7,859 | 0.576 | Revenue decente, gini moderado. |
| 41 | Almanac | $7,649 | 0.489 | Revenue decente, gini moderado. |
| 65 | TAO Private Net | $5,596 | 0.616 | Revenue OK. |
| 85 | Vidaio | $5,168 | 0.355 | Revenue OK, gini baixo. |

**SN18 Zeus e SN73 MetaHash** são particularmente interessantes por terem revenue mediana alta com distribuição muito egalitária — deep dive recomendado.

---

## Meta-observações

1. **O ecossistema é brutalmente concentrado**: 67% das subnets têm < 5 miners activos. Das que têm, a maioria tem burn/tax mechanisms que desviam 80-99% para insiders.

2. **A fórmula "emission / miners" é enganadora**: Sem verificar a distribuição real (Gini), não se pode avaliar viabilidade. SN22 parece ter $1,853/mês uniform — mas na realidade o mediano ganha $366 porque 80% vai para o team.

3. **SN56 Gradients é o único GO claro** dos top 6: não tem GPU requirement, não tem burn trap, e a mediana de revenue é genuinamente alta ($11k/mês). Mas requer expertise significativa em ML.

4. **Subnets com gini < 0.2 merecem investigação**: SN18, SN73, SN57 têm distribuições muito igualitárias que sugerem fairness genuína — mas precisam de deep dive para confirmar que não há armadilhas escondidas.

---

## Recomendação Claude Chat

**Para mining com investimento mínimo e máximo ROI:**
1. **SN56 Gradients** — se tens competência em ML/AutoML, é o melhor ROI do ecossistema inteiro. Custo < $400/mês, mediana > $11k/mês.

**Para investigação futura (Caminho A v4):**
2. **SN18 Zeus** — mediana $44k/mês com gini 0.167 é quase bom demais para ser verdade. Precisa deep dive urgente.
3. **SN73 MetaHash** — gini=0.000 é literalmente perfeito. 6 miners. Precisa investigação.
4. **SN105 Beam** — mediana $47k/mês mas repo não clonou (org page). Encontrar repo real.

**Evitar absolutamente:**
- SN45, SN22, SN59 — burn traps confirmados por code review
- Qualquer subnet com < 5 active miners — monopólio estrutural
- Subnets com outflow > 1000 TAO/30d — capital flight

---

*Gerado por pipeline_v3_fast.py + deep dive manual*
*Ficheiros: data/fase0_v3_*.csv, data/fase1_v3_*.csv, data/fase2_v3_*.{json,csv}*
*Deep dives: notes/v3_{56,34,12,45,22,59}_codereview.md*
