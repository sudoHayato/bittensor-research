#!/usr/bin/env python3
"""Fetch Bittensor subnet data from taostats.io API for shortlisted netuids."""

import json
import time
import statistics
import requests

API_KEY = "tao-1453ed31-5e73-4303-a634-9a98b576c3b5:84ae2f06"
BASE = "https://api.taostats.io/api"
HEADERS = {"Authorization": API_KEY}
NETUIDS = [51, 120, 5, 93, 17, 64, 4]
OUTPUT_FILE = "~/bittensor-research/data/shortlist_taostats_2026-04-11.json"
TIMEOUT = 30


def api_get(endpoint, params=None, max_retries=4):
    """Make a GET request to the API with retry on 429. On failure, print only status code."""
    url = f"{BASE}/{endpoint}"
    for attempt in range(max_retries):
        try:
            r = requests.get(url, headers=HEADERS, params=params, timeout=TIMEOUT)
            if r.status_code == 429:
                wait = 5 * (attempt + 1)
                print(f"  [RATE LIMITED] {endpoint} -> waiting {wait}s (attempt {attempt+1}/{max_retries})")
                time.sleep(wait)
                continue
            if r.status_code != 200:
                print(f"  [ERROR] {endpoint} -> status {r.status_code}")
                return None
            return r.json()
        except requests.exceptions.RequestException as e:
            print(f"  [ERROR] {endpoint} -> request failed: {type(e).__name__}")
            return None
    print(f"  [ERROR] {endpoint} -> exhausted retries (429)")
    return None


def rao_to_tao(rao_val):
    """Convert rao (int or string) to TAO float. 1 TAO = 1e9 rao."""
    if rao_val is None:
        return None
    try:
        return float(rao_val) / 1e9
    except (ValueError, TypeError):
        return None


def compute_gini(values):
    """Compute Gini coefficient for a list of non-negative values."""
    values = sorted(values)
    n = len(values)
    if n == 0 or sum(values) == 0:
        return 0.0
    cumsum = 0.0
    weighted_sum = 0.0
    for i, v in enumerate(values):
        cumsum += v
        weighted_sum += (i + 1) * v
    return (2 * weighted_sum) / (n * cumsum) - (n + 1) / n


def fetch_subnet_data(netuid):
    """Fetch all data for a single subnet."""
    print(f"Fetching netuid {netuid}...")
    result = {"netuid": netuid}

    # 1. Subnet latest
    time.sleep(2)
    data = api_get("subnet/latest/v1", {"netuid": netuid})
    if data and data.get("data"):
        s = data["data"][0]
        result["emission_raw"] = s.get("emission")
        result["projected_emission_tao"] = float(s.get("projected_emission", 0))
        result["registration_cost_rao"] = s.get("registration_cost")
        result["neuron_registration_cost_rao"] = s.get("neuron_registration_cost")
        result["active_miners"] = s.get("active_miners")
        result["active_validators"] = s.get("active_validators")
        result["validators"] = s.get("validators")
        result["active_keys"] = s.get("active_keys")
        result["max_neurons"] = s.get("max_neurons")
        result["tempo"] = s.get("tempo")
        result["net_flow_1_day"] = rao_to_tao(s.get("net_flow_1_day"))
        result["net_flow_7_days"] = rao_to_tao(s.get("net_flow_7_days"))
        result["net_flow_30_days"] = rao_to_tao(s.get("net_flow_30_days"))
        result["ema_tao_flow"] = s.get("ema_tao_flow")

        # Compute emission per day: projected_emission is per-tempo-block
        # emission field is rao per block; projected_emission is TAO per tempo
        # 7200 blocks/day, tempo is blocks per epoch
        tempo = s.get("tempo", 360)
        epochs_per_day = 7200 / tempo if tempo else 20
        result["emission_tao_day"] = result["projected_emission_tao"] * epochs_per_day

    # 2. Subnet history (7d)
    time.sleep(2)
    hist = api_get("subnet/history/v1", {"netuid": netuid, "period": "7d"})
    if hist and hist.get("data"):
        result["history_records"] = len(hist["data"])
        # Get earliest and latest for comparison
        earliest = hist["data"][-1]
        latest = hist["data"][0]
        result["history_earliest_block"] = earliest.get("block_number")
        result["history_latest_block"] = latest.get("block_number")

    # 3. Subnet metadata (for name)
    time.sleep(2)
    meta = api_get("subnet/metadata/v1", {"netuid": netuid})
    if meta and meta.get("data"):
        m = meta["data"][0]
        result["name"] = m.get("name", "Unknown")
    else:
        result["name"] = "Unknown"

    # 4. DTAO pool data (for tao_in, alpha_in, price)
    time.sleep(2)
    pool = api_get("dtao/pool/latest/v1", {"netuid": netuid})
    if pool and pool.get("data"):
        p = pool["data"][0]
        result["total_tao_rao"] = p.get("total_tao")
        result["total_tao"] = rao_to_tao(p.get("total_tao"))
        result["total_alpha_rao"] = p.get("total_alpha")
        result["total_alpha"] = rao_to_tao(p.get("total_alpha"))
        result["alpha_in_pool"] = rao_to_tao(p.get("alpha_in_pool"))
        result["alpha_staked"] = rao_to_tao(p.get("alpha_staked"))
        result["price"] = float(p.get("price", 0))
        result["market_cap"] = p.get("market_cap")
        result["liquidity_rao"] = p.get("liquidity")
        result["liquidity"] = rao_to_tao(p.get("liquidity"))
        result["rank"] = p.get("rank")
        result["fear_and_greed_index"] = p.get("fear_and_greed_index")
        result["price_change_1_day"] = p.get("price_change_1_day")
        result["price_change_1_week"] = p.get("price_change_1_week")
        result["price_change_1_month"] = p.get("price_change_1_month")
        # Override name from pool if metadata failed
        if result["name"] == "Unknown" and p.get("name"):
            result["name"] = p["name"]

    return result


