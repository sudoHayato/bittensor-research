# SN51 (Lium / Compute Subnet) -- Code Review

**Repo**: https://github.com/Datura-ai/lium-io  
**Date**: 2026-04-11  
**Scope**: Read-only static analysis of `main` branch  

---

## 1. Real Miner Task (from code, not README)

The miner's actual job is to **provide GPU-equipped machines as rentable compute nodes**.

Architecture is three-tier:

- **Miner** (`neurons/miners/`) -- A lightweight FastAPI process running on a CPU server. It registers on Bittensor (netuid 51), announces its axon, tracks validators, and exposes a WebSocket/REST interface so validators can discover and connect to executors.
- **Executor** (`neurons/executor/`) -- A FastAPI process running on each GPU machine. It runs inside Docker with NVIDIA GPU passthrough. Provides SSH access, runs Docker-in-Docker (DinD) containers for tenant isolation (Sysbox runtime), and responds to validator challenges.
- **Validator** (`neurons/validators/`) -- Periodically SSHs into every executor, runs a 21-step validation pipeline, scrapes hardware specs (GPU model, VRAM, driver version), runs a **hashcat-based proof-of-work** challenge (`miner_jobs/score.py`), checks port connectivity, GPU fingerprinting, NVML library digest verification, collateral, and TDX attestation (optional).

**The synthetic challenge** is hashcat password cracking. The validator generates randomized hashcat jobs per GPU, sends them to the executor, and verifies the answers match. This proves the GPU is real and available. The scoring script (`miner_jobs/score.py`) runs `hashcat` with `--attack-mode 3` (brute-force mask attack) on each GPU device in parallel.

---

## 2. Minimum Hardware

**No `min_compute.yml` file exists in the repo.** Hardware requirements are inferred from code and READMEs:

### Miner (central server)
- CPU: 4 cores
- RAM: 8 GB
- Storage: 50 GB
- No GPU needed

### Executor (GPU machine)
- Must have NVIDIA GPU(s) from the supported list (see `GPU_MODEL_RATES` in `services/const.py`)
- Docker with NVIDIA Container Toolkit
- Sysbox runtime strongly recommended (penalty without it)
- Min 100 GB storage (`STORAGE_MIN_AVAILABLE_GB = 100`)
- Min 8 GB RAM (`MEMORY_MIN_TEST_GB = 8`)
- Min 50 Mbps download (`NETWORK_MIN_DOWNLOAD_SPEED_MBPS = 50.0`)
- Min 3 open ports (`MIN_PORT_COUNT = 3`)
- GPU utilization must be below 5% when idle (`GPU_UTILIZATION_LIMIT = 5`)
- Max 14 GPUs per executor (`MAX_GPU_COUNT = 14`)

### Validator
- CPU: 4 cores
- RAM: 8 GB
- Redis, PostgreSQL (via docker-compose)
- No GPU needed

### Supported GPUs (from `GPU_MODEL_RATES`)
Top-tier (highest emission rates): H200 (0.56), H200 NVL (0.49), H100 SXM (0.10), B300 (0.05), B200 (0.05), RTX 4090 (0.05), A100 SXM (0.05)

---

## 3. Scoring Function Summary

### 3a. Validation Pipeline (21 checks, `pipeline_factory.py`)

```
StartGPUMonitorCheck -> UploadFilesCheck -> MachineSpecScrapeCheck ->
GpuCountCheck -> GpuModelValidCheck -> NvmlDigestCheck ->
SpecChangeCheck -> GpuFingerprintCheck -> BannedGpuCheck ->
DuplicateExecutorCheck -> CollateralCheck -> PortConnectivityCheck ->
PortCountCheck -> TenantEnforcementCheck -> GpuUsageCheck ->
VerifyXCheck -> TdxHostCheck -> CapabilityCheck ->
RentalVerificationCheck -> ScoreCheck -> FinalizeCheck
```

