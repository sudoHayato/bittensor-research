# SN75 (Hippius) -- Code Review
**Repo**: https://github.com/thenervelab/thebrain
**Date**: 2026-04-11
**Scope**: Read-only static analysis + on-chain/off-chain cross-check

## 1. Real Miner Task (from code, not README)

Hippius is a **decentralized storage infrastructure** subnet. Unlike typical Python-based Bittensor subnets, it runs its own **Substrate blockchain** (custom chain with pallets) that acts as the scoring/ranking layer. Miners run IPFS-backed storage nodes and are scored on:

- **Bandwidth served** (70% of node quality score) -- log2 concave curve
- **Shard data stored** (30% of node quality score) -- log2 concave curve
- **Uptime** (multiplier on total score, permille-based)
- **Penalties** subtracted for strikes and data integrity failures

Miner types: StorageMiner, StorageS3, ComputeMiner, GpuMiner. Only StorageMiner currently receives non-zero Bittensor weights. Compute and GPU ranking instances are commented out in the submission code (`pallets/bittensor/src/lib.rs` lines 946-969).

Miners register on the Hippius chain, run IPFS nodes, and submit hardware metrics via offchain workers. Validators periodically report quality metrics (`NodeQuality` struct with `shard_data_bytes`, `bandwidth_bytes`, `uptime_permille`, `strikes`, `integrity_fails`) and compute family-aggregated weights that are submitted to Bittensor SN75.

There is NO traditional Python miner.py/validator.py pattern. This is a **custom Substrate chain** that runs its own validators and miners, with a bridge to Bittensor for weight submission.

## 2. Minimum Hardware

No `min_compute.yml` exists. From `minner-setup.md` and code analysis:

- Rust toolchain (nightly) required to build the Substrate node binary (`hippius`)
- IPFS node required for storage miners
- Storage: scalable (tracked in bytes, score uses log2 so initial GB matter most)
- Network: bandwidth-heavy (70% of score); good upload bandwidth critical
- Offline detection: StorageMiner gets 3,000 blocks (~5 hours) grace; others get 300 blocks (~30 min)
- New miners face 80% weight reduction for first 1,000 blocks (~100 minutes) on non-storage types
- No specific CPU/RAM/disk minimums documented in the repository

External docs (docs.hippius.com) reference: 4 cores, 16 GB RAM, 2 TB+ ZFS storage, public IPv4, Ubuntu 24.04.

## 3. Scoring Function Summary

**Layer 1 -- Node Quality (arion-pallet):**
```rust
bw_score  = log2(bandwidth_bytes + 1)
st_score  = log2(shard_data_bytes + 1)
raw_score = (bw_score * 700 + st_score * 300) * NodeScoreScale / (1000 * 127)
score     = raw_score * uptime_permille / 1000
penalty   = strikes * 50 + integrity_fails * 100
node_weight = clamp(score - penalty, 0, MaxNodeWeight=50000)
```

**Layer 2 -- Family Aggregation (arion-pallet):**
```
Top 10 children sorted desc, rank decay FamilyRankDecayPermille=800 (0.8x each)
family_raw = w[0] + w[1]*0.8 + w[2]*0.64 + ...
smoothed   = prev * 0.7 + raw * 0.3  (EMA, alpha=300 permille)
clamped    = prev +/- MaxFamilyWeightDeltaPerBucket=100 per update
```

**Layer 3 -- Pool Economics (execution-unit/weight_calculation.rs):**
```rust
cost       = total_network_storage_gb * price_per_gb_token
emissions  = alpha_price_token * EMISSION_PERIOD(50)
burn_pct   = max(0, emissions - cost) / emissions  // default 0.2 if emissions=0
uid_zero_pool = 65535 * burn_pct     // goes to UID 0 (owner)
miners_pool   = 65535 - uid_zero_pool
```

**Layer 4 -- Per-miner final weight (bittensor pallet):**
```rust
miner_weight = (family_arion_weight / total_arion_weight) * miners_pool
final_uid_zero = min(uid_zero_weight, 65535 - sum_all_miner_weights)
```

