#!/usr/bin/env python3
"""
Caminho A v3 REFRAMED — Fase 0: Discover operational subnets by category.
Scan READMEs for scraping/storage/oracle/data keywords.
"""
import json, csv, time, sys, re
import requests

sys.stdout.reconfigure(line_buffering=True)

API_KEY = "tao-1453ed31-5e73-4303-a634-9a98b576c3b5:84ae2f06"
BASE = "https://api.taostats.io/api"
HEADERS = {"Authorization": API_KEY}
TAO_USD = 270

ANALYZED_EXCLUSIONS = {0, 4, 5, 17, 32, 51, 64, 75, 83, 93, 114, 120, 2}
OUTDIR = "~/bittensor-research/data"

with open(f"{OUTDIR}/subnets_snapshot_2026-04-11.json") as f:
    snapshot = {s["netuid"]: s for s in json.load(f)}

# Category keywords
CATEGORIES = {
    "scraping": ["scrape", "scraping", "crawler", "crawl", "web data", "web scraping",
                 "extract data from web", "html parsing", "selenium", "beautifulsoup"],
    "storage": ["storage", "ipfs", "store data", "file hosting", "object storage",
                "distributed storage", "data storage", "decentralized storage", "filecoin"],
    "oracle": ["oracle", "predict", "forecast", "data feed", "external data",
               "price feed", "price oracle", "financial data", "market data",
               "time series", "prediction market"],
    "data_collection": ["data collection", "dataset", "data marketplace", "data sourcing",
                        "data labeling", "data annotation", "data pipeline",
                        "data ingestion", "data aggregat"],
}

# Also match broader operational patterns (non-ML work)
OPERATIONAL_EXTRA = {
    "indexing": ["index", "indexing", "search engine", "search index"],
    "networking": ["vpn", "proxy", "bandwidth", "network relay", "mesh network"],
    "compute_light": ["compute task", "simple computation", "hash", "proof of work"],
    "api_service": ["api service", "rest api", "endpoint", "serve requests"],
    "monitoring": ["monitor", "uptime", "health check", "alert"],
}


def api_get(endpoint, params=None, max_retries=5):
    url = f"{BASE}/{endpoint}"
    for attempt in range(max_retries):
        try:
            r = requests.get(url, headers=HEADERS, params=params, timeout=30)
            if r.status_code == 429:
                wait = 10 * (attempt + 1)
                print(f"    [429] waiting {wait}s")
                time.sleep(wait)
                continue
            if r.status_code != 200:
                return None
            return r.json()
        except Exception:
            if attempt < max_retries - 1:
                time.sleep(5)
                continue
            return None
    return None


def fetch_readme(github_url):
    """Fetch README.md from GitHub repo."""
    if not github_url:
        return None

    # Normalize URL
    url = github_url.strip().rstrip("/")

    # Handle /tree/main, /tree/master etc
    url = re.sub(r"/tree/[^/]+/?$", "", url)

    # Handle orgs page (e.g. /orgs/X/repositories)
    if "/orgs/" in url:
        return None

    # Extract owner/repo
    match = re.search(r"github\.com/([^/]+)/([^/]+)", url)
    if not match:
        return None

    owner, repo = match.group(1), match.group(2)

    # Try raw.githubusercontent.com for README
    for branch in ["main", "master"]:
        for fname in ["README.md", "readme.md", "Readme.md"]:
            raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{fname}"
            try:
                r = requests.get(raw_url, timeout=15)
                if r.status_code == 200:
                    return r.text
            except Exception:
                continue
    return None


def categorize_text(text):
    """Search text for category keywords. Returns dict of category -> matches."""
    if not text:
        return {}

    text_lower = text.lower()
    results = {}

    for cat, keywords in {**CATEGORIES, **OPERATIONAL_EXTRA}.items():
        matches = []
        for kw in keywords:
            if kw.lower() in text_lower:
                matches.append(kw)
        if matches:
            results[cat] = matches

    return results


# ============================================================
# STEP 1: Bulk subnet data
# ============================================================
print("=" * 70)
print("STEP 1: Bulk subnet metadata")
print("=" * 70)

subnet_api = api_get("subnet/latest/v1", {"limit": "200"})
if not subnet_api or not subnet_api.get("data"):
    print("FATAL: Cannot get subnet data")
    sys.exit(1)

api_subnets = {s["netuid"]: s for s in subnet_api["data"]}
print(f"Got {len(api_subnets)} subnets from API")

# ============================================================
# STEP 2: Scan READMEs
# ============================================================
print(f"\n{'='*70}")
print("STEP 2: Scanning READMEs for operational categories")
print("=" * 70)

all_subnets = []
category_matches = []
no_github = 0
no_readme = 0
no_match = 0

target_netuids = sorted([n for n in range(1, 129) if n not in ANALYZED_EXCLUSIONS])

