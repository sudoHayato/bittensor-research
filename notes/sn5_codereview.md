# SN5 (Hone) Security-Focused Code Review

**Repo**: https://github.com/manifold-inc/hone  
**Team**: Manifold Inc (formerly OpenKaito, transferred mid-2025)  
**Claimed Purpose**: Decentralized ARC-AGI-2 reasoning benchmarking  
**Review Date**: 2026-04-11  
**Status**: [DOC, possibly outdated] — README appears current with code

---

## Real Miner Task (from code, not README)

Miners run a minimal HTTP server exposing `/info` endpoint that returns a pointer (git repo URL + branch + commit) to their ARC-AGI-2 solver. The heavy computation is NOT done by the miner — it is done by the **Sandbox Runner**, a centralized GPU execution service operated by validators.

Miners do NOT:
- Run inference themselves
- Need GPUs
- Execute any model locally

Miners DO:
- Maintain a public HTTP server (FastAPI on port 8091)
- Point to a git repository containing their solver code
- Register on-chain with their IP

The actual "work" (cloning repo, building Docker image, running prep/inference phases on H200 GPUs) is done entirely by the Sandbox Runner, which is controlled by validators.

---

## Minimum Hardware

**No min_compute.yml exists in this repo.**

From README:
- **Miner**: "Minimal compute" — public IP, open port 8091. No GPU needed.
- **Validator**: 4+ CPU cores, 8GB+ RAM, 20GB disk, reliable network
- **Sandbox Runner** (validator-operated): 8x H200 GPUs (referenced in architecture)

The miner hardware requirement is essentially a VPS with a public IP. The real compute cost is borne by the solver development (training/testing elsewhere) and by the validator's sandbox runner infrastructure.

---

## Scoring Function Summary

From `validator/scoring.py`:

```python
# Score calculation (lines 89-99):
avg_exact_match_rate = stats["exact_match_rate_sum"] / stats["successful_responses"]
if avg_exact_match_rate < min_accuracy_floor:  # default 20%
    continue  # filtered out
qualifying_miners.append((hotkey, stats["uid"], avg_exact_match_rate))

# Weight distribution (lines 161-168):
decay_factor = 0.8
for rank in range(len(top_miners)):
    exponential_weights.append(math.exp(-decay_factor * rank))
total_weight = sum(exponential_weights)
normalized_weights = [w / total_weight for w in exponential_weights]
```

Weight setting (lines 211-260):
```python
BURN_UID = int(os.getenv("BURN_UID", "251"))
BURN_PERCENTAGE = float(os.getenv("BURN_PERCENTAGE", "0.95"))
MINER_PERCENTAGE = 1.0 - BURN_PERCENTAGE  # 0.05

# If miners qualify: 95% to BURN_UID, 5% split among top 5
all_weights[BURN_UID] = BURN_PERCENTAGE
for uid, weight in scores.items():
    normalized_miner_weight = (weight / miner_weight_sum) * MINER_PERCENTAGE
    all_weights[uid] = normalized_miner_weight

# If NO miners qualify: 100% to BURN_UID
all_weights[BURN_UID] = 1.0
```

---

## Emission Capture Analysis

### CRITICAL FINDING: 95% emission capture via "BURN_UID"

**Code location**: `validator/scoring.py` lines 211-213

```python
BURN_UID = int(os.getenv("BURN_UID", "251"))
BURN_PERCENTAGE = float(os.getenv("BURN_PERCENTAGE", "0.95"))
```

**What this means**:
- 95% of ALL emissions from SN5 are directed to UID 251
- Only 5% goes to actual miners (split among top 5 with exponential decay)
- If no miners meet the 20% accuracy floor, 100% goes to UID 251

**Is UID 251 a real burn?**

In Bittensor, there is NO native "burn via UID" mechanism. A UID is a registered hotkey on the subnet. Sending weight to a UID means that UID **receives emissions**. The only way this could be a true "burn" is if:
1. UID 251 is the subnet creator/owner hotkey AND creator burn is enabled on-chain
2. UID 251 is a provably unowned address (no private key)

Based on the code, UID 251 is also used as the **default validator UID** in the telemetry dashboard (`telemetry/dashboard/app.py` line 846: `value=251`), strongly suggesting UID 251 is the team's own validator. The `check_weights.py` tool also uses `--uid 251` as the example validator UID.

