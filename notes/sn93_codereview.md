# SN93 (Bitcast) - Security-Focused Code Review

**Repo**: https://github.com/bitcast-network/bitcast  
**Date**: 2026-04-11  
**Commit**: main branch (latest)

---

## Real Miner Task (from code, not README)

The miner's actual job is trivial from a compute standpoint:

1. Miner registers YouTube OAuth tokens via `token_mgmt.init()`
2. When a validator queries, the miner responds with its YouTube access tokens (`synapse.YT_access_tokens = token_mgmt.load_token()`)
3. The validator uses these OAuth tokens to pull YouTube Analytics data and score videos

**The miner does NOT do any ML inference, GPU computation, or data processing.** It simply hands over OAuth credentials. The "real work" is creating YouTube content off-chain, then giving the validator API access to check analytics.

---

## Minimum Hardware (from min_compute.yml)

```yaml
miner:
  cpu: 2
  ram: 4  # GB

validator:
  cpu: 2
  ram: 8  # GB
```

No GPU required for either role. This is accurate -- the miner is just serving OAuth tokens and the validator is making API calls.

---

## Scoring Function Summary

### Core Curve-Based Scoring (`curve_scoring.py`)
```python
def calculate_curve_value(value: float) -> float:
    sqrt_value = math.sqrt(value)
    curve_value = sqrt_value / (1 + YT_CURVE_DAMPENING_FACTOR * sqrt_value)
    return curve_value

def calculate_curve_difference(day1_avg, day2_avg) -> float:
    return calculate_curve_value(day2_avg) - calculate_curve_value(day1_avg)
```
Score = gain along a diminishing returns curve between two 7-day periods of YouTube Premium Revenue.

### USD Target Calculation (`main.py`)
```python
adjusted_score = calculate_adjusted_curve_difference(
    curve_input_day1, curve_input_day2, scaling_factor, lifetime_deduction
)
usd_target = adjusted_score * scaling_factor * boost_factor
```
- `scaling_factor`: 1800 (dedicated), 400 (ad-read/integration)
- `boost_factor`: from brief JSON (controlled by Bitcast API)
- `lifetime_deduction`: $100 (dedicated), $25 (ad-read) -- ensures first ~$100/$25 of lifetime revenue earns nothing

### Final Weight Distribution (`reward_distribution_service.py`)
```python
# Sum each miner's scores across briefs
rewards = scores_matrix.sum(axis=1)
# Ensure total rewards sum to 1 by adjusting UID 0 (burn)
uid_0_idx = next((i for i, uid in enumerate(uids) if uid == 0), None)
if uid_0_idx is not None:
    other_sum = sum(rewards[i] for i in range(len(rewards)) if i != uid_0_idx)
    rewards[uid_0_idx] = max(1.0 - other_sum, 0.0)
```
UID 0 (the burn address) receives all unclaimed emissions (1.0 - sum of miner rewards).

---

## Emission Capture Analysis

### Subnet Treasury Mechanism

**File**: `bitcast/validator/utils/config.py`
```python
SUBNET_TREASURY_PERCENTAGE = 0
SUBNET_TREASURY_UID = int(os.getenv('SUBNET_TREASURY_UID', '106'))
```

**File**: `bitcast/validator/rewards_scaling.py`
```python
def allocate_subnet_treasury(rewards: np.ndarray, uids: List[int]) -> np.ndarray:
    burn_uid = 0
    burn_uid_idx = np.where(uids_array == burn_uid)[0][0]
    treasury_idx = np.where(uids_array == SUBNET_TREASURY_UID)[0][0]
    allocation = min(SUBNET_TREASURY_PERCENTAGE, rewards[burn_uid_idx])
    rewards[burn_uid_idx] -= allocation
    rewards[treasury_idx] += allocation
```

**Current state**: `SUBNET_TREASURY_PERCENTAGE = 0`, meaning the treasury mechanism is **currently inactive**. However:
- The code exists and is wired in -- it redirects from UID 0 (burn) to UID 106 (treasury)
- The `SUBNET_TREASURY_UID` is configurable via environment variable
- Changing `SUBNET_TREASURY_PERCENTAGE` to any value would silently redirect emissions to UID 106
- This is a "dormant capture valve" -- not currently extracting, but can be turned on without code changes (just env var or config change + auto-update)

### UID 0 (Burn) Handling

