"""Launch with python -m streamlit run streamlit_app.py from this project root."""

import sys
from pathlib import Path

# Also works from a checkout before editable installation.
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from geo_research.dashboard.app import main  # noqa: E402

main()