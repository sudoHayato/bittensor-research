#!/usr/bin/env python3
"""
Bittensor subnet filtering pipeline.
Phase 1: Statistical filter via taostats API.
Phase 2: Automated grep with off-chain detection.
"""

import json
import csv
import os
import re
import time
import subprocess
import sys
from pathlib import Path

# === CONFIG ===
API_KEY = "tao-1453ed31-5e73-4303-a634-9a98b576c3b5:84ae2f06"
BASE_DIR = Path("~/bittensor-research")
DATA_DIR = BASE_DIR / "data"
REPOS_DIR = BASE_DIR / "repos"
SNAPSHOT_FILE = DATA_DIR / "subnets_snapshot_2026-04-11.json"

EXCLUDED_NETUIDS = {0, 4, 5, 17, 51, 64, 93, 120}
TOP_N_EXCLUDE = 25
RATE_LIMIT_SLEEP = 7
BACKOFF_START = 15
MAX_RETRIES = 5

# === PHASE 1 ===

def load_snapshot():
    with open(SNAPSHOT_FILE) as f:
        return json.load(f)

def api_request(url, headers):
    """Make API request with rate limiting and exponential backoff."""
    import urllib.request
    import urllib.error

    for attempt in range(MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = BACKOFF_START * (2 ** attempt)
                print(f"  429 rate limited, waiting {wait}s (attempt {attempt+1})")
                time.sleep(wait)
                continue
            elif e.code in (404, 500, 502, 503):
                print(f"  HTTP {e.code} for {url}")
                return None
            else:
                print(f"  HTTP error {e.code} for {url}")
                return None
        except Exception as e:
            print(f"  Request error: {e}")
            return None
    return None

def fetch_subnet_data(netuid):
    """Fetch subnet data from taostats API."""
    headers = {
        "Authorization": API_KEY,
        "User-Agent": "BittensorResearch/1.0"
    }

    url = f"https://api.taostats.io/api/subnet/latest/v1?netuid={netuid}"
    data = api_request(url, headers)

    result = {"flow_30d": None, "miner_count": None, "emission_tao_day": None}

    if data:
        # Handle response structure - could be dict with 'data' key or direct
        record = data
        if isinstance(data, dict) and "data" in data:
            record = data["data"]
            if isinstance(record, list) and len(record) > 0:
                record = record[0]

        # Extract fields
        if isinstance(record, dict):
            result["emission_tao_day"] = _to_float(record.get("emission_tao_day") or record.get("emission_per_day"))
            result["miner_count"] = _to_int(record.get("active_miners") or record.get("miner_count"))
            result["flow_30d"] = _to_float(record.get("net_flow_30_days") or record.get("net_flow_30d"))

    # If flow_30d not found, try history endpoint
    if result["flow_30d"] is None:
        time.sleep(RATE_LIMIT_SLEEP)
        url2 = f"https://api.taostats.io/api/subnet/history/v1?netuid={netuid}&period=30d"
        data2 = api_request(url2, headers)
        if data2:
            record2 = data2
            if isinstance(data2, dict) and "data" in data2:
                record2 = data2["data"]
                if isinstance(record2, list) and len(record2) > 0:
                    record2 = record2[0]
            if isinstance(record2, dict):
                result["flow_30d"] = _to_float(record2.get("net_flow_30_days") or record2.get("net_flow_30d") or record2.get("net_flow"))

    return result

def _to_float(v):
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None

def _to_int(v):
    if v is None:
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None

def phase1():
    print("=" * 60)
    print("PHASE 1: Statistical Filter")
    print("=" * 60)

    subnets = load_snapshot()

    # Exclude specific netuids
    filtered = [s for s in subnets if s["netuid"] not in EXCLUDED_NETUIDS]
    print(f"After excluding netuids: {len(filtered)} subnets")

    # Sort by emission_tao_day desc, exclude top 25
    filtered.sort(key=lambda x: x.get("emission_tao_day", 0) or 0, reverse=True)
    remaining = filtered[TOP_N_EXCLUDE:]
    print(f"After excluding top {TOP_N_EXCLUDE}: {len(remaining)} subnets")

    # Only those with github
    with_github = [s for s in remaining if s.get("github")]
    print(f"With github field: {len(with_github)} subnets")

    # Query taostats for each
    print(f"\nQuerying taostats API for {len(with_github)} subnets...")
    candidates = []
    for i, subnet in enumerate(with_github):
        netuid = subnet["netuid"]
        print(f"  [{i+1}/{len(with_github)}] Querying netuid {netuid} ({subnet['name']})...")

        api_data = fetch_subnet_data(netuid)

        emission = api_data["emission_tao_day"] if api_data["emission_tao_day"] is not None else subnet.get("emission_tao_day", 0)
        flow_30d = api_data["flow_30d"]
        miner_count = api_data["miner_count"]

        candidates.append({
            "netuid": netuid,
            "name": subnet["name"],
            "emission_tao_day": emission,
            "flow_30d": flow_30d,
            "miner_count": miner_count,
            "github_url": subnet["github"]
        })

        if i < len(with_github) - 1:
            time.sleep(RATE_LIMIT_SLEEP)

    # Apply filters
    survivors = []
    for c in candidates:
        # flow_30d > 0
        if c["flow_30d"] is None or c["flow_30d"] <= 0:
            continue
        # emission_tao_day >= 0.1
        if (c["emission_tao_day"] or 0) < 0.1:
            continue
        # github_url != null (already filtered)
        c["low_onchain_miners"] = (c["miner_count"] is not None and c["miner_count"] < 32)
        survivors.append(c)

    # Sort by flow_30d desc
    survivors.sort(key=lambda x: x["flow_30d"] or 0, reverse=True)

    # Save CSV
    csv_path = DATA_DIR / "fase1_survivors.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["netuid", "name", "emission_tao_day", "flow_30d", "miner_count", "low_onchain_miners", "github_url"])
        writer.writeheader()
        for s in survivors:
            writer.writerow(s)

    print(f"\nPhase 1 survivors: {len(survivors)}")
    print(f"Saved to: {csv_path}")

    # Print ASCII table of top 15
    print(f"\n{'netuid':<7}{'name':<20}{'emission':<12}{'flow_30d':<14}{'miners':<8}{'low_miners':<12}")
    print("-" * 73)
    for s in survivors[:15]:
        print(f"{s['netuid']:<7}{s['name'][:19]:<20}{s['emission_tao_day']:<12.4f}{s['flow_30d']:<14.2f}{str(s['miner_count']):<8}{str(s['low_onchain_miners']):<12}")

    return survivors

# === PHASE 2 ===

PATTERNS_BURN = [
    r"BURN_?(LIST|UID|UIDS|EMISSION|ERS|PCT)",
    r"TEAM_?(UID|UIDS|ALLOCATION|SHARE)",
    r"FOUNDER_?(UID|SHARE|ALLOC)",
    r"TREASURY_?(UID|HOTKEY)",
    r"NEW_BURNERS",
    r"weights\s*\[\s*\d+\s*\]\s*=\s*0?\.\d",
    r"set_weights.*bias",
]

PATTERNS_CENTRAL = [
    r"https?://[a-z0-9.-]+\.io/api",
    r"requests\.(get|post)\(.{0,80}http",
    r"BACKEND_URL",
    r"API_ENDPOINT",
]

PATTERNS_OFFCHAIN = [
    r"leaderboard",
    r"dashboard\.[a-z]+",
    r"wandb\.(ai|init)",
    r"huggingface\.co/(spaces|datasets)",
    r"score_buffer|rolling_(avg|average|score)|accumulated_scores|ema_score",
    r"requests\.(get|post).{0,80}(score|reward|leaderboard)",
    r"httpx\.(get|post).{0,80}(score|reward|leaderboard)",
]

def clone_repo(netuid, github_url):
    """Clone repo, return path or None if failed."""
    repo_dir = REPOS_DIR / f"sn{netuid}"
    repo_path = repo_dir / "repo"

    os.makedirs(repo_dir, exist_ok=True)

    if repo_path.exists():
        # Already cloned
        return repo_path

    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", github_url, str(repo_path)],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode != 0:
            print(f"    Clone failed: {result.stderr[:100]}")
            return None
        return repo_path
    except Exception as e:
        print(f"    Clone error: {e}")
        return None

def search_patterns(repo_path, patterns):
    """Search .py files for patterns, return list of matched pattern strings."""
    matches = []
    skip_dirs = {".git", "venv", "__pycache__", "node_modules"}

    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for fname in files:
            if not fname.endswith(".py"):
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, "r", errors="ignore") as f:
                    content = f.read()
            except:
                continue

            for pattern in patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    if pattern not in matches:
                        matches.append(pattern)
    return matches