UID 0 receives ALL unclaimed emissions. This is standard Bittensor behavior. The code explicitly ensures `rewards[uid_0_idx] = max(1.0 - other_sum, 0.0)`.

### No Other Hardcoded UID Advantages Found

No `TEAM_UID`, `FOUNDER`, `BURNER`, `SPECIAL_UID`, or similar hardcoded privileged UID lists were found.

---

## Discrepancies README vs Code

| Claim (README) | Reality (Code) |
|---|---|
| "rewards based on YouTube Premium revenue stats" | Accurate - uses `estimatedRedPartnerRevenue` |
| "7-day moving average" | Accurate - `YT_ROLLING_WINDOW = 7` |
| "3-day delay in rewards" | Accurate - `YT_REWARD_DELAY = 3` |
| "14 days after published" | Accurate - `YT_SCORING_WINDOW = 14` |
| "Unclaimed emissions automatically allocated to subnet treasury" | MISLEADING - treasury percentage is currently 0. Unclaimed goes to UID 0 (burn). Treasury is dormant. |
| No mention of lifetime deduction | Code deducts first $100 (dedicated) / $25 (ad-read) from lifetime earnings before any rewards |
| "up to 5 YouTube accounts" per miner | Code allows `MAX_ACCOUNTS_PER_SYNAPSE = 1000` |
| No mention of `min_stake` requirement | Code has `YT_MIN_ALPHA_STAKE_THRESHOLD = 1000` -- miners need 1000 alpha stake for full scoring |

---

## Red Flags

### 1. CRITICAL: Centralized Brief Control (HIGH)
All briefs (which determine what content gets rewarded and at what boost multiplier) come from a centralized API controlled by Bitcast:
```python
BITCAST_API_URL = 'https://bitcast-api.bitcast.network'
BITCAST_BRIEFS_ENDPOINT = f"{BITCAST_API_URL}/api/v2/validator/briefs"
```
The team controls which content gets rewarded, the boost multipliers, and emission caps per brief. This is the primary emission control lever -- whoever controls briefs controls where emissions flow.

### 2. HIGH: Auto-Update with `git reset --hard` (HIGH)
```python
def run_auto_update(neuron_type):
    reset_cmd = "git reset --hard " + remote_commit
    process = subprocess.Popen(reset_cmd.split(), stdout=subprocess.PIPE)
```
Both miners and validators auto-update from the repo every 10-15 minutes. This means:
- Team can push code that activates the dormant treasury
- Team can push code that changes scoring to favor specific UIDs
- No governance or delay mechanism

### 3. MEDIUM: Dormant Treasury Extraction Valve
`SUBNET_TREASURY_PERCENTAGE = 0` can be changed to extract emissions to UID 106 at any time via auto-update or env var change.

### 4. MEDIUM: External Pricing Dependencies
Scoring depends on CoinGecko price and on-chain emission data. If these APIs fail or are manipulated, rewards could be distorted.

### 5. LOW: Briefs Caching Allows Stale Data
If the briefs API goes down, validators use cached briefs indefinitely. The team could change briefs then "accidentally" take down the API, leaving some validators on old briefs.

### 6. LOW: CloudWatch Logging to Bitcast Infrastructure
Validators send logs to Bitcast's AWS CloudWatch (`/bitcast/youtube-validator`), potentially leaking miner scoring data to the team.

### 7. LOW: Data Publishing to Bitcast Server
```python
DATA_CLIENT_URL = os.getenv('DATA_CLIENT_URL', 'http://44.254.20.95')
```
Validators publish miner account data and weight corrections to a Bitcast-controlled IP. This gives the team real-time visibility into all miner performance before weights are set.

---

## VERDICT

```
team_burn_capture: NO (currently 0%, but dormant mechanism exists for UID 106)
hardware_real: Minimal (2 CPU, 4GB RAM) - accurate since miner just serves OAuth tokens
red_flags_count: 7
```

**Summary**: The subnet is architecturally centralized around the Bitcast team's control of the briefs API (which determines all emission routing) and the auto-update mechanism (which can silently alter scoring logic). There is no direct emission theft currently active, but the infrastructure for it exists in dormant form. The primary risk is not outright theft but rather the team's ability to steer emissions toward specific content/miners via brief manipulation, since briefs set boost multipliers and caps that directly control emission allocation.
