r"""
DSE MARKET UPDATE -- analytics layer.

Everything derived rather than read straight off a cell lives here:
moving averages / MACD / RSI on the DSEX series, index-level support and
resistance by swing-point clustering with turnover confirmation, category
and market-cap breadth cuts built from ALL DATA, sector aggregates,
leaderboards, high/low check lists and the corporate calendar.

Dependencies: numpy (plus dse_data).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

import numpy as np

from dse_data import num, txt, serial_to_date


# --------------------------------------------------------------------------
# technical indicators
# --------------------------------------------------------------------------

def sma(values, window):
    v = np.asarray(values, dtype=float)
    if len(v) < window:
        return np.full(len(v), np.nan)
    out = np.full(len(v), np.nan)
    csum = np.cumsum(np.insert(v, 0, 0.0))
    out[window - 1:] = (csum[window:] - csum[:-window]) / window
    return out


def ema(values, span):
    v = np.asarray(values, dtype=float)
    if len(v) == 0:
        return v
    alpha = 2.0 / (span + 1.0)
    out = np.empty(len(v))
    out[0] = v[0]
    for i in range(1, len(v)):
        out[i] = alpha * v[i] + (1 - alpha) * out[i - 1]
    return out


def macd(values, fast=12, slow=26, signal=9):
    line = ema(values, fast) - ema(values, slow)
    sig = ema(line, signal)
    return line, sig, line - sig


def rsi(values, period=14):
    v = np.asarray(values, dtype=float)
    if len(v) <= period:
        return np.full(len(v), np.nan)
    delta = np.diff(v)
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    out = np.full(len(v), np.nan)
    ag, al = gain[:period].mean(), loss[:period].mean()
    out[period] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    for i in range(period + 1, len(v)):
        ag = (ag * (period - 1) + gain[i - 1]) / period
        al = (al * (period - 1) + loss[i - 1]) / period
        out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def index_technicals(dates, closes, windows=(3, 9, 21)):
    """MA set, MACD, RSI and the index's position against each MA."""
    closes = list(map(float, closes))
    spot = closes[-1]
    mas = {}
    for w in windows:
        arr = sma(closes, w)
        mas[w] = float(arr[-1]) if not np.isnan(arr[-1]) else None
    line, sig, histo = macd(closes)
    r = rsi(closes)
    trend = {}
    for w, val in mas.items():
        if val is None:
            trend[w] = "n/a"
        else:
            trend[w] = "above" if spot >= val else "below"
    return {
        "spot": spot,
        "ma": mas,
        "trend": trend,
        "macd": float(line[-1]),
        "macd_signal": float(sig[-1]),
        "macd_hist": float(histo[-1]),
        "macd_cross": "bullish" if histo[-1] > 0 else "bearish",
        "macd_flip": (len(histo) > 1 and np.sign(histo[-1]) != np.sign(histo[-2])),
        "rsi": (float(r[-1]) if not np.isnan(r[-1]) else None),
        "series": {"dates": dates, "close": closes,
                   "ma": {w: sma(closes, w) for w in windows},
                   "macd": line, "signal": sig, "hist": histo},
    }


# --------------------------------------------------------------------------
# support / resistance -- swing-point clustering + turnover confirmation
# --------------------------------------------------------------------------

def swing_points(values, k=5):
    """Pivot highs/lows: a bar that is the extreme of its +/- k neighbourhood."""
    v = np.asarray(values, dtype=float)
    highs, lows = [], []
    for i in range(k, len(v) - k):
        window = v[i - k:i + k + 1]
        if v[i] == window.max() and (window.max() > window.min()):
            highs.append(i)
        if v[i] == window.min() and (window.max() > window.min()):
            lows.append(i)
    return highs, lows


