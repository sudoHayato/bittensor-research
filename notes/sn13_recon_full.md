# SN13 Data Universe — Full Reconnaissance
## Data: 2026-04-13
## Commit auditado: 5672ac633d (2026-04-08, "Merge PR #820 from dev")

---

## 1. O que o miner faz (descrição operacional precisa)

O miner SN13 é um scraper de dados sociais. Corre como processo Python persistente com axon aberto para receber requests de validators. Opera em 5 threads paralelos:

1. **Scraping contínuo** (`ScraperCoordinator`): Scrape periódico de Reddit (via JSON API pública, sem auth obrigatória), X/Twitter (via Apidojo Apify actor, pago), e YouTube transcripts. Configurável via `scraping_config.json`. Cadência default: Reddit a cada 10s, X a cada 300s, YouTube a cada 100s.

2. **Index serving** (axon): Responde a requests `GetMinerIndex` e `GetDataEntityBucket` de validators. Os validators pedem o índice comprimido do miner para saber que dados tem, e depois amostragens aleatórias para verificar credibilidade.

3. **S3 upload** (`S3PartitionedUploader`): A cada 2h, faz upload dos dados scrapeados para S3 via presigned URLs obtidas da API da Macrocosmos (`data-universe-api.api.macrocosmos.ai`). Autenticação via wallet keypair.

4. **On-Demand jobs** (`poll_on_demand_active_jobs`): Poll a cada 5s à API central da Macrocosmos por jobs de scraping de clientes Gravity. Quando recebe um job, scrape e submete resultados via API.

5. **Dynamic desirability** (`get_updated_lookup`): A cada 20min, puxa da API da Macrocosmos a lista actualizada de labels desejáveis (driven by Gravity customer requests). Escreve `total.json` local.

Dados armazenados em SQLite local (`miner.db`). Dados mais velhos que 30 dias não são scored.

---

## 2. Reward formula completa

O score final de cada miner é composto por 3 componentes independentes, cada um com a sua própria credibilidade:

```
final_score = P2P_component + S3_component + OD_component
```

### P2P Component (miner_scorer.py:549)
```
P2P_component = scorable_bytes × P2P_REWARD_SCALE(0.05) × (p2p_credibility ^ 2.5)
```
Onde `scorable_bytes` = Σ(data_value per bucket), calculado por `DataValueCalculator`:
```
data_value = data_type_scale_factor × time_scalar × size_bytes × duplication_factor
```

### S3 Component (miner_scorer.py:550)
```
S3_component = s3_boost × (s3_credibility ^ 2.5)
s3_boost = (my_effective_size² / total_effective_size) × 1.0
effective_size = total_size_bytes × coverage²
```
**CAP**: `S3_component <= 2 × OD_component` (sem OD, S3 = 0)

### On-Demand Component (miner_scorer.py:551)
```
OD_component = ondemand_boost × ondemand_credibility
ondemand_boost = EMA(α=0.3) de rewards dos jobs
reward_per_job = ONDEMAND_BASE_REWARD(100M) × speed_multiplier(0.1-1.0) × volume_multiplier(0.0-1.0)
```

### Cap entre componentes (miner_scorer.py:194-198 em `get_scores_for_weights`)
```
S3 <= 2 × OD          (sem OD, S3 = 0)
P2P <= S3 + OD         (sem S3+OD, P2P = 0)
```

**Implicação CRÍTICA**: Sem participação em On-Demand jobs, o score total é ZERO. OD é prerequisite absoluto.

### Peso final na chain (validator.py:774-780)
```
raw_weights = normalize(final_scores)
raw_weights = apply_burn(raw_weights, burn_percentage=0.70)
# Owner UID recebe 70%, restantes 30% distribuídos proporcionalmente entre miners
```

---

## 3. Burn mechanism actual

**Percentagem**: 70% — hardcoded em `common/constants.py:51`:
```python
EMISSION_CONTROL_PERCENTAGE = 0.70
```

**Implementação**: `common/utils.py:364-404` (`apply_burn_to_weights`):
- Query o hotkey do owner do subnet via subtensor
- Set owner UID weight = 0.70
- Scale restantes weights para somar 0.30

