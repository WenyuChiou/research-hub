from __future__ import annotations

import json
import zipfile
from pathlib import Path


def test_build_dxt_writes_valid_zip(tmp_path: Path):
    from research_hub.dxt import build_dxt

    out_path = build_dxt(tmp_path / "research-hub.dxt", "0.37.3")

    assert out_path.exists()
    assert zipfile.is_zipfile(out_path)


def test_dxt_manifest_has_required_fields(tmp_path: Path):
    from research_hub.dxt import build_dxt

    out_path = build_dxt(tmp_path / "research-hub.dxt", "0.37.3")
    with zipfile.ZipFile(out_path) as zf:
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))

    assert manifest["dxt_version"] == "0.1"
    assert manifest["name"] == "research-hub"
    assert manifest["display_name"] == "Research Hub"
    assert manifest["server"]["type"] == "python"
    assert manifest["server"]["mcp_config"]["args"] == ["-m", "research_hub.mcp_server"]


def test_cli_package_dxt_writes_output(tmp_path: Path, capsys):
    from research_hub.cli import main

    out_path = tmp_path / "cli-package.dxt"
    rc = main(["package-dxt", "--out", str(out_path)])

    assert rc == 0
    assert out_path.exists()
    assert "Wrote" in capsys.readouterr().out
