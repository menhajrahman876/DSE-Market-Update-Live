r"""
DSE MARKET UPDATE -- data layer.

Reads "DSE MARKET UPDATE.xlsb" and exposes every table the day-end report
needs.  Nothing about the workbook's geometry is hardcoded: the DSE sheet's
side-by-side tables are found by scanning for their banner text and walking
each banner's contiguous header block, and Historical Data's date columns
and section blocks are discovered the same way.  Column letters can move as
the file grows without breaking this module.

Dependencies: pyxlsb, numpy.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pyxlsb

EXCEL_EPOCH = date(1899, 12, 30)


# --------------------------------------------------------------------------
# scalar coercion
# --------------------------------------------------------------------------

def serial_to_date(v):
    """Excel serial / datetime / 'dd-mm-yyyy' string -> date, else None."""
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        if 20000 < v < 80000:
            return EXCEL_EPOCH + timedelta(days=int(v))
        return None
    s = str(v).strip()
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%b-%Y", "%d-%b-%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def num(v, default=None):
    """Float, tolerating DSE's '--' / '-' / '' placeholders."""
    if v is None or isinstance(v, bool):
        return default
    if isinstance(v, (int, float)):
        f = float(v)
        return default if (np.isnan(f) or np.isinf(f)) else f
    s = str(v).strip().replace(",", "").replace("%", "")
    if s in ("", "-", "--", "n/a", "N/A", "#N/A", "nan", "NULL"):
        return default
    try:
        return float(s)
    except ValueError:
        return default


def txt(v, default=""):
    if v is None:
        return default
    if isinstance(v, float) and float(v).is_integer():
        return str(int(v))
    return str(v).strip()


# --------------------------------------------------------------------------
# sparse sheet
# --------------------------------------------------------------------------

class Sheet:
    """cells[(row, col)] -> value, both 0-based."""

    def __init__(self, name, cells, nrows, ncols):
        self.name = name
        self.cells = cells
        self.nrows = nrows
        self.ncols = ncols

    def get(self, r, c, default=None):
        v = self.cells.get((r, c), default)
        return default if v == "" else v

    def find_cells(self, pattern, max_row=None):
        rx = re.compile(pattern, re.I)
        hits = []
        for (r, c), v in self.cells.items():
            if max_row is not None and r > max_row:
                continue
            if isinstance(v, str) and rx.search(v):
                hits.append((r, c, v))
        return sorted(hits)

    def find_header_row(self, *labels, max_row=30):
        """First row containing every one of `labels` (exact, case-insensitive)."""
        want = {l.strip().lower() for l in labels}
        by_row = {}
        for (r, c), v in self.cells.items():
            if r <= max_row and isinstance(v, str):
                by_row.setdefault(r, set()).add(v.strip().lower())
        for r in sorted(by_row):
            if want <= by_row[r]:
                return r
        return None


def read_workbook(path):
    """{sheet name: Sheet}."""
    sheets = {}
    with pyxlsb.open_workbook(str(path)) as wb:
        for name in wb.sheets:
            cells, nrows, ncols = {}, 0, 0
            with wb.get_sheet(name) as sh:
                for row in sh.rows():
                    for cell in row:
                        if cell.v is not None and cell.v != "":
                            cells[(cell.r, cell.c)] = cell.v
                            nrows = max(nrows, cell.r + 1)
                            ncols = max(ncols, cell.c + 1)
            sheets[name] = Sheet(name, cells, nrows, ncols)
    return sheets


# --------------------------------------------------------------------------
# header-row -> list of dicts
# --------------------------------------------------------------------------

def table_from_header(sheet, header_row, col_lo, col_hi, max_blank_rows=3):
    headers = {}
    for c in range(col_lo, col_hi + 1):
        h = sheet.get(header_row, c)
        if h is not None and str(h).strip():
            headers[c] = str(h).strip()
    if not headers:
        return []
    out, blanks = [], 0
    for r in range(header_row + 1, sheet.nrows):
        rec = {headers[c]: sheet.get(r, c) for c in headers}
        if all(v is None for v in rec.values()):
            blanks += 1
            if blanks >= max_blank_rows:
                break
            continue
        blanks = 0
        rec["_row"] = r
        out.append(rec)
    return out


