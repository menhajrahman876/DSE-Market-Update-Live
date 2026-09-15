# DSE Market Update — Live

An interactive Dhaka Stock Exchange (DSE) day-end market dashboard — 12 tabs
(Overview, Trend, Summary & Breadth, Top Movers, Sectors heatmap, Technicals,
Extremes, Leaderboards, Blocks, Treasury & Macro, Global Markets, Calendar) with
sortable/searchable tables, sparklines, gain/loss flashes and a sector heatmap.

**[▶ Live on Streamlit Community Cloud](#deploy-to-streamlit-community-cloud)**
· light "Steel Contrast" theme · self-contained (Chart.js via CDN).

---

## How it works

A **GitHub Actions cron job** runs every trading day after market close
(4:30 PM BDT), reads a **private Google Sheet** via a service account, runs
the full analytics pipeline, generates `dashboard_snapshot.html`, and pushes
it to `main`. Streamlit Cloud auto-redeploys on push.

```
Private Google Sheet ──▶ GitHub Actions (daily cron)
                              │
                              ▼
                   dse_data.py  (reads sheet)
                   dse_analytics.py  (MAs, MACD, RSI, S/R, breadth…)
                   dse_context.py  (assembles context)
                   dse_live_dashboard.py  (generates HTML)
                              │
                              ▼
                   dashboard_snapshot.html ──push──▶ Streamlit Cloud
```

The raw market data stays in a private Google Sheet — only the rendered
dashboard (the HTML snapshot) is committed to this public repo.

### Local refresh (optional)

You can also generate the snapshot from a local `.xlsx` file — the `--gsheet`
flag is only needed for the cloud path:

```bash
python dse_live_dashboard.py \
    --workbook "PATH/TO/DSE MARKET UPDATE.xlsx" \
    --out dashboard_snapshot.html
git commit -am "Refresh snapshot" && git push
```

## Deploy to Streamlit Community Cloud

1. Push this repo to GitHub (public — the free tier requires it).
2. Go to <https://share.streamlit.io> → **Create app** → pick this repo.
3. Main file path: **`streamlit_app.py`**. Deploy.

## Cloud automation setup

See **[SETUP_CLOUD.md](SETUP_CLOUD.md)** for the step-by-step guide to:

1. Upload and convert the workbook to a Google Sheet.
2. Create a Google Cloud service account.
3. Store secrets in GitHub and (optionally) Streamlit Cloud.
4. Test the workflow with a manual dispatch.

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
| `dse_live_dashboard.py` | Snapshot generator — reads local `.xlsx` or Google Sheets |
| `dse_dashboard_template.html` | HTML/CSS/JS shell (tabs, tables, charts, heatmap) |
| `dse_data.py` | Reads the workbook (local or Google Sheets); finds every table at runtime |
| `dse_analytics.py` | All derived analytics (MAs, MACD, RSI, S/R, breadth, sectors…) |
| `dse_context.py` | Assembles workbook + analytics into one context dict |
| `macro_data.json` | External macro inputs (govt yield curve, inflation) with sources |
| `.github/workflows/refresh.yml` | GitHub Actions cron job — daily cloud refresh |
| `SETUP_CLOUD.md` | Step-by-step cloud setup guide |

## Data provenance

Everything except the two macro panels comes from the workbook / Google Sheet.
The government yield curve and inflation series are external (from
`macro_data.json`, with source attribution shown in-app). Missing figures
render as "Not Available" — never estimated.
