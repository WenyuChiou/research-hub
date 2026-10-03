"""Real parser -> handler -> checker acceptance; no live accounts or models."""

import builtins
import contextlib
from decimal import Decimal
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
from textwrap import dedent
import urllib.request

import httpx
import pytest
import requests
import yaml

import research_hub
from research_hub import cli


FIXTURES = Path(__file__).parent / "fixtures" / "direction_review"
DOSSIER_NAME = "topic_dossier.v1.gaps.yml"
REVIEW_NAME = "topic_dossier.v1.direction-review.json"


@pytest.fixture
def inputs(tmp_path):
    root = tmp_path / "direction-inputs"
    shutil.copytree(FIXTURES, root)
    return root


def argv(root):
    return ["paper", "direction-check", "--dossier", str(root / DOSSIER_NAME),
            "--review", str(root / REVIEW_NAME), "--source-root", str(root), "--json"]


def snapshot(root):
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*") if path.is_file()}


def rewrite_json(root, mutate):
    path = root / REVIEW_NAME
    value = json.loads(path.read_text(encoding="utf-8"))
    mutate(value)
    path.write_text(json.dumps(value), encoding="utf-8")


def assert_limits(result):
    assert result["format"] == "research-direction-check/1.0"
    assert result["semantic_assessment"] == "not-performed"
    assert result["human_selection"] == "outside-checker"
    assert result["execution_authorized"] is False
    assert "selected_id" not in result
    assert "feasible" not in result


@pytest.fixture
def forbid_external_effects(monkeypatch):
    """Tripwires supplement (not substitute for) the real handler integration."""
    import research_hub.audit
    import research_hub.cli_paper
    import research_hub.config
    import research_hub.gap_analysis
    import research_hub.llm_cli

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Offline direction-check attempted a prohibited side effect")

    with monkeypatch.context() as patch:
        for module in (cli, research_hub.cli_paper, research_hub.config):
            for name in ("get_config", "require_config", "load_config"):
                if hasattr(module, name):
                    patch.setattr(module, name, forbidden)
        patch.setattr(research_hub.llm_cli, "detect_llm_cli", forbidden)
        patch.setattr(research_hub.llm_cli, "invoke_llm_cli", forbidden)
        patch.setattr(research_hub.cli_paper, "_cmd_paper_gaps", forbidden)
        patch.setattr(requests.sessions.Session, "request", forbidden)
        patch.setattr(httpx.Client, "request", forbidden)
        patch.setattr(httpx.AsyncClient, "request", forbidden)
        patch.setattr(urllib.request, "urlopen", forbidden)
        patch.setattr(socket, "getaddrinfo", forbidden)
        patch.setattr(socket.socket, "connect", forbidden)
        patch.setattr(socket.socket, "connect_ex", forbidden)
        patch.setattr(subprocess, "Popen", forbidden)
        patch.setattr(os, "system", forbidden)
        original_open, original_io_open = builtins.open, io.open
        def read_only(original):
            def guarded(file, mode="r", *args, **kwargs):
                if any(flag in mode for flag in "wax+"):
                    forbidden()
                return original(file, mode, *args, **kwargs)
            return guarded
        patch.setattr(builtins, "open", read_only(original_open))
        patch.setattr(io, "open", read_only(original_io_open))
        for name in ("mkdir", "remove", "unlink", "rename", "replace"):
            patch.setattr(os, name, forbidden)
        # Do not patch the checker, parser, paper dispatcher, or handler.
        yield


def test_real_cli_complete_record_unknowns_and_over_budget_exit_zero_without_effects(inputs, capsys, forbid_external_effects):
    before = snapshot(inputs)
    code = cli.main(argv(inputs))
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert code == 0
    assert captured.err == ""
    assert result["record_status"] == "valid"
    assert result["binding_status"] == "current"
    assert result["resource_estimates"]["totals"][0]["demand"] == 15
    assert result["resource_estimates"]["status"] == "exceeds-estimate"
    assert any(check["status"] == "unknown" for check in result["prerequisites"])
    assert any(check["status"] == "contradicted" for check in result["prerequisites"])
    assert result["resource_estimates"]["runtime_budget_verification"] == "not-performed"
    assert snapshot(inputs) == before
    assert_limits(result)


def test_real_parser_registers_three_explicit_required_local_inputs(inputs):
    parsed = cli.build_parser().parse_args(argv(inputs))
    assert parsed.command == "paper"
    assert parsed.paper_command == "direction-check"
    assert parsed.dossier == str(inputs / DOSSIER_NAME)
    assert parsed.review == str(inputs / REVIEW_NAME)
    assert parsed.source_root == str(inputs)
    assert parsed.json is True