Any `fatal=True` check failure zeroes the score.

### 3b. Score Calculation (`score_calculator.py`)

```python
job_score = 1.0
actual_score = 1.0
# Zero if rental verification fails (unless SKIP_RENTAL_VERIFICATION)
# Zero if GPU price > base_price * MACHINE_MAX_PRICE_RATE (2.0x)
# Zero if collateral not deposited (when ENABLE_NO_COLLATERAL=False)
# Zero if old contract version (SCORE_PORTION_FOR_OLD_CONTRACT = 0)
```

### 3c. Mining Score Formula (`incentive/default.py`)

```
mining_score = score * gpu_portion * gpu_count / total_gpu_count
             * sysbox_multiplier * uptime_multiplier
```

Where:
- `gpu_portion` = per-GPU-type emission share from Redis
- `sysbox_multiplier` = 1 if Sysbox runtime, else (1 - PORTION_FOR_SYSBOX)
  - For rented after cutoff (2026-04-03): PORTION_FOR_SYSBOX_RENTED = 1.0 (full penalty = zero score)
  - For unrented: PORTION_FOR_SYSBOX_UNRENTED = 1.0 (full penalty = zero score)
- `uptime_multiplier` = ramps from 0 to 1 over 14 days if no collateral

### 3d. Incentive Formula (final weight = who gets TAO)

Two algorithms, selected via config (default: `rental_price`):

**Default algorithm**: `incentive = mining_share * mining_score / total_mining_score`  
where `mining_share = 1 - TOTAL_BURN_EMISSION = 1 - 0.91 = 0.09`

**Rental Price algorithm** (active): Three pools:
1. **Burn pool** (up to 91%): Distributed to hardcoded burner UIDs
2. **Mining pool** (~9%): For rented GPUs, uses default formula
3. **Rental pool** (dynamic, carved from burn): For unrented eligible GPUs, proportional to `gpu_count * effective_rate / total_rental_cost`

`rental_share = rental_cost_per_epoch / FIXED_RATIO(0.41) / epoch_subnet_emission`

### 3e. Burn Distribution (`burn_service.py`)

```python
BURNERS = [4, 206, 207, 208]           # old logic
NEW_BURNERS = [187..196]               # new logic (10 UIDs)
TOTAL_BURN_EMISSION = 0.91             # 91% of emission to burners
ENABLE_NEW_BURN_LOGIC = True           # equal split among NEW_BURNERS
```

New logic: `burn_score_per_burner = burn_share / len(NEW_BURNERS)`

---

## 4. Discrepancies: README vs Code

| Claim in README | Reality in Code |
|---|---|
| "scored based on GPU type, bandwidth, and overall GPU performance" | Bandwidth has minimal weight (5% upload + 5% download). Main scoring is hashcat PoW + GPU model rate. Uptime and Sysbox matter more. |
| Links to `Datura-ai/compute-subnet` for installation | Repo is now `Datura-ai/lium-io`. README still links old repo name for `install_miner_on_ubuntu.sh`. |
| "fair compensation based on GPU contributions" | 91% of emission goes to 10 hardcoded burner UIDs. Actual GPU miners split the remaining ~9% (plus dynamic rental share). |
| No mention of collateral/staking | Miners must deposit TAO collateral per executor via Ethereum smart contract. Without it, scoring penalties apply. |
| No mention of Sysbox requirement | Without Sysbox runtime: unrented GPUs get 0 score, rented GPUs after 2026-04-03 get 0 score. Effectively mandatory. |
| Miner README says "compatible GPUs" links to `compute-subnet` repo | Should point to own repo's `const.py`. |

---

## 5. Red Flags

### CRITICAL: 91% Emission to Hardcoded Burner UIDs

```python
TOTAL_BURN_EMISSION = 0.91
NEW_BURNERS = [187, 188, 189, 190, 191, 192, 193, 194, 195, 196]
ENABLE_NEW_BURN_LOGIC = True
```