def cluster_levels(values, idxs, turnover, tol_pct, min_touches=2):
    """
    Group pivots whose prices sit within tol_pct of each other into one level.

    Level price is the turnover-weighted mean of its members, so a level
    defended on heavy volume prints where the trading actually happened.
    """
    pts = sorted(((float(values[i]), i) for i in idxs), key=lambda p: p[0])
    clusters, cur = [], []
    for price, i in pts:
        if not cur or abs(price - cur[0][0]) / cur[0][0] * 100.0 <= tol_pct:
            cur.append((price, i))
        else:
            clusters.append(cur)
            cur = [(price, i)]
    if cur:
        clusters.append(cur)

    mean_to = float(np.mean(turnover)) if len(turnover) else 1.0
    out = []
    for cl in clusters:
        if len(cl) < min_touches:
            continue
        prices = np.array([p for p, _ in cl])
        idx = [i for _, i in cl]
        vols = np.array([turnover[i] for i in idx], dtype=float)
        w = vols if vols.sum() > 0 else np.ones_like(prices)
        level = float((prices * w).sum() / w.sum())
        vol_conf = float(vols.mean() / mean_to) if mean_to else 1.0
        out.append({
            "level": level,
            "touches": len(cl),
            "last_touch": max(idx),
            "vol_confirmation": vol_conf,
            "score": len(cl) * (0.5 + 0.5 * min(vol_conf, 3.0)),
        })
    return out


def support_resistance(dates, closes, turnover, k=5, tol_pct=0.75,
                       min_touches=2, top_n=3):
    """
    Index-level S/R.  Pivots from a +/-k-bar swing scan, clustered within
    tol_pct, each cluster confirmed by the turnover traded on its touch days.
    Supports are clusters below spot, resistances above.
    """
    highs, lows = swing_points(closes, k=k)
    spot = float(closes[-1])
    all_levels = cluster_levels(closes, highs + lows, turnover, tol_pct, min_touches)

    sup = sorted([l for l in all_levels if l["level"] < spot * 0.999],
                 key=lambda l: (-l["score"], spot - l["level"]))
    res = sorted([l for l in all_levels if l["level"] > spot * 1.001],
                 key=lambda l: (-l["score"], l["level"] - spot))

    def decorate(levels):
        out = []
        for l in levels[:top_n]:
            l = dict(l)
            l["distance_pct"] = (l["level"] - spot) / spot * 100.0
            l["last_touch_date"] = dates[l["last_touch"]]
            out.append(l)
        return sorted(out, key=lambda x: -x["level"])

    return {
        "spot": spot,
        "supports": decorate(sup),
        "resistances": decorate(res),
        "params": {"swing_window": k, "tolerance_pct": tol_pct,
                   "min_touches": min_touches, "sample_days": len(closes),
                   "from": dates[0], "to": dates[-1]},
    }


# --------------------------------------------------------------------------
# breadth, category and market-cap cuts (derived from ALL DATA)
# --------------------------------------------------------------------------

def _chg(rec):
    return num(rec.get("Day Change (%)"), None)


def breadth_by(rows, key):
    """Advanced / declined / unchanged + trade / value / volume by `key` field."""
    agg = defaultdict(lambda: {"adv": 0, "dec": 0, "unch": 0, "n": 0,
                               "trade": 0.0, "value": 0.0, "volume": 0.0,
                               "mcap": 0.0, "mcap_wk": 0.0})
    for r in rows:
        k = txt(r.get(key)) or "Unclassified"
        a = agg[k]
        c = _chg(r)
        traded = (num(r.get("TRADE"), 0) or 0) > 0
        if traded:
            a["n"] += 1
            if c is None or abs(c) < 1e-9:
                a["unch"] += 1
            elif c > 0:
                a["adv"] += 1
            else:
                a["dec"] += 1
        a["trade"] += num(r.get("TRADE"), 0) or 0
        a["value"] += num(r.get("VALUE (mn)"), 0) or 0
        a["volume"] += num(r.get("Volume"), 0) or 0
        a["mcap"] += num(r.get("Today's MCap"), 0) or 0
        a["mcap_wk"] += num(r.get("Week-end Mcap"), 0) or 0
    for k, a in agg.items():
        a["wow_pct"] = ((a["mcap"] / a["mcap_wk"] - 1) * 100.0
                        if a["mcap_wk"] else None)
    return dict(agg)


CAP_ORDER = ["Mega Cap", "Large Cap", "Mid Cap", "Small Cap", "Micro Cap"]
CAT_ORDER = ["A", "B", "N", "Z", "MF", "CB", "G-sec"]


def ordered(agg, order):
    keys = [k for k in order if k in agg] + sorted(k for k in agg if k not in order)
    return [(k, agg[k]) for k in keys]


# --------------------------------------------------------------------------
# movers, leaderboards, check lists
# --------------------------------------------------------------------------