@pytest.mark.parametrize("flag", ["--dossier", "--review", "--source-root"])
def test_parser_does_not_infer_missing_input_paths(inputs, capsys, flag):
    args = argv(inputs)
    index = args.index(flag)
    del args[index:index + 2]
    with pytest.raises(SystemExit) as error:
        cli.main(args)
    assert error.value.code == 2
    assert flag in capsys.readouterr().err


def test_valid_unknown_estimate_has_exit_zero_not_a_pass(inputs, capsys):
    rewrite_json(inputs, lambda review: review["resources"]["components"][1].update(amount=None))
    assert cli.main(argv(inputs)) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["record_status"] == "valid"
    assert result["resource_estimates"]["status"] == "unknown"
    assert result["resource_estimates"]["totals"][0]["demand"] is None
    assert_limits(result)


@pytest.mark.parametrize("change,expected", [("version", "stale-candidate"), ("content", "stale-candidate"),
                                               ("legacy", "missing-candidate-version")])
def test_noncurrent_candidate_has_nonzero_code_and_preserves_diagnostics(inputs, capsys, change, expected):
    path = inputs / DOSSIER_NAME
    dossier = yaml.safe_load(path.read_text(encoding="utf-8"))
    if change == "version":
        dossier["gaps"][0]["candidate_version"] = 2
    elif change == "content":
        dossier["gaps"][0]["statement"] = "A revised question."
    else:
        del dossier["gaps"][0]["candidate_version"]
    path.write_text(yaml.safe_dump(dossier), encoding="utf-8")
    assert cli.main(argv(inputs)) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["record_status"] == "valid"
    assert result["binding_status"] == "not-current"
    assert result["candidate_bindings"][0]["status"] == expected
    assert result["candidate_bindings"][1]["status"] == "current"
    assert result["resource_estimates"]["status"] == "unknown"
    assert_limits(result)


def test_changed_source_has_nonzero_code_without_repairing_file_or_hash(inputs, capsys):
    path = inputs / "sources/data-dictionary.txt"
    path.write_bytes(path.read_bytes() + b"\nChanged evidence.\n")
    before = snapshot(inputs)
    assert cli.main(argv(inputs)) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["binding_status"] == "not-current"
    assert result["evidence_bindings"][0]["status"] == "changed"
    assert snapshot(inputs) == before
    assert_limits(result)


@pytest.mark.parametrize("filename,content,code", [
    (DOSSIER_NAME, "gaps: [SECRET_DO_NOT_LEAK", "input-malformed"),
    (REVIEW_NAME, '{"format": "SECRET_DO_NOT_LEAK",', "input-malformed"),
    (DOSSIER_NAME, "gaps: []\ngaps: [SECRET_DO_NOT_LEAK]\n", "duplicate-object-key"),
    (REVIEW_NAME, '{"format":"SECRET_DO_NOT_LEAK","format":"again"}', "duplicate-object-key"),
])
def test_malformed_input_returns_exact_bounded_json_without_traceback_or_source_text(inputs, capsys, filename, content, code):
    (inputs / filename).write_text(content, encoding="utf-8")
    assert cli.main(argv(inputs)) == 2
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {
        "format": "research-direction-check/1.0", "record_status": "invalid", "error": code,
        "semantic_assessment": "not-performed", "human_selection": "outside-checker",
        "execution_authorized": False,
    }
    assert captured.err == ""
    assert "SECRET_DO_NOT_LEAK" not in captured.out
    assert "Traceback" not in captured.out


def test_missing_input_has_machine_readable_error(inputs, capsys):
    (inputs / REVIEW_NAME).unlink()
    assert cli.main(argv(inputs)) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["record_status"] == "invalid"
    assert result["error"] == "input-unreadable"
    assert_limits(result)


def test_text_output_discloses_estimate_and_selection_boundaries(inputs, capsys):
    assert cli.main(argv(inputs)[:-1]) == 0
    output = capsys.readouterr().out
    assert "exceeds-estimate" in output
    assert "unknown" in output
    assert "contradicted" in output
    assert "not verified" in output
    assert "human selection" in output
    assert "does not authorize execution" in output


