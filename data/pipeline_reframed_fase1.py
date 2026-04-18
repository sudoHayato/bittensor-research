#!/usr/bin/env python3
"""
Caminho A v3 REFRAMED — Fase 1: Economic filter by infra tier.
Reuses neuron data from v3 run, queries only missing subnets.
"""
import json, csv, time, sys, statistics
import requests

sys.stdout.reconfigure(line_buffering=True)

API_KEY = "tao-1453ed31-5e73-4303-a634-9a98b576c3b5:84ae2f06"
BASE = "https://api.taostats.io/api"
HEADERS = {"Authorization": API_KEY}
TAO_USD = 270

OUTDIR = "~/bittensor-research/data"

# Infra tiers
TIER_VPS = 8
TIER_VPS_PLUS = 25
TIER_STORAGE = 50
MIN_PROFIT = 30  # minimum monthly profit to justify time

# Load candidates
with open(f"{OUTDIR}/operacional_candidates.json") as f:
    candidates = json.load(f)

# Load cached v3 neuron data
with open(f"{OUTDIR}/fase0_v3_results.json") as f:
    v3_cache = {s["netuid"]: s for s in json.load(f)}

# Also load failed v3 data (they may still have neuron stats)
# We need to re-query those that aren't in cache

session = requests.Session()
session.headers.update({"Authorization": API_KEY})
last_req = 0
delay = 12


def api_get(endpoint, params=None):
    global last_req, delay
    url = f"{BASE}/{endpoint}"
    for attempt in range(6):
        elapsed = time.time() - last_req
        if elapsed < delay:
            time.sleep(delay - elapsed)
        try:
            last_req = time.time()
            r = session.get(url, params=params, timeout=30)
            if r.status_code == 429:
                delay = min(delay + 5, 30)
                wait = 15 + 5 * attempt
                print(f"    [429] waiting {wait}s (delay={delay}s)")
                time.sleep(wait)
                continue
            if r.status_code == 200:
                delay = max(10, delay * 0.9)
                return r.json()
            return None
        except Exception:
            if attempt < 5:
                time.sleep(5)
                continue
            return None
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


def get_neuron_stats(netuid, emission_tao_day):
    """Fetch neurons and compute distribution stats."""
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
        return None

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
        return {"miners_scoring": 0}

    total_inc = sum(incentives)
    shares = [inc / total_inc for inc in incentives] if total_inc > 0 else incentives
    shares_sorted = sorted(shares, reverse=True)

    top1_share = shares_sorted[0]
    top10_shares = shares_sorted[:min(10, len(shares_sorted))]
    top10_avg_share = statistics.mean(top10_shares)
    median_share = statistics.median(shares)
    gini = gini_coefficient(shares)

    return {
        "miners_scoring": miners_scoring,
        "top1_share": round(top1_share, 6),
        "top10_avg_share": round(top10_avg_share, 6),
        "median_share": round(median_share, 6),
        "gini": round(gini, 4),
    }


# ============================================================
# Process each candidate
# ============================================================
print("=" * 70)
print("FASE 1 REFRAMED — Economic filter by infra tier")
print(f"TAO=${TAO_USD} | VPS=${TIER_VPS}/mo | VPS+=${TIER_VPS_PLUS}/mo | Storage=${TIER_STORAGE}/mo")
print("=" * 70)

results = []
need_query = [c["netuid"] for c in candidates if c["netuid"] not in v3_cache]
print(f"Cached: {len(candidates) - len(need_query)}, Need query: {len(need_query)}")

