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
"""

from pathlib import Path

import streamlit as st

SNAPSHOT = Path(__file__).parent / "dashboard_snapshot.html"

st.set_page_config(page_title="DSE Market Update — Live", layout="wide",
                   initial_sidebar_state="collapsed")

# strip Streamlit's default chrome so the embedded dashboard fills the page
st.markdown("""
<style>
  header[data-testid="stHeader"]{display:none;}
  .block-container{padding:0 !important;max-width:100% !important;}
  [data-testid="stAppViewContainer"]>.main{padding:0 !important;}
</style>
""", unsafe_allow_html=True)

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