def check_hardware(repo_path):
    """Check min_compute.yml or similar for heavy hardware requirements."""
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in {".git", "venv", "__pycache__", "node_modules"}]
        for fname in files:
            if "compute" in fname.lower() and (fname.endswith(".yml") or fname.endswith(".yaml")):
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, "r", errors="ignore") as f:
                        content = f.read()
                    # Check gpu_memory >= 40 or gpu_count >= 2
                    mem_match = re.search(r"gpu_memory[:\s]+(\d+)", content, re.IGNORECASE)
                    count_match = re.search(r"gpu_count[:\s]+(\d+)", content, re.IGNORECASE)

                    gpu_mem = int(mem_match.group(1)) if mem_match else 0
                    gpu_count = int(count_match.group(1)) if count_match else 0

                    if gpu_mem >= 40 or gpu_count >= 2:
                        return True, f"gpu_memory={gpu_mem}, gpu_count={gpu_count} in {fname}"
                    return False, f"gpu_memory={gpu_mem}, gpu_count={gpu_count} in {fname}"
                except:
                    pass
    return False, "no compute yaml found"

def phase2(survivors):
    print("\n" + "=" * 60)
    print("PHASE 2: Automated Grep with Off-Chain Detection")
    print("=" * 60)

    phase2_survivors = []
    phase2_rejected = []

    for i, subnet in enumerate(survivors):
        netuid = subnet["netuid"]
        name = subnet["name"]
        github_url = subnet["github_url"]

        print(f"\n  [{i+1}/{len(survivors)}] SN{netuid} ({name})")

        repo_path = clone_repo(netuid, github_url)

        if repo_path is None:
            phase2_rejected.append({
                "netuid": netuid,
                "name": name,
                "reason": "REPO_INACCESSIBLE",
                "sample_match": ""
            })
            continue

        # Search patterns
        burn_matches = search_patterns(repo_path, PATTERNS_BURN)
        central_matches = search_patterns(repo_path, PATTERNS_CENTRAL)
        offchain_matches = search_patterns(repo_path, PATTERNS_OFFCHAIN)

        # Check hardware
        hardware_heavy, min_compute_summary = check_hardware(repo_path)

        # Scoring
        red_flags_burn = len(burn_matches)
        red_flags_central = len(central_matches)
        offchain_signals = len(offchain_matches)
        offchain_heavy = offchain_signals >= 2

        # Survival criteria
        survives = (red_flags_burn == 0 and red_flags_central <= 1 and not hardware_heavy)

        entry = {
            "netuid": netuid,
            "name": name,
            "github_url": github_url,
            "emission_tao_day": subnet["emission_tao_day"],
            "flow_30d": subnet["flow_30d"],
            "miner_count": subnet["miner_count"],
            "red_flags_burn": red_flags_burn,
            "red_flags_central": red_flags_central,
            "offchain_signals_count": offchain_signals,
            "offchain_heavy": offchain_heavy,
            "hardware_heavy": hardware_heavy,
            "low_onchain_miners": subnet["low_onchain_miners"],
            "sample_burn_matches": burn_matches,
            "sample_offchain_matches": offchain_matches,
            "min_compute_summary": min_compute_summary
        }

        if survives:
            phase2_survivors.append(entry)
            status = "PASS"
            if offchain_heavy:
                status += " (offchain_heavy)"
        else:
            reasons = []
            if red_flags_burn > 0:
                reasons.append(f"BURN_FLAGS({red_flags_burn})")
            if red_flags_central > 1:
                reasons.append(f"CENTRAL_FLAGS({red_flags_central})")
            if hardware_heavy:
                reasons.append("HARDWARE_HEAVY")
            reason = "|".join(reasons)
            sample = "; ".join(burn_matches[:2] + central_matches[:2])
            phase2_rejected.append({
                "netuid": netuid,
                "name": name,
                "reason": reason,
                "sample_match": sample[:200]
            })
            status = f"REJECTED: {reason}"

        print(f"    burn={red_flags_burn} central={red_flags_central} offchain={offchain_signals} hw_heavy={hardware_heavy} -> {status}")

    # Save survivors JSON
    json_path = DATA_DIR / "fase2_survivors.json"
    with open(json_path, "w") as f:
        json.dump(phase2_survivors, f, indent=2)

    # Save rejected CSV
    csv_path = DATA_DIR / "fase2_rejected.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["netuid", "name", "reason", "sample_match"])
        writer.writeheader()
        for r in phase2_rejected:
            writer.writerow(r)

    # Print results
    offchain_heavy_count = sum(1 for s in phase2_survivors if s["offchain_heavy"])

    print(f"\n\nPhase 2 Survivors:")
    print(f"{'netuid':<7}{'name':<20}{'burn':<6}{'central':<9}{'offchain':<9}{'hw_heavy':<10}{'offchain_heavy':<14}")
    print("-" * 75)
    for s in phase2_survivors:
        print(f"{s['netuid']:<7}{s['name'][:19]:<20}{s['red_flags_burn']:<6}{s['red_flags_central']:<9}{s['offchain_signals_count']:<9}{str(s['hardware_heavy']):<10}{str(s['offchain_heavy']):<14}")

    # Count rejected by reason
    print(f"\nRejected ({len(phase2_rejected)} total):")
    reason_counts = {}
    for r in phase2_rejected:
        reason_counts[r["reason"]] = reason_counts.get(r["reason"], 0) + 1
    for reason, count in sorted(reason_counts.items(), key=lambda x: -x[1]):
        print(f"  {reason}: {count}")

    return phase2_survivors, phase2_rejected, offchain_heavy_count

# === MAIN ===

if __name__ == "__main__":
    survivors_p1 = phase1()
    survivors_p2, rejected_p2, offchain_count = phase2(survivors_p1)

    print("\n" + "=" * 60)
    print(f"FASE 1: {len(survivors_p1)} candidatos")
    print(f"FASE 2: {len(survivors_p2)} sobreviventes ({offchain_count} marcados off-chain heavy para review humano)")
    print("=" * 60)
    print(f"\nFiles:")
    print(f"  {DATA_DIR / 'fase1_survivors.csv'}")
    print(f"  {DATA_DIR / 'fase2_survivors.json'}")
    print(f"  {DATA_DIR / 'fase2_rejected.csv'}")
