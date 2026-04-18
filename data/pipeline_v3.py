#!/usr/bin/env python3
"""
Caminho A v3 — exhaustive economic viability filter for Bittensor subnets.
Phases: 0 (economic hard filter) → 1 (flow) → 2 (code grep) → 3 (deep dive)
"""

import json, csv, os, re, subprocess, time, math, sys
from pathlib import Path
import urllib.request, urllib.error

# === CONFIG ===
_K = "tao-1453ed31-5e73-4303-a634-9a98b576c3b5:84ae2f06"
BASE = Path("~/bittensor-research")
DATA = BASE / "data"
REPOS = BASE / "repos"
NOTES = BASE / "notes"
API = "https://api.taostats.io/api"

TAO_USD = 263.65  # verified via coingecko 2026-04-12
ANALYZED_EXCLUSIONS = {0, 4, 5, 17, 32, 51, 64, 75, 83, 93, 114, 120, 2}
RATE_SLEEP = 7
BACKOFF_START = 15
MAX_RETRIES = 5

# Economic thresholds
TOP1_MIN_USD_MONTH = 300
UNIFORM_MIN_USD_MONTH = 50
MIN_MINERS_SCORING = 5

PATTERNS_BURN = [
    r"BURN_?(LIST|UID|UIDS|EMISSION|ERS|PCT)",
    r"TEAM_?(UID|UIDS|ALLOCATION|SHARE)",
    r"FOUNDER_?(UID|SHARE|ALLOC)",
    r"TREASURY_?(UID|HOTKEY)",
    r"NEW_BURNERS",
    r"weights\s*\[\s*\d+\s*\]\s*=\s*0?\.\d",
    r"set_weights.*bias",
    r"sudo_",
]
PATTERNS_MATH = [
    r"softmax.*\*\s*[1-9]\d{1,}",
    r"torch\.pow.*[5-9]",
    r"\*\s*100\s*\)",
]
PATTERNS_CENTRAL = [
    r"https?://[a-z0-9.-]+\.io/api",
    r"requests\.(get|post)\(.{0,80}http",
    r"BACKEND_URL",
    r"API_ENDPOINT",
]


def api_get(endpoint, params=None):
    url = f"{API}/{endpoint}"
    if params:
        url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
    for attempt in range(MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url)
            req.add_header("Authorization", _K)
            req.add_header("User-Agent", "BittensorResearch/1.0")
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                w = BACKOFF_START * (2 ** attempt)
                print(f"      429, wait {w}s...", flush=True)
                time.sleep(w)
            elif e.code in (404, 500, 502, 503):
                return None
            else:
                return None
        except Exception:
            if attempt < MAX_RETRIES:
                time.sleep(5)
            else:
                return None
    return None


def extract_data(resp):
    """Unwrap taostats response envelope."""
    if not resp:
        return None
    d = resp
    if isinstance(d, dict) and "data" in d:
        d = d["data"]
    if isinstance(d, list) and len(d) > 0:
        d = d[0]
    return d if isinstance(d, dict) else None


def extract_list(resp):
    """Unwrap taostats response to list."""
    if not resp:
        return []
    d = resp
    if isinstance(d, dict) and "data" in d:
        d = d["data"]
    return d if isinstance(d, list) else []


def to_f(v):
    if v is None: return None
    try: return float(v)
    except: return None


def gini(values):
    if not values or len(values) < 2:
        return 0.0
    s = sorted(values)
    n = len(s)
    total = sum(s)
    if total == 0:
        return 0.0
    cum = sum((2 * (i + 1) - n - 1) * v for i, v in enumerate(s))
    return cum / (n * total)


