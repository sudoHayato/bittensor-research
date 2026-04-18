#!/usr/bin/env python3
"""
Caminho A v3 — Fase 0: Filtro económico HARD
Query taostats neuron/latest para cada subnet, calcular métricas, filtrar.
"""

import json, csv, time, sys, statistics, os
import requests

# Force unbuffered output
sys.stdout.reconfigure(line_buffering=True)

API_KEY = "tao-1453ed31-5e73-4303-a634-9a98b576c3b5:84ae2f06"
BASE = "https://api.taostats.io/api"
HEADERS = {"Authorization": API_KEY}
TAO_USD = 320  # Verified via web search Apr 12 2026

ANALYZED_EXCLUSIONS = {0, 4, 5, 17, 32, 51, 64, 75, 83, 93, 114, 120, 2}

# Load snapshot for names, emission, github
with open("~/bittensor-research/data/subnets_snapshot_2026-04-11.json") as f:
    snapshot = {s["netuid"]: s for s in json.load(f)}


def api_get(endpoint, params=None, max_retries=4):
    url = f"{BASE}/{endpoint}"
    for attempt in range(max_retries):
        try:
            r = requests.get(url, headers=HEADERS, params=params, timeout=30)
            if r.status_code == 429:
                wait = 3 * (attempt + 1)
                print(f"  [429] {endpoint} netuid={params.get('netuid','')} waiting {wait}s")
                time.sleep(wait)
                continue
            if r.status_code != 200:
                return None
            return r.json()
        except Exception:
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            return None
    return None


def fetch_all_neurons(netuid):
    """Fetch all neurons for a subnet (paginated)."""
    all_neurons = []
    page = 1
    while True:
        data = api_get("neuron/latest/v1", {"netuid": str(netuid), "limit": "200", "page": str(page)})
        if not data or not data.get("data"):
            break
        all_neurons.extend(data["data"])
        pag = data.get("pagination", {})
        if pag.get("next_page") is None:
            break
        page += 1
        time.sleep(0.1)
    return all_neurons


def gini_coefficient(values):
    if not values or len(values) < 2:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    total = sum(sorted_vals)
    if total == 0:
        return 0.0
    cumsum = 0
    gini_sum = 0
    for i, v in enumerate(sorted_vals):
        cumsum += v
        gini_sum += (2 * (i + 1) - n - 1) * v
    return gini_sum / (n * total)


results = []
failed_economic = []
errors = []

target_netuids = sorted([n for n in range(1, 129) if n not in ANALYZED_EXCLUSIONS])
print(f"Querying {len(target_netuids)} subnets for neuron data...")