def test_global_audit_option_is_rejected_before_creating_any_output(inputs, tmp_path, capsys):
    destination = tmp_path / "must-not-create-audit"
    before = snapshot(tmp_path)
    with pytest.raises(SystemExit) as error:
        cli.main(argv(inputs) + ["--audit-output", str(destination)])
    assert error.value.code == 2
    assert not destination.exists()
    assert snapshot(tmp_path) == before
    assert "--audit-output" in capsys.readouterr().err


@pytest.mark.parametrize("field", ["reason", "metadata", "key"])
@pytest.mark.parametrize("json_output", [True, False])
def test_lone_surrogate_has_bounded_cli_output_on_strict_utf8(inputs, field, json_output):
    value = json.loads((inputs / REVIEW_NAME).read_text(encoding="utf-8"))
    if field == "reason":
        value["checks"][0]["reason"] = chr(0xD800)
    elif field == "metadata":
        value["evidence"][0]["publication_version"] = chr(0xDFFF)
    else:
        value[chr(0xD800)] = "invalid key"
    (inputs / REVIEW_NAME).write_text(json.dumps(value), encoding="utf-8")
    sink = io.BytesIO()
    stream = io.TextIOWrapper(sink, encoding="utf-8", errors="strict")
    with contextlib.redirect_stdout(stream):
        code = cli.main(argv(inputs) if json_output else argv(inputs)[:-1])
    stream.flush()
    output = sink.getvalue().decode("utf-8")
    assert code == 2
    assert "non-scalar-unicode" in output
    assert "Traceback" not in output
    if json_output:
        assert json.loads(output)["record_status"] == "invalid"


def test_cli_serializes_full_precision_decimal_totals_as_json_numbers(inputs, capsys):
    from research_hub.direction_review import dumps_direction_json
    value = json.loads((inputs / REVIEW_NAME).read_text(encoding="utf-8"))
    value["resources"]["components"][0]["amount"] = Decimal("0.10000000000000000001")
    value["resources"]["components"][1]["amount"] = Decimal("0.2")
    value["resources"]["capacities"][0]["amount"] = Decimal("0.3")
    (inputs / REVIEW_NAME).write_text(dumps_direction_json(value), encoding="utf-8")
    assert cli.main(argv(inputs)) == 0
    result = json.loads(capsys.readouterr().out, parse_float=Decimal)
    row = result["resource_estimates"]["totals"][0]
    assert row["demand"] == Decimal("0.30000000000000000001")
    assert row["capacity"] == Decimal("0.3")
    assert row["status"] == "exceeds-estimate"


def test_output_serialization_limit_stays_inside_bounded_cli_error_path(inputs, capsys, monkeypatch):
    import research_hub.direction_review as module
    def nodes(value):
        if isinstance(value, dict):
            return 1 + sum(nodes(item) for item in value.values())
        if isinstance(value, list):
            return 1 + sum(nodes(item) for item in value)
        return 1
    review = json.loads((inputs / REVIEW_NAME).read_text(encoding="utf-8"))
    result = module.check_direction_review(inputs / DOSSIER_NAME, inputs / REVIEW_NAME, inputs)
    assert nodes(result) > nodes(review)
    monkeypatch.setattr(module, "MAX_JSON_NODES", nodes(review))
    assert cli.main(argv(inputs)) == 2
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["record_status"] == "invalid"
    assert parsed["error"] == "input-node-limit"


@pytest.mark.parametrize("token", ["1e999999999999999999999999", "1e-999999999999999999999999"])
@pytest.mark.parametrize("json_output", [True, False])
def test_short_out_of_range_decimal_token_has_bounded_cli_error(inputs, capsys, token, json_output):
    value = json.loads((inputs / REVIEW_NAME).read_text(encoding="utf-8"))
    value["resources"]["components"][0]["amount"] = "NUMBER_TOKEN"
    text = json.dumps(value).replace('"NUMBER_TOKEN"', token, 1)
    (inputs / REVIEW_NAME).write_text(text, encoding="utf-8")
    assert cli.main(argv(inputs) if json_output else argv(inputs)[:-1]) == 2
    captured = capsys.readouterr()
    assert captured.err == ""
    assert "numeric-precision-limit" in captured.out
    assert "InvalidOperation" not in captured.out
    assert "Traceback" not in captured.out
    if json_output:
        assert json.loads(captured.out)["record_status"] == "invalid"