**Mudou recentemente?** Não. O valor 0.70 esteve constante nos últimos 30 dias. A função `apply_burn_to_weights` foi introduzida antes desse período.

**Pode mudar sem deploy?** Não. É uma constante Python hardcoded. Requer push de código + validators a actualizar. Não há remote config para isto.

---

## 4. Credibility system

### P2P Credibility
- **Início**: 0.0 (`STARTING_CREDIBILITY = 0`, miner_scorer.py:29)
- **Update**: EMA com α=0.15 (`cred_alpha=0.15`)
  - `new_cred = 0.15 × validation_result + 0.85 × old_cred`
  - Onde `validation_result` = proporção de bytes validados com sucesso
- **Expoente**: 2.5 — um miner com credibilidade 0.5 só recebe 0.5^2.5 = 0.177 (17.7%) do score
- **Ramp-up real**: Para ir de 0 → 0.8 com 100% validações correctas:
  - Cada eval: `new = 0.15 + 0.85 × old`
  - Após 1 eval: 0.15
  - Após 5 evals: 0.56
  - Após 10 evals: 0.80
  - Evals a cada ~60 min → ~10 horas para credibilidade competitiva
- **Decay se offline**: A credibilidade NÃO decai por estar offline. Mantém-se no último valor. Mas o score P2P decai porque depende de dados frescos (max 30 dias).

### S3 Credibility
- **Início**: 0.375 (`STARTING_S3_CREDIBILITY`)
- **Update**: EMA com α=0.30
- **Forgiving**: Failure mantém effective_size anterior, apenas reduz credibilidade
- **Expoente**: 2.5

### On-Demand Credibility
- **Início**: 0.5 (`STARTING_ONDEMAND_CREDIBILITY`)
- **Update**: EMA com α=0.02 (lento — ~35 jobs para halve)
- **SEM expoente**: Multiplicação directa (miner_scorer.py:181)
- **Bad data penalty**: -5% directa por submissão rejeitada

### STATE_VERSION reset
Actualmente em **v7** (miner_scorer.py:27). Cada bump de version RESETA TUDO (scores, credibilidades, boosts) para todos os miners. Houve 3 resets nos últimos 30 dias (v5→v6→v7). **Isto é devastador para miners novos e incumbentes igualmente.**

---

## 5. Estado actual on-chain (2026-04-13)

### Métricas de rede
| Métrica | Valor |
|---------|-------|
| Active miners | 240 |
| Active validators | 11 |
| Tempo | 360 |
| Net flow 30d | -1,794 TAO |
| Net flow 7d | +75 TAO |
| Net flow 1d | +303 TAO |

### Top 20 miners (por incentive share, receita APÓS 70% burn)
| # | UID | Share | TAO/dia | $/mês |
|---|-----|-------|---------|-------|
| 1 | 6 | 0.960% | 0.127 | $1,029 |
| 2 | 13 | 0.960% | 0.127 | $1,029 |
| 3 | 81 | 0.960% | 0.127 | $1,029 |
| 4 | 186 | 0.960% | 0.127 | $1,029 |
| 5 | 231 | 0.960% | 0.127 | $1,029 |
| 6 | 37 | 0.955% | 0.126 | $1,023 |
| 7 | 47 | 0.955% | 0.126 | $1,023 |
| 8 | 68 | 0.955% | 0.126 | $1,023 |
| 9 | 238 | 0.955% | 0.126 | $1,023 |
| 10 | 22 | 0.950% | 0.126 | $1,017 |
| 11 | 50 | 0.950% | 0.126 | $1,017 |
| 12 | 60 | 0.950% | 0.126 | $1,017 |
| 13 | 71 | 0.950% | 0.126 | $1,017 |
| 14 | 134 | 0.950% | 0.126 | $1,017 |
| 15 | 164 | 0.939% | 0.124 | $1,006 |
| 16 | 112 | 0.929% | 0.123 | $995 |
| 17 | 208 | 0.918% | 0.121 | $984 |
| 18 | 1 | 0.908% | 0.120 | $972 |
| 19 | 165 | 0.903% | 0.119 | $967 |
| 20 | 161 | 0.892% | 0.118 | $956 |

