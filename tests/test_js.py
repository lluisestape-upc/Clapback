"""Runs the JavaScript tests (the 3D acoustics in web/acoustics3d.js) with Node."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not installed")
def test_js():
    tests = sorted(str(p) for p in (ROOT / "tests" / "js").glob("*.test.mjs"))
    r = subprocess.run(["node", "--test", *tests], cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]