**91% of all subnet emission is distributed equally among 10 hardcoded miner UIDs.** These are presumably team-controlled "burner" nodes. Only 9% (minus any rental share carved from the burn pool) goes to actual GPU-providing miners. This is the single largest centralization risk in the subnet. The burn UIDs are set in code with no on-chain governance.

### Hardcoded GPU Pricing and Rates

All GPU model rates (`GPU_MODEL_RATES`), machine prices (`MACHINE_PRICES`), required deposit amounts (`REQUIRED_DEPOSIT_AMOUNT`), and rental incentive caps (`MAX_UNRENTED_GPUS_BY_TYPE`) are hardcoded in Python source. Changes require a code deploy by the team. There is no community input mechanism.

### Centralized Backend Dependency

- Validators fetch rented executor data from `https://lium.io/api` (a centralized backend)
- Banned GPU lists come from the backend API
- Rental verification depends on backend state
- If the backend is down, validation skips the iteration entirely:
  ```python
  if rented_executors is None:
      logger.error("Failed to fetch rented executors, skipping this iteration")
      return
  ```

### NVML Digest Whitelist

`LIB_NVIDIA_ML_DIGESTS` contains ~60+ whitelisted NVIDIA driver version hashes. This is an anti-spoofing measure but also means miners MUST run one of these exact driver versions. New driver releases require a code update from the team.

### Sysbox Now Effectively Mandatory

As of the `SYSBOX_RENTED_CUTOFF` (2026-04-03), both rented and unrented executors without Sysbox get `sysbox_multiplier = 0` (for unrented) or `sysbox_multiplier = 0` (for rented after cutoff). This was recently tightened -- `PORTION_FOR_SYSBOX_RENTED = 1.0` means 100% penalty.

### Collateral via Ethereum Smart Contract

Miners must interact with a specific Ethereum smart contract (`0x8A4023FdD1...`) on Subtensor EVM to deposit collateral. This adds complexity and potential loss risk. The `COLLATERAL_EXCLUDED_GPU_TYPES` only exempts "NVIDIA B200" -- all other GPU types require collateral.

### GPU Count Custom Prices Filter

Only `gpu_count=1` and `gpu_count=8` are eligible for rental incentive by default:
```python
GPU_COUNT_CUSTOM_PRICES = {"*": {"*": 0, "1": D, "8": D}, ...}
```
Miners with 2, 4, or 6 GPUs get `hourly_rate = 0` for the rental pool -- effectively excluded from unrented rewards.

### MAX_UNRENTED_GPUS Caps Set to 0 for Many GPUs

Most GPU types have `MAX_UNRENTED_GPUS = 0`, meaning they get zero rental incentive when unrented. Only H100, H200, B200, RTX 4090, A100, RTX A6000, and RTX 3090 get a nonzero cap (8 each). All others (including B300, RTX 5090, L4, L40S, etc.) are set to 0.

### No Rate Limiting on Validator Connections to Miners

The validator connects to all miners in parallel with no concurrency limit beyond the asyncio timeout (15 minutes). Large networks could overwhelm miner/executor resources.

### Debug/Skip Flags in Production Config

Several bypass flags exist in the production settings class:
- `SKIP_RENTAL_VERIFICATION` (default False)
- `DEBUG_SKIP_STAKE_CHECKS`
- `DEBUG_USE_LOCAL_MINER`
These are env-var controlled and could be exploited if a validator's environment is compromised.

---

## Summary

SN51 is a well-structured GPU rental marketplace with thorough hardware validation (21-check pipeline, hashcat PoW, NVML fingerprinting, TDX attestation). However, the **91% burn emission to 10 team-controlled UIDs** is the dominant economic feature -- actual miners compete for only ~9% of emission. Combined with centralized backend dependencies, hardcoded pricing, and mandatory collateral, the subnet has significant centralization characteristics that should be weighed carefully before committing capital.
