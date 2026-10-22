"""Clean-source startup, deliberately excluding setup/login/live providers."""

import json
import os
from pathlib import Path
import subprocess
import sys


# Run before any Hub import. -I excludes user site / inherited PYTHONPATH;
# explicit source insertion ensures this clone, not a stale editable install.
_CHILD = r'''
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from contextlib import redirect_stdout

source, original_home, mode = sys.argv[1:]
original_home = Path(original_home).resolve()
home = Path.home().resolve()
assert home != original_home
# Permit only the explicitly selected code, interpreter, and temporary data
# roots when a developer keeps their checkout/venv under HOME.
allowed = tuple(Path(p).resolve() for p in (source, sys.prefix, sys.base_prefix, Path.cwd()))

def guard(event, args):
    if event.startswith("socket.") or event in {"subprocess.Popen", "os.system", "os.posix_spawn", "os.fork"}:
        raise PermissionError("offline guard: " + event)
    if event in {"open", "os.listdir", "os.scandir"} and args and isinstance(args[0], (str, bytes, os.PathLike)):
        path = Path(os.fsdecode(args[0])).resolve()
        if (path == original_home or original_home in path.parents) and not any(
            path == root or root in path.parents for root in allowed
        ):
            raise RuntimeError("private HOME guard")
sys.addaudithook(guard)

if mode == "network":
    socket.getaddrinfo("example.invalid", 443)
elif mode == "process":
    subprocess.run([sys.executable, "-c", "pass"], check=True)
elif mode == "home":
    (original_home / "baseline-must-not-read").read_text()
else:
    sys.path.insert(0, source)
    import research_hub
    assert Path(research_hub.__file__).resolve().is_relative_to(Path(source).resolve())
    from research_hub.cli import main
    root = Path.cwd() / "demo"
    sys.argv = ["research-hub", "project", "demo", "--root", str(root), "--json"]
    with redirect_stdout(io.StringIO()) as output:
        code = main()
    assert code in (None, 0), code
    result = json.loads(output.getvalue())
    assert result["warnings"]
    from research_hub.workspace.core import Workspace
    workspace = Workspace(root)
    assert {p["id"] for p in workspace.list_projects()} == {"summation-demo", "review-demo"}
    for project in result["projects"]:
        snapshot = workspace.snapshot(project["id"])
        assert snapshot["tasks"] == snapshot["actions"] == []
        assert snapshot["manuscript"] is None
    claims = [r for r in workspace.records("review-demo") if r["kind"] == "claim"]
    assert claims and all(r["data"]["verification_status"] == "unverified" and
                          r["data"]["human_acceptance"] == "pending" for r in claims)
    assert not list(home.iterdir()), "Demo unexpectedly populated isolated HOME"
    print(json.dumps({"status": "PASS", "projects": len(result["projects"]),
                      "connectors": "not_exercised", "native_host": "not_verified",
                      "scientific_quality": "not_assessed"}))
'''


def _run(tmp_path, mode, original_home=None):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    # Do not inherit credentials, provider URLs, adapter paths, HOME config or
    # PYTHONPATH. SystemRoot is required by the Python runtime on Windows.
    env = {key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR") if key in os.environ}
    env.update({"HOME": str(home), "USERPROFILE": str(home),
                "APPDATA": str(home), "LOCALAPPDATA": str(home),
                "XDG_CONFIG_HOME": str(home), "XDG_CACHE_HOME": str(home),
                "XDG_DATA_HOME": str(home), "TMPDIR": str(tmp_path),
                "TMP": str(tmp_path), "TEMP": str(tmp_path), "PATH": ""})
    source = Path(__file__).resolve().parents[1] / "src"
    return subprocess.run(
        [sys.executable, "-I", "-B", "-c", _CHILD, str(source), str(original_home or Path.home()), mode],
        env=env, cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", timeout=20,
    )


def test_clean_source_demo_is_local_unaccepted_and_home_isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("RESEARCH_HUB_CONFIG", str(tmp_path / "must-not-use-config.json"))
    monkeypatch.setenv("RESEARCH_HUB_WRITING_ADAPTER", str(tmp_path / "must-not-use-adapter"))
    result = _run(tmp_path, "demo")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "PASS"
    assert report["projects"] == 2
    assert report["native_host"] == "not_verified"


def test_clean_baseline_guards_reject_network_process_and_original_home(tmp_path):
    for mode, message in (("network", "offline guard"), ("process", "offline guard"),
                          ("home", "private HOME guard")):
        result = _run(tmp_path, mode)
        assert result.returncode != 0
        assert message in result.stderr, result.stderr


def test_clean_baseline_allows_selected_source_inside_protected_home(tmp_path):
    # Simulate a checkout nested under HOME without reading any real home data.
    protected = Path(__file__).resolve().parents[1]
    result = _run(tmp_path, "demo", original_home=protected)
    assert result.returncode == 0, result.stderr
    denied = _run(tmp_path, "home", original_home=protected)
    assert denied.returncode != 0 and "private HOME guard" in denied.stderr
