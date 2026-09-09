r"""
DSE Market Update — Live | Streamlit Community Cloud entry point (static viewer).

Displays a pre-generated, self-contained snapshot committed to the repo:

    dashboard_snapshot.html

The snapshot is refreshed automatically every trading day by a GitHub Actions
cron job that reads a private Google Sheet, runs the analytics pipeline, and
commits the updated HTML.  Cloud redeploys automatically on push.

The snapshot's own header shows the exact "as of" / "workbook refreshed" /
"generated" timestamps so viewers always know how fresh it is.
"""

from pathlib import Path

import streamlit as st

SNAPSHOT = Path(__file__).parent / "dashboard_snapshot.html"

st.set_page_config(page_title="DSE Market Update — Live", layout="wide",
                   initial_sidebar_state="collapsed")

# strip Streamlit's default chrome so the embedded dashboard fills the page
# (a little top padding is kept for the refresh row below)
st.markdown("""
<style>
  header[data-testid="stHeader"]{display:none;}
  .block-container{padding:6px 16px 0 16px !important;max-width:100% !important;}
  [data-testid="stAppViewContainer"]>.main{padding:0 !important;}
</style>
""", unsafe_allow_html=True)

top_l, top_r = st.columns([6, 1])
with top_l:
    st.caption("Auto-refreshed daily after market close via GitHub Actions — not a live market feed.")
with top_r:
    if st.button("🔄 Refresh", use_container_width=True,
                 help="Re-reads dashboard_snapshot.html from disk. Shows new data only "
                      "after the GitHub Actions job has pushed an update — it does not "
                      "re-scrape the market itself."):
        st.rerun()

if not SNAPSHOT.exists():
    st.error(
        "No dashboard_snapshot.html found in the repository. Generate it locally "
        "with `python dse_live_dashboard.py --workbook \"<path to .xlsx>\" "
        "--out dashboard_snapshot.html` and commit it."
    )
    st.stop()

html = SNAPSHOT.read_text(encoding="utf-8")

# Full-height embed. The snapshot is a complete self-contained document
# (Chart.js via CDN, data inlined), so it just needs a frame to live in.
try:
    st.iframe(html, height=2600)              # Streamlit >= 1.49
except AttributeError:
    import streamlit.components.v1 as components
    components.html(html, height=2600, scrolling=True)
