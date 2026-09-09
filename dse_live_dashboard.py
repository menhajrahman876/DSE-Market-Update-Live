r"""
DSE DAY-END MARKET UPDATE  --  interactive HTML dashboard.

Companion to dse_daily_market_update.py (the PPTX generator). Reuses the
exact same context-assembly pipeline -- Workbook, dse_analytics ("A") and
build_context() -- so the dashboard and the PPTX never disagree on a number.
This script performs zero analytics of its own: every figure it emits is
either read straight off build_context()'s dict or produced by calling into
dse_analytics, exactly as dse_daily_market_update.py's slide builders do.

    python "dse_live_dashboard.py" [--workbook PATH] [--out PATH]

Output is a single self-contained HTML file (dse_live_dashboard.html by
default) with all data embedded as JSON and Chart.js pulled from a CDN --
no server, no build step. It is a point-in-time snapshot: re-run this
script (same cadence as the PPTX) to refresh it. See the header banner in
the generated page for the exact "as of" / "workbook refreshed" timestamps.

In THIS repository the layout is flat: dse_data.py, dse_analytics.py and
dse_context.py sit right beside this file, so it imports them directly with
no path juggling. (They are copies of the modules maintained in the private
pipeline; regenerate the snapshot there or here -- the analytics are
identical.)

Dependencies: openpyxl, numpy.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date, datetime
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
# flat repo layout: core modules are siblings of this file, imported directly

import dse_analytics as A
from dse_context import (DEFAULT_WB, NA, build_context, dstr,
                         latest_news_note)
from dse_data import Workbook, num, txt

TEMPLATE = SCRIPT_DIR / "dse_dashboard_template.html"
DATA_PLACEHOLDER = "/*__DSE_DASHBOARD_DATA__*/"


# --------------------------------------------------------------------------
# JSON-safe conversion
# --------------------------------------------------------------------------

def jsafe(v):
    """Recursively coerce dates / numpy scalars / NaN-Inf into JSON-safe values."""
    if v is None:
        return None
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, (np.floating,)):
        v = float(v)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, float):
        return None if (math.isnan(v) or math.isinf(v)) else v
    if isinstance(v, (bool, int, str)):
        return v
    if isinstance(v, dict):
        return {str(k): jsafe(val) for k, val in v.items()}
    if isinstance(v, (list, tuple, np.ndarray)):
        return [jsafe(x) for x in v]
    return v


def pct(v):
    """ALL DATA / summary-row returns are stored as fractions -- render as
    percent, exactly as dse_analytics._pct() does for the PPTX."""
    f = num(v)
    return None if f is None else f * 100.0


# --------------------------------------------------------------------------
# section builders -- reshape ctx / A.* output only, never recompute
# --------------------------------------------------------------------------

def build_summary_section(wb, ctx):
    cats, cur = [], None
    for row in ctx["summary_rows"]:
        lab, cat, val = row["label"], row["category"], row["value"]
        if lab.startswith("ISSUES") or lab.startswith("TOTAL ISSUES"):
            continue
        if lab == "Category-Wise":
            continue
        if cat:
            cur = {"cat": cat, "adv": None, "dec": None, "unch": None, "total": None}
            cats.append(cur)
        if cur is None:
            continue
        key = {"ADVANCED": "adv", "DECLINED": "dec", "UNCHANGED": "unch",
               "TOTAL TRADED": "total"}.get(lab.upper())
        if key:
            cur[key] = val

    derived = ctx["cat_breadth"]
    category_rows = []
    for c in cats:
        d = derived.get(c["cat"])
        category_rows.append({
            "category": c["cat"], "adv": c["adv"], "dec": c["dec"],
            "unch": c["unch"], "total": c["total"],
            "trade": (d.get("trade") if d else None),
            "value": (d.get("value") if d else None),
            "volume": (d.get("volume") if d else None),
            "has_breakdown": d is not None,
        })
    category_all = {
        "adv": ctx["adv"], "dec": ctx["dec"], "unch": ctx["unch"],
        "traded": ctx["traded"], "trade": ctx["today"]["trade"],
        "value": ctx["today"]["value"], "volume": ctx["today"]["volume"],
    }

    cap_segments = []
    tot_val = sum(v["value"] for v in ctx["cap_breadth"].values()) or 1
    for name, v in A.ordered(ctx["cap_breadth"], A.CAP_ORDER):
        cap_segments.append({
            "segment": name, "n": v["n"], "adv": v["adv"], "dec": v["dec"],
            "unch": v["unch"], "trade": v["trade"], "value": v["value"],
            "pct_value": v["value"] / tot_val * 100.0, "mcap": v["mcap"],
            "wow_pct": v["wow_pct"],
        })

    paid = A.breadth_by(wb.all_data, "Paid-up Segment")
    order = ["Large Paid-up", "Mid Paid-up", "Small Paid-up", "Micro Paid-up"]
    paidup_segments = []
    for name, v in A.ordered(paid, order):
        paidup_segments.append({
            "segment": name, "n": v["n"], "adv": v["adv"], "dec": v["dec"],
            "unch": v["unch"], "trade": v["trade"], "value": v["value"],
            "mcap": v["mcap"], "wow_pct": v["wow_pct"],
        })

    tail_labels = ("No. of Trades", "Volume", "Value (Tk.)", "Equity Mcap",
                   "MF Mcap", "Debt Mcap", "Total")
    totals = [{"label": r["label"], "value": r["value"]}
              for r in ctx["summary_rows"] if r["label"] in tail_labels]

    return {
        "category_rows": category_rows, "category_all": category_all,
        "cap_segments": cap_segments, "paidup_segments": paidup_segments,
        "totals": totals,
    }


def build_universe(wb):
    rows = []
    for r in wb.all_data:
        ticker = txt(r.get("Tickers"))
        if not ticker:
            continue
        rows.append({
            "ticker": ticker, "company": txt(r.get("Company Name")),
            "sector": txt(r.get("Sector")), "category": txt(r.get("Category")),
            "cap_segment": txt(r.get("Mcap Segment")),
            "paidup_segment": txt(r.get("Paid-up Segment")),
            "close": num(r.get("CLOSEP*")), "ycp": num(r.get("YCP*")),
            "day_pct": pct(r.get("Day Change (%)")),
            "week_pct": pct(r.get("1 Week Mcap Return")),
            "month_pct": pct(r.get("1 Month MCap Return")),
            "year_pct": pct(r.get("52 Week Mcap Return")),
            "ytd_pct": pct(r.get("YTD Change")),
            "value_mn": num(r.get("VALUE (mn)")), "volume": num(r.get("Volume")),
            "trade": num(r.get("TRADE")),
            "mcap_bn": (num(r.get("Today's MCap")) or 0) / 1e9,
            "pe": num(r.get("P/E (DSE)")) or None,
            "eps": num(r.get("Annualized EPS")),
        })
    return rows


def build_technicals(ctx):
    t, sr = ctx["tech"], ctx["sr"]
    p = sr["params"]

    supports = [{"level": l["level"], "touches": l["touches"],
                 "vol_confirmation": l["vol_confirmation"],
                 "distance_pct": l["distance_pct"],
                 "last_touch_date": l["last_touch_date"]}
                for l in sr["supports"]]
    resistances = [{"level": l["level"], "touches": l["touches"],
                    "vol_confirmation": l["vol_confirmation"],
                    "distance_pct": l["distance_pct"],
                    "last_touch_date": l["last_touch_date"]}
                   for l in sr["resistances"]]

    # same "Reading" synthesis as slide_technicals() in dse_daily_market_update.py
    nearest_sup = sr["supports"][0] if sr["supports"] else None
    nearest_res = sr["resistances"][-1] if sr["resistances"] else None
    bits = []
    if all(v == "below" for v in t["trend"].values()):
        bits.append(
            f"DSEX closed at {sr['spot']:,.2f}, below all three moving "
            f"averages (MA3 {t['ma'][3]:,.2f}, MA9 {t['ma'][9]:,.2f}, MA21 "
            f"{t['ma'][21]:,.2f}).")
    else:
        bits.append(
            f"DSEX closed at {sr['spot']:,.2f}, "
            + ", ".join(f"{v} MA({w}) at {t['ma'][w]:,.2f}"
                        for w, v in sorted(t["trend"].items())) + ".")
    bits.append(
        f"MACD at {t['macd']:,.2f} against a signal of {t['macd_signal']:,.2f} "
        f"leaves the histogram at {t['macd_hist']:,.2f}, a {t['macd_cross']} "
        f"reading" + (" that flipped today." if t["macd_flip"] else "."))
    if t["rsi"] is not None:
        state = ("overbought" if t["rsi"] > 70 else
                 "oversold" if t["rsi"] < 30 else "neutral")
        bits.append(f"RSI(14) is {t['rsi']:,.1f} ({state}).")
    if nearest_res:
        bits.append(
            f"The nearest resistance is {nearest_res['level']:,.2f} "
            f"({nearest_res['distance_pct']:+.2f}%, {nearest_res['touches']} touches)")
    if nearest_sup:
        bits.append(
            f"and the nearest support {nearest_sup['level']:,.2f} "
            f"({nearest_sup['distance_pct']:+.2f}%, {nearest_sup['touches']} touches).")

    series = t["series"]
    return {
        "spot": t["spot"], "ma": {str(w): v for w, v in t["ma"].items()},
        "trend": {str(w): v for w, v in t["trend"].items()},
        "rsi": t["rsi"], "macd": t["macd"], "macd_signal": t["macd_signal"],
        "macd_hist": t["macd_hist"], "macd_cross": t["macd_cross"],
        "macd_flip": bool(t["macd_flip"]),
        "series": {
            "dates": series["dates"], "close": series["close"],
            "ma3": list(series["ma"][3]), "ma9": list(series["ma"][9]),
            "ma21": list(series["ma"][21]), "macd": list(series["macd"]),
            "signal": list(series["signal"]), "hist": list(series["hist"]),
        },
        "supports": supports, "resistances": resistances,
        "params": {"swing_window": p["swing_window"],
                   "tolerance_pct": p["tolerance_pct"],
                   "min_touches": p["min_touches"],
                   "sample_days": p["sample_days"],
                   "from": p["from"], "to": p["to"]},
        "reading": " ".join(bits),
    }


def build_leaderboards(wb):
    rows_all = wb.all_data
    return {
        "most_active_by_sector": A.most_active(rows_all, "Sector", 1),
        "turnover_leaders_by_sector": A.turnover_leaders(rows_all, "Sector", 1),
        "most_active_by_cap": A.most_active(rows_all, "Mcap Segment", 3),
        "turnover_leaders_by_cap": A.turnover_leaders(rows_all, "Mcap Segment", 3),
        "top12_market": A.top_by(rows_all, "VALUE (mn)", 12,
                                 extra={"vol": "Volume", "trade": "TRADE"}),
    }


def build_blocks(ctx):
    blocks = []
    for b in ctx["wb"].dse.get("block", []):
        code = txt(b.get("Instr Code"))
        if not code:
            continue
        blocks.append({
            "code": code, "max": num(b.get("Max Price")),
            "min": num(b.get("Min Price")), "trades": num(b.get("Trades")),
            "qty": num(b.get("Quantity")),
            "value": num(b.get("Value(In Mn)"), 0) or 0,
        })
    blocks.sort(key=lambda b: b["value"], reverse=True)
    tot_v = sum(b["value"] for b in blocks)
    tot_q = sum(b["qty"] or 0 for b in blocks)
    tot_t = sum(b["trades"] or 0 for b in blocks)
    day_turnover = ctx["today"]["value"]
    return {
        "rows": blocks,
        "totals": {
            "trades": tot_t, "qty": tot_q, "value": tot_v,
            "pct_of_turnover": (tot_v / day_turnover * 100.0) if day_turnover else None,
        },
    }


def build_macro(ctx):
    macro = ctx["macro"]
    yc = macro.get("yield_curve") or {}
    infl = macro.get("inflation") or {}
    retrieved = macro.get("retrieved")
    stale_days = macro.get("stale_after_days", 10)
    stale = False
    if retrieved:
        try:
            age = (ctx["as_of"] - datetime.strptime(retrieved, "%Y-%m-%d").date()).days
            stale = age > stale_days
        except ValueError:
            stale = True

    bonds = []
    for b in ctx["wb"].dse.get("treasury", []):
        code = txt(b.get("TRADING CODE"))
        if not code:
            continue
        bonds.append({
            "code": code, "close": num(b.get("CLOSEP*")), "ycp": num(b.get("YCP*")),
            "trade": num(b.get("TRADE")), "value": num(b.get("VALUE (mn)")),
            "vol": num(b.get("VOLUME")),
        })
    bonds.sort(key=lambda b: (b["value"] or 0), reverse=True)

    return {
        "retrieved": retrieved, "stale": stale, "stale_after_days": stale_days,
        "yield_curve": yc, "inflation": infl, "bonds": bonds,
    }


def build_global(ctx):
    items = []
    for g in ctx["wb"].dse.get("global", []):
        from dse_data import serial_to_date
        name = txt(g.get("INSTRUMENT"))
        if not name:
            continue
        items.append({
            "name": name, "ticker": txt(g.get("TICKER")),
            "date": serial_to_date(g.get("DATE")),
            "open": num(g.get("OPEN")), "high": num(g.get("HIGH")),
            "low": num(g.get("LOW")), "close": num(g.get("CLOSE")),
            "vol": num(g.get("VOLUME")), "prev": num(g.get("PREV CLOSE")),
            "chg": num(g.get("CHANGE")), "pct": num(g.get("% CHANGE")),
        })
    idx_names = {"S&P 500", "Nasdaq 100", "Hang Seng", "Nifty 50", "Dow Jones",
                 "FTSE 100", "Nikkei 225", "DAX", "Shanghai Composite",
                 "KOSPI", "Sensex", "Straits Times"}
    return {
        "commodities": [i for i in items if i["name"] not in idx_names],
        "indices": [i for i in items if i["name"] in idx_names],
    }


def build_calendar(ctx):
    macro_talk = (ctx["macro"] or {}).get("talk_of_the_market")
    news_file, hits = latest_news_note()
    return {
        "records": ctx["records"], "agms": ctx["agms"],
        "talk_of_market": macro_talk,
        "talk_hits": hits if (not macro_talk and hits) else None,
        "news_file": news_file,
    }


def build_provenance(ctx):
    macro = ctx["macro"]
    macro_talk = (macro or {}).get("talk_of_the_market")
    yc_source = (macro.get("yield_curve") or {}).get("source") or NA
    return [
        {"section": "Overview, Trend, Summary & Breadth, Movers, Sectors, "
                    "Technicals, Extremes, Leaderboards, Blocks, Global",
         "source": "DSE MARKET UPDATE.xlsx", "origin": "Workbook"},
        {"section": "Macro -- yield curve, inflation",
         "source": yc_source, "origin": "External"},
        {"section": "Macro -- listed bond prices",
         "source": "DSE / Treasury Bond table", "origin": "Workbook"},
        {"section": "Calendar -- Talk of the Market",
         "source": ("macro_data.json" if macro_talk
                    else "daily-bd-financial-news / manual"),
         "origin": "External"},
    ]


# --------------------------------------------------------------------------
# top-level payload
# --------------------------------------------------------------------------

def build_payload(wb, ctx):
    today = ctx["today"]
    pe_now = ctx["pe_hist"][-1] if ctx["pe_hist"] else None
    ext5_hi, ext5_lo, ok5 = ctx["ext5"]
    ext10_hi, ext10_lo, ok10 = ctx["ext10"]
    near_hi, near_lo = A.near_extremes(wb.all_data, band=3.0, limit=9)

    payload = {
        "meta": {
            "as_of": ctx["as_of"], "wb_stamp": wb.dse.get("_stamp"),
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "hist_span_from": ctx["hist_span_from"],
            "hist_span_to": ctx["hist_dates"][-1] if ctx["hist_dates"] else None,
            "n_tickers": len(wb.all_data), "n_sessions": len(ctx["hist_dates"]),
            "workbook_file": wb.path.name,
            "missing_dse_tables": wb.dse.get("_missing") or [],
        },
        "provenance": build_provenance(ctx),
        "commentary": ctx["commentary"],
        "kpi": {
            "dsex": {"level": today["dsex"], "chg": ctx["dsex_chg"], "pct": ctx["dsex_pct"]},
            "dses": {"level": today["dses"], "chg": ctx["dses_chg"], "pct": ctx["dses_pct"]},
            "ds30": {"level": today["ds30"], "chg": ctx["ds30_chg"], "pct": ctx["ds30_pct"]},
            "turnover": {"value": today["value"], "chg_pct": ctx["turnover_chg"]},
            "mcap": {"value": today["mcap"], "chg_pct": ctx["mcap_chg"]},
            "trades": {"value": today["trade"], "chg_pct": ctx["trade_chg"]},
            "volume": {"value": today["volume"], "chg_pct": ctx["volume_chg"]},
            "pe": pe_now,
        },
        "breadth": {"adv": ctx["adv"], "dec": ctx["dec"], "unch": ctx["unch"],
                    "traded": ctx["traded"]},
        "extremes_summary": {
            "hi52": ctx["hi52"], "lo52": ctx["lo52"],
            "ext5": {"hi": ext5_hi, "lo": ext5_lo, "covered": bool(ok5)},
            "ext10": {"hi": ext10_hi, "lo": ext10_lo, "covered": bool(ok10)},
            "hist_span_from": ctx["hist_span_from"],
        },
        "index_movers": [{"ticker": tk, "pts": pts, "day_pct": chg}
                         for tk, pts, chg in ctx["movers"]],
        "index_draggers": [{"ticker": tk, "pts": pts, "day_pct": chg}
                           for tk, pts, chg in ctx["draggers"]],
        "index_returns": A.index_returns(wb.hist),
        "trend": {
            "dates": ctx["hist_dates"], "dsex": ctx["dsex_hist"],
            "dses": ctx["dses_hist"], "ds30": ctx["ds30_hist"],
            "turnover": ctx["turnover_hist"], "pe": ctx["pe_hist"],
        },
        "recent": ctx["recent"],
        "summary": build_summary_section(wb, ctx),
        "movers": {
            "gainers": ctx["gainers"], "losers": ctx["losers"],
            "ff_mcap_top12": A.top_by(wb.all_data, "FF Mcap", 12),
            "mcap_top12": A.top_by(wb.all_data, "Today's MCap", 12),
            "universe": build_universe(wb),
        },
        "sectors": ctx["sectors"],
        "sector_label_audit_n": len(ctx["label_audit"]),
        "turnover_weight_change": [
            {"sector": name, "share": v["share"], "avg_share": v["avg_share"],
             "change_pp": v["change_pp"]}
            for name, v in A.turnover_weight_change(wb.hist).items()
        ],
        "technicals": build_technicals(ctx),
        "hi_list": ctx["hi_list"], "lo_list": ctx["lo_list"],
        "near_hi": near_hi, "near_lo": near_lo,
        "leaderboards": build_leaderboards(wb),
        "blocks": build_blocks(ctx),
        "macro": build_macro(ctx),
        "global": build_global(ctx),
        "calendar": build_calendar(ctx),
    }
    return jsafe(payload)


# --------------------------------------------------------------------------
# render
# --------------------------------------------------------------------------

def render(payload):
    if not TEMPLATE.exists():
        raise FileNotFoundError(f"Template not found: {TEMPLATE}")
    html = TEMPLATE.read_text(encoding="utf-8")
    if DATA_PLACEHOLDER not in html:
        raise RuntimeError(f"Template is missing the {DATA_PLACEHOLDER} marker")
    data_js = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return html.replace(DATA_PLACEHOLDER, data_js)


def build(workbook_path, out_path=None):
    print(f"Reading {workbook_path} ...")
    wb = Workbook(workbook_path)
    missing = wb.dse.get("_missing") or []
    if missing:
        print(f"  ! DSE sheet tables not found: {', '.join(missing)}")
    ctx = build_context(wb)
    print(f"  as of {ctx['as_of']}  |  {len(wb.all_data)} tickers  |  "
          f"{len(ctx['hist_dates'])} sessions of history")

    payload = build_payload(wb, ctx)
    html = render(payload)

    out = Path(out_path) if out_path else (SCRIPT_DIR / "dse_live_dashboard.html")
    out.write_text(html, encoding="utf-8")
    size_kb = out.stat().st_size / 1024
    print(f"\nWrote {out}  ({size_kb:,.0f} KB)")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workbook", default=str(DEFAULT_WB))
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    wb_path = Path(args.workbook)
    if not wb_path.exists():
        print(f"Workbook not found: {wb_path}")
        return 1
    build(wb_path, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