for i, c in enumerate(candidates):
    netuid = c["netuid"]
    name = c["name"]
    emission = c["emission_tao_day"]
    cats = c["categorias_match"]

    # Get neuron stats (from cache or API)
    if netuid in v3_cache:
        cached = v3_cache[netuid]
        stats = {
            "miners_scoring": cached["miners_scoring"],
            "top1_share": cached["top1_share"],
            "median_share": cached["median_share"],
            "gini": cached["gini"],
            "top10_avg_share": cached.get("top10_avg_share", cached["top1_share"]),
        }
        # Recalculate top10_avg if not available — estimate from top1 and median
        if "top10_avg_share" not in cached:
            # Rough estimate: geometric mean of top1 and median
            stats["top10_avg_share"] = round((cached["top1_share"] + cached["median_share"]) / 2, 6)
    else:
        print(f"  Querying neurons for SN{netuid} {name}...")
        stats = get_neuron_stats(netuid, emission)
        if stats is None or stats.get("miners_scoring", 0) == 0:
            print(f"  [{i+1}/{len(candidates)}] SN{netuid} {name}: NO DATA")
            results.append({
                "netuid": netuid, "name": name, "categorias": cats,
                "emission_tao_day": emission, "miners_scoring": 0,
                "viable_tier": "DEAD", "reason": "no_scoring_miners",
            })
            continue

    miners_scoring = stats["miners_scoring"]
    top1_share = stats["top1_share"]
    top10_avg_share = stats.get("top10_avg_share", top1_share)
    median_share = stats["median_share"]
    gini = stats["gini"]

    # Calculate revenues
    top1_usd_mo = top1_share * emission * TAO_USD * 30
    top10_usd_mo = top10_avg_share * emission * TAO_USD * 30
    median_usd_mo = median_share * emission * TAO_USD * 30

    # Determine viable tier
    if top10_usd_mo >= TIER_STORAGE + MIN_PROFIT:
        tier = "VIABLE_STORAGE"
    elif top10_usd_mo >= TIER_VPS_PLUS + MIN_PROFIT:
        tier = "VIABLE_VPS_PLUS"
    elif top10_usd_mo >= TIER_VPS + MIN_PROFIT:
        tier = "VIABLE_VPS"
    else:
        tier = "DEAD"

    row = {
        "netuid": netuid,
        "name": name,
        "categorias": cats,
        "emission_tao_day": round(emission, 4),
        "miners_scoring": miners_scoring,
        "top1_usd_mo": round(top1_usd_mo, 0),
        "top10_usd_mo": round(top10_usd_mo, 0),
        "median_usd_mo": round(median_usd_mo, 0),
        "gini": gini,
        "viable_tier": tier,
        "github_url": c.get("github_url", ""),
    }
    results.append(row)

    tag = tier if tier != "DEAD" else "DEAD"
    print(f"  [{i+1}/{len(candidates)}] SN{netuid} {name}: {tag} top10=${top10_usd_mo:,.0f} med=${median_usd_mo:,.0f} gini={gini:.3f}")

# Sort by viable_tier (VIABLE > DEAD) then by top10_usd_mo desc
tier_order = {"VIABLE_STORAGE": 0, "VIABLE_VPS_PLUS": 1, "VIABLE_VPS": 2, "DEAD": 3}
results.sort(key=lambda r: (tier_order.get(r["viable_tier"], 4), -r.get("top10_usd_mo", 0)))

# Write outputs
fields = ["netuid", "name", "categorias", "emission_tao_day", "miners_scoring",
          "top1_usd_mo", "top10_usd_mo", "median_usd_mo", "gini", "viable_tier", "github_url"]

with open(f"{OUTDIR}/reframed_fase1_all.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    w.writerows(results)

viable = [r for r in results if r["viable_tier"] != "DEAD"]
dead = [r for r in results if r["viable_tier"] == "DEAD"]

with open(f"{OUTDIR}/reframed_fase1_viable.json", "w") as f:
    json.dump(viable, f, indent=2)

# Summary
print(f"\n{'='*70}")
print(f"FASE 1 REFRAMED — RESULTADOS")
print(f"{'='*70}")
print(f"Total candidates:    {len(results)}")
print(f"VIABLE_STORAGE:      {sum(1 for r in results if r['viable_tier'] == 'VIABLE_STORAGE')}")
print(f"VIABLE_VPS_PLUS:     {sum(1 for r in results if r['viable_tier'] == 'VIABLE_VPS_PLUS')}")
print(f"VIABLE_VPS:          {sum(1 for r in results if r['viable_tier'] == 'VIABLE_VPS')}")
print(f"DEAD:                {sum(1 for r in results if r['viable_tier'] == 'DEAD')}")

if viable:
    print(f"\n{'='*70}")
    print(f"VIABLE CANDIDATES ({len(viable)}):")
    print(f"{'='*70}")
    hdr = f"{'SN':>4} {'name':<20} {'categorias':<25} {'tier':<15} {'top10$/mo':>10} {'med$/mo':>9} {'gini':>5}"
    print(hdr)
    print("-" * len(hdr))
    for r in viable:
        cats = r["categorias"][:23]
        print(f"{r['netuid']:>4} {r['name']:<20} {cats:<25} {r['viable_tier']:<15} {r['top10_usd_mo']:>10,.0f} {r['median_usd_mo']:>9,.0f} {r['gini']:>5.3f}")

if dead:
    print(f"\n--- DEAD ({len(dead)}) ---")
    for r in dead[:10]:
        print(f"  SN{r['netuid']} {r['name']}: top10=${r.get('top10_usd_mo',0):,.0f} med=${r.get('median_usd_mo',0):,.0f}")
    if len(dead) > 10:
        print(f"  ...and {len(dead)-10} more")

print(f"\nDone. {len(viable)} viable for Fase 2.")