**If UID 251 is NOT a provable burn address, the team captures 95% of subnet emissions.**

Even if creator burn IS enabled, the team controls whether to keep it enabled. This is a configurable env var — validators could theoretically change it, but the default config shipped in the repo directs 95% to the team's UID.

### Emission distribution summary:
| Recipient | Percentage | Notes |
|-----------|-----------|-------|
| UID 251 ("burn") | 95% | Team-controlled UID, likely validator/owner |
| Top 5 miners | 5% total | Split with exponential decay (0.8 factor) |
| Miner #1 | ~2.4% | Best performer |
| Miner #2 | ~1.8% | |
| Miner #3 | ~1.3% | |
| Miner #4 | ~0.8% | |
| Miner #5 | ~0.5% | |

---

## Discrepancies README vs Code

1. **BURN_PERCENTAGE not in .env.example**: The README shows `BURN_PERCENTAGE=0.95` as a config option, but the `.env.example` file does NOT include this variable. Only `BURN_UID=251` is present. The 95% is hardcoded as the default in `scoring.py` and not transparently surfaced in the example config.

2. **"burn" terminology is misleading**: README says "No qualifiers: If no miners meet the floor, 100% is burned" — but "burned" here means "sent to UID 251" which is likely a team-controlled address.

3. **README mentions "Top 5 miners above floor receive rewards"** — technically true, but omits that they only receive 5% of total emissions.

4. **Validator hardware**: README says "4+ CPU cores, 8GB RAM" for validator, but the Sandbox Runner (which validators must operate) requires 8x H200 GPUs — a massive infrastructure requirement that makes validation extremely exclusive/centralized.

---

## Red Flags

### 1. CRITICAL: 95% Emission Capture (HIGH)
The default configuration sends 95% of all subnet emissions to a single UID (251) that appears to be team-controlled. This is presented as "burn" but there's no on-chain proof this actually burns tokens.

### 2. CRITICAL: Centralized Execution Infrastructure (HIGH)
The Sandbox Runner is a centralized service. Validators must operate expensive GPU infrastructure (8x H200). This creates a massive barrier to entry for validators and concentrates validation power in the hands of those who can afford ~$200K+ in GPU hardware.

### 3. HIGH: Only Top 5 Miners Rewarded (MEDIUM-HIGH)
Only 5 miners out of potentially hundreds registered receive any reward, and even then only 5% of emissions total. The minimum 20% accuracy floor on ARC-AGI-2 (when current best AI scores ~5%) means effectively NO miners may qualify, sending 100% to the burn UID.

### 4. HIGH: Configurable Burn Parameters (MEDIUM)
`BURN_UID` and `BURN_PERCENTAGE` are env vars — the team could silently change which UID receives emissions or increase the percentage at any time via validator config updates.

### 5. MEDIUM: Auto-updater (MEDIUM)
Validator includes an auto-update mechanism (`validator/autoupdate/`) that pulls and restarts on new commits from the repo. This means the team can push code changes that all validators automatically deploy without review — including changes to emission distribution.

### 6. MEDIUM: No Decentralized Scoring Verification
Scoring relies entirely on the Sandbox Runner's reported `exact_match_rate`. There's no mechanism for miners or third parties to verify that their solutions were fairly evaluated.

### 7. LOW: Telemetry Collection
Validator publishes heartbeat telemetry to a centralized endpoint, which could be used to track validator activity.

---

## VERDICT

```
team_burn_capture: YES — 95% of emissions directed to UID 251 (likely team-controlled)
hardware_real: Miner=VPS only (no GPU), Validator=8xH200 GPUs ($200K+), extremely centralized
red_flags_count: 7
```

**Summary**: This subnet directs 95% of emissions to a single "burn" UID that circumstantial evidence suggests is team-controlled (same UID used as default validator in tooling). Only 5% reaches miners, split among just 5 participants. The 20% accuracy floor on ARC-AGI-2 (a benchmark where SOTA is ~5%) means the "burn" condition (100% to UID 251) may be triggered most of the time. Combined with centralized validator infrastructure requirements and auto-update, this represents significant centralization and potential emission extraction by the team.
