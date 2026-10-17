"""Checks on the deployable app folder (CONTRACT tasks H-04, H-06)."""

from __future__ import annotations

import filecmp
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_app_data_copy_matches_data_folder():
    # Posit Connect only gets app/, so app/data/ is a copy. It must never drift.
    for src in sorted((ROOT / "data").glob("*/*.csv")):
        dst = ROOT / "app" / "data" / src.parent.name / src.name
        assert dst.exists(), f"{dst} missing: run app/sync_data.sh"
        assert filecmp.cmp(src, dst, shallow=False), f"{dst} differs: run app/sync_data.sh"


def test_app_module_builds():
    # Load app/app.py by path (the name "app" is taken by the app/ folder here),
    # with app/ on sys.path so its "import qc" works exactly as on Connect.
    sys.path.insert(0, str(ROOT / "app"))
    try:
        spec = importlib.util.spec_from_file_location("fleet_app", ROOT / "app" / "app.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert type(mod.app).__name__ == "App"
        html = str(mod.app.ui)
        # Dashboard is the active landing tab, not the intro essay
        assert "Drone Fleet Health &amp; Part Wear Monitor" in html
        assert "Weibull reliability &amp; replace-at ages" in html
        assert "due_soon" in html and "fleet_timeline" in html          # the replacement views
        assert 'id="dataset"' not in html                              # one fleet, no switch
        assert "healthy fleet" not in html.lower() and "crash" not in html.lower()
        detail_html = str(mod.drone_detail_body())
        for output in ("drone_timeline", "drone_parts", "drone_charts"):
            assert output in detail_html
    finally:
        sys.path.remove(str(ROOT / "app"))