def contiguous_header_span(sheet, header_row, start_col):
    """Walk right from start_col until the header row goes blank."""
    c, last = start_col, start_col
    while c < sheet.ncols:
        if sheet.get(header_row, c) is not None:
            last = c
        elif c > start_col:
            break
        c += 1
    return start_col, last


# --------------------------------------------------------------------------
# DSE sheet -- banner-driven discovery of the side-by-side tables
# --------------------------------------------------------------------------

DSE_BANNERS = {
    "latest_price": r"LATEST SHARE PRICE",
    "dsex_shares": r"DSEX INDEX SHARES",
    "ds30_shares": r"DS30 INDEX SHARES",
    "treasury": r"TREASURY BOND",
    "recent_market": r"RECENT MARKET INFORMATION",
    "gainers": r"TOP TEN GAINER",
    "losers": r"TOP TEN LOSER",
    "latest_pe": r"LATEST P/E",
    "market_summary": r"Market Summary",
    "block": r"Block Transaction",
    "global": r"GLOBAL MARKETS",
}


def parse_dse_sheet(sheet):
    banner_row, positions = None, {}
    for key, pat in DSE_BANNERS.items():
        hits = sheet.find_cells(pat, max_row=8)
        if not hits:
            continue
        r, c, _ = hits[0]
        positions[key] = c
        if banner_row is None or r < banner_row:
            banner_row = r
    if banner_row is None:
        raise RuntimeError("DSE sheet: no recognisable table banners found")

    header_row = banner_row + 1
    tables = {}
    for key, col in positions.items():
        lo, hi = contiguous_header_span(sheet, header_row, col)
        tables[key] = table_from_header(sheet, header_row, lo, hi)

    stamp = None
    for r in range(0, banner_row + 1):
        for c in range(0, 6):
            v = sheet.get(r, c)
            if isinstance(v, str) and "Last Updated" in v:
                stamp = v.split(":", 1)[1].strip()
    tables["_stamp"] = stamp
    tables["_missing"] = [k for k in DSE_BANNERS if k not in positions]
    return tables


# --------------------------------------------------------------------------
# Historical Data
# --------------------------------------------------------------------------

class Historical:
    """Wide time series: one row per metric, one column per trading date."""

    def __init__(self, sheet):
        self.sheet = sheet
        self.date_row = self._find_date_row()
        self.date_cols = []
        for c in range(sheet.ncols):
            d = serial_to_date(sheet.get(self.date_row, c))
            if d:
                self.date_cols.append((c, d))
        self.date_cols.sort(key=lambda p: p[1])
        self.dates = [d for _, d in self.date_cols]
        self.label_col = 0
        self.name_col = min(c for c, _ in self.date_cols) - 1
        self._index = self._build_index()

    def _find_date_row(self):
        best, best_n = None, 0
        for r in range(min(15, self.sheet.nrows)):
            n = sum(1 for c in range(self.sheet.ncols)
                    if serial_to_date(self.sheet.get(r, c)))
            if n > best_n:
                best, best_n = r, n
        if best is None or best_n < 20:
            raise RuntimeError("Historical Data: date header row not found")
        return best

    def _build_index(self):
        idx, section = {}, None
        for r in range(self.date_row + 1, self.sheet.nrows):
            lab = self.sheet.get(r, self.label_col)
            if isinstance(lab, str) and lab.strip():
                section = lab.strip()
            name = self.sheet.get(r, self.name_col)
            if isinstance(name, str) and name.strip():
                idx[(section, name.strip().upper())] = r
        return idx

    def sections(self):
        return sorted({s for s, _ in self._index if s})

    def names(self, section=None):
        return [n for s, n in self._index if s == section]

    def row_of(self, name, section=None):
        key = (section, name.strip().upper())
        if key in self._index:
            return self._index[key]
        for (sec, nm), r in self._index.items():
            if nm == name.strip().upper():
                return r
        return None

    def series(self, name, section=None):
        """(dates, values), chronological, blanks dropped."""
        row = self.row_of(name, section)
        if row is None:
            return [], []
        ds, vs = [], []
        for c, d in self.date_cols:
            v = num(self.sheet.get(row, c))
            if v is not None:
                ds.append(d)
                vs.append(v)
        return ds, vs