def index_movers(rows, n=5):
    """Top index movers / draggers from ALL DATA's Index Mover (Today) points."""
    scored = []
    for r in rows:
        m = num(r.get("Index Mover (Today)"))
        if m is None or abs(m) < 1e-9:
            continue
        scored.append((txt(r.get("Tickers")), m, num(r.get("Day Change (%)"), 0) * 100))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:n], list(reversed(scored[-n:]))


def top_movers(gainers, losers, by_ticker):
    """DSE's own gainer/loser tables joined to ALL DATA's multi-period returns."""
    def build(rows):
        out = []
        for rec in rows:
            t = txt(rec.get("TRADING CODE")).upper()
            a = by_ticker.get(t, {})
            out.append({
                "ticker": t,
                "close": num(rec.get("CLOSEP*")),
                "high": num(rec.get("HIGH")),
                "low": num(rec.get("LOW")),
                "ycp": num(rec.get("YCP*")),
                "day": num(rec.get("% CHANGE")),
                "week": _pct(a.get("1 Week Mcap Return")),
                "month": _pct(a.get("1 Month MCap Return")),
                "year": _pct(a.get("52 Week Mcap Return")),
                "sector": txt(a.get("Sector")),
            })
        return out
    return build(gainers), build(losers)


def _pct(v):
    """ALL DATA stores returns as fractions; render as percent."""
    f = num(v)
    return None if f is None else f * 100.0


def top_by(rows, field, n=12, extra=None):
    out = []
    for r in rows:
        v = num(r.get(field))
        if v is None:
            continue
        item = {
            "ticker": txt(r.get("Tickers")),
            "sector": txt(r.get("Sector")),
            "value": v,
            "close": num(r.get("CLOSEP*")),
            "day": _pct(r.get("Day Change (%)")),
        }
        if extra:
            for label, fld in extra.items():
                item[label] = num(r.get(fld))
        out.append(item)
    out.sort(key=lambda x: x["value"], reverse=True)
    return out[:n]


def most_active(rows, group_field, n_per=1, metric="V/TPS"):
    """Most-active scrip per sector / segment by turnover-to-paid-up ratio."""
    groups = defaultdict(list)
    for r in rows:
        v = num(r.get(metric))
        if v is None:
            continue
        groups[txt(r.get(group_field)) or "Unclassified"].append((v, r))
    out = []
    for g, items in groups.items():
        items.sort(key=lambda p: p[0], reverse=True)
        for v, r in items[:n_per]:
            out.append({
                "group": g,
                "ticker": txt(r.get("Tickers")),
                "metric": v,
                "value_mn": num(r.get("VALUE (mn)")),
                "day": _pct(r.get("Day Change (%)")),
                "close": num(r.get("CLOSEP*")),
            })
    out.sort(key=lambda x: x["metric"], reverse=True)
    return out


def turnover_leaders(rows, group_field, n_per=1):
    groups = defaultdict(list)
    for r in rows:
        v = num(r.get("VALUE (mn)"))
        if v is None:
            continue
        groups[txt(r.get(group_field)) or "Unclassified"].append((v, r))
    out = []
    for g, items in groups.items():
        items.sort(key=lambda p: p[0], reverse=True)
        for v, r in items[:n_per]:
            out.append({
                "group": g,
                "ticker": txt(r.get("Tickers")),
                "value_mn": v,
                "day": _pct(r.get("Day Change (%)")),
                "close": num(r.get("CLOSEP*")),
            })
    out.sort(key=lambda x: x["value_mn"], reverse=True)
    return out


def high_low_checklist(rows, eps_map, tol=0.001):
    """
    Tickers whose close sits at (or through) their 52-week high / low.

    5-year and 10-year windows are reported only if the workbook's own
    price history actually spans them -- the caller passes what it has.
    """
    highs, lows = [], []
    for r in rows:
        close = num(r.get("CLOSEP*"))
        hi = num(r.get("52 week High"))
        lo = num(r.get("52 week Low"))
        if not close or close <= 0:
            continue
        # a scrip that did not trade today cannot have "hit" anything -- its
        # stored 52-week high and low often both equal its stale last price,
        # which would otherwise put it on both lists at once
        if (num(r.get("TRADE"), 0) or 0) <= 0:
            continue
        t = txt(r.get("Tickers")).upper()
        e = eps_map.get(t, {})
        base = {
            "ticker": t,
            "sector": txt(r.get("Sector")),
            "close": close,
            "day": _pct(r.get("Day Change (%)")),
            "high52": hi,
            "low52": lo,
            "qoq": _pct(e.get("Cur Y. LQ v/s Cur Y. Prev.Q")),
            "yoy": _pct(e.get("Cur Y LatestQ v/s PrevY ThisQ")),
            "ytd": _pct(r.get("YTD Change")),
        }
        if hi and close >= hi * (1 - tol):
            item = dict(base)
            item["vs_level"] = (close / hi - 1) * 100.0 if hi else None
            highs.append(item)
        if lo and close <= lo * (1 + tol):
            item = dict(base)
            item["vs_level"] = (close / lo - 1) * 100.0 if lo else None
            lows.append(item)
    highs.sort(key=lambda x: (x["day"] or 0), reverse=True)
    lows.sort(key=lambda x: (x["day"] or 0))
    return highs, lows


