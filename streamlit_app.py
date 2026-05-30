"""
Streamlit Community Cloud entry point.

Streamlit Cloud looks for `streamlit_app.py` at the repo root by convention.
The real dashboard lives in `src/app.py`; this shim just executes it so the
default "Main file path" works out of the box.
"""
from pathlib import Path
import runpy

app_path = Path(__file__).resolve().parent / "src" / "app.py"
runpy.run_path(str(app_path), run_name="__main__")
