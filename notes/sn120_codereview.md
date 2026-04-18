# SN120 (Affine) Security-Focused Code Review

**Repo**: https://github.com/AffineFoundation/affine-cortex  
**Subnet**: 120  
**Review Date**: 2026-04-11  
**Commit**: HEAD of main branch at clone time  
**Status**: [DOC, possibly outdated — README mentions `affine.git` but actual repo is `affine-cortex`]

---

## Real Miner Task (from code, not README)

Miners fine-tune LLMs for reinforcement learning tasks (program abduction, coding, game-playing, SWE tasks). The actual workflow:

1. Pull an existing frontier model from another miner (`af pull <UID>`)
2. Improve it via RL training locally (offline, no GPU requirement from subnet code itself)
3. Upload improved model to HuggingFace
4. Deploy to Chutes (SN64) for inference load-balancing
5. Commit on-chain (model repo + revision + chute_id)

The **validator backend** evaluates models by calling the Chutes API endpoint and scoring responses against RL environments (containerized via "Affinetes"). Miners do NOT run any daemon — they simply submit improved models.

---

## Minimum Hardware

**No `min_compute.yml` file exists.**

From `docs/VALIDATOR.md`:
- **Validator**: 2 CPU cores, 4GB RAM, 20GB storage, no GPU (all computation on backend)
- **Miner**: No explicit hardware requirement in code. Mining is offline RL training + model upload. GPU needed for training only (not enforced by subnet).

---

## Scoring Function Summary

### 4-Stage Pipeline (`affine/src/scorer/scorer.py`)

```
Stage 1: Data Collection — validate sample completeness (>90% required)
Stage 2: Pareto Filtering — anti-plagiarism, later miners must beat earlier 
         miners by z_score * SE margin (2-10% improvement required)
Stage 3: ELO Rating — geometric mean of env scores, ELO update with K=32/96
Stage 4: Weight Normalization — min 1% threshold, redistribute dust to UID 0
```

### Key: Weight redistribution to UID 0 (`affine/src/scorer/utils.py:243-280`)

```python
def apply_min_threshold(weights, threshold=0.01, redistribute_to_uid_zero=False):
    # Calculate total weight below threshold (excluding uid 0)
    below_threshold_weight = sum(
        w for uid, w in weights.items()
        if uid != 0 and w > 0 and w < threshold
    )
    # Apply threshold and set below-threshold weights to 0
    result = {uid: (w if w >= threshold else 0.0) for uid, w in weights.items()}
    # Add redistributed weight to uid 0
    if below_threshold_weight > 0:
        result[0] = result.get(0, 0.0) + below_threshold_weight
    return result
```

### Key: Burn percentage + System miner redirect (`affine/src/validator/weight_setter.py:20-97`)

```python
async def process_weights(self, api_weights, burn_percentage=0.0):
    for uid_str, weight_data in api_weights.items():
        uid = int(uid_str)
        if uid < 0 or uid > 1000:
            # System miner: accumulate weight for UID 0
            system_weight_total += weight
        else:
            uids.append(uid); weights.append(weight)
    
    # Apply burn: scale all by (1 - burn%), add burn% to extra
    if burn_percentage > 0:
        weights_array *= (1.0 - burn_percentage)
        extra_weight += burn_percentage
    # Add system miner weights to extra
    extra_weight += normalized_system_weight
    # Add extra weight to UID 0
    if extra_weight > 0:
        uids = [0] + uids
        weights_array = np.concatenate([[extra_weight], weights_array])
```

---

## Emission Capture Analysis

### YES — Team captures emission via UID 0 through multiple mechanisms:

**Mechanism 1: `validator_burn_percentage` (configurable, 0-100%)**
- Stored in database, fetched by validator at runtime via API
- Set via admin CLI: `af db set-burn-percentage <value>`
- The burn percentage is applied to ALL miner weights and redirected to UID 0
- **Default is 0.0** but can be changed at any time by whoever controls the backend database
- Code: `affine/src/validator/main.py:248` — `burn_percentage = config.get("validator_burn_percentage", 0.0)`