def near_extremes(rows, band=3.0, limit=10):
    """
    Traded scrips sitting within `band` percent of a 52-week extreme without
    having printed it today -- the watch list behind the check lists.
    """
    near_hi, near_lo = [], []
    for r in rows:
        close = num(r.get("CLOSEP*"))
        hi, lo = num(r.get("52 week High")), num(r.get("52 week Low"))
        if not close or (num(r.get("TRADE"), 0) or 0) <= 0:
            continue
        base = {"ticker": txt(r.get("Tickers")),
                "sector": txt(r.get("Sector")),
                "close": close,
                "day": _pct(r.get("Day Change (%)")),
                "value": num(r.get("VALUE (mn)"))}
        if hi and hi > close:
            gap = (close / hi - 1) * 100.0
            if -band <= gap < 0:
                near_hi.append(dict(base, level=hi, gap=gap))
        if lo and lo < close:
            gap = (close / lo - 1) * 100.0
            if 0 < gap <= band:
                near_lo.append(dict(base, level=lo, gap=gap))
    near_hi.sort(key=lambda x: x["gap"], reverse=True)
    near_lo.sort(key=lambda x: x["gap"])
    return near_hi[:limit], near_lo[:limit]


def turnover_weight_change(hist, lookback=5):
    """
    Each sector's share of market turnover today against its average share
    over the previous `lookback` sessions -- computed from Historical Data's
    "Sector Value" block, in percentage points.
    """
    names = hist.names("Sector Value")
    series = {}
    for n in names:
        ds, vs = hist.series(n, "Sector Value")
        if len(vs) > lookback:
            series[n] = vs
    if not series:
        return {}
    span = min(len(v) for v in series.values())
    today_total = sum(v[-1] for v in series.values()) or 1.0
    out = {}
    for n, v in series.items():
        share_now = v[-1] / today_total * 100.0
        prev = []
        for i in range(2, min(lookback + 2, span + 1)):
            tot = sum(x[-i] for x in series.values()) or 1.0
            prev.append(x_share := v[-i] / tot * 100.0)
        avg_prev = sum(prev) / len(prev) if prev else share_now
        out[n] = {"share": share_now, "avg_share": avg_prev,
                  "change_pp": share_now - avg_prev, "turnover": v[-1]}
    return out


def index_returns(hist, names=("DSEX", "DSES", "DS30")):
    """Day / WoW / MoM / YTD / 1Y for each headline index, off its own series."""
    import datetime as _dt
    out = []
    for name in names:
        ds, vs = hist.series(name)
        if len(vs) < 2:
            continue
        spot, last = vs[-1], ds[-1]

        def at_or_before(target):
            best = None
            for d, v in zip(ds, vs):
                if d <= target:
                    best = v
                else:
                    break
            return best

        bases = {
            "day": vs[-2],
            "week": at_or_before(last - _dt.timedelta(days=7)),
            "month": at_or_before(last - _dt.timedelta(days=30)),
            "ytd": at_or_before(_dt.date(last.year, 1, 1)),
            "year": at_or_before(last - _dt.timedelta(days=365)),
        }
        row = {"index": name, "level": spot}
        for k, b in bases.items():
            row[k] = ((spot / b - 1) * 100.0) if b else None
        window = [v for d, v in zip(ds, vs)
                 if d >= last - _dt.timedelta(days=365)]
        row["high"] = max(window)
        row["low"] = min(window)
        out.append(row)
    return out


