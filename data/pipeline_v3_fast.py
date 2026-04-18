#!/usr/bin/env python3
"""
Caminho A v3 — Fast pipeline: uses sessions, adaptive rate limiting.
"""
import json, csv, time, sys, statistics
import requests

sys.stdout.reconfigure(line_buffering=True)

API_KEY = "tao-1453ed31-5e73-4303-a634-9a98b576c3b5:84ae2f06"
BASE = "https://api.taostats.io/api"
TAO_USD = 320
ANALYZED_EXCLUSIONS = {0, 4, 5, 17, 32, 51, 64, 75, 83, 93, 114, 120, 2}
OUTDIR = "~/bittensor-research/data"

with open(f"{OUTDIR}/subnets_snapshot_2026-04-11.json") as f:
    snapshot = {s["netuid"]: s for s in json.load(f)}

# Use session for connection reuse
session = requests.Session()
session.headers.update({"Authorization": API_KEY})

# Adaptive rate limiter
last_request_time = 0
min_delay = 10  # 10s between requests avoids most 429s
max_delay = 30
current_delay = 10


def api_get(endpoint, params=None):
    global last_request_time, current_delay
    url = f"{BASE}/{endpoint}"

    for attempt in range(8):
        # Enforce minimum delay between requests
        elapsed = time.time() - last_request_time
        if elapsed < current_delay:
            time.sleep(current_delay - elapsed)

        try:
            last_request_time = time.time()
            r = session.get(url, params=params, timeout=30)

            if r.status_code == 429:
                current_delay = min(current_delay + 5, max_delay)
                wait = 15 + (5 * attempt)  # fixed backoff: 15, 20, 25, 30...
                print(f"    [429] waiting {wait}s (delay={current_delay:.0f}s)")
                time.sleep(wait)
                continue

            if r.status_code == 200:
                # Success — slowly reduce delay
                current_delay = max(min_delay, current_delay * 0.9)
                return r.json()

            return None
        except Exception as e:
            if attempt < 7:
                time.sleep(5)
                continue
            print(f"    [ERR] {endpoint}: {e}")
            return None
    return None


def rao_to_tao(rao):
    try:
        return float(rao) / 1e9
    except:
        return None


def gini_coefficient(values):
    if not values or len(values) < 2:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    total = sum(sorted_vals)
    if total == 0:
        return 0.0
    gini_sum = sum((2 * (i + 1) - n - 1) * v for i, v in enumerate(sorted_vals))
    return gini_sum / (n * total)


# ============================================================
# STEP 1: Bulk subnet query + pre-filter
# ============================================================
print("=" * 70)
print("STEP 1: Bulk subnet query + pre-filter")
print("=" * 70)

subnet_api = api_get("subnet/latest/v1", {"limit": "200"})
if not subnet_api or not subnet_api.get("data"):
    print("FATAL: Cannot get subnet data")
    sys.exit(1)

api_subnets = {s["netuid"]: s for s in subnet_api["data"]}
print(f"Got {len(api_subnets)} subnets from API")

candidates = []
auto_fail = []

for netuid in sorted(range(1, 129)):
    if netuid in ANALYZED_EXCLUSIONS:
        continue
    snap = snapshot.get(netuid, {})
    api_s = api_subnets.get(netuid, {})
    name = snap.get("name", f"SN{netuid}")
    emission = snap.get("emission_tao_day", 0) or 0
    active_miners = api_s.get("active_miners", 0) or 0
    github = snap.get("github")
    flow_30d = rao_to_tao(api_s.get("net_flow_30_days"))

    if emission <= 0:
        auto_fail.append({"netuid": netuid, "name": name, "reason": "zero_emission"})
        continue
    if active_miners < 5:
        auto_fail.append({"netuid": netuid, "name": name,
                          "reason": f"active_miners={active_miners}<5"})
        continue
    max_uniform = (emission / active_miners) * TAO_USD * 30
    if max_uniform < 50:
        auto_fail.append({"netuid": netuid, "name": name,
                          "reason": f"uniform=${max_uniform:.0f}<50"})
        continue

    candidates.append({
        "netuid": netuid, "name": name, "emission": emission,
        "active_miners": active_miners, "max_uniform": max_uniform,
        "github": github, "net_flow_30d": flow_30d,
    })

print(f"Auto-failed: {len(auto_fail)}, Need neuron query: {len(candidates)}")

