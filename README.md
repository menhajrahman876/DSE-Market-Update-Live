# DSE Market Update — Live

An interactive Dhaka Stock Exchange (DSE) day-end market dashboard — 12 tabs
(Overview, Trend, Summary & Breadth, Top Movers, Sectors heatmap, Technicals,
Extremes, Leaderboards, Blocks, Treasury & Macro, Global Markets, Calendar) with
sortable/searchable tables, sparklines, gain/loss flashes and a sector heatmap.

**[▶ Live on Streamlit Community Cloud](#deploy-to-streamlit-community-cloud)**
· light "Steel Contrast" theme · self-contained (Chart.js via CDN).

---

## How this works — important

This repo shows a **static snapshot**, not a real-time feed.

The underlying pipeline reads a local Excel workbook (`DSE MARKET UPDATE.xlsb`)
and, for true intraday updates, drives Excel via `pywin32` COM automation on
Windows. **Streamlit Community Cloud runs Linux with no Excel and no access to
that workbook**, so it can't scrape. Instead:

1. You generate a self-contained `dashboard_snapshot.html` **locally** (it only
   needs `pyxlsb` + `numpy` — no Excel required, it reads the `.xlsb` directly).
2. You commit + push that snapshot.
3. `streamlit_app.py` on Cloud simply displays it.

The snapshot's own header always prints the exact **as-of / workbook-refreshed /
generated** timestamps, so viewers know how fresh it is.

## Refresh what Cloud shows

On a machine that has the workbook:

```bash
python dse_live_dashboard.py \
    --workbook "PATH/TO/DSE MARKET UPDATE.xlsb" \
    --out dashboard_snapshot.html
git commit -am "Refresh snapshot" && git push
```

Cloud redeploys automatically on push.

## Deploy to Streamlit Community Cloud

1. Push this repo to GitHub (public — the free tier requires it).
2. Go to <https://share.streamlit.io> → **Create app** → pick this repo.
3. Main file path: **`streamlit_app.py`**. Deploy.

## Run locally

```bash
pip install -r requirements.txt
# view the current snapshot exactly as Cloud shows it:
streamlit run streamlit_app.py
# or just open dashboard_snapshot.html directly in a browser
```

## Files

| File | Role |
|---|---|
| `streamlit_app.py` | Cloud entry point — displays the committed snapshot |
| `dashboard_snapshot.html` | The generated snapshot (the data Cloud shows) |
| `dse_live_dashboard.py` | Snapshot generator — reads the `.xlsb`, fills the template |
| `dse_dashboard_template.html` | HTML/CSS/JS shell (tabs, tables, charts, heatmap) |
| `dse_data.py` | Reads the workbook; finds every table at runtime |
| `dse_analytics.py` | All derived analytics (MAs, MACD, RSI, S/R, breadth, sectors…) |
| `dse_context.py` | Assembles workbook + analytics into one context dict |
| `macro_data.json` | External macro inputs (govt yield curve, inflation) with sources |

## Data provenance

Everything except the two macro panels comes from the workbook. The government
yield curve and inflation series are external (from `macro_data.json`, with
source attribution shown in-app). Missing figures render as "Not Available" —
never estimated.

## Note

`dse_data.py` / `dse_analytics.py` / `dse_context.py` are copies of modules
maintained in a separate private pipeline that also produces a PowerPoint deck
from the same numbers; the analytics are identical so the dashboard and the deck
never disagree.