### Distribuição completa (após 70% burn)
| Métrica | Valor |
|---------|-------|
| Emissão total | 44.08 TAO/dia |
| Emissão para miners (30%) | 13.22 TAO/dia |
| Miners scoring (incentive>0) | 239 |
| Top 1 revenue | $1,029/mês |
| Top 10 avg revenue | $1,025/mês |
| Mediana revenue | $354/mês |
| Bottom 10 avg revenue | $95/mês |
| Gini (entre miners) | 0.272 |
| Miners com >$100/mês | 235 |
| Miners com >$50/mês | 236 |
| Miners com >$8/mês (VPS cost) | 239 (todos) |

**Observação**: A distribuição é notavelmente plana no topo — top 5 miners estão todos a ~$1,029/mês. Isto sugere que o OD component domina e equaliza os top miners.

---

## 6. Trajectória 14 dias do top 10

**Nota**: Não foi possível obter dados históricos de miner individual via taostats (endpoint `miner/history` rate limited). Contudo, a análise do git log revela:

- **Apr 8 (v7 deploy)**: Full state reset — todos os scores e credibilidades zerados
- **Apr 4**: S3 cap implementado (S3 <= 2x OD)
- **Apr 3**: Exploit fix (UID 194 fabrication detection)
- **Apr 1**: Sampling fix (.head → .sample)
- **Mar 27 (v5)**: Full state reset anterior

**Implicação**: Os scores actuais representam apenas ~5 dias de acumulação desde o reset v7 de Apr 8. A distribuição ainda está a estabilizar. **Miners novos entram em condições quase iguais aos incumbentes após um reset.**

**Flow trend**: 30d flow é -1,794 TAO (outflow), mas 7d é +75 TAO e 1d é +303 TAO. O outflow está a reverter — capital está a entrar novamente.

---

## 7. Discrepância on-chain vs leaderboard externo

Dashboard oficial: `https://sn13-dashboard.api.macrocosmos.ai/`

Não foi possível fazer web_fetch do dashboard (sem endpoint API público documentado para métricas de miners individuais). O dashboard mostra dados agregados por DataSource e DataLabel, não leaderboard de miners.

O leaderboard de miners é visível no WandB: `https://wandb.ai/macrocosmos/data-universe-validators` (anonymous logging).

**Sem discrepância verificável** — os dados on-chain do taostats parecem consistentes com a arquitectura do código.

---

## 8. Requisitos técnicos REAIS

### Dependências externas
| Dependência | Obrigatória? | Custo | Notas |
|-------------|--------------|-------|-------|
| Apify (X scraping) | NÃO para Reddit, SIM para X | $49/mês (Actor tier) | Pode construir custom scraper para X |
| Reddit account | NÃO (JSON API pública funciona) | Grátis | OAuth setup se usar PRAW, mas `RedditJsonScraper` não precisa |
| S3-compatible storage | SIM (S3 component = 0 sem isto) | Via Macrocosmos API (grátis?) | Auth via wallet keypair, presigned URLs |
| Macrocosmos API access | SIM (OD jobs + S3 auth) | Grátis (incluído no subnet) | `data-universe-api.api.macrocosmos.ai` |
| Bittensor wallet | SIM | Registration cost ~0.001 TAO | Precisa de hotkey registado no SN13 |

### Hardware mínimo realista
| Recurso | Mínimo | Recomendado |
|---------|--------|-------------|
| CPU | 2 cores | 4 cores |
| RAM | 4 GB | 8 GB |
| Disk | 50 GB (SQLite cresce) | 100+ GB |
| Bandwidth | ~5 GB/dia (scraping + serving) | Unlimited |
| Python | >= 3.10 | 3.11+ |

### Variáveis de ambiente obrigatórias (.env)
```
# Opcional (para X scraping via Apify):
APIFY_API_TOKEN="..."

# Opcional (para Reddit via PRAW — alternativa ao JSON scraper):
REDDIT_CLIENT_ID="..."
REDDIT_CLIENT_SECRET="..."
REDDIT_USERNAME="..."
REDDIT_PASSWORD="..."
```

### Portas
- **Axon port** (default: 8091) — DEVE estar aberto e acessível externamente. Validators query o miner via axon.

### Tempo estimado de setup
- **Mínimo viável (Reddit only, sem Apify)**: 2-4 horas
  - Clone, install, criar wallet, registar no SN13, configurar scraping_config para Reddit only, pm2 start
- **Completo (Reddit + X + S3 + OD)**: 4-8 horas
  - Tudo acima + criar conta Apify + configurar X scraping + confirmar S3 uploads

---

## 9. Custos reais mensais (não optimistas)

### Cenário A: Mínimo (Reddit only, sem Apify)
| Item | Custo/mês |
|------|-----------|
| VPS (Hetzner CX23, 4GB RAM, 80GB disk) | €4.51 (~$5) |
| Apify | $0 (não usado) |
| Reddit API | $0 (JSON API pública) |
| Registration (one-time) | ~$0.27 (0.001 TAO) |
| **Total mensal** | **~$5** |

**PROBLEMA**: Sem Apify, não há X scraping. X vale 35% do peso de data. E sem dados X diversificados, o miner terá score inferior.

### Cenário B: Completo (Reddit + X via Apify)
| Item | Custo/mês |
|------|-----------|
| VPS (Hetzner CPX21, 4GB RAM, 80GB disk) | €8.49 (~$9) |
| Apify ($49/mês Actor tier) | $49 |
| Reddit API | $0 |
| **Total mensal** | **~$58** |

### Cenário C: Budget (Reddit + custom X scraper)
| Item | Custo/mês |
|------|-----------|
| VPS | ~$9 |
| Custom X scraper (tempo dev, não $$$) | $0 |
| **Total mensal** | **~$9** |

**Notas**: O docs diz "We recommend miners build a custom scraper for economic purposes". Isto confirma que Apify é evitável.

---

## 10. Red flags descobertos no recon

1. **70% emission burn para o owner** — Confirmado em `constants.py:51` + `utils.py:364`. O owner (Macrocosmos) captura 70% de toda a emissão. Miners dividem 30%.

2. **STATE_VERSION resets frequentes** — 3 resets completos em 30 dias (v5→v6→v7). Cada reset zera scores E credibilidades de TODOS os miners. Isto é positivo para novos entrants mas devastador para quem já acumulou credibilidade.

3. **OD é gate obrigatório** — Sem participação em On-Demand jobs, S3 = 0 e P2P = 0 (caps em `get_scores_for_weights`). OD depende de API central da Macrocosmos. Se a API falhar, miner fica sem score.

4. **Dependência da API central** — O miner depende de `data-universe-api.api.macrocosmos.ai` para: (a) poll OD jobs, (b) submit OD results, (c) S3 auth/upload, (d) dynamic desirability list. Se esta API falhar, o miner não pode operar.

5. **Credibility exponent 2.5** — Um miner novo começa com credibilidade 0.0. Mesmo após o primeiro eval positivo, cred = 0.15 → 0.15^2.5 = 0.0087 (0.87% multiplier). Leva ~10 horas de operação limpa para chegar a 0.8 (~57% multiplier).

6. **S3 upload é via presigned URLs do team** — O miner não controla o storage. Upload é para infrastructure da Macrocosmos. Dependência total.

7. **Apify como dependência para X scraping** — Docs recomendam custom scraper, mas o scraper default usa Apidojo actor no Apify. Construir custom scraper para X é não-trivial (rate limits, anti-bot).

---

## 11. Mudanças recentes (30d) que afectam economia do miner

| Data | Commit | Impacto |
|------|--------|---------|
| Apr 8 | `5672ac6` v7 deploy | **FULL RESET**: todos scores, credibilidades, boosts zerados. OD scoring movido para evaluator. P2P cap adicionado. |
| Apr 8 | `a95e9a5` | P2P capped at (S3 + OD). Sem OD participation, P2P = 0. |
| Apr 8 | `520f6d4` | Fix: P2P contamination — OD failures no longer affect P2P credibility |
| Apr 8 | `dd01b50` | OD scoring moved to evaluator, removed expensive poller validation |
| Apr 4 | `2f6ffa1` | S3 cap implementado: S3 <= 2x OD |
| Apr 3 | `07bc498` | UID 194 exploit fix: empty username fabrication detection |
| Apr 1 | `7303e07` | .head() → .sample() fix para parquet reads (anti-exploit) |
| Mar 27 | `c232989` | **STATE v5 RESET**: S3 + OD + scores full reset |
| Mar 27 | `a0d39a4` | S3 validation hardening: engagement, uniqueness, URL checks |
| Mar 17 | `918d401` | Don't punish for non-existent data |
| Mar 14 | `bfdcbe2` | Fix empty field submission |