def fetch_miner_stats(netuid=51):
    """Fetch miner emission stats for netuid 51."""
    print(f"Fetching miner data for netuid {netuid}...")
    time.sleep(2)
    data = api_get("neuron/latest/v1", {"netuid": netuid, "limit": 256})
    if not data or not data.get("data"):
        return None

    neurons = data["data"]
    # Separate miners (no validator_permit or validator_rank is None)
    miners = [n for n in neurons if not n.get("validator_permit")]
    validators = [n for n in neurons if n.get("validator_permit")]

    emissions = [float(n.get("emission", 0)) for n in miners if n.get("emission")]
    emissions_tao = [rao_to_tao(e) for e in emissions]
    emissions.sort(reverse=True)
    emissions_tao.sort(reverse=True)

    if not emissions:
        return {"error": "no miner emissions found"}

    stats = {
        "total_neurons": len(neurons),
        "miner_count": len(miners),
        "validator_count": len(validators),
        "top1_emission_rao": emissions[0],
        "top1_emission_tao": emissions_tao[0],
        "top10_avg_emission_rao": statistics.mean(emissions[:10]) if len(emissions) >= 10 else statistics.mean(emissions),
        "top10_avg_emission_tao": statistics.mean(emissions_tao[:10]) if len(emissions_tao) >= 10 else statistics.mean(emissions_tao),
        "median_emission_rao": statistics.median(emissions),
        "median_emission_tao": statistics.median(emissions_tao),
        "gini_coefficient": round(compute_gini(emissions), 4),
    }
    return stats


def print_ascii_table(subnets):
    """Print a formatted ASCII table."""
    # Columns: netuid, name, emission_day, flow_7d, flow_30d, miner_count
    headers = ["netuid", "name", "emission_day", "flow_7d", "flow_30d", "miner_count"]
    rows = []
    for s in subnets:
        rows.append([
            str(s["netuid"]),
            s.get("name", "?")[:20],
            f"{s.get('emission_tao_day', 0):.2f}",
            f"{s.get('net_flow_7_days', 0):.1f}" if s.get('net_flow_7_days') is not None else "N/A",
            f"{s.get('net_flow_30_days', 0):.1f}" if s.get('net_flow_30_days') is not None else "N/A",
            str(s.get("active_miners", "?")),
        ])

    # Compute column widths
    widths = [max(len(h), max(len(r[i]) for r in rows)) for i, h in enumerate(headers)]

    def fmt_row(vals):
        return "| " + " | ".join(v.ljust(w) for v, w in zip(vals, widths)) + " |"

    sep = "+-" + "-+-".join("-" * w for w in widths) + "-+"

    print("\n" + sep)
    print(fmt_row(headers))
    print(sep)
    for r in rows:
        print(fmt_row(r))
    print(sep)


def main():
    results = {"subnets": [], "miner_stats_sn51": None, "fetch_date": "2026-04-11"}

    # Fetch data for each netuid
    for netuid in NETUIDS:
        subnet_data = fetch_subnet_data(netuid)
        results["subnets"].append(subnet_data)

    # Fetch miner stats for SN51
    miner_stats = fetch_miner_stats(51)
    results["miner_stats_sn51"] = miner_stats

    # Save to JSON (ensure no API key leaks)
    output = json.dumps(results, indent=2, default=str)
    assert API_KEY not in output, "API key detected in output!"
    with open(OUTPUT_FILE, "w") as f:
        f.write(output)
    print(f"\nSaved results to {OUTPUT_FILE}")

    # Print ASCII table
    print_ascii_table(results["subnets"])

    # Print miner stats for SN51
    if miner_stats:
        print(f"\n--- SN51 Miner Emission Stats ---")
        print(f"  Miners: {miner_stats['miner_count']}, Validators: {miner_stats['validator_count']}")
        print(f"  Top-1 emission:     {miner_stats['top1_emission_tao']:.4f} TAO")
        print(f"  Top-10 avg emission: {miner_stats['top10_avg_emission_tao']:.4f} TAO")
        print(f"  Median emission:    {miner_stats['median_emission_tao']:.4f} TAO")
        print(f"  Gini coefficient:   {miner_stats['gini_coefficient']:.4f}")


if __name__ == "__main__":
    main()
