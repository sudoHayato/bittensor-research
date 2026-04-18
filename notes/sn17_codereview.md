# SN17 (404-GEN / three-gen-subnet) — Security Code Review

**Repo**: https://github.com/404-Repo/three-gen-subnet  
**Commit reviewed**: `5e9dbf5` ("100% emission burn (#119)")  
**Date**: 2026-04-11  

---

## Real Miner Task (from code, not README)

Miners generate **3D Gaussian Splat assets** (PLY files compressed via SPZ) from text or image prompts. The workflow:
1. Miner pulls a task (text prompt or image URL) from a validator's axon
2. Miner calls a local generation endpoint (`/generate/`) that runs DreamGaussian (Gaussian Splatting + diffusion guidance)
3. Miner submits the SPZ-compressed PLY result back to the validator
4. Validator scores it via a separate validation service (aesthetic quality, prompt alignment, SSIM, LPIPS)

The generation code uses MVDream/ImageDream for multi-view diffusion and trains a 3D Gaussian Splatting model per prompt.

---

## Minimum Hardware

From `docs/running_validator.md`:
- **Validator GPU**: RTX 6000 Ada (48 GB VRAM minimum), or 2x4090
- **Miner GPU**: Not explicitly documented in a min_compute file. From the generation code (`generation/serve.py` + DreamGaussian configs), miners need a CUDA GPU capable of running multi-view diffusion + Gaussian splatting training. Realistically **RTX 3090/4090 or higher** (24+ GB VRAM).
- **OS**: Ubuntu 22.04 LTS with NVIDIA drivers and CUDA

No `min_compute.yml` file exists in the repo.

---

## Scoring Function Summary

### Validation Score (validation_service.py)
Validator sends the generated SPZ to an external validation endpoint that returns:
```python
class ValidationResponse(BaseModel):
    score: float       # 0.0 to 1.0 (combined quality metric)
    iqa: float         # Aesthetic Predictor score
    alignment_score: float  # prompt vs rendered images alignment
    ssim: float        # Structure similarity
    lpips: float       # Perceptive similarity
```
Minimum threshold: `quality_threshold = 0.6` (configurable).

### Reward Calculation (miner_data.py)
```python
def calculate_reward(self, current_time, rating, observation_window=4*60*60):
    self._expire_observations(current_time, observation_window)
    return len(self.observations) * rating
```
Reward = (number of successful tasks in last 4 hours) * (Glicko2 duel rating)

### Weight Setting (_set_weights, CURRENTLY DISABLED)
```python
reward_mask = rewards > 5.0
processed_uids = np.nonzero(reward_mask)[0]
# ... sigmoid-based probability distribution across qualifying miners
processed_weights = final_probs / np.sum(final_probs)
```

---

## Emission Capture Analysis

### CRITICAL FINDING: 100% Emission Burn to UID 199

**File**: `neurons/validator/validator.py`, lines 482-500  
**Commit**: `5e9dbf5` (Nov 17, 2025) — titled "100% emission burn (#119)"

```python
def _burn_all(self) -> None:
    if not self._is_enough_stake_to_set_weights():
        return
    if self.metagraph.last_update[self.uid] + self.config.neuron.weight_set_interval > self.metagraph.block:
        return
    result, msg = self.subtensor.set_weights(
        wallet=self.wallet,
        netuid=self.config.netuid,
        uids=[199,],
        weights=[1.0],
        wait_for_finalization=False,
        wait_for_inclusion=False,
    )
```

**In the `run()` loop (line 463)**: `self._burn_all()` is called instead of `self._set_weights()`.

This means **ALL validators running this code direct 100% of their weight to UID 199**. The legitimate `_set_weights()` method still exists in the code but is never called.

Additionally, the axon is commented out (lines 440-446), meaning miners cannot submit tasks to validators running this code. The subnet is effectively **paused/dead** while still burning emissions to UID 199.

### Owner Hotkey

**File**: `neurons/common/owner.py`
```python
HOTKEY = "5E7eSeRr2aHzCV7SkY4a2Pi5NXHrU4anZz3phEQgn4HCen2B"
```
Used for: prioritizing the owner's validator for task queries (miner queries owner every 5th turn), and allowing the owner to bypass stake requirements for version checks.

---

## Discrepancies README vs Code

| README says | Code actually does |
|---|---|
| "Democratize 3D Content Creation" | Subnet is paused; 100% emission directed to UID 199 |
| Implies active miner/validator loop | Axon is commented out; validators just burn weights |
| Links to validator setup guide | Setup guide is valid but the running code won't serve tasks |
| Mentions duel rating system | Duels disabled by default (`--duels.disabled` = True) AND ratings not saved |
| README does not mention the emission burn | Code explicitly burns 100% to a single UID |

---

## Red Flags

1. **100% emission capture to hardcoded UID 199** — All validators running this code direct all subnet emissions to a single UID. This is the most extreme form of emission capture possible.

2. **Subnet is functionally paused** — The axon serving is commented out, telemetry is disabled, no miners can submit work. Yet emissions continue flowing to UID 199.

3. **Hardcoded owner hotkey** (`5E7eSeRr2aHzCV7SkY4a2Pi5NXHrU4anZz3phEQgn4HCen2B`) with special privileges in both miner and validator code.

4. **Auto-updater** — Validators auto-update from the repo every 30 minutes. This means the team can push code changes (like `_burn_all`) that immediately take effect on all validators without operator consent.

5. **Centralized validation** — Validation relies on an external HTTP service. The validator does not verify quality locally; it trusts an endpoint. This endpoint could be manipulated to favor specific miners.

6. **Centralized prompt generation** — Prompts fetched from a hardcoded IP (`http://44.219.222.104:9100`). The team controls what prompts miners receive.

7. **Default netuid mismatch** — Config defaults to `--netuid 29` (not 17), suggesting possible testnet/mainnet confusion or migration.

8. **No transparency about burn** — The PR title "100% emission burn" was merged openly, but there is no explanation in the README or documentation about why this exists or when it will end.

---

## VERDICT

```
team_burn_capture: YES — 100% of emissions directed to hardcoded UID 199 via _burn_all()
hardware_real: RTX 6000 Ada / 48GB VRAM for validators; ~24GB GPU for miners (legitimate when active)
red_flags_count: 8
```

**Severity: EXTREME** — This is not a subtle emission tax. The subnet is completely paused with all emissions funneled to a single UID. Every validator running the official code is a weight-setting puppet for UID 199.
