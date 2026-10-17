"""Checks on the deployable app folder (CONTRACT tasks H-04, H-06)."""

from __future__ import annotations

import filecmp
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_app_data_copy_matches_data_folder():
    # Posit Connect only gets app/, so app/data/ is a copy. It must never drift.
    for src in sorted((ROOT / "data").glob("*/*.csv")):
        dst = ROOT / "app" / "data" / src.parent.name / src.name
        assert dst.exists(), f"{dst} missing: run app/sync_data.sh"
        assert filecmp.cmp(src, dst, shallow=False), f"{dst} differs: run app/sync_data.sh"


def test_app_serves_the_react_build():
    # Connect runs app/api.py; it serves the React dashboard built from web/ into app/static/.
    # A missing build means the deploy would show JSON instead of the dashboard.
    index = ROOT / "app" / "static" / "index.html"
    assert index.exists(), "no React build: run  cd web && npm run build"
    html = index.read_text(encoding="utf-8")
    assert '<div id="root"></div>' in html
    for asset in re.findall(r'(?:src|href)="\./(assets/[^"]+)"', html):
        assert (ROOT / "app" / "static" / asset).exists(), f"{asset} missing: rebuild web/"


def test_shiny_app_is_gone():
    # H-14: React replaced the Shiny dashboard; one front end only.
    for name in ("app.py", "intro.py", "charts.py"):
        assert not (ROOT / "app" / name).exists(), f"app/{name} is the old Shiny app"
