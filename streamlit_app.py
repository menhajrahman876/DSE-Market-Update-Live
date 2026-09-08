r"""
DSE Market Update — Live | Streamlit Community Cloud entry point (static viewer).

Streamlit Community Cloud runs Linux and has neither Excel/pywin32 nor access
to the local Google Drive workbook, so it CANNOT scrape live data. Instead
this app displays a pre-generated, self-contained snapshot committed to the
repo:

    dashboard_snapshot.html   <- built locally by dse_live_dashboard.py

To refresh what Cloud shows, regenerate the snapshot on a machine that has the
workbook and push it:

    python dse_live_dashboard.py \
        --workbook "PATH/TO/DSE MARKET UPDATE.xlsb" \
        --out dashboard_snapshot.html
    git commit -am "Refresh snapshot" && git push

Cloud redeploys automatically on push. The snapshot's own header shows the
exact "as of" / "workbook refreshed" / "generated" timestamps, so viewers
always know how fresh it is.

The page also has a "Refresh" button. It ONLY re-reads dashboard_snapshot.html
from disk (via st.rerun()) -- useful in the minute or two right after a push,
while Cloud is still swapping to the new container. It never talks to dsebd.org
or the workbook; there is no button anywhere that can, because this process
has no path to either.
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
    st.caption("Periodic snapshot pushed from the maintainer's PC — not a live market feed.")
with top_r:
    if st.button("🔄 Refresh", use_container_width=True,
                 help="Re-reads dashboard_snapshot.html from disk. Shows new data only "
                      "after the maintainer has pushed an update — it does not re-scrape "
                      "the market itself."):
        st.rerun()

if not SNAPSHOT.exists():
    st.error(
        "No dashboard_snapshot.html found in the repository. Generate it locally "
        "with `python dse_live_dashboard.py --workbook \"<path to .xlsb>\" "
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