**Mechanism 2: System miners (UIDs > 1000) → all weight to UID 0**
- Team can register "system miners" via CLI (`af db set-miner --uid 1001 --model "..."`)
- System miners participate in scoring/ELO but ALL their earned weight is redirected to UID 0
- These are team-controlled models that compete with real miners
- Code: `affine/src/validator/weight_setter.py:51-53`

**Mechanism 3: Sub-threshold weight redistribution to UID 0**
- After normalization, miners below 1% threshold have their weight sent to UID 0
- Code: `affine/src/scorer/stage4_weights.py:84-89` with `redistribute_to_uid_zero=True`

**Mechanism 4: UID 0 exemptions (admin/test miner)**
- UID 0 skips template validation checks (`miners_monitor.py:457`)
- UID 0 skips duplicate detection (`miners_monitor.py:444`)
- UID 0 skips model naming requirements (`miners_monitor.py:387`)
- UID 0 has `block=0` hardcoded, giving it maximum Pareto priority (`miners.py:54`)
- UID 0 is not rate-limited (`sampling_scheduler.py:310`)

**Current percentage**: Unknown without database access. The burn percentage is dynamically configurable (0-100%). The system miner weight capture is additive.

---

## Discrepancies: README vs Code

| Issue | README/Docs | Code Reality |
|-------|-------------|--------------|
| Repo URL | `git clone https://github.com/AffineFoundation/affine.git` | Actual repo is `affine-cortex` |
| Validator role | "Fetch weights and set on-chain" | True — but weights come from centralized backend API |
| Burn mechanism | Not mentioned in README | Exists, configurable 0-100% to UID 0 |
| System miners | Not mentioned in README | Can be added by team, weight goes to UID 0 |
| UID 0 privileges | Not documented | Exempt from all validation, priority in Pareto |
| Decentralization | "sybil-proof, decoy-proof, copy-proof" | Scoring runs on centralized backend, validators just relay |

---

## Red Flags

1. **CRITICAL: Centralized scoring backend** — Validators do NOT independently evaluate miners. They fetch pre-computed weights from a single backend API controlled by the team. This means the team has absolute power over weight distribution regardless of what the open-source scoring code says.

2. **CRITICAL: Dynamic burn percentage to UID 0** — The team can set any burn percentage (0-100%) at any time via their database, diverting that fraction of ALL emissions to UID 0 (the validator/owner). No on-chain governance or transparency.

3. **HIGH: System miners as hidden emission capture** — Team-controlled "system miners" (UID > 1000) compete in scoring but all their weight goes to UID 0. The team can add reference models that earn weight and silently capture it.

4. **HIGH: UID 0 has unfair competitive advantages** — Exempt from duplicate detection, template checks, naming requirements, rate limiting, and has Pareto priority (block=0 means it always "registered first").

5. **MEDIUM: Blacklist controlled by team** — Both env var and database blacklist. Team can exclude any miner without on-chain governance.

6. **MEDIUM: Admin commands hidden behind env var** — `AFFINE_SHOW_ADMIN_COMMANDS=true` reveals database manipulation commands not visible to regular users.

7. **LOW: Sub-threshold weight always goes to UID 0** — Small miners' weights are not burned/distributed fairly but accumulated to the owner UID.

---

## VERDICT

```
team_burn_capture: YES
hardware_real: No GPU needed for validator (2 CPU/4GB RAM); miner hardware is offline RL training (not enforced)
red_flags_count: 7
```

**Summary**: Affine SN120 has a fundamentally centralized architecture where a backend API controlled by the team dictates all weight distributions. Multiple mechanisms (burn percentage, system miners, UID 0 exemptions, sub-threshold redistribution) funnel emission to UID 0. The burn percentage is dynamically adjustable with no on-chain governance. While the scoring algorithm itself (ELO + Pareto) is well-designed and the anti-copy mechanisms are sophisticated, the centralized backend makes all of this irrelevant from a trust perspective — the team can override any outcome.