# ============================================================
# STEP 2: Neuron queries
# ============================================================
print(f"\n{'='*70}")
print(f"STEP 2: Querying neurons for {len(candidates)} subnets")
print("=" * 70)

fase0_pass = []
fase0_fail = []
errors = []
start_time = time.time()

for i, c in enumerate(candidates):
    netuid = c["netuid"]
    name = c["name"]
    emission = c["emission"]

    all_neurons = []
    for page in [1, 2]:
        data = api_get("neuron/latest/v1", {"netuid": str(netuid), "limit": "200", "page": str(page)})
        if not data or not data.get("data"):
            break
        all_neurons.extend(data["data"])
        pag = data.get("pagination", {})
        if pag.get("next_page") is None:
            break

    if not all_neurons:
        errors.append({"netuid": netuid, "name": name, "reason": "no_neuron_data"})
        print(f"  [{i+1}/{len(candidates)}] SN{netuid} {name}: ERR no neurons")
        continue

    miners = [n for n in all_neurons if not n.get("validator_permit")]

    incentives = []
    for m in miners:
        try:
            inc = float(m.get("incentive", 0) or 0)
        except:
            inc = 0
        if inc > 0:
            incentives.append(inc)

    if not incentives:
        emissions_raw = []
        for m in miners:
            try:
                em = float(m.get("emission", 0) or 0)
            except:
                em = 0
            if em > 0:
                emissions_raw.append(em)
        if emissions_raw:
            total_em = sum(emissions_raw)
            incentives = [e / total_em for e in emissions_raw] if total_em > 0 else []

    miners_scoring = len(incentives)

    if miners_scoring == 0:
        fase0_fail.append({"netuid": netuid, "name": name,
                          "reason": f"no_scoring_miners (miners={len(miners)})"})
        print(f"  [{i+1}/{len(candidates)}] SN{netuid} {name}: FAIL no scoring")
        continue

    total_inc = sum(incentives)
    shares = [inc / total_inc for inc in incentives] if total_inc > 0 else incentives

    max_uniform_usd_month = (emission / miners_scoring) * TAO_USD * 30
    top1_share = max(shares)
    top1_usd_month = top1_share * emission * TAO_USD * 30
    median_share = statistics.median(shares)
    median_usd_month = median_share * emission * TAO_USD * 30
    gini = gini_coefficient(shares)

    row = {
        "netuid": netuid, "name": name,
        "emission_total_tao_day": round(emission, 4),
        "miners_scoring": miners_scoring,
        "max_uniform_usd_month": round(max_uniform_usd_month, 2),
        "top1_usd_month": round(top1_usd_month, 2),
        "median_usd_month": round(median_usd_month, 2),
        "gini": round(gini, 4),
        "github_url": c["github"] or "",
        "top1_share": round(top1_share, 6),
        "median_share": round(median_share, 6),
        "net_flow_30d": c["net_flow_30d"],
        "active_miners_api": c["active_miners"],
    }

    pass_top1 = top1_usd_month >= 300
    pass_uniform = max_uniform_usd_month >= 50
    pass_miners = miners_scoring >= 5

    if pass_top1 and pass_uniform and pass_miners:
        fase0_pass.append(row)
        tag = "PASS"
    else:
        reasons = []
        if not pass_top1: reasons.append(f"top1=${top1_usd_month:.0f}<300")
        if not pass_uniform: reasons.append(f"uniform=${max_uniform_usd_month:.0f}<50")
        if not pass_miners: reasons.append(f"miners={miners_scoring}<5")
        fase0_fail.append({"netuid": netuid, "name": name,
                          "reason": "; ".join(reasons),
                          "top1_usd_month": round(top1_usd_month, 0),
                          "miners_scoring": miners_scoring})
        tag = "FAIL"

    elapsed = time.time() - start_time
    rate = (i + 1) / elapsed * 60 if elapsed > 0 else 0
    eta = (len(candidates) - i - 1) / rate if rate > 0 else 0
    print(f"  [{i+1}/{len(candidates)}] SN{netuid} {name}: {tag} scoring={miners_scoring} top1=${top1_usd_month:,.0f}/mo gini={gini:.3f} [{rate:.1f}/min, ETA {eta:.0f}m]")

fase0_pass.sort(key=lambda r: r["top1_usd_month"], reverse=True)

