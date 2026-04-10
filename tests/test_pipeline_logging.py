"""Tests for per-paper error logging in pipeline runs."""

import json
import time
from pathlib import Path


def write_error_log(logs_dir: Path, errors: list) -> Path:
    """Write per-paper errors to JSONL file. Returns log path."""
    logs_dir.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    log_path = logs_dir / f"pipeline_errors_{ts}.jsonl"
    with open(log_path, "w", encoding="utf-8") as file_obj:
        for error in errors:
            file_obj.write(json.dumps(error, ensure_ascii=False) + "\n")
    return log_path


def test_error_log_written(tmp_path):
    logs_dir = tmp_path / "logs"
    errors = [
        {"paper": "Test Paper 1", "step": "zotero", "error": "rate limited"},
        {"paper": "Test Paper 2", "step": "obsidian", "error": "write failed"},
    ]
    log_path = write_error_log(logs_dir, errors)

    assert log_path.exists()
    assert log_path.suffix == ".jsonl" or "pipeline_errors_" in log_path.name


def test_error_log_is_valid_jsonl(tmp_path):
    logs_dir = tmp_path / "logs"
    errors = [{"paper": "X", "step": "z", "error": "e"}]
    log_path = write_error_log(logs_dir, errors)

    lines = log_path.read_text(encoding="utf-8").strip().split("\n")
    for line in lines:
        parsed = json.loads(line)
        assert "paper" in parsed
        assert "error" in parsed


def test_logs_dir_auto_created(tmp_path):
    logs_dir = tmp_path / "new" / "logs"
    assert not logs_dir.exists()
    write_error_log(logs_dir, [{"paper": "X", "step": "z", "error": "e"}])
    assert logs_dir.exists()


def test_empty_errors_creates_empty_log(tmp_path):
    logs_dir = tmp_path / "logs"
    log_path = write_error_log(logs_dir, [])
    assert log_path.exists()
    assert log_path.read_text(encoding="utf-8").strip() == ""


def test_log_filename_has_timestamp(tmp_path):
    before = int(time.time())
    logs_dir = tmp_path / "logs"
    log_path = write_error_log(logs_dir, [])
    after = int(time.time())

    stem = log_path.stem
    parts = stem.rsplit("_", 1)
    epoch = int(parts[-1])
    assert before <= epoch <= after