for i, netuid in enumerate(target_netuids):
    snap = snapshot.get(netuid, {})
    name = snap.get("name", f"SN{netuid}")
    emission_tao_day = snap.get("emission_tao_day", 0) or 0
    github_url = snap.get("github")

    if emission_tao_day <= 0:
        failed_economic.append({
            "netuid": netuid, "name": name,
            "reason": f"zero_emission ({emission_tao_day})"
        })
        if (i + 1) % 20 == 0:
            print(f"  ...{i+1}/{len(target_netuids)} (skipped {name} - zero emission)")
        continue

    neurons = fetch_all_neurons(netuid)
    if not neurons:
        errors.append({"netuid": netuid, "name": name, "reason": "api_error_no_neurons"})
        print(f"  [ERR] SN{netuid} {name}: no neuron data")
        continue

    # Separate miners (no validator_permit) from validators
    miners = [n for n in neurons if not n.get("validator_permit")]

    # Get incentive values - these are decimal strings
    incentives = []
    for m in miners:
        try:
            inc = float(m.get("incentive", 0) or 0)
        except (ValueError, TypeError):
            inc = 0
        if inc > 0:
            incentives.append(inc)

    miners_scoring = len(incentives)

    if miners_scoring == 0:
        # Maybe try emission-based approach as fallback
        emissions = []
        for m in miners:
            try:
                em = float(m.get("emission", 0) or 0)
            except (ValueError, TypeError):
                em = 0
            if em > 0:
                emissions.append(em)
        if emissions:
            # Use emission as proxy for incentive
            total_em = sum(emissions)
            incentives = [e / total_em for e in emissions] if total_em > 0 else []
            miners_scoring = len(incentives)

    if miners_scoring == 0:
        failed_economic.append({
            "netuid": netuid, "name": name,
            "reason": f"no_scoring_miners (total_miners={len(miners)}, total_neurons={len(neurons)})"
        })
        continue

    # Calculate metrics
    # incentives are shares (already normalized or we normalize them)
    total_incentive = sum(incentives)
    if total_incentive > 0:
        # Normalize to shares summing to 1
        shares = [inc / total_incentive for inc in incentives]
    else:
        shares = incentives

    max_uniform_rev_tao_day = emission_tao_day / max(miners_scoring, 1)
    max_uniform_rev_usd_month = max_uniform_rev_tao_day * TAO_USD * 30

    top1_share = max(shares) if shares else 0
    top1_rev_tao_day = top1_share * emission_tao_day
    top1_rev_usd_month = top1_rev_tao_day * TAO_USD * 30

    median_share = statistics.median(shares) if shares else 0
    median_rev_usd_month = median_share * emission_tao_day * TAO_USD * 30

    gini = gini_coefficient(shares)

    row = {
        "netuid": netuid,
        "name": name,
        "emission_total_tao_day": round(emission_tao_day, 4),
        "miners_scoring": miners_scoring,
        "max_uniform_usd_month": round(max_uniform_rev_usd_month, 2),
        "top1_usd_month": round(top1_rev_usd_month, 2),
        "median_usd_month": round(median_rev_usd_month, 2),
        "gini": round(gini, 4),
        "github_url": github_url or "",
        # Keep raw data for Fase 1+
        "top1_share": round(top1_share, 6),
        "median_share": round(median_share, 6),
    }

    # HARD economic filter
    pass_top1 = top1_rev_usd_month >= 300
    pass_uniform = max_uniform_rev_usd_month >= 50
    pass_miners = miners_scoring >= 5

    if pass_top1 and pass_uniform and pass_miners:
        results.append(row)
    else:
        reasons = []
        if not pass_top1:
            reasons.append(f"top1=${top1_rev_usd_month:.0f}<300")
        if not pass_uniform:
            reasons.append(f"uniform=${max_uniform_rev_usd_month:.0f}<50")
        if not pass_miners:
            reasons.append(f"miners={miners_scoring}<5")
        failed_economic.append({
            "netuid": netuid, "name": name,
            "reason": "; ".join(reasons),
            "top1_usd_month": round(top1_rev_usd_month, 0),
            "uniform_usd_month": round(max_uniform_rev_usd_month, 0),
        })

    # Progress & rate limiting
    print(f"  [{i+1}/{len(target_netuids)}] SN{netuid} {name}: scoring={miners_scoring} top1=${top1_rev_usd_month:.0f}/mo {'PASS' if (pass_top1 and pass_uniform and pass_miners) else 'FAIL'}")
    time.sleep(0.15)

# Sort by top1_usd_month desc
results.sort(key=lambda r: r["top1_usd_month"], reverse=True)

# Write CSV
outpath = "~/bittensor-research/data/fase0_v3_economically_viable.csv"
fields = ["netuid", "name", "emission_total_tao_day", "miners_scoring",
          "max_uniform_usd_month", "top1_usd_month", "median_usd_month",
          "gini", "github_url"]
with open(outpath, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    w.writerows(results)

# Write failed filter log
failpath = "~/bittensor-research/data/fase0_v3_failed.csv"
with open(failpath, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["netuid", "name", "reason", "top1_usd_month", "uniform_usd_month"])
    w.writeheader()
    w.writerows(failed_economic)

# Print summary
print(f"\n{'='*70}")
print(f"FASE 0 v3 — FILTRO ECONÓMICO HARD (TAO=${TAO_USD})")
print(f"{'='*70}")
print(f"Subnets queryadas:         {len(target_netuids)}")
print(f"Passaram filtro económico: {len(results)}")
print(f"Falharam filtro económico: {len(failed_economic)}")
print(f"Erros API:                 {len(errors)}")
print(f"\nFicheiro: {outpath}")

if results:
    top_n = min(15, len(results))
    print(f"\n{'='*70}")
    print(f"TOP {top_n} ECONOMICAMENTE VIÁVEIS:")
    print(f"{'='*70}")
    hdr = f"{'SN':>4} {'name':<22} {'emit/day':>9} {'miners':>6} {'top1$/mo':>10} {'med$/mo':>9} {'unif$/mo':>9} {'gini':>5}"
    print(hdr)
    print("-" * len(hdr))
    for r in results[:top_n]:
        print(f"{r['netuid']:>4} {r['name']:<22} {r['emission_total_tao_day']:>9.2f} {r['miners_scoring']:>6} {r['top1_usd_month']:>10,.0f} {r['median_usd_month']:>9,.0f} {r['max_uniform_usd_month']:>9,.0f} {r['gini']:>5.3f}")

# Save results as JSON too for next phases
with open("~/bittensor-research/data/fase0_v3_results.json", "w") as f:
    json.dump(results, f, indent=2)

print(f"\nDone. {len(results)} subnets passed to Fase 1.")