## 4. ON-CHAIN Signals
- Gini: 0.99
- 159/256 miners active (emission > 0)
- top1: 246.06 TAO, top10 avg: 29.49 TAO, median: 0.004234 TAO
- Distribution shape: **Extreme head-heavy**. UID 0 (subnet owner hotkey 5G1Qj93Fy22grpiGKq6BEvqqmS2HVRs3jaEdMhq9absQzs6g) captures 246 TAO while #2 gets 23.5 TAO. After top 10 (~1.1 TAO), emissions cliff to ~0.01 TAO. Long tail of ~97 miners at near-zero. 77/256 UIDs have zero emission.
- UID 0 hotkey **matches subnet owner_hotkey** (confirmed: 5G1Qj93Fy22grpiGKq6BEvqqmS2HVRs3jaEdMhq9absQzs6g)
- UID 0 coldkey: 5DAQpczEK4vzBn1waHkC4BZGqGPZ1dwPxKVsj36JDofHAw3a (same as subnet owner coldkey)
- UID 0 incentive: 0.99290 (99.29% of all incentive)
- On-chain `incentive_burn`: 0.99290 -- confirming the dynamic burn mechanism routes ~99.3% of weight to UID 0
- Subnet registered: 2025-03-11 (13 months old)
- Active keys: 256/256 (full), validators: 11, active_miners: ~120
- Subtoken enabled, alpha-based emissions (projected_emission: 0 in TAO terms)

## 5. OFF-CHAIN Signals
- Leaderboard URL: None found in codebase or external searches
- External dashboard: `console.hippius.com` (file storage UI, requires login, not a miner leaderboard)
- Community forum: `community.hippius.com` (announcements, not stats)
- Docs: `docs.hippius.com` (miner setup, CLI, blockchain API docs)
- External miner count: Marketing materials claim "400+ miners running, 500+ nodes". Taostats: 256 UIDs, 159 with emission > 0, ~120 active miners.
- Discrepancy: "on-chain 159 miners with emission > 0 (of 256 UIDs), external marketing claims 400+ miners" -- the 400+ figure likely counts Hippius-chain registered nodes (separate registry), not Bittensor UIDs
- wandb/HF links: None found
- No external scoring API or centralized backend detected in codebase (scoring is all on-chain via Substrate pallets)

