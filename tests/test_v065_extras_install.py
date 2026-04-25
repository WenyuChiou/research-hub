from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.slow
@pytest.mark.parametrize(
    ("extra", "probe_module"),
    [
        ("secrets", "cryptography"),
        ("import", "pdfplumber"),
        ("playwright", "patchright.sync_api"),
        ("mcp", "fastmcp"),
        ("dev", "pytest_cov"),
    ],
)
def test_extra_installs_cleanly(tmp_path: Path, extra: str, probe_module: str):
    venv_dir = tmp_path / f"venv_{extra}"
    subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True, timeout=120)
    scripts_dir = "Scripts" if sys.platform == "win32" else "bin"
    pip = str(venv_dir / scripts_dir / ("pip.exe" if sys.platform == "win32" else "pip"))
    py = str(venv_dir / scripts_dir / ("python.exe" if sys.platform == "win32" else "python"))
    repo_root = Path(__file__).resolve().parent.parent

    subprocess.run([pip, "install", "-q", f"{repo_root}[{extra}]"], check=True, timeout=300)
    result = subprocess.run(
        [py, "-c", f"import {probe_module}; print('ok')"],
        capture_output=True,
        check=False,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout
