# VERDICT SUMMARY — Bittensor Subnet Code Reviews
**Date**: 2026-04-11 | **Scope**: Read-only static analysis

---

## Cross-Subnet Comparison

| netuid | name | tem_burn_capture | burn_% | hardware_real | red_flags | severity |
|--------|------|-----------------|--------|---------------|-----------|----------|
| 5 | Hone (OpenKaito) | **YES** | **95%** to UID 251 | Miner: VPS; Validator: 8x H200 (~$200K+) | 7 | CRITICAL |
| 17 | 404—GEN | **YES** | **100%** to UID 199 | Subnet DEAD (axon commented out) | 8 | EXTREME |
| 51 | Celium (lium.io) | **YES** | **91%** to 10 UIDs [187-196] | Miner: NVIDIA GPU (H100/H200/4090); Executor: 100GB+8GB RAM | 7 | CRITICAL |
| 93 | Bitcast | NO (dormant) | 0% (valve exists for UID 106) | Miner: 2 CPU / 4GB RAM (token server) | 7 | HIGH |
| 120 | Affine | **YES** | Variable (DB-controlled) to UID 0 | Miner: GPU (inference); Validator: centralized backend | 7 | CRITICAL |

---

## Burn Capture Details

### SN5 — Hone / OpenKaito
- `BURN_UID = 251`, `BURN_PERCENTAGE = 0.95` hardcoded in `validator/scoring.py`
- Only 5% reaches miners, split among top 5 with exponential decay
- UID 251 is almost certainly team-controlled (same UID used as default validator in tooling)
- ARC-AGI-2 benchmark SOTA is ~5% accuracy; 20% floor means burn fires constantly

### SN17 — 404—GEN
- Commit `5e9dbf5` replaced `_set_weights()` with `_burn_all()`: `uids=[199], weights=[1.0]`
- **100% of emission to single UID 199**. Subnet functionally dead (axon commented out).
- Auto-updater runs every 30min — team can change this at will without notice.

### SN51 — Celium / lium.io
- `TOTAL_BURN_EMISSION = 0.91`, `NEW_BURNERS = [187..196]` (10 hardcoded UIDs)
- Miners compete for ~9% of emission only
- Centralized backend at `lium.io/api` controls rental verification

### SN93 — Bitcast
- `SUBNET_TREASURY_PERCENTAGE = 0` currently, but mechanism routes to UID 106
- Real emission control is via centralized briefs API (`bitcast-api.bitcast.network`)
- Auto-update `git reset --hard` every 10-15 min = silent activation risk

### SN120 — Affine
- `validator_burn_percentage` stored in team-controlled database (not in code)
- "System miners" (UID > 1000) redirect earned weight to UID 0
- Sub-threshold weight redistribution also goes to UID 0
- UID 0 exempt from all validation checks

---

## Common Red Flags Across All 5 Subnets

| Pattern | SN5 | SN17 | SN51 | SN93 | SN120 |
|---------|-----|------|------|------|-------|
| Hardcoded burn/team UIDs | Y | Y | Y | dormant | Y |
| Auto-updater (silent code push) | Y | Y | ? | Y | ? |
| Centralized backend dependency | Y | Y | Y | Y | Y |
| Validator fetches weights from API | - | - | - | - | Y |
| Emission % controllable without governance | Y | Y | N | Y | Y |

---

## Recommendation Matrix

| netuid | Mine? | Why / Why not |
|--------|-------|---------------|
| 5 | **NO** | 95% burn + $200K validator barrier = miners get crumbs |
| 17 | **NO** | Subnet is dead. 100% burn to single UID. No work accepted. |
| 51 | **MAYBE** | 91% burn is brutal, but real GPU demand exists. Only if you have H100/H200 AND accept ~9% emission share. flow_7d is strong (+8,674 τ). |
| 93 | **MAYBE** | No burn today, minimal hardware (2CPU/4GB). But YouTube token model is fragile, and dormant treasury valve is a risk. flow_7d is weak (+422 τ). |
| 120 | **CAUTION** | Variable burn % controlled by team DB. Architecture is centralized. flow_7d decent (+2,452 τ) but only 6 miners active. |

---

## TL;DR

**4 out of 5 subnets have active or dormant emission capture mechanisms.** The pattern is consistent: team controls a supermajority of emission via hardcoded UIDs, centralized backends, or database-controlled percentages. Only SN93 has no active burn, but the valve exists.

**SN17 is the worst offender** — 100% capture, subnet functionally dead, still receiving emission from the network.

SN93 is the lowest-risk entry (cheap, low hardware, no active burn) but also lowest reward. SN51 has the strongest fundamentals (real GPU demand, strong inflows) but 91% burn means you're fighting for scraps unless you bring serious hardware.