# --------------------------------------------------------------------------
# top-level bundle
# --------------------------------------------------------------------------

class Workbook:
    def __init__(self, path):
        self.path = Path(path)
        self.sheets = read_workbook(self.path)
        self.dse = parse_dse_sheet(self.sheets["DSE"])
        self.hist = Historical(self.sheets["Historical Data"])
        self.all_data = self._all_data()
        self.sector = self._sector_report()
        self.eps = self._eps_sheet()

    # ---- ALL DATA -------------------------------------------------------
    def _all_data(self):
        sh = self.sheets["ALL DATA"]
        hr = sh.find_header_row("Tickers", "Sector", "LTP")
        if hr is None:
            hits = sh.find_cells(r"^Tickers$", max_row=10)
            hr = hits[0][0] if hits else 1
        lo = min(c for (r, c) in sh.cells if r == hr)
        hi = max(c for (r, c) in sh.cells if r == hr)
        rows = table_from_header(sh, hr, lo, hi)
        return [r for r in rows if txt(r.get("Tickers"))]

    # ---- Sector Report --------------------------------------------------
    def _sector_report(self):
        sh = self.sheets["Sector Report"]
        hits = sh.find_cells(r"^Sector$", max_row=10)
        hr = hits[0][0] if hits else 1
        lo = min(c for (r, c) in sh.cells if r == hr)
        hi = max(c for (r, c) in sh.cells if r == hr)
        rows = table_from_header(sh, hr, lo, hi)
        return [r for r in rows if txt(r.get("Sector"))]

    # ---- EPS PE & NAV ---------------------------------------------------
    def _eps_sheet(self):
        sh = self.sheets.get("EPS PE & NAV")
        if sh is None:
            return {}
        hits = sh.find_cells(r"^Tickers$", max_row=10)
        if not hits:
            return {}
        hr = hits[0][0]
        lo = min(c for (r, c) in sh.cells if r == hr)
        hi = max(c for (r, c) in sh.cells if r == hr)
        out = {}
        for rec in table_from_header(sh, hr, lo, hi):
            t = txt(rec.get("Tickers")).upper()
            if t:
                out[t] = rec
        return out

    # ---- convenience ----------------------------------------------------
    def by_ticker(self):
        return {txt(r["Tickers"]).upper(): r for r in self.all_data}

    def recent_market(self):
        """Recent Market Information rows, newest first, dates parsed."""
        out = []
        for rec in self.dse.get("recent_market", []):
            d = serial_to_date(rec.get("Date"))
            if not d:
                continue
            out.append({
                "date": d,
                "trade": num(rec.get("Total Trade")),
                "volume": num(rec.get("Total Volume")),
                "value": num(rec.get("Total Value in Taka (mn)")),
                "mcap": num(rec.get("Total Market Cap. in Taka (mn)")),
                "dsex": num(rec.get("DSEX Index")),
                "dses": num(rec.get("DSES Index")),
                "ds30": num(rec.get("DS30 Index")),
                "dgen": num(rec.get("DGEN Index")),
            })
        out.sort(key=lambda r: r["date"], reverse=True)
        return out

    def market_summary(self):
        """Market Summary label/category/value list, in sheet order."""
        out = []
        for rec in self.dse.get("market_summary", []):
            label = txt(rec.get("Label"))
            if not label:
                continue
            out.append({
                "label": label,
                "category": txt(rec.get("Category")),
                "value": num(rec.get("Value")),
            })
        return out

    def as_of(self):
        rm = self.recent_market()
        if rm:
            return rm[0]["date"]
        return self.hist.dates[-1] if self.hist.dates else date.today()