**Pattern**: O team está em modo de combate activo contra exploits. 42 commits em 30 dias, maioritariamente anti-exploit + scoring fixes. **O scoring system está instável e muda frequentemente.**

---

## 12. Perguntas em aberto que exigem intel da Discord/community

1. **Quais miners custom X scrapers usam em vez de Apify?** Há alternativas open-source? Ou cada miner constrói o seu?

2. **Qual é a taxa de success real dos OD jobs?** Se um miner falha OD jobs por falta de Apify/X data, qual é o impacto na credibilidade OD?

3. **Os S3 presigned URLs têm custos escondidos?** O upload S3 é grátis para miners ou a Macrocosmos cobra?

4. **Qual é a frequência real de OD jobs?** Se são raros, o componente OD fica baixo mesmo para miners bons. Se são frequentes, miners sem X scraping ficam para trás.

5. **Há planos de reduzir o burn de 70%?** A Macrocosmos já sinalizou alguma redução futura?

6. **Qual é o storage real dos top miners?** O dashboard mostra dados agregados — quanto disk space usa um top-20 miner?

7. **O STATE_VERSION vai estabilizar?** 3 resets em 30 dias é brutal. Há sinais de que v7 é a versão final?

8. **O miner pode correr SEM S3 upload?** O cap (S3 <= 2x OD) sugere que S3 é importante, mas é obrigatório?

9. **Reddit-only miners (sem X) — qual é o ranking típico deles?** Reddit vale 55% do peso mas sem X (35%), perdem ~35% do score potencial.

10. **O registration cost de SN13 é fixo?** Com 240 miners activos e 256 slots, há slots livres?

---

## 13. Veredicto técnico actualizado

### Anterior: MARGINAL (5/10)
### Actualizado: **MARGINAL-POSITIVO (6/10)**

**Razões para subir de 5 para 6:**

1. **Timing favorável**: O reset v7 de Apr 8 nivelou o campo. Miners novos entram em condições quase iguais a incumbentes. Quanto mais tempo passar, mais difícil será alcançar os incumbentes.

2. **Flow reverting**: O outflow de 30d (-1,794 TAO) está a reverter (7d +75, 1d +303). Capital está a reentrar.

3. **Reddit-only viável**: Com Reddit valendo 55% do peso e o JSON scraper a funcionar sem auth, um miner Reddit-only a $5-9/mês pode ser economicamente viável.

4. **Distribuição plana**: Gini=0.272 é baixo. Top 20 miners estão todos entre $956-$1,029/mês. Não há monopólio.

**Razões para manter MARGINAL:**

1. **70% burn** — O elefante na sala. De $44/dia de emissão, apenas $13.22/dia chega aos miners.

2. **Instabilidade do scoring** — 3 resets em 30 dias. Qualquer acumulação de credibilidade pode ser zerada amanhã.

3. **OD dependency** — Sem OD, score = 0. OD depende da API central. Single point of failure.

4. **Revenue mediana real: $354/mês** — Contra ~$58/mês de custos (cenário B), lucro = ~$296/mês. Contra ~$9/mês (cenário C Reddit-only), lucro = ~$345/mês. É positivo mas não é transformador.

5. **Perguntas sem resposta** — Sem saber a taxa de success de OD jobs e o storage real necessário, o risco é difícil de quantificar.

### Próximos passos recomendados:
1. **Juntar o Discord SN13** e perguntar as 10 perguntas em aberto
2. **Registar um miner em testnet primeiro** para validar setup e OD participation
3. **Se Reddit-only for viável** (confirmar via Discord), setup em Hetzner CX23 a $5/mês
4. **Monitorar 1 semana** antes de escalar

---

*Gerado por análise manual do repo macrocosm-os/data-universe@5672ac6 + taostats API live queries*
