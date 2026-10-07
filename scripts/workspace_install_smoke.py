"""Validate the installed wheel from an isolated environment, with no Node PATH."""
import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import threading
import time
from urllib.request import urlopen


def run():
    import research_hub
    from research_hub.doctor import check_installation_version
    from research_hub.workspace.server import WorkspaceServer
    from research_hub.workspace.service import call_workspace
    from research_hub.mcp_server import workspace_project
    installed = Path(research_hub.__file__).resolve()
    assert installed.is_relative_to(Path(sys.prefix).resolve()), "Must test a clean installed wheel, not an editable checkout"
    started = time.monotonic()
    checks = []
    # Exact sys.executable remains callable; Node and external providers do not.
    os.environ["PATH"] = ""
    for key in ("RESEARCH_HUB_WRITING_ADAPTER", "RESEARCH_HUB_AGENT_POLICY", "RESEARCH_HUB_AGENT_CHECKPOINT"):
        os.environ.pop(key, None)
    with tempfile.TemporaryDirectory(prefix="workspace-wheel-") as temporary:
        root = Path(temporary) / "demo"
        command = [sys.executable, "-m", "research_hub", "project", "demo", "--root", str(root), "--json"]
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=45, cwd=temporary)
        assert result.returncode == 0, result.stderr
        assert len(json.loads(result.stdout)["projects"]) == 2
        checks.append("CLI demo from installed wheel without Node")
        direct = call_workspace(root, "project", "show", {"project_id": "summation-demo"})
        func = getattr(workspace_project, "fn", workspace_project)
        assert func(str(root), "show", {"project_id": "summation-demo"}) == direct
        checks.append("MCP/domain project parity")
        assert check_installation_version().status == "OK"
        checks.append("Source/installed metadata parity")
        server = WorkspaceServer(root, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            html = urlopen(base + "/app/", timeout=10).read().decode()
            import re
            assets = re.findall(r'(?:src|href)="(/app/assets/[^\"]+)"', html)
            assert len(assets) >= 2, html
            for asset in assets:
                assert len(urlopen(base + asset, timeout=5).read()) > 100
            checks.append("Bundled React JS/CSS served from wheel")
            actual = json.load(urlopen(base + "/api/v1/projects/summation-demo", timeout=10))
            assert actual == direct
            checks.append("REST/domain project parity")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
    return {"status": "PASS", "checks": checks, "passed": len(checks), "failed": 0,
            "duration_seconds": round(time.monotonic() - started, 3),
            "python": platform.python_version(), "platform": platform.platform(),
            "installed_module": str(installed), "node_path": "absent", "human_acceptance": "not_performed"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