def dividend_yield(rec, face=10.0):
    """
    Cash dividend as a yield on the current price.  DSE quotes the cash
    dividend as a percentage of the BDT 10 face value, so the payout per
    share is cash%/100 * face -- ALL DATA's own Dividend Yield column is 0
    for most scrips in this workbook, so the deck derives it instead.
    """
    cash = num(rec.get("Cash Dividend%"))
    close = num(rec.get("CLOSEP*")) or num(rec.get("close"))
    if not cash or not close:
        return None
    return cash / 100.0 * face / close * 100.0


def extreme_counts(hist, years, as_of):
    """
    New N-year highs / lows from Historical Data's own CP* block.

    Returns (count_high, count_low, covered) -- covered is False when the
    stored history is shorter than the requested lookback, in which case the
    counts are not computed at all.
    """
    if not hist.dates:
        return None, None, False
    span_days = (hist.dates[-1] - hist.dates[0]).days
    if span_days < years * 365 - 30:
        return None, None, False
    cutoff = as_of - __import__("datetime").timedelta(days=int(years * 365))
    cols = [(c, d) for c, d in hist.date_cols if d >= cutoff]
    n_hi = n_lo = 0
    for (section, name), row in hist._index.items():
        if section != "CP*":
            continue
        vals = [num(hist.sheet.get(row, c)) for c, _ in cols]
        vals = [v for v in vals if v is not None and v > 0]
        if len(vals) < 20:
            continue
        last = vals[-1]
        if last >= max(vals) * 0.999:
            n_hi += 1
        if last <= min(vals) * 1.001:
            n_lo += 1
    return n_hi, n_lo, True


# --------------------------------------------------------------------------
# sector table
# --------------------------------------------------------------------------


def sector_aggregates(all_rows, sector_rows, basis_dates=None):
    """
    Sector table built from ALL DATA (turnover / trade / volume / Mcap summed
    per sector) with No. of Companies, Sector P/E and market weight taken from
    Sector Report.  Every return is computed here from the dated Mcap columns
    -- see `basis_dates`, which comes from ALL DATA's own date stamps -- rather
    than read off the sheet, because Sector Report's "YTD Return" and
    "1 Year Return" labels are transposed relative to the Mcap columns they
    are derived from.
    """
    meta = {}
    for r in sector_rows:
        meta[txt(r.get("Sector"))] = {
            "n": num(r.get("Number of Companies")),
            "pe": num(r.get("Sector P/E")),
            "weight": _pct(r.get("Total Market Weight")),
            "e_weight": _pct(r.get("E. Market Weight")),
        }

    agg = defaultdict(lambda: defaultdict(float))
    for r in all_rows:
        s = txt(r.get("Sector")) or "Unclassified"
        a = agg[s]
        a["turnover"] += num(r.get("VALUE (mn)"), 0) or 0
        a["trade"] += num(r.get("TRADE"), 0) or 0
        a["volume"] += num(r.get("Volume"), 0) or 0
        for label, field in (("mcap", "Today's MCap"), ("d1", "Yesterday Mcap"),
                             ("w1", "Week-end Mcap"), ("m1", "Month-end Mcap"),
                             ("y1", "52 Week-end Mcap"),
                             ("ytd", "Last Year  Ending Mcap")):
            a[label] += num(r.get(field), 0) or 0
        a["_n"] += 1

    total_turnover = sum(a["turnover"] for a in agg.values()) or 1.0
    total_mcap = sum(a["mcap"] for a in agg.values()) or 1.0

    out = []
    for s, a in agg.items():
        m = meta.get(s, {})
        def rel(base):
            return (a["mcap"] / a[base] - 1) * 100.0 if a[base] else None
        out.append({
            "sector": s,
            "n": m.get("n") or a["_n"],
            "turnover": a["turnover"],
            "turnover_share": a["turnover"] / total_turnover * 100.0,
            "trade": a["trade"],
            "volume": a["volume"],
            "mcap": a["mcap"],
            "weight": a["mcap"] / total_mcap * 100.0,
            "day": rel("d1"),
            "week": rel("w1"),
            "month": rel("m1"),
            "ytd": rel("ytd"),
            "year": rel("y1"),
            "pe": m.get("pe"),
        })
    out.sort(key=lambda x: x["turnover"], reverse=True)
    return out


def basis_dates(all_data_sheet, header_row=1):
    """
    Read the date stamps ALL DATA parks one row above its Mcap/Price columns,
    so every lookback the deck quotes names the day it is actually measured
    from instead of assuming a convention.
    """
    out = {}
    for c in range(all_data_sheet.ncols):
        h = all_data_sheet.get(header_row, c)
        d = serial_to_date(all_data_sheet.get(header_row - 1, c))
        if isinstance(h, str) and d:
            out[h.strip()] = d
    return out


