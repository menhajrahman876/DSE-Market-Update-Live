r"""
DSE Market Update — Live | Streamlit Community Cloud entry point (static viewer).

Displays a pre-generated, self-contained snapshot committed to the repo:

    dashboard_snapshot.html

The snapshot is refreshed automatically every trading day by a GitHub Actions
cron job that reads a private Google Sheet, runs the analytics pipeline, and
commits the updated HTML.  Cloud redeploys automatically on push.
"""

from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

SNAPSHOT = Path(__file__).parent / "dashboard_snapshot.html"

st.set_page_config(
    page_title="DSE Market Update — Live",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
  header[data-testid="stHeader"]{display:none;}
  .block-container{padding:0 0 0 0 !important;max-width:100% !important;}
  [data-testid="stAppViewContainer"]>.main{padding:0 !important;}
  footer{visibility:hidden;}
  iframe{border:none !important;}
</style>
""", unsafe_allow_html=True)

if not SNAPSHOT.exists():
    st.error(
        "No dashboard_snapshot.html found in the repository. Generate it locally "
        "with `python dse_live_dashboard.py --workbook \"<path to .xlsx>\" "
        "--out dashboard_snapshot.html` and commit it."
    )
    st.stop()

html = SNAPSHOT.read_text(encoding="utf-8")

# Inject auto-height script: the iframe tells Streamlit its real content
# height so there's no fixed guess and no blank tail.
_AUTO_HEIGHT = """\
<script>
(function(){
  function rh(){
    var h=document.documentElement.scrollHeight;
    window.parent.postMessage({type:'streamlit:setFrameHeight',height:h},'*');
  }
  window.addEventListener('load',rh);
  window.addEventListener('resize',rh);
  new MutationObserver(rh).observe(document.body,{childList:true,subtree:true});
  setTimeout(rh,500);
  setTimeout(rh,2000);
})();
</script>
"""
html = html.replace("</body>", _AUTO_HEIGHT + "</body>")

components.html(html, height=0, scrolling=False)
