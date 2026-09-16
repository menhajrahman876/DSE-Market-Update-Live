# DSE Market Update — Live

An interactive, auto-updating day-end market dashboard for the **Dhaka Stock
Exchange (DSE)** — 11 tabs (Overview, Trend, Summary & Breadth, Top Movers,
Sectors, Extremes, Leaderboards, Blocks, Treasury & Macro, Global Markets,
Calendar) with sortable/searchable tables, sparklines, gain/loss flashes and
a sector heatmap.

Built with a light "Steel Contrast" theme, self-contained (charts via
Chart.js from a CDN, no server-side rendering needed to view it).

## How it works

A **GitHub Actions cron job** runs every trading day after market close
(4:00 PM BDT / 10:00 UTC, Sunday–Thursday), reads a private Google Sheet via
a service account, runs the analytics pipeline, generates
`dashboard_snapshot.html`, and pushes it to `main`. Streamlit Community
Cloud auto-redeploys on every push, so the live app always shows the latest
snapshot with no server-side scheduler of its own.

```
Private Google Sheet ──▶ GitHub Actions (daily cron)
                              │
                              ▼
              Supporting code/dse_data.py        (reads the sheet)
              Supporting code/dse_analytics.py    (MAs, MACD, RSI, S/R, breadth…)
              Supporting code/dse_context.py      (assembles one context dict)
              Supporting code/dse_live_dashboard.py (renders the HTML)
                              │
                              ▼
                   dashboard_snapshot.html ──push──▶ Streamlit Community Cloud
                                                      (streamlit_app.py)
```

Only the rendered dashboard (the HTML snapshot) is committed to this public
repo — the underlying market data stays in a private Google Sheet.

### Local refresh (optional)

The snapshot can also be generated from a local `.xlsx` workbook — the
`--gsheet` flag is only needed for the cloud path:

```bash
python "Supporting code/dse_live_dashboard.py" \
    --workbook "PATH/TO/DSE MARKET UPDATE.xlsx" \
    --out dashboard_snapshot.html
git commit -am "Refresh snapshot" && git push
```

### Macro data

`Supporting code/macro_data.json` holds the two panels that don't come from
the workbook — the government treasury yield curve and inflation series.
`Supporting code/update_macro.py` refreshes the yield curve from Bangladesh
Bank; inflation is added manually via a CLI flag since BBS releases it
monthly. Every figure carries source attribution in-app; anything missing
renders as "Not Available" — never estimated.

## Run locally

```bash
pip install -r requirements.txt
# view the current snapshot exactly as Cloud shows it:
streamlit run streamlit_app.py
# or just open dashboard_snapshot.html directly in a browser
```

## Deploy your own copy to Streamlit Community Cloud

1. Push this repo to GitHub (public — the free tier requires it).
2. Go to <https://share.streamlit.io> → **Create app** → pick this repo.
3. Main file path: **`streamlit_app.py`**. Deploy.

For the full cloud automation setup (Google Sheet, service account, GitHub
secrets, cron), see
**[Supporting code/Readme & Markdown/SETUP_CLOUD.md](Supporting%20code/Readme%20%26%20Markdown/SETUP_CLOUD.md)**.

## Repository layout

| Path | Role |
|---|---|
| `streamlit_app.py` | Cloud entry point — displays the committed snapshot |
| `dashboard_snapshot.html` | The generated snapshot (what Cloud shows) |
| `requirements.txt` | Python dependencies for Streamlit Cloud / local runs |
| `.github/workflows/refresh.yml` | GitHub Actions cron job — daily cloud refresh |
| `Supporting code/dse_live_dashboard.py` | Snapshot generator — reads a local `.xlsx` or Google Sheets |
| `Supporting code/dse_dashboard_template.html` | HTML/CSS/JS shell (tabs, tables, charts, heatmap) |
| `Supporting code/dse_data.py` | Reads the workbook (local or Google Sheets); finds every table at runtime |
| `Supporting code/dse_analytics.py` | All derived analytics (moving averages, MACD, RSI, support/resistance, breadth, sectors…) |
| `Supporting code/dse_context.py` | Assembles workbook + analytics into one context dict |
| `Supporting code/macro_data.json` | External macro inputs (govt yield curve, inflation) with sources |
| `Supporting code/update_macro.py` | Refreshes `macro_data.json` from Bangladesh Bank |
| `Supporting code/Readme & Markdown/SETUP_CLOUD.md` | Step-by-step cloud automation setup guide |

## Data provenance

Everything except the two macro panels comes from the private workbook /
Google Sheet. The government yield curve and inflation series are external
(from `macro_data.json`, with source attribution shown in-app).
