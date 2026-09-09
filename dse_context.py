r"""
DSE MARKET UPDATE -- shared context assembly.

build_context() and its small support functions (load_macro, latest_news_note,
dstr), pulled out of dse_daily_market_update.py so anything that only needs
"today's fully-assembled market context" -- the live dashboard, the auto-
refresh server -- can import it without pulling in python-pptx/matplotlib,
which dse_daily_market_update.py's slide-rendering code needs but this
doesn't. Nothing here recomputes an analytic dse_analytics.py doesn't already
produce; this module only assembles Workbook + dse_analytics output into one
dict, same as before.

Dependencies: openpyxl, numpy (via dse_data / dse_analytics only).
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import dse_analytics as A

SCRIPT_DIR = Path(__file__).resolve().parent
# This is the public repo's own flat copy: it lives directly in
# "DSE-Market-Update-Live", a sibling of "Menhaj_Stock Market Files_Code"
# under "STOCK MARKET". The workbook and the news briefings sit inside that
# sibling, so WB_ROOT is SCRIPT_DIR's parent ("STOCK MARKET") plus that
# subfolder -- NOT SCRIPT_DIR.parent.parent, which would land on "My Drive",
# outside "STOCK MARKET" entirely. (In practice every call site here passes an
# explicit --workbook/WORKBOOK that overrides DEFAULT_WB, so this only affects
# a bare no-argument run -- but it should still point at the real file.)
WB_ROOT = SCRIPT_DIR.parent / "Menhaj_Stock Market Files_Code"
DEFAULT_WB = WB_ROOT / "DSE MARKET UPDATE.xlsx"
MACRO_JSON = SCRIPT_DIR / "macro_data.json"
NEWS_DIR = WB_ROOT / "DSE DAILY NEWS_Update"

WB_SRC = "Source: DSE MARKET UPDATE.xlsx"
NA = "Not Available"


def dstr(d):
    return d.strftime("%d-%b-%Y") if d else "-"


def load_macro():
    if not MACRO_JSON.exists():
        return {}
    try:
        return json.loads(MACRO_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"  ! macro_data.json unreadable ({exc}) -- macro section will "
              f"print '{NA}'")
        return {}


def latest_news_note():
    """Newest daily-bd-financial-news briefing, if one has been generated."""
    if not NEWS_DIR.exists():
        return None, None
    mds = sorted(NEWS_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime,
                 reverse=True)
    if not mds:
        return None, None
    text = mds[0].read_text(encoding="utf-8", errors="ignore")
    hits = []
    for line in text.splitlines():
        s = line.strip(" -*#\t")
        if not s or len(s) < 25:
            continue
        low = s.lower()
        if any(k in low for k in ("bsec", "bangladesh bank", "circular",
                                  "regulator", "policy rate", "directive",
                                  "commission", "margin rule")):
            hits.append(s)
        if len(hits) >= 4:
            break
    return mds[0].name, hits


def build_context(wb):
    ctx = {"wb": wb}
    rm = wb.recent_market()
    ctx["recent"] = rm
    today, prev = rm[0], (rm[1] if len(rm) > 1 else rm[0])
    ctx["today"], ctx["prev"] = today, prev
    ctx["as_of"] = today["date"]

    ms = {(m["label"], m["category"]): m["value"] for m in wb.market_summary()}
    ctx["summary_rows"] = wb.market_summary()
    ctx["adv"] = ms.get(("ISSUES ADVANCED", ""), 0)
    ctx["dec"] = ms.get(("ISSUES DECLINED", ""), 0)
    ctx["unch"] = ms.get(("ISSUES UNCHANGED", ""), 0)
    ctx["traded"] = ms.get(("TOTAL ISSUES TRADED", ""), 0)

    hist = wb.hist
    ctx["hist_dates"], ctx["dsex_hist"] = hist.series("DSEX")
    _, ctx["turnover_hist"] = hist.series("Turnover (BDT mn)")
    _, ctx["dses_hist"] = hist.series("DSES")
    _, ctx["ds30_hist"] = hist.series("DS30")
    _, ctx["pe_hist"] = hist.series("Market P/E")

    ctx["tech"] = A.index_technicals(ctx["hist_dates"], ctx["dsex_hist"])
    ctx["sr"] = A.support_resistance(ctx["hist_dates"], ctx["dsex_hist"],
                                     ctx["turnover_hist"])

    ctx["by_ticker"] = wb.by_ticker()
    ctx["basis"] = A.basis_dates(wb.sheets["ALL DATA"])
    ctx["sectors"] = A.sector_aggregates(wb.all_data, wb.sector)
    ctx["label_audit"] = A.sector_label_audit(wb.sector, wb.all_data)
    ctx["movers"], ctx["draggers"] = A.index_movers(wb.all_data, n=6)
    ctx["gainers"], ctx["losers"] = A.top_movers(
        wb.dse.get("gainers", []), wb.dse.get("losers", []), ctx["by_ticker"])
    ctx["cat_breadth"] = A.breadth_by(wb.all_data, "Category")
    ctx["cap_breadth"] = A.breadth_by(wb.all_data, "Mcap Segment")
    ctx["hi_list"], ctx["lo_list"] = A.high_low_checklist(wb.all_data, wb.eps)
    ctx["records"], ctx["agms"] = A.corporate_calendar(wb.all_data, ctx["as_of"])
    ctx["macro"] = load_macro()

    # index / turnover / mcap day-on-day
    ctx["dsex_chg"] = today["dsex"] - prev["dsex"]
    ctx["dsex_pct"] = ctx["dsex_chg"] / prev["dsex"] * 100.0
    ctx["dses_chg"] = today["dses"] - prev["dses"]
    ctx["dses_pct"] = ctx["dses_chg"] / prev["dses"] * 100.0
    ctx["ds30_chg"] = today["ds30"] - prev["ds30"]
    ctx["ds30_pct"] = ctx["ds30_chg"] / prev["ds30"] * 100.0
    ctx["turnover_chg"] = (today["value"] / prev["value"] - 1) * 100.0
    ctx["mcap_chg"] = (today["mcap"] / prev["mcap"] - 1) * 100.0
    ctx["trade_chg"] = (today["trade"] / prev["trade"] - 1) * 100.0
    ctx["volume_chg"] = (today["volume"] / prev["volume"] - 1) * 100.0

    ranked = [s for s in ctx["sectors"] if s["day"] is not None]
    ranked.sort(key=lambda s: s["day"], reverse=True)
    ctx["lead_sectors"] = [(s["sector"], s["day"]) for s in ranked[:2]]
    ctx["lag_sectors"] = [(s["sector"], s["day"]) for s in ranked[-2:]]

    ctx["commentary"] = A.commentary({
        "dsex": today["dsex"], "dsex_chg": ctx["dsex_chg"],
        "dsex_pct": ctx["dsex_pct"], "adv": ctx["adv"], "dec": ctx["dec"],
        "unch": ctx["unch"], "traded": ctx["traded"],
        "turnover": today["value"], "turnover_chg": ctx["turnover_chg"],
        "trades": today["trade"], "mcap": today["mcap"],
        "mcap_chg": ctx["mcap_chg"], "lead_sectors": ctx["lead_sectors"],
        "lag_sectors": ctx["lag_sectors"], "movers": ctx["movers"],
        "draggers": ctx["draggers"],
    })

    # 52-week / 5-year / 10-year extremes
    ctx["hi52"], ctx["lo52"] = len(ctx["hi_list"]), len(ctx["lo_list"])
    ctx["ext5"] = A.extreme_counts(hist, 5, ctx["as_of"])
    ctx["ext10"] = A.extreme_counts(hist, 10, ctx["as_of"])
    ctx["hist_span_from"] = hist.dates[0]
    return ctx