# Write outputs
fields0 = ["netuid", "name", "emission_total_tao_day", "miners_scoring",
           "max_uniform_usd_month", "top1_usd_month", "median_usd_month",
           "gini", "github_url"]

with open(f"{OUTDIR}/fase0_v3_economically_viable.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields0, extrasaction="ignore")
    w.writeheader()
    w.writerows(fase0_pass)

all_fails = auto_fail + fase0_fail
with open(f"{OUTDIR}/fase0_v3_failed.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["netuid", "name", "reason", "top1_usd_month", "miners_scoring"])
    w.writeheader()
    w.writerows(all_fails)

with open(f"{OUTDIR}/fase0_v3_results.json", "w") as f:
    json.dump(fase0_pass, f, indent=2)

# Summary
print(f"\n{'='*70}")
print(f"FASE 0 v3 RESULTS — FILTRO ECONÓMICO HARD (TAO=${TAO_USD})")
print(f"{'='*70}")
print(f"Total subnets (excl. analyzed):   {len(auto_fail) + len(candidates)}")
print(f"Auto-failed (pre-filter):         {len(auto_fail)}")
print(f"Neuron-queried:                   {len(candidates)}")
print(f"Passaram filtro económico:        {len(fase0_pass)}")
print(f"Falharam (pre+neuron):            {len(all_fails)}")
print(f"Erros API:                        {len(errors)}")
print(f"Tempo total:                      {(time.time()-start_time)/60:.1f} min")

if fase0_pass:
    top_n = min(20, len(fase0_pass))
    print(f"\n{'='*70}")
    print(f"TOP {top_n} ECONOMICAMENTE VIÁVEIS:")
    print(f"{'='*70}")
    hdr = f"{'SN':>4} {'name':<22} {'emit/d':>7} {'min#':>4} {'top1$/mo':>10} {'med$/mo':>9} {'unif$/mo':>9} {'gini':>5}"
    print(hdr)
    print("-" * len(hdr))
    for r in fase0_pass[:top_n]:
        print(f"{r['netuid']:>4} {r['name']:<22} {r['emission_total_tao_day']:>7.1f} {r['miners_scoring']:>4} {r['top1_usd_month']:>10,.0f} {r['median_usd_month']:>9,.0f} {r['max_uniform_usd_month']:>9,.0f} {r['gini']:>5.3f}")

# Fase 1: Flow + GitHub
print(f"\n{'='*70}")
print(f"FASE 1 v3 — FILTRO FLOW + GITHUB")
print(f"{'='*70}")

fase1_pass = []
fase1_fail = []

for r in fase0_pass:
    reasons = []
    flow = r.get("net_flow_30d")
    if flow is not None and flow < -1000:
        reasons.append(f"flow_30d={flow:.0f}<-1000")
    if not r.get("github_url"):
        reasons.append("no_github")
    if reasons:
        fase1_fail.append({"netuid": r["netuid"], "name": r["name"],
                          "reason": "; ".join(reasons), "top1_usd_month": r["top1_usd_month"]})
    else:
        fase1_pass.append(r)

with open(f"{OUTDIR}/fase1_v3_survivors.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields0, extrasaction="ignore")
    w.writeheader()
    w.writerows(fase1_pass)

with open(f"{OUTDIR}/fase1_v3_rejected.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["netuid", "name", "reason", "top1_usd_month"])
    w.writeheader()
    w.writerows(fase1_fail)

with open(f"{OUTDIR}/fase1_v3_results.json", "w") as f:
    json.dump(fase1_pass, f, indent=2)

print(f"Fase 1 input:    {len(fase0_pass)}")
print(f"Fase 1 survived: {len(fase1_pass)}")
print(f"Fase 1 rejected: {len(fase1_fail)}")

if fase1_fail:
    print("\nRejected:")
    for r in fase1_fail:
        print(f"  SN{r['netuid']} {r['name']}: {r['reason']}")

if fase1_pass:
    print(f"\nFase 1 survivors:")
    for r in fase1_pass:
        gh = (r.get("github_url") or "")[:50]
        print(f"  SN{r['netuid']:>3} {r['name']:<22} top1=${r['top1_usd_month']:>10,.0f} med=${r['median_usd_month']:>8,.0f} gini={r['gini']:.3f}")

print(f"\nDone. {len(fase1_pass)} subnets ready for Fase 2.")
