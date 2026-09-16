r"""
update_macro.py -- Refresh macro_data.json from external sources

Scrapes Bangladesh Bank for latest treasury auction yields.
Inflation can be added via CLI flags (BBS data changes monthly).

Usage:
    pip install requests beautifulsoup4

    python update_macro.py                          # update yields only
    python update_macro.py --add-inflation Aug-26 8.15
    python update_macro.py --add-inflation Aug-26 8.15 --food 7.0 --nonfood 9.1
    python update_macro.py --dry-run                # preview without writing
    python update_macro.py --info                   # show current values
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import date, datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

SCRIPT_DIR = Path(__file__).resolve().parent
MACRO_JSON = SCRIPT_DIR / "macro_data.json"
STOCK_ROOT = SCRIPT_DIR.parent.parent

OTHER_COPIES = [
    STOCK_ROOT / "DSE-Lab" / "engine" / "macro_data.json",
    STOCK_ROOT / "Menhaj_Stock Market Files_Code" / "Daily Market Update"
    / "Daily Market Update_PPTX_Helper Code" / "macro_data.json",
]

BB_URL = ("https://www.bb.org.bd/en/index.php/"
          "monetaryactivity/treasury")

WANT_TENORS = ["91D", "182D", "364D", "2Y", "10Y", "15Y", "20Y"]

TENOR_KEYS = {
    "91 day":  "91D",  "91 days":  "91D",  "91days": "91D",
    "182 day": "182D", "182 days": "182D", "182days": "182D",
    "364 day": "364D", "364 days": "364D", "364days": "364D",
    "2yr": "2Y",  "2 year": "2Y",  "2year": "2Y",
    "3yr": "3Y",  "3 year": "3Y",
    "5yr": "5Y",  "5 year": "5Y",  "5year": "5Y",
    "10yr": "10Y", "10 year": "10Y", "10year": "10Y",
    "15yr": "15Y", "15 year": "15Y", "15year": "15Y",
    "20yr": "20Y", "20 year": "20Y", "20year": "20Y",
}


def _sfloat(s):
    if not s:
        return None
    s = s.strip().replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _pdate(s):
    if not s:
        return None
    s = s.strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d-%b-%Y", "%d %b %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def _classify_tenor(text):
    low = text.lower().strip()
    for key, val in TENOR_KEYS.items():
        if key in low:
            return val
    return None


# ─── Yield-curve scraper ────────────────────────────────────────

def _get(url, **kw):
    kw.setdefault("headers", {})["User-Agent"] = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
    kw.setdefault("timeout", 20)
    try:
        return requests.get(url, **kw)
    except requests.exceptions.SSLError:
        return requests.get(url, verify=False, **kw)


def scrape_bb_yields():
    print("Fetching Bangladesh Bank treasury auction data ...")
    resp = _get(BB_URL)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    auctions: list[dict] = []
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 5:
                continue
            texts = [c.get_text(strip=True) for c in cells]

            tenor, auc_date, cut_off = None, None, None
            for t in texts:
                if tenor is None:
                    tenor = _classify_tenor(t)
                if auc_date is None:
                    auc_date = _pdate(t)

            for t in reversed(texts):
                v = _sfloat(t)
                if v is not None and 4.0 <= v <= 15.0:
                    cut_off = v
                    break

            if tenor and auc_date and cut_off and tenor in WANT_TENORS:
                auctions.append({"tenor": tenor, "date": auc_date,
                                 "yield": cut_off})

    if not auctions:
        print("  ! No auction rows parsed — page structure may have changed")
        return None

    best: dict[str, dict] = {}
    for a in auctions:
        t = a["tenor"]
        if t not in best or a["date"] > best[t]["date"]:
            best[t] = a

    result = []
    for t in WANT_TENORS:
        b = best.get(t)
        result.append({
            "tenor": t,
            "auction_date": b["date"].isoformat() if b else None,
            "yield": round(b["yield"], 4) if b else None,
            "prev_month": None,
        })

    found = sum(1 for r in result if r["yield"] is not None)
    print(f"  {found}/{len(result)} tenors found:")
    for r in result:
        if r["yield"] is not None:
            print(f"    {r['tenor']:>4s}  {r['yield']:.4f}%  "
                  f"(auction {r['auction_date']})")
    return result


# ─── Main ───────────────────────────────────────────────────────

def show_info(macro):
    print("=== macro_data.json ===")
    print(f"  Retrieved: {macro['retrieved']}")
    print(f"  Stale after: {macro['stale_after_days']} days")
    yc = macro.get("yield_curve", {})
    print(f"\n  Yield curve ({yc.get('source', '?')[:60]}):")
    for t in yc.get("tenors", []):
        y = t.get("yield")
        print(f"    {t['tenor']:>4s}  "
              f"{'—' if y is None else f'{y:.4f}%':>10s}  "
              f"  auction {t.get('auction_date', '—')}")
    inf = macro.get("inflation", {})
    print(f"\n  Inflation ({inf.get('source', '?')[:60]}):")
    for s in inf.get("series", []):
        g = s.get("general")
        f = s.get("food")
        nf = s.get("non_food")
        print(f"    {s['month']:>7s}  general={g}  food={f}  non_food={nf}")
    ld = inf.get("latest_detail")
    if ld:
        print(f"    Detail ({ld.get('month', '?')}): "
              f"rural={ld.get('rural')}  urban={ld.get('urban')}")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true",
                    help="Preview changes without writing")
    ap.add_argument("--info", action="store_true",
                    help="Show current values and exit")
    ap.add_argument("--add-inflation", nargs=2, metavar=("MONTH", "GENERAL"),
                    help='Add an inflation month, e.g. --add-inflation Aug-26 8.15')
    ap.add_argument("--food", type=float, default=None,
                    help="Food inflation for --add-inflation")
    ap.add_argument("--nonfood", type=float, default=None,
                    help="Non-food inflation for --add-inflation")
    ap.add_argument("--skip-yields", action="store_true",
                    help="Skip BB yield-curve scraping")
    args = ap.parse_args(argv)

    if not MACRO_JSON.exists():
        print(f"Not found: {MACRO_JSON}")
        return 1

    macro = json.loads(MACRO_JSON.read_text(encoding="utf-8"))

    if args.info:
        show_info(macro)
        return 0

    changed = False

    # --- yields ---
    if not args.skip_yields:
        yields = scrape_bb_yields()
        if yields:
            macro["yield_curve"]["tenors"] = yields
            changed = True
            print("  Yield curve updated")
        else:
            print("  Yield curve: keeping existing values")
    else:
        print("  Yield curve: skipped (--skip-yields)")

    # --- inflation ---
    if args.add_inflation:
        month_label, general_str = args.add_inflation
        general = float(general_str)
        existing = {s["month"] for s in macro["inflation"]["series"]}
        if month_label in existing:
            for s in macro["inflation"]["series"]:
                if s["month"] == month_label:
                    s["general"] = general
                    if args.food is not None:
                        s["food"] = args.food
                    if args.nonfood is not None:
                        s["non_food"] = args.nonfood
            print(f"  Updated inflation for {month_label}")
        else:
            macro["inflation"]["series"].append({
                "month": month_label,
                "general": general,
                "food": args.food,
                "non_food": args.nonfood,
            })
            print(f"  Added inflation for {month_label}: "
                  f"general={general}, food={args.food}, non_food={args.nonfood}")
        changed = True
    else:
        print("\n  Inflation: no --add-inflation flag provided")
        print("    To add: python update_macro.py --add-inflation Aug-26 8.15 "
              "--food 7.0 --nonfood 9.1")
        print("    Sources:")
        print("      https://tradingeconomics.com/bangladesh/inflation-cpi")
        print("      https://www.theglobaleconomy.com/Bangladesh/inflation_annual/")

    if not changed:
        print("\nNo changes — macro_data.json is already up to date")
        return 0

    macro["retrieved"] = date.today().isoformat()

    if args.dry_run:
        print(f"\n[DRY RUN] Would update {MACRO_JSON}")
        show_info(macro)
        return 0

    text = json.dumps(macro, indent=2, ensure_ascii=False) + "\n"
    MACRO_JSON.write_text(text, encoding="utf-8")
    print(f"\nWrote {MACRO_JSON}")

    for dest in OTHER_COPIES:
        if dest.parent.exists():
            shutil.copy2(MACRO_JSON, dest)
            print(f"  Synced -> {dest}")
        else:
            print(f"  Skipped {dest.name} (dir not found)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