def sector_label_audit(sector_rows, all_rows):
    """
    Cross-check Sector Report's stated returns against the Mcap columns.
    Returns the list of (sector, stated field, matching basis) mismatches --
    used to footnote the deck rather than to silently "correct" the sheet.
    """
    issues = []
    for r in sector_rows:
        name = txt(r.get("Sector"))
        cur = num(r.get("Day Close Mcap"))
        if not cur:
            continue
        bases = {
            "Yesterday": num(r.get("Yestderday Mcap")),
            "Week-end": num(r.get("Week-end Mcap")),
            "Month-end": num(r.get("Month-end Mcap")),
            "52 Week-end": num(r.get("52 Week-end Mcap")),
            "Year-start": num(r.get("Beginning Price this Year")),
        }
        for stated_field, expected in (("YTD Return", "Year-start"),
                                       ("1 Year Return", "52 Week-end")):
            stated = num(r.get(stated_field))
            if stated is None:
                continue
            match = None
            for bname, b in bases.items():
                if b and abs((cur / b - 1) - stated) < 1e-6:
                    match = bname
                    break
            if match and match != expected:
                issues.append((name, stated_field, match))
    return issues


# --------------------------------------------------------------------------
# corporate calendar
# --------------------------------------------------------------------------

def corporate_calendar(rows, as_of, horizon_days=60, limit=18):
    """Upcoming record dates and AGMs, from today forward."""
    end = as_of + __import__("datetime").timedelta(days=horizon_days)
    recs, agms = [], []
    for r in rows:
        t = txt(r.get("Tickers"))
        rd = serial_to_date(r.get("Latest Record Date"))
        ag = serial_to_date(r.get("Latest AGM"))
        base = {"ticker": t, "sector": txt(r.get("Sector")),
                "close": num(r.get("CLOSEP*")),
                "cash": num(r.get("Cash Dividend%")),
                "stock": num(r.get("Stock Dividend %")),
                "yield": dividend_yield(r)}
        if rd and as_of <= rd <= end:
            recs.append(dict(base, date=rd))
        if ag and as_of <= ag <= end:
            agms.append(dict(base, date=ag))
    recs.sort(key=lambda x: (x["date"], x["ticker"]))
    agms.sort(key=lambda x: (x["date"], x["ticker"]))
    return recs[:limit], agms[:limit]


# --------------------------------------------------------------------------
# market commentary
# --------------------------------------------------------------------------

def commentary(ctx):
    """
    3-4 sentence day wrap, built only from figures already computed.
    No narrative that isn't traceable to a number on the deck.
    """
    d = ctx
    dsex_dir = "gained" if d["dsex_chg"] >= 0 else "shed"
    s = []
    s.append(
        f"DSEX {dsex_dir} {abs(d['dsex_chg']):,.2f} points ({d['dsex_pct']:+.2f}%) to close at "
        f"{d['dsex']:,.2f}, with {d['adv']:,.0f} issues advancing against "
        f"{d['dec']:,.0f} declining and {d['unch']:,.0f} unchanged out of "
        f"{d['traded']:,.0f} traded."
    )
    turn_dir = "rose" if d["turnover_chg"] >= 0 else "fell"
    s.append(
        f"Turnover {turn_dir} {abs(d['turnover_chg']):.1f}% to BDT {d['turnover']:,.0f}mn on "
        f"{d['trades']:,.0f} trades, and total market capitalisation ended at BDT "
        f"{d['mcap'] / 1000:,.2f}bn ({d['mcap_chg']:+.2f}%)."
    )
    if d["lead_sectors"]:
        up = ", ".join(f"{n} ({v:+.2f}%)" for n, v in d["lead_sectors"])
        dn = ", ".join(f"{n} ({v:+.2f}%)" for n, v in d["lag_sectors"])
        s.append(f"{up} led the sector board while {dn} lagged.")
    if d["movers"]:
        mv = ", ".join(f"{t} ({p:+.2f} pts)" for t, p, _ in d["movers"][:3])
        dg = ", ".join(f"{t} ({p:+.2f} pts)" for t, p, _ in d["draggers"][:3])
        s.append(f"{mv} contributed most to the index, against {dg} on the other side.")
    return " ".join(s)