def median(values):
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    if n % 2 == 0:
        return (s[n // 2 - 1] + s[n // 2]) / 2
    return s[n // 2]


# ============================================================
# PHASE 0: Economic hard filter
# ============================================================
def phase0():
    print("=" * 70)
    print(f"PHASE 0: Economic Hard Filter (TAO=${TAO_USD})")
    print("=" * 70)

    with open(DATA / "subnets_snapshot_2026-04-11.json") as f:
        snapshot = json.load(f)

    candidates = [s for s in snapshot if s["netuid"] not in ANALYZED_EXCLUSIONS and s["netuid"] > 0]
    print(f"  Candidates (excl. analyzed): {len(candidates)}")

    viable = []
    fail_reasons = {"top1_too_low": 0, "uniform_too_low": 0, "too_few_miners": 0,
                    "api_fail": 0, "no_emission": 0}

    for i, sn in enumerate(candidates):
        nid = sn["netuid"]
        name = sn.get("name", f"SN{nid}")
        github = sn.get("github", "")
        print(f"  [{i+1}/{len(candidates)}] SN{nid} {name}...", end=" ", flush=True)

        # Get subnet latest
        time.sleep(RATE_SLEEP)
        latest = extract_data(api_get("subnet/latest/v1", {"netuid": nid}))

        if not latest:
            print("API FAIL")
            fail_reasons["api_fail"] += 1
            continue

        emission_raw = to_f(latest.get("emission_tao_day"))
        if emission_raw is None or emission_raw <= 0:
            # Fallback to snapshot
            emission_raw = sn.get("emission_tao_day", 0)

        if emission_raw <= 0:
            print("no emission")
            fail_reasons["no_emission"] += 1
            continue

        # Get neurons
        time.sleep(RATE_SLEEP)
        neurons = extract_list(api_get("neuron/latest/v1", {"netuid": nid, "limit": "256"}))

        # Compute miner incentives (exclude validators)
        miners = []
        for n in neurons:
            # Miners have axon_ip or active flag; validators have validator_permit
            # Simplification: use incentive > 0 as signal for "scoring miner"
            inc = to_f(n.get("incentive"))
            if inc is not None:
                miners.append({"uid": n.get("uid"), "incentive": inc,
                               "hotkey": n.get("hotkey", ""),
                               "emission": to_f(n.get("emission"))})

        scoring = [m for m in miners if m["incentive"] > 0]
        n_scoring = len(scoring)

        if n_scoring == 0:
            print(f"0 scoring miners, FAIL")
            fail_reasons["too_few_miners"] += 1
            continue

        incentives = [m["incentive"] for m in scoring]
        total_inc = sum(incentives)
        if total_inc == 0:
            total_inc = 1  # avoid div by zero

        # Normalize incentives to shares
        shares = [inc / total_inc for inc in incentives]
        shares.sort(reverse=True)

        top1_share = shares[0]
        top10_avg = sum(shares[:10]) / min(10, len(shares))
        med_share = median(shares)
        g = gini(incentives)

        # Revenue calculations
        top1_tao_day = top1_share * emission_raw
        uniform_tao_day = emission_raw / n_scoring
        med_tao_day = med_share * emission_raw

        top1_usd_month = top1_tao_day * TAO_USD * 30
        uniform_usd_month = uniform_tao_day * TAO_USD * 30
        med_usd_month = med_tao_day * TAO_USD * 30

        # Economic filter
        passes = True
        reasons = []
        if top1_usd_month < TOP1_MIN_USD_MONTH:
            passes = False
            reasons.append(f"top1=${top1_usd_month:.0f}")
            fail_reasons["top1_too_low"] += 1
        if uniform_usd_month < UNIFORM_MIN_USD_MONTH:
            passes = False
            reasons.append(f"uniform=${uniform_usd_month:.0f}")
            fail_reasons["uniform_too_low"] += 1
        if n_scoring < MIN_MINERS_SCORING:
            passes = False
            reasons.append(f"miners={n_scoring}")
            fail_reasons["too_few_miners"] += 1

        if passes:
            viable.append({
                "netuid": nid,
                "name": name,
                "emission_total_tao_day": round(emission_raw, 6),
                "miners_scoring": n_scoring,
                "max_uniform_usd_month": round(uniform_usd_month, 2),
                "top1_usd_month": round(top1_usd_month, 2),
                "median_usd_month": round(med_usd_month, 2),
                "top1_tao_day": round(top1_tao_day, 6),
                "median_tao_day": round(med_tao_day, 6),
                "gini": round(g, 4),
                "github_url": github or "",
                "top1_share": round(top1_share, 6),
                "flow_30d": to_f(latest.get("net_flow_30_days")),
            })
            print(f"VIABLE top1=${top1_usd_month:.0f}/m uniform=${uniform_usd_month:.0f}/m miners={n_scoring}")
        else:
            print(f"FAIL: {', '.join(reasons)}")

    # Sort by top1_usd_month desc
    viable.sort(key=lambda x: x["top1_usd_month"], reverse=True)

    # Save CSV
    csv_path = DATA / "fase0_v3_economically_viable.csv"
    fields = ["netuid", "name", "emission_total_tao_day", "miners_scoring",
              "max_uniform_usd_month", "top1_usd_month", "median_usd_month",
              "gini", "github_url"]
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(viable)

    # Print
    total_fail = len(candidates) - len(viable)
    print(f"\n{'=' * 70}")
    print(f"PHASE 0 RESULTS: {len(viable)} economically viable / {len(candidates)} queried")
    print(f"  Failed economic filter: {total_fail}")
    for reason, count in sorted(fail_reasons.items(), key=lambda x: -x[1]):
        if count > 0:
            print(f"    {reason}: {count}")
    print(f"{'=' * 70}")
    print(f"{'nid':>4} {'name':<22} {'emit τ/d':>10} {'miners':>7} {'top1$/m':>10} {'unif$/m':>10} {'med$/m':>10} {'gini':>6}")
    print("-" * 85)
    for s in viable[:20]:
        print(f"{s['netuid']:>4} {s['name'][:21]:<22} {s['emission_total_tao_day']:>10.4f} {s['miners_scoring']:>7} {s['top1_usd_month']:>10.0f} {s['max_uniform_usd_month']:>10.0f} {s['median_usd_month']:>10.0f} {s['gini']:>6.3f}")

    return viable


# ============================================================
# PHASE 1: Flow filter
# ============================================================
def phase1(viable):
    print(f"\n{'=' * 70}")
    print("PHASE 1: Flow + GitHub Filter")
    print("=" * 70)

    survivors = []
    rejected = []

    for sn in viable:
        nid = sn["netuid"]

        # Get flow_30d if not already present
        flow = sn.get("flow_30d")
        if flow is None:
            time.sleep(RATE_SLEEP)
            hist = extract_data(api_get("subnet/history/v1", {"netuid": nid, "period": "30d"}))
            if hist:
                flow = to_f(hist.get("net_flow_30_days"))

        github = sn.get("github_url", "")

        # Filters
        reasons = []
        if flow is not None and flow < -1000:
            reasons.append(f"flow_30d={flow:.0f}")
        if not github:
            reasons.append("no_github")

        if reasons:
            sn["reject_reason"] = "; ".join(reasons)
            rejected.append(sn)
            print(f"  SN{nid} REJECTED: {sn['reject_reason']}")
        else:
            sn["flow_30d"] = flow
            survivors.append(sn)
            print(f"  SN{nid} {sn['name']} PASS (flow={flow})")

    # Save
    csv_path = DATA / "fase1_v3_survivors.csv"
    fields = ["netuid", "name", "emission_total_tao_day", "miners_scoring",
              "top1_usd_month", "median_usd_month", "gini", "flow_30d", "github_url"]
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(survivors)

    rej_path = DATA / "fase1_v3_rejected.csv"
    with open(rej_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["netuid", "name", "reject_reason"], extrasaction="ignore")
        w.writeheader()
        w.writerows(rejected)

    print(f"\n  Phase 1: {len(survivors)} survive, {len(rejected)} rejected")
    return survivors


# ============================================================
# PHASE 2: Code grep
# ============================================================
def phase2(survivors):
    print(f"\n{'=' * 70}")
    print("PHASE 2: Automated Code Grep")
    print("=" * 70)

    passed = []
    rejected = []

    for sn in survivors:
        nid = sn["netuid"]
        name = sn["name"]
        github = sn["github_url"]
        print(f"\n  SN{nid} ({name})...")

        repo_dir = REPOS / f"sn{nid}"
        clone_path = repo_dir / "repo"
        os.makedirs(repo_dir, exist_ok=True)

        # Clone if needed
        if not clone_path.exists():
            cmd = f"git clone --depth 1 {github} {clone_path} 2>&1"
            try:
                r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
                if r.returncode != 0:
                    # Try existing subdirs
                    existing = [d for d in repo_dir.iterdir() if d.is_dir() and d.name != '.git']
                    if existing:
                        clone_path = existing[0]
                    else:
                        print(f"    CLONE FAILED")
                        rejected.append({"netuid": nid, "name": name, "reason": "REPO_INACCESSIBLE"})
                        continue
            except subprocess.TimeoutExpired:
                print(f"    CLONE TIMEOUT")
                rejected.append({"netuid": nid, "name": name, "reason": "CLONE_TIMEOUT"})
                continue
        else:
            # Already cloned, check for subdirs
            pass

        # Also check if repo was cloned at repo_dir level directly
        actual_path = clone_path
        if not actual_path.exists():
            existing = [d for d in repo_dir.iterdir() if d.is_dir() and d.name != '.git']
            if existing:
                actual_path = existing[0]
            else:
                rejected.append({"netuid": nid, "name": name, "reason": "NO_CLONE_DIR"})
                continue

        # Find .py files
        py_files = []
        for root, dirs, files in os.walk(actual_path):
            dirs[:] = [d for d in dirs if d not in ('.git', 'venv', '.venv', 'node_modules', '__pycache__')]
            for f in files:
                if f.endswith('.py'):
                    py_files.append(os.path.join(root, f))

        burn_matches = set()
        math_matches = set()
        central_matches = set()

        for pyf in py_files:
            try:
                with open(pyf, 'r', errors='ignore') as fh:
                    content = fh.read()
            except:
                continue
            for p in PATTERNS_BURN:
                if re.search(p, content, re.IGNORECASE):
                    burn_matches.add(p)
            for p in PATTERNS_MATH:
                if re.search(p, content, re.IGNORECASE):
                    math_matches.add(p)
            for p in PATTERNS_CENTRAL:
                if re.search(p, content, re.IGNORECASE):
                    central_matches.add(p)

        # Hardware check
        hw_heavy = False
        for root, dirs, files in os.walk(actual_path):
            dirs[:] = [d for d in dirs if d not in ('.git', 'venv', '.venv')]
            for f in files:
                if 'min_compute' in f.lower() and f.endswith(('.yml', '.yaml')):
                    try:
                        with open(os.path.join(root, f), 'r') as fh:
                            c = fh.read().lower()
                        m = re.search(r'gpu_memory[:\s]*(\d+)', c)
                        if m and int(m.group(1)) >= 24:
                            hw_heavy = True
                    except:
                        pass

        nb = len(burn_matches)
        nm = len(math_matches)
        nc = len(central_matches)

        print(f"    burn={nb} math={nm} central={nc} hw_heavy={hw_heavy}")
        if burn_matches:
            print(f"    burn: {list(burn_matches)[:3]}")
        if math_matches:
            print(f"    math: {list(math_matches)[:3]}")

        survives = (nb == 0 and nm == 0 and nc <= 2)

        entry = {**sn, "burn_flags": nb, "math_flags": nm, "central_flags": nc,
                 "hw_heavy": hw_heavy, "clone_path": str(actual_path),
                 "burn_patterns": list(burn_matches), "math_patterns": list(math_matches),
                 "central_patterns": list(central_matches)}

        if survives:
            passed.append(entry)
            print(f"    => SURVIVES")
        else:
            reasons = []
            if nb > 0: reasons.append(f"burn={nb}")
            if nm > 0: reasons.append(f"math={nm}")
            if nc > 2: reasons.append(f"central={nc}")
            entry["reason"] = " + ".join(reasons)
            rejected.append(entry)
            print(f"    => REJECTED: {entry['reason']}")

    # Save
    with open(DATA / "fase2_v3_survivors.json", "w") as f:
        json.dump(passed, f, indent=2, default=str)

    with open(DATA / "fase2_v3_rejected.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["netuid", "name", "reason", "burn_flags", "math_flags", "central_flags"],
                           extrasaction="ignore")
        w.writeheader()
        w.writerows(rejected)

    print(f"\n  Phase 2: {len(passed)} survive, {len(rejected)} rejected")
    return passed


# ============================================================
# PHASE 3: Auto deep dive
# ============================================================
def phase3(survivors):
    print(f"\n{'=' * 70}")
    print("PHASE 3: Automated Deep Dive (max 6)")
    print("=" * 70)

    # Pick top 6 by top1_usd_month
    targets = sorted(survivors, key=lambda x: x["top1_usd_month"], reverse=True)[:6]

    results = []
    for sn in targets:
        nid = sn["netuid"]
        name = sn["name"]
        clone_path = sn.get("clone_path", str(REPOS / f"sn{nid}" / "repo"))
        print(f"\n  === Deep Dive SN{nid} ({name}) ===")

        # Find validator and reward files
        val_files = []
        reward_files = []
        miner_files = []
        for root, dirs, files in os.walk(clone_path):
            dirs[:] = [d for d in dirs if d not in ('.git', 'venv', '.venv', '__pycache__')]
            for f in files:
                fl = f.lower()
                fp = os.path.join(root, f)
                if 'validator' in fl and fl.endswith('.py'):
                    val_files.append(fp)
                if 'reward' in fl and fl.endswith('.py'):
                    reward_files.append(fp)
                if 'miner' in fl and fl.endswith('.py'):
                    miner_files.append(fp)

        # Deep pattern search
        adversarial = []
        for pyf_list, label in [(val_files, "validator"), (reward_files, "reward")]:
            for pyf in pyf_list:
                try:
                    with open(pyf, 'r', errors='ignore') as fh:
                        content = fh.read()
                        lines = content.split('\n')
                except:
                    continue

                # Softmax temperature > 10
                for j, line in enumerate(lines):
                    if re.search(r'temperature\s*[=:]\s*(\d+)', line, re.IGNORECASE):
                        m = re.search(r'temperature\s*[=:]\s*(\d+)', line, re.IGNORECASE)
                        if m and int(m.group(1)) > 10:
                            adversarial.append(f"softmax temp={m.group(1)} in {os.path.basename(pyf)}:{j+1}")

                # Lambda/weight manipulation before set_weights
                if re.search(r'lambda.*weight|weight.*lambda', content, re.IGNORECASE):
                    adversarial.append(f"lambda weight manipulation in {os.path.basename(pyf)}")

                # Hardcoded UIDs
                uid_lists = re.findall(r'\[(\d+(?:\s*,\s*\d+){3,})\]', content)
                for ul in uid_lists:
                    nums = [int(x.strip()) for x in ul.split(',')]
                    if all(0 <= n <= 256 for n in nums) and len(nums) >= 4:
                        adversarial.append(f"hardcoded UID list {nums[:5]}... in {os.path.basename(pyf)}")

                # trust_remote_code
                if 'trust_remote_code=True' in content or 'trust_remote_code = True' in content:
                    adversarial.append(f"trust_remote_code=True in {os.path.basename(pyf)}")

                # Auto-updater
                if re.search(r'git\s+pull|git\s+reset.*hard|subprocess.*git', content, re.IGNORECASE):
                    adversarial.append(f"auto-updater in {os.path.basename(pyf)}")

                # Kill switches
                if re.search(r'min_alpha|min_stake.*amount|min_deposit', content, re.IGNORECASE):
                    adversarial.append(f"min_alpha/stake gate in {os.path.basename(pyf)}")

        # Economics
        emission = sn["emission_total_tao_day"]
        top1_tao = sn["top1_tao_day"]
        med_tao = sn["median_tao_day"]

        vast_cost_usd_month = 180  # RTX 4090 $0.25/h
        hetzner_cost_usd_month = 184 * 1.1  # GEX44 €184 * ~1.1 USD/EUR

        top1_usd_month = top1_tao * TAO_USD * 30
        med_usd_month = med_tao * TAO_USD * 30

        be_vast = (vast_cost_usd_month / med_usd_month * 30) if med_usd_month > 0 else float('inf')
        be_hetzner = (hetzner_cost_usd_month / med_usd_month * 30) if med_usd_month > 0 else float('inf')

        if med_usd_month > vast_cost_usd_month:
            econ_verdict = "VIABLE"
        elif med_usd_month > vast_cost_usd_month * 0.5:
            econ_verdict = "MARGINAL"
        else:
            econ_verdict = "IMPOSSIBLE"

        # Determine overall verdict
        if len(adversarial) == 0 and econ_verdict == "VIABLE":
            verdict = "GO"
        elif len(adversarial) <= 2 and econ_verdict in ("VIABLE", "MARGINAL"):
            verdict = "WATCH"
        else:
            verdict = "SKIP"

        result = {
            "netuid": nid, "name": name,
            "emission_tao_day": emission,
            "miners_scoring": sn["miners_scoring"],
            "gini": sn["gini"],
            "top1_usd_month": round(top1_usd_month, 2),
            "median_usd_month": round(med_usd_month, 2),
            "break_even_vast_days": round(be_vast, 1) if be_vast != float('inf') else "INFINITE",
            "break_even_hetzner_days": round(be_hetzner, 1) if be_hetzner != float('inf') else "INFINITE",
            "adversarial_flags": adversarial,
            "adversarial_count": len(adversarial),
            "econ_verdict": econ_verdict,
            "verdict": verdict,
            "hw_heavy": sn.get("hw_heavy", False),
            "github_url": sn.get("github_url", ""),
        }
        results.append(result)

        print(f"    Adversarial flags: {len(adversarial)}")
        for af in adversarial:
            print(f"      - {af}")
        print(f"    Econ: top1=${top1_usd_month:.0f}/m med=${med_usd_month:.0f}/m")
        print(f"    Break-even Vast: {result['break_even_vast_days']} days")
        print(f"    Verdict: {verdict} ({econ_verdict})")

        # Write individual review
        review_path = NOTES / f"v3_{nid}_codereview.md"
        with open(review_path, "w") as f:
            f.write(f"=== SUBNET {nid} — {name} ===\n")
            f.write(f"Status: active\n")
            f.write(f"GitHub: {sn.get('github_url', 'N/A')}\n")
            f.write(f"Hardware heavy: {'YES' if sn.get('hw_heavy') else 'NO'}\n\n")
            f.write(f"ECONOMIA REAL (TAO=${TAO_USD}):\n")
            f.write(f"  Emission total: {emission:.6f} TAO/day\n")
            f.write(f"  Miners scoring: {sn['miners_scoring']}\n")
            f.write(f"  Gini: {sn['gini']:.4f}\n")
            f.write(f"  Top 1 revenue: ${top1_usd_month:.0f}/month ({top1_tao:.6f} τ/day)\n")
            f.write(f"  Median revenue: ${med_usd_month:.0f}/month ({med_tao:.6f} τ/day)\n")
            f.write(f"  Break-even Vast.ai ($180/m): {result['break_even_vast_days']} days\n")
            f.write(f"  Break-even Hetzner (€184/m): {result['break_even_hetzner_days']} days\n")
            f.write(f"  VEREDICTO ECONÓMICO: {econ_verdict}\n\n")
            f.write(f"Adversarial flags ({len(adversarial)}):\n")
            for af in adversarial:
                f.write(f"  - {af}\n")
            f.write(f"\nBurn flags: {sn.get('burn_flags', 0)}\n")
            f.write(f"Math flags: {sn.get('math_flags', 0)}\n")
            f.write(f"Central flags: {sn.get('central_flags', 0)}\n")
            f.write(f"\nVeredicto: {verdict}\n")

    return results


# ============================================================
# FINAL REPORT
# ============================================================
def final_report(p0_count, p0_total, p1_count, p2_count, results):
    report_path = NOTES / "CAMINHO_A_V3_FINAL.md"

    with open(report_path, "w") as f:
        f.write("# CAMINHO A V3 — RELATÓRIO FINAL\n")
        f.write(f"**Date**: 2026-04-12\n")
        f.write(f"**TAO/USD**: ${TAO_USD}\n\n")
        f.write(f"## Funnel\n")
        f.write(f"- Total subnets queried: {p0_total}\n")
        f.write(f"- Phase 0 (economic): {p0_count} passed\n")
        f.write(f"- Phase 1 (flow+github): {p1_count} passed\n")
        f.write(f"- Phase 2 (code grep): {p2_count} passed\n")
        f.write(f"- Phase 3 (deep dive): {len(results)} analyzed\n\n")

        f.write(f"## Cross-Subnet Table\n\n")
        f.write(f"| netuid | name | top1 $/m | median $/m | BE vast (d) | adversarial | econ | verdict |\n")
        f.write(f"|--------|------|----------|------------|-------------|-------------|------|---------|\n")
        for r in sorted(results, key=lambda x: x["top1_usd_month"], reverse=True):
            f.write(f"| {r['netuid']} | {r['name']} | {r['top1_usd_month']:.0f} | {r['median_usd_month']:.0f} | {r['break_even_vast_days']} | {r['adversarial_count']} | {r['econ_verdict']} | {r['verdict']} |\n")

        go = [r for r in results if r["verdict"] == "GO"]
        watch = [r for r in results if r["verdict"] == "WATCH"]
        skip = [r for r in results if r["verdict"] == "SKIP"]

        f.write(f"\n## Verdicts\n")
        f.write(f"- GO: {len(go)} — {[r['netuid'] for r in go] if go else 'NONE'}\n")
        f.write(f"- WATCH: {len(watch)} — {[r['netuid'] for r in watch] if watch else 'NONE'}\n")
        f.write(f"- SKIP: {len(skip)} — {[r['netuid'] for r in skip] if skip else 'NONE'}\n")

        if go:
            best = max(go, key=lambda x: x["median_usd_month"])
            f.write(f"\n## Recomendação\n")
            f.write(f"Top pick: SN{best['netuid']} ({best['name']}) — median ${best['median_usd_month']:.0f}/month, ")
            f.write(f"break-even {best['break_even_vast_days']} days\n")
        elif watch:
            best = max(watch, key=lambda x: x["median_usd_month"])
            f.write(f"\n## Recomendação\n")
            f.write(f"Best WATCH: SN{best['netuid']} ({best['name']}) — needs manual review before commit\n")
        else:
            f.write(f"\n## Recomendação\n")
            f.write(f"NENHUMA subnet viável encontrada neste batch. O ecossistema Bittensor mining ")
            f.write(f"para participantes externos é economicamente hostil — a maioria das emissões ")
            f.write(f"são capturadas por insiders via mechanisms documentados nos deep dives anteriores.\n")

    print(f"\n  Report saved: {report_path}")


# ============================================================
# MAIN
# ============================================================
def main():
    print(f"TAO/USD = ${TAO_USD} (coingecko 2026-04-12)")
    print(f"Exclusions: {sorted(ANALYZED_EXCLUSIONS)}")
    print(f"Thresholds: top1>=${TOP1_MIN_USD_MONTH}$/m, uniform>={UNIFORM_MIN_USD_MONTH}$/m, miners>={MIN_MINERS_SCORING}\n")

    viable = phase0()
    p0_count = len(viable)
    p0_total = 128 - len(ANALYZED_EXCLUSIONS)

    if not viable:
        print("\nNo economically viable subnets found. Pipeline stops.")
        final_report(0, p0_total, 0, 0, [])
        return

    surv1 = phase1(viable)
    p1_count = len(surv1)

    if not surv1:
        print("\nNo Phase 1 survivors. Pipeline stops.")
        final_report(p0_count, p0_total, 0, 0, [])
        return

    surv2 = phase2(surv1)
    p2_count = len(surv2)

    if not surv2:
        print("\nNo Phase 2 survivors. Pipeline stops.")
        final_report(p0_count, p0_total, p1_count, 0, [])
        return

    results = phase3(surv2)

    final_report(p0_count, p0_total, p1_count, p2_count, results)

    # Final stdout
    go_list = [r for r in results if r["verdict"] == "GO"]
    watch_list = [r for r in results if r["verdict"] == "WATCH"]

    print(f"\n{'=' * 70}")
    print(f"CAMINHO A V3 — DONE")
    print(f"Subnets analisadas: {p0_total}")
    print(f"Sobreviveram filtro económico: {p0_count}")
    print(f"Sobreviveram filtro flow: {p1_count}")
    print(f"Sobreviveram filtro código: {p2_count}")
    print(f"Deep dived: {len(results)}")
    verdicts = ", ".join(f"SN{r['netuid']}={r['verdict']}" for r in results)
    print(f"Veredictos: {verdicts}")
    if go_list:
        best = max(go_list, key=lambda x: x["median_usd_month"])
        print(f"Recomendação: SN{best['netuid']} ({best['name']})")
    elif watch_list:
        best = max(watch_list, key=lambda x: x["median_usd_month"])
        print(f"Melhor WATCH: SN{best['netuid']} ({best['name']})")
    else:
        print(f"Veredictos GO/MARGINAL: NENHUMA")
    print(f"Path: {NOTES / 'CAMINHO_A_V3_FINAL.md'}")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