def _direction_child_environment(tmp_path):
    """Tripwire for accidental I/O by trusted Python code, not an OS sandbox."""
    fence = tmp_path / "child-offline-fence"
    fence.mkdir()
    attempts = fence / "attempts.log"
    attempts.write_text("", encoding="utf-8")
    source = dedent(f"""\
        import os
        import sys
        def offline(event, args):
            socket_io = event.startswith("socket.") and event not in {{
                "socket.__new__", "socket.bind", "socket.gethostname",
                "socket.getservbyname", "socket.getservbyport",
            }}
            process_io = event in {{
                "subprocess.Popen", "os.system", "os.exec", "os.posix_spawn",
            }}
            if socket_io or process_io:
                try:
                    with open({str(attempts)!r}, "a", encoding="utf-8") as stream:
                        stream.write(event + "\\n")
                except BaseException:
                    os._exit(98)
                raise RuntimeError("offline direction-check child blocked " + event)
        try:
            sys.addaudithook(offline)
            sys._direction_offline_guard = True
        except BaseException:
            os._exit(98)
        """)
    compile(source, "sitecustomize.py", "exec")
    (fence / "sitecustomize.py").write_text(source, encoding="utf-8")
    home = tmp_path / "child-home"
    home.mkdir()
    # Bind the package to the actual source/wheel under test. The explicit
    # pytest dependency location supports the separately installed wheel venv.
    # A surrounding aggregate launcher may prepend its own reviewed guard.
    env = {key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR") if key in os.environ}
    env.update({
        "PATH": str(Path(sys.executable).parent), "HOME": str(home),
        "USERPROFILE": str(home), "APPDATA": str(home), "LOCALAPPDATA": str(home),
        "XDG_CONFIG_HOME": str(home), "XDG_CACHE_HOME": str(home),
        "RESEARCH_HUB_CONFIG": str(home / "no-config.json"),
        "PYTHONPATH": os.pathsep.join((str(fence),
            str(Path(research_hub.__file__).resolve().parent.parent),
            str(Path(pytest.__file__).resolve().parent.parent))),
        "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8:strict", "RESEARCH_HUB_NO_ZOTERO": "1",
    })
    return env, attempts


def test_child_guard_records_caught_synthetic_events_and_excludes_ambient_config(tmp_path, monkeypatch):
    monkeypatch.setenv("DIRECTION_TEST_AMBIENT_SECRET", "synthetic-do-not-inherit")
    env, attempts = _direction_child_environment(tmp_path)
    assert "DIRECTION_TEST_AMBIENT_SECRET" not in env
    events = ["socket.getaddrinfo", "socket.connect", "socket.sendto",
              "subprocess.Popen", "os.system", "os.exec", "os.posix_spawn"]
    # These zero-argument audit notifications perform no underlying operation.
    # Real CPython operations for every event here require audit arguments.
    probe = ("import sys; assert sys._direction_offline_guard\n"
             + f"for event in {events!r}:\n"
             + " try: sys.audit(event)\n"
             + " except RuntimeError: pass\n"
             + " else: raise AssertionError(event)\n")
    completed = subprocess.run([sys.executable, "-c", probe], cwd=tmp_path,
                               env=env, capture_output=True, text=True, timeout=15)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == completed.stderr == ""
    assert attempts.read_text(encoding="utf-8").splitlines() == events


@pytest.mark.parametrize("entrypoint", ["module", "console"])
def test_subprocess_entrypoints_emit_json_without_configuration(inputs, tmp_path, entrypoint):
    """The actual console script is checked when installed; module is universal."""
    if entrypoint == "console":
        executable = Path(sys.executable).parent / ("research-hub.exe" if os.name == "nt" else "research-hub")
        if not executable.is_file():
            pytest.skip("Console script not installed; module entrypoint is separately exercised")
        command = [str(executable)]
    else:
        command = [sys.executable, "-m", "research_hub"]
    # pytest-socket does not propagate to children. This trusted-Python
    # tripwire records accidental audited I/O even if production catches it.
    env, attempts = _direction_child_environment(tmp_path)
    before = snapshot(tmp_path)
    completed = subprocess.run(command + argv(inputs), cwd=tmp_path, env=env,
                               capture_output=True, text=True, timeout=15)
    assert attempts.read_text(encoding="utf-8") == "", "Child attempted audited external I/O"
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert completed.stderr == ""
    assert result["record_status"] == "valid"
    assert result["resource_estimates"]["status"] == "exceeds-estimate"
    assert result["input_receipts"]["dossier_sha256"] == hashlib.sha256((inputs / DOSSIER_NAME).read_bytes()).hexdigest()
    assert snapshot(tmp_path) == before
    assert_limits(result)