for i, netuid in enumerate(target_netuids):
    snap = snapshot.get(netuid, {})
    api_s = api_subnets.get(netuid, {})
    name = snap.get("name", f"SN{netuid}")
    emission = snap.get("emission_tao_day", 0) or 0
    github = snap.get("github")
    description = snap.get("description", "") or ""
    active_miners = api_s.get("active_miners", 0) or 0

    entry = {
        "netuid": netuid,
        "name": name,
        "emission_tao_day": emission,
        "active_miners": active_miners,
        "github_url": github or "",
        "description": description,
    }

    if not github:
        no_github += 1
        entry["categories"] = {}
        entry["status"] = "no_github"
        all_subnets.append(entry)
        continue

    # Fetch README
    readme = fetch_readme(github)
    if not readme:
        no_readme += 1
        # Still check description
        cats = categorize_text(description + " " + name)
        entry["categories"] = cats
        entry["status"] = "no_readme"
        if cats:
            category_matches.append(entry)
        all_subnets.append(entry)
        if (i + 1) % 10 == 0:
            print(f"  ...{i+1}/{len(target_netuids)}")
        continue

    # Categorize README + description + name
    full_text = f"{name} {description} {readme}"
    cats = categorize_text(full_text)
    entry["categories"] = cats
    entry["readme_len"] = len(readme)
    entry["status"] = "scanned"

    if cats:
        category_matches.append(entry)
        cat_str = ", ".join(cats.keys())
        print(f"  [{i+1}/{len(target_netuids)}] SN{netuid} {name}: MATCH [{cat_str}]")
    else:
        no_match += 1

    all_subnets.append(entry)

    if (i + 1) % 10 == 0 and not cats:
        print(f"  ...{i+1}/{len(target_netuids)}")

# ============================================================
# STEP 3: Filter and output
# ============================================================
print(f"\n{'='*70}")
print("STEP 3: Filter results")
print("=" * 70)

# Apply filters: emission >= 0.05, active_miners >= 3
candidates = []
for m in category_matches:
    if m["emission_tao_day"] < 0.05:
        continue
    if m["active_miners"] < 3:
        continue
    # Flatten categories for CSV
    cat_names = sorted(m["categories"].keys())
    keywords = []
    for c in cat_names:
        keywords.extend(m["categories"][c])
    candidates.append({
        "netuid": m["netuid"],
        "name": m["name"],
        "categorias_match": "|".join(cat_names),
        "emission_tao_day": round(m["emission_tao_day"], 4),
        "miners_count": m["active_miners"],
        "github_url": m["github_url"],
        "readme_keywords_found": ", ".join(keywords[:10]),
        "description": (m.get("description") or "")[:100],
    })

candidates.sort(key=lambda x: x["emission_tao_day"], reverse=True)

# Write CSV
outpath = f"{OUTDIR}/operacional_candidates.csv"
fields = ["netuid", "name", "categorias_match", "emission_tao_day",
          "miners_count", "github_url", "readme_keywords_found"]
with open(outpath, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    w.writerows(candidates)

# Write full JSON for next phases
with open(f"{OUTDIR}/operacional_candidates.json", "w") as f:
    json.dump(candidates, f, indent=2)

# ============================================================
# Summary
# ============================================================
print(f"\n{'='*70}")
print(f"FASE 0 REFRAMED — RESULTADOS")
print(f"{'='*70}")
print(f"Total subnets scanned:     {len(target_netuids)}")
print(f"No GitHub URL:             {no_github}")
print(f"No README found:           {no_readme}")
print(f"Category matches (raw):    {len(category_matches)}")
print(f"After emission+miners:     {len(candidates)}")

# Count by category
cat_counts = {}
for c in candidates:
    for cat in c["categorias_match"].split("|"):
        cat_counts[cat] = cat_counts.get(cat, 0) + 1

print(f"\nContagem por categoria:")
for cat, count in sorted(cat_counts.items(), key=lambda x: -x[1]):
    print(f"  {cat:<20} {count}")

# ASCII table
if candidates:
    top_n = min(25, len(candidates))
    print(f"\n{'='*70}")
    print(f"TOP {top_n} CANDIDATOS OPERACIONAIS:")
    print(f"{'='*70}")
    hdr = f"{'SN':>4} {'name':<22} {'categorias':<30} {'emit/d':>7} {'min#':>4}"
    print(hdr)
    print("-" * len(hdr))
    for c in candidates[:top_n]:
        cats = c["categorias_match"][:28]
        print(f"{c['netuid']:>4} {c['name']:<22} {cats:<30} {c['emission_tao_day']:>7.2f} {c['miners_count']:>4}")

print(f"\nFicheiro: {outpath}")
print(f"Done. {len(candidates)} candidates for Fase 1.")