## 6. Emission Capture Analysis
- Burn capture: **YES -- CRITICAL**
- Mechanism: Dynamic burn percentage computed in `pool_context()` at `pallets/execution-unit/src/weight_calculation.rs` lines 32-80
- Formula: `burn_pct = max(0, emissions - cost) / emissions` where `emissions = alpha_price * 50` and `cost = total_storage_gb * price_per_gb`
- When emissions >> cost (low network utilization relative to token price), burn_pct approaches 1.0, routing nearly all weight to UID 0
- Current state: **99.29% of incentive goes to UID 0** (subnet owner's hotkey)
- UID 0 receives `uid_zero_pool = 65535 * burn_pct` weight; all miners share the remainder (`miners_pool = 65535 - uid_zero_pool`)
- Default fallback: if `emissions == 0`, `burn_percentage = 0.2` (20% minimum floor for UID 0)
- The mechanism is structurally guaranteed to give the majority to the owner unless `cost >= emissions` (i.e., the network stores enough data that storage costs match or exceed token emissions)
- Additionally: `distribute_alpha` in marketplace pallet hardcodes 75/25 split (75% to rankings pallet, 25% to marketplace pallet). Era payouts split marketplace balance 75% validators / 25% treasury.

## 7. Discrepancies README vs Code

1. **README lists Compute, GPU miners** as active features. Code shows ranking instances 2 (Compute), 4 (GPU), 5 (StorageS3) are **commented out** in `get_signed_weight_hex()` (lines 946-969). Only Instance 1 (Storage) and Instance 3 (Validator) submit rankings to Hippius chain.

2. **Older docs reference 70/20/10 split.** `incentives.md` explicitly notes: "Older descriptions sometimes used a 70/20/10 style breakdown. Mainnet currently uses 75/25." The code confirms 75/25.

3. **Miner hardware requirements** are not in the repo. External docs (docs.hippius.com) provide more detail than the repo's `minner-setup.md` (which has a typo in its filename).

4. **readme_weights.md** documents the current Arion-based scoring system accurately, but `incentives.md` describes a different scoring formula (80% file_size_score + 20% pin_score) that appears to be an older or alternative system. The Arion-based system is the live implementation.

5. **Weight submission** has two paths: (a) Substrate offchain worker every 100 blocks (`BittensorCallSubmission = 100`) and (b) Python `vali-weights-submitter` every 101 blocks. Both read from the same Hippius chain state. Python path described as backup.

## 8. Red Flags (numbered)

1. **CRITICAL -- UID 0 captures 99.29% of emissions.** The `uid_zero_pool` formula allocates almost all weight budget to UID 0 when `emissions >> storage_cost`. UID 0 is the subnet owner's hotkey. Currently getting 246 TAO while median miner gets 0.004 TAO. This is structural and by design -- not a bug.

2. **CRITICAL -- UID 0 IS the subnet owner.** Confirmed match: hotkey `5G1Qj93Fy22grpiGKq6BEvqqmS2HVRs3jaEdMhq9absQzs6g`, coldkey `5DAQpczEK4vzBn1waHkC4BZGqGPZ1dwPxKVsj36JDofHAw3a`. The burn mechanism sends directly to the team's wallet, not a dead address or treasury.

3. **HIGH -- Opaque weight computation.** All scoring happens on a proprietary Substrate chain. Weights are not computed by standard Bittensor validator logic. External verification requires running a full Hippius node and querying RPC. No wandb, no public leaderboard, no independent auditing.

4. **HIGH -- Extensive sudo control.** 30+ `ensure_root`-gated functions across pallets: marketplace pricing (`set_price_per_gb`), credit settings (`set_alpha_price`), weight submission toggle (`set_weight_submission_enabled`), alpha bridge params, notification bans, IPFS config, rank distribution limits. The sudo key holder can unilaterally alter economic parameters that affect the burn percentage and thus emission distribution.

5. **HIGH -- `distribute_alpha` transfers from sudo account.** The marketplace pallet's `distribute_alpha` function (line 1711-1743) transfers tokens from the `SudoKey` storage account. Combined with `set_sudo_key` being root-only, this creates a tight loop of team control over alpha distribution.

6. **MEDIUM -- Weight submission kill switch.** `set_weight_submission_enabled()` is root-only (`pallets/utils/src/lib.rs` lines 83-90). The team can pause Bittensor weight submissions at will, potentially to manipulate timing of weight updates.

7. **MEDIUM -- Burn percentage default floor.** When `emissions == 0`, `burn_percentage` defaults to `0.2` (20%). This guarantees UID 0 always receives at least 20% of weight budget even in edge cases where the formula would otherwise yield 0.

8. **MEDIUM -- Auto-update in deployment.** `minner-setup.md` uses `git pull` for updates. Node-setup ansible playbook (`node-setup.yml`) also uses `git pull`. While not an auto-updater in the binary itself, the deployment pattern encourages blind code updates.

9. **LOW -- Validator quality reporting is closed loop.** Only registered Validator nodes can call `update_rankings` (line 226-242 of ranking pallet) and `submit_node_quality` in arion pallet. Validators are team-controlled infrastructure, making quality reporting a closed system.

## 9. Data Quality
"on-chain only" -- All scoring happens on the Hippius proprietary Substrate chain with no external dashboards, wandb, or HuggingFace to cross-reference. Bittensor-side emission data from taostats is available but cannot inspect Hippius-chain internals. Independent verification requires running a full Hippius node and querying `RankedList`, `FamilyWeight`, `NodeMetrics` storage directly via RPC.

## 10. Verdict
**SKIP** -- Legitimate decentralized storage infrastructure with real code and a genuine miner task (IPFS storage with bandwidth/uptime scoring). However, the dynamic burn mechanism currently routes 99.29% of all emissions to the subnet owner's UID 0. This is not a bug but a deliberate economic design that concentrates emissions to the team when network utilization is low relative to token price -- which is the current state. The extreme Gini (0.99), opaque custom-chain scoring, 30+ sudo-gated economic parameters, and absence of any external verification mechanism (no leaderboard, no wandb, no public dashboard) make this subnet unsuitable for external mining or delegation at current utilization levels. The mechanism would self-correct if real storage demand grew enough for `cost >= emissions`, but there is no governance cap or timeline guarantee for this.
