#!/usr/bin/env python3
"""
Scrape Bittensor subnet data from subtensor finney chain.
Uses bittensor SDK for proper SCALE decoding.
Read-only - no wallet required.
"""

import json
import csv
import asyncio
import re
from datetime import datetime

DATE = "2026-04-11"
OUTPUT_DIR = "~/bittensor-research/data"
SUBTENSOR_ENDPOINT = "wss://entrypoint-finney.opentensor.ai:443"

BLOCKS_PER_DAY = 7200  # 12s blocks


def parse_balance(val):
    """Parse a bittensor Balance object to float, stripping any unit suffix."""
    if val is None:
        return None
    s = str(val)
    # Remove any unicode chars, Greek letters (τ, α, β, etc.), commas
    s = re.sub(r'[^\d.\-eE]', '', s)
    try:
        return float(s)
    except:
        return None


async def main():
    print("=" * 60)
    print(f"Bittensor Subnet Scraper - {DATE}")
    print("=" * 60)

    import bittensor as bt

    print(f"\nBittensor version: {bt.__version__}")
    print(f"Connecting to {SUBTENSOR_ENDPOINT}...")

    async with bt.AsyncSubtensor(network=SUBTENSOR_ENDPOINT) as sub:
        print("Connected!")

        block = await sub.substrate.get_block_number()
        print(f"Current block: {block}")

        print("\nFetching all subnets info...")
        all_subnets = await sub.all_subnets()
        print(f"  Found {len(all_subnets)} subnets")

        subnets_data = []

        for sn in all_subnets:
            netuid = sn.netuid
            name = sn.subnet_name or f"SN{netuid}"
            symbol = sn.symbol or ""
            tempo = int(sn.tempo) if sn.tempo else 360

            # Parse balance values
            tao_in = parse_balance(sn.tao_in) or 0
            alpha_in = parse_balance(sn.alpha_in) or 0
            alpha_out = parse_balance(sn.alpha_out) or 0
            price = parse_balance(sn.price) or 0
            volume = parse_balance(sn.subnet_volume) or 0
            pending_alpha = parse_balance(sn.pending_alpha_emission) or 0
            pending_root = parse_balance(sn.pending_root_emission) or 0
            alpha_out_emission = parse_balance(sn.alpha_out_emission) or 0
            tao_in_emission = parse_balance(sn.tao_in_emission) or 0

            # Emission per day estimate
            # pending emissions accumulate between tempo steps
            # tempos per day = BLOCKS_PER_DAY / tempo
            tempos_per_day = BLOCKS_PER_DAY / tempo if tempo > 0 else 0
            # Total emission per day in TAO:
            # alpha_out_emission * price gives TAO equivalent per tempo step
            emission_alpha_day = alpha_out_emission * tempos_per_day
            emission_tao_day = emission_alpha_day * price + tao_in_emission * tempos_per_day
            # Also estimate from pending (accumulated since last step)
            blocks_since = sn.blocks_since_last_step or 1
            if blocks_since > 0 and pending_alpha > 0:
                pending_rate_per_block = pending_alpha / blocks_since
                emission_alpha_day_est = pending_rate_per_block * BLOCKS_PER_DAY
                emission_tao_day_est = emission_alpha_day_est * price
                # Use the higher estimate
                if emission_tao_day_est > emission_tao_day:
                    emission_tao_day = emission_tao_day_est
                    emission_alpha_day = emission_alpha_day_est

            # Market cap: total alpha supply * price in TAO
            total_alpha = alpha_in + alpha_out
            market_cap_tao = total_alpha * price

            # Identity-based info
            github = None
            desc = None
            identity = sn.subnet_identity
            if identity:
                github = getattr(identity, 'github_repo', None) or None
                desc = getattr(identity, 'description', None) or None
                id_name = getattr(identity, 'subnet_name', None)
                if id_name:
                    name = str(id_name)
                if github and not github.strip():
                    github = None

            info = {
                "netuid": netuid,
                "name": name,
                "symbol": symbol,
                "emission_tao_day": round(emission_tao_day, 4),
                "emission_alpha_day": round(emission_alpha_day, 4),
                "market_cap_tao": round(market_cap_tao, 2),
                "price_tao": round(price, 9),
                "tau_in": round(tao_in, 4),
                "alpha_in": round(alpha_in, 4),
                "alpha_out": round(alpha_out, 4),
                "total_alpha": round(total_alpha, 4),
                "subnet_volume": round(volume, 4),
                "moving_price": round(sn.moving_price, 9) if sn.moving_price else None,
                "net_flow_24h": None,   # Requires taostats API
                "net_flow_7d": None,    # Requires taostats API
                "reg_cost_tao": None,
                "immunity_period": None,
                "tempo": tempo,
                "is_dynamic": bool(sn.is_dynamic),
                "registered_at_block": int(sn.network_registered_at) if sn.network_registered_at else None,
                "owner_hk": str(sn.owner_hotkey) if sn.owner_hotkey else "",
                "owner_ck": str(sn.owner_coldkey) if sn.owner_coldkey else "",
                "github": github,
                "description": desc,
                "blocks_since_last_step": sn.blocks_since_last_step,
                "k_constant": str(sn.k) if sn.k else None,
            }
            subnets_data.append(info)

        # Fetch hyperparams (immunity_period, burn/reg cost)
        print("\nFetching per-subnet hyperparameters...")
        for info in subnets_data:
            netuid = info["netuid"]
            try:
                hp = await sub.get_subnet_hyperparameters(netuid)
                if hp:
                    if hasattr(hp, 'immunity_period') and hp.immunity_period is not None:
                        info["immunity_period"] = int(hp.immunity_period)
            except:
                pass

            # Get actual burn cost from chain storage (in rao, 1e-9 TAO)
            try:
                result = await sub.substrate.query('SubtensorModule', 'Burn', [netuid])
                if result:
                    s = str(result)
                    if 'value=' in s:
                        val = int(s.split('value=')[1].split(')')[0])
                    else:
                        val = int(s)
                    info["reg_cost_tao"] = round(val / 1e9, 6)
            except:
                pass

            if netuid % 30 == 0:
                print(f"  Processed SN{netuid}...")

    # =============================================
    # OUTPUT
    # =============================================

    # Top 10 by emission
    print("\n--- Top 15 by emission τ/day ---")
    by_emission = sorted(subnets_data, key=lambda x: x["emission_tao_day"], reverse=True)
    for s in by_emission[:15]:
        print(f"  SN{s['netuid']:>3} {s['name'][:25]:<25} {s['emission_tao_day']:>10.2f} τ/day  mcap={s['market_cap_tao']:>12,.0f}τ  price={s['price_tao']:.6f}")

    # Top 10 by market cap
    print("\n--- Top 15 by market cap (τ) ---")
    by_mcap = sorted(subnets_data, key=lambda x: x["market_cap_tao"], reverse=True)
    for s in by_mcap[:15]:
        print(f"  SN{s['netuid']:>3} {s['name'][:25]:<25} mcap={s['market_cap_tao']:>12,.0f}τ  τ_in={s['tau_in']:>10,.0f}  α_total={s['total_alpha']:>12,.0f}")

    # Top by tau_in (liquidity)
    print("\n--- Top 15 by τ_in (pool liquidity) ---")
    by_tao_in = sorted(subnets_data, key=lambda x: x["tau_in"], reverse=True)
    for s in by_tao_in[:15]:
        print(f"  SN{s['netuid']:>3} {s['name'][:25]:<25} τ_in={s['tau_in']:>10,.0f}  α_in={s['alpha_in']:>12,.0f}  price={s['price_tao']:.6f}")

    # Save JSON
    json_path = f"{OUTPUT_DIR}/subnets_snapshot_{DATE}.json"
    with open(json_path, 'w') as f:
        json.dump(subnets_data, f, indent=2, default=str)
    print(f"\nSaved JSON: {json_path} ({len(subnets_data)} subnets)")

    # Save CSV
    csv_path = f"{OUTPUT_DIR}/subnets_snapshot_{DATE}.csv"

    csv_fields = ["netuid", "name", "symbol", "emission_tao_day",
                  "net_flow_7d", "reg_cost_tao", "market_cap_tao", "price_tao",
                  "tau_in", "alpha_in", "alpha_out", "total_alpha",
                  "subnet_volume", "immunity_period", "tempo", "is_dynamic",
                  "moving_price", "owner_hk", "github"]

    # Sort by emission desc (best proxy for health without net_flow)
    subnets_sorted = sorted(subnets_data, key=lambda x: x["emission_tao_day"], reverse=True)

    with open(csv_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=csv_fields, extrasaction='ignore')
        writer.writeheader()
        for s in subnets_sorted:
            writer.writerow({k: s.get(k, "") for k in csv_fields})
    print(f"Saved CSV: {csv_path}")

    # Summary stats
    dynamic = [s for s in subnets_data if s["is_dynamic"]]
    total_emission = sum(s["emission_tao_day"] for s in subnets_data)
    zero_emission = [s for s in subnets_data if s["emission_tao_day"] <= 0.001]
    total_mcap = sum(s["market_cap_tao"] for s in subnets_data)
    total_tao_in = sum(s["tau_in"] for s in subnets_data)

    print(f"\n{'=' * 60}")
    print(f"SUMMARY STATS:")
    print(f"  Block: {block}")
    print(f"  Total subnets: {len(subnets_data)} (dynamic: {len(dynamic)})")
    print(f"  Total emission: {total_emission:,.2f} τ/day")
    print(f"  Total market cap: {total_mcap:,.0f} τ")
    print(f"  Total pool liquidity (τ_in): {total_tao_in:,.0f} τ")
    print(f"  Subnets with ~0 emission: {len(zero_emission)}")
    with_github = [s for s in subnets_data if s.get("github")]
    print(f"  Subnets with github: {len(with_github)}/{len(subnets_data)}")

    print(f"\n  NET FLOW DATA:")
    print(f"    net_flow_7d NOT AVAILABLE - requires taostats.io API key")
    print(f"    Sign up: https://taostats.io/dashboard")
    print(f"    Without flow data, use τ_in as proxy for subnet health:")
    low_liquidity = [s for s in dynamic if s["tau_in"] < 1000]
    print(f"    Dynamic subnets with τ_in < 1000: {len(low_liquidity)} (likely struggling)")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    asyncio.run(main())
