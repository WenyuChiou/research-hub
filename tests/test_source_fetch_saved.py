from __future__ import annotations

from hashlib import sha256
import json
import os
import shutil
from pathlib import Path

import pytest

from research_hub import cli
from research_hub import source_fetch as sf
from research_hub.source_fetch_saved import import_saved_public_source
from research_hub import source_fetch_saved as saved


def _saved_input(tmp_path: Path, raw: bytes, **changes):
    tmp_path.mkdir(parents=True, exist_ok=True)
    raw_path = tmp_path / "article.md"
    raw_path.write_bytes(raw)
    manifest = {
        "schema_version": "saved-public-source-input/v1",
        "url": "https://example.org/article",
        "final_url": "https://cdn.example.org/article.md",
        "doi": "10.1000/example",
        "title": "A saved public study",
        "raw_path": "article.md",
        "raw_sha256": sha256(raw).hexdigest(),
        "content_type": "text/markdown",
        "original_acquired_at": None,
    }
    manifest.update(changes)
    manifest_path = tmp_path / "manifest.json"
    manifest_bytes = json.dumps(manifest, separators=(",", ":")).encode()
    manifest_path.write_bytes(manifest_bytes)
    return manifest_path, sha256(manifest_bytes).hexdigest(), manifest


def _document() -> bytes:
    return (
        "# A saved public study\n\n"
        "DOI: 10.1000/example\n\n"
        "## Introduction\n" + "Public offline evidence and context. " * 20 + "\n\n"
        "## Methods\n"
        + "Deterministic methods and reproducible measurements. "
        * 15
        + "\n\n"
        "## Results\n" + "Results, uncertainty, and sensitivity checks. " * 15
    ).encode()


def test_import_and_replay_are_offline_and_preserve_bytes(tmp_path, monkeypatch):
    manifest_path, manifest_hash, _ = _saved_input(tmp_path, _document())
    monkeypatch.setattr(
        "requests.Session", lambda: (_ for _ in ()).throw(AssertionError("network"))
    )

    result = import_saved_public_source(
        input_manifest=manifest_path,
        expected_manifest_sha256=manifest_hash,
        output_dir=tmp_path / "bundle",
    )

    assert result.request == {
        "operation": "source import-saved",
        "doi": "10.1000/example",
        "url": "https://example.org/article",
        "title": "A saved public study",
        "output_dir": str((tmp_path / "bundle").resolve()),
        "public_only": True,
    }
    assert result.status == "available"
    assert result.evidence_level == "full-text"
    assert [attempt.purpose for attempt in result.attempts] == [
        "saved-input-provenance",
        "saved-public-source",
    ]
    assert all(attempt.http_status is None for attempt in result.attempts)
    assert Path(result.attempts[0].raw_path).read_bytes() == manifest_path.read_bytes()
    assert Path(result.attempts[1].raw_path).read_bytes() == _document()
    assert result.diagnostics["saved_import"]["original_acquired_at"] is None
    assert result.diagnostics["saved_import"]["imported_at"] == result.retrieved_at
    assert (
        result.diagnostics["saved_import"]["original_http_acquisition_verified"]
        is False
    )
    assert sf.validate_source_fetch(tmp_path / "bundle" / "source-fetch-result.json")[
        "valid"
    ]


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"url": "https://user:secret@example.org/article"}, "credential-free"),
        ({"raw_path": "../article.md"}, "contained relative"),
        ({"raw_sha256": "0" * 64}, "saved source SHA-256 mismatch"),
    ],
)
def test_bad_inputs_fail_before_output_write(tmp_path, changes, message):
    manifest_path, manifest_hash, _ = _saved_input(tmp_path, _document(), **changes)
    output = tmp_path / "bundle"
    with pytest.raises(ValueError, match=message):
        import_saved_public_source(
            input_manifest=manifest_path,
            expected_manifest_sha256=manifest_hash,
            output_dir=output,
        )
    assert not output.exists()


def test_manifest_hash_and_existing_output_fail_without_writes(tmp_path):
    manifest_path, manifest_hash, _ = _saved_input(tmp_path, _document())
    output = tmp_path / "existing"
    with pytest.raises(ValueError, match="manifest SHA-256 mismatch"):
        import_saved_public_source(
            input_manifest=manifest_path,
            expected_manifest_sha256="0" * 64,
            output_dir=tmp_path / "absent",
        )
    assert not (tmp_path / "absent").exists()
    output.mkdir()
    marker = output / "keep.txt"
    marker.write_text("keep")
    with pytest.raises(FileExistsError):
        import_saved_public_source(
            input_manifest=manifest_path,
            expected_manifest_sha256=manifest_hash,
            output_dir=output,
        )
    assert marker.read_text() == "keep"


def test_symlink_raw_input_is_rejected_before_output(tmp_path):
    target = tmp_path / "target.md"
    target.write_bytes(_document())
    link = tmp_path / "article.md"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation is unavailable")
    manifest_path, manifest_hash, manifest = _saved_input(tmp_path, _document())
    (tmp_path / manifest["raw_path"]).unlink()
    link.symlink_to(target)
    with pytest.raises(ValueError, match="symlink or reparse"):
        import_saved_public_source(
            input_manifest=manifest_path,
            expected_manifest_sha256=manifest_hash,
            output_dir=tmp_path / "bundle",
        )
    assert not (tmp_path / "bundle").exists()


def test_parser_failure_and_identity_mismatch_remain_visible(tmp_path):
    bad_manifest, bad_hash, _ = _saved_input(tmp_path / "bad", b"text\x00binary")
    bad = import_saved_public_source(
        input_manifest=bad_manifest,
        expected_manifest_sha256=bad_hash,
        output_dir=tmp_path / "bad-bundle",
    )
    assert bad.status == "parse-error"
    assert bad.evidence_level == "metadata"
    assert sf.validate_source_fetch(
        tmp_path / "bad-bundle" / "source-fetch-result.json"
    )["valid"]

    other = tmp_path / "other"
    other.mkdir()
    manifest_path, manifest_hash, _ = _saved_input(
        other, _document(), doi="10.9999/different", title="An unrelated expected title"
    )
    mismatch = import_saved_public_source(
        input_manifest=manifest_path,
        expected_manifest_sha256=manifest_hash,
        output_dir=tmp_path / "other-bundle",
    )
    assert mismatch.status == "identity-mismatch"
    assert mismatch.identity_status == "mismatch"


def test_saved_login_page_remains_inaccessible(tmp_path):
    html = b"<html><body><form action='/login'>Sign in to continue</form></body></html>"
    manifest_path, manifest_hash, _ = _saved_input(
        tmp_path, html, raw_path="article.md", content_type="text/html"
    )
    result = import_saved_public_source(
        input_manifest=manifest_path,
        expected_manifest_sha256=manifest_hash,
        output_dir=tmp_path / "bundle",
    )
    assert result.status == "inaccessible"
    assert result.attempts[1].outcome == "inaccessible"
    assert sf.validate_source_fetch(tmp_path / "bundle" / "source-fetch-result.json")[
        "valid"
    ]


def test_rehashed_changed_manifest_origin_is_rejected(tmp_path):
    manifest_path, manifest_hash, _ = _saved_input(tmp_path, _document())
    output = tmp_path / "bundle"
    import_saved_public_source(
        input_manifest=manifest_path,
        expected_manifest_sha256=manifest_hash,
        output_dir=output,
    )
    result_path = output / "source-fetch-result.json"
    payload = json.loads(result_path.read_text())
    provenance_path = Path(payload["attempts"][0]["raw_path"])
    manifest = json.loads(provenance_path.read_text())
    manifest["url"] = "https://changed.example.org/article"
    changed = json.dumps(manifest, separators=(",", ":")).encode()
    provenance_path.write_bytes(changed)
    changed_hash = sha256(changed).hexdigest()
    payload["attempts"][0]["raw_sha256"] = changed_hash
    payload["attempts"][0]["response_bytes"] = len(changed)
    payload["diagnostics"]["saved_import"]["manifest_sha256"] = changed_hash
    attempts = [sf.FetchAttempt(**item) for item in payload["attempts"]]
    payload["receipt_sha256"] = sf._receipt_hash(
        payload["request"],
        attempts,
        payload["extracted_text_sha256"],
        sf._receipt_result_fields(payload),
    )
    result_path.write_text(json.dumps(payload))

    report = sf.validate_source_fetch(result_path)
    assert not report["valid"]
    assert any("request URL differs" in error for error in report["errors"])


def test_cli_import_saved_emits_json(tmp_path, capsys):
    manifest_path, manifest_hash, _ = _saved_input(tmp_path, _document())
    output = tmp_path / "bundle"
    assert (
        cli.main(
            [
                "source",
                "import-saved",
                str(manifest_path),
                "--manifest-sha256",
                manifest_hash,
                "--output-dir",
                str(output),
                "--json",
            ]
        )
        == 0
    )
    assert (
        json.loads(capsys.readouterr().out)["request"]["operation"]
        == "source import-saved"
    )


def _rehash_result(path, payload):
    payload["receipt_sha256"] = sf._receipt_hash(
        payload["request"],
        [sf.FetchAttempt(**a) for a in payload["attempts"]],
        payload["extracted_text_sha256"],
        sf._receipt_result_fields(payload),
    )
    path.write_text(json.dumps(payload), encoding="utf-8")


@pytest.mark.parametrize("operation", [[], {}, None, 1])
def test_malformed_operation_is_reported_without_raising(tmp_path, operation):
    manifest, digest, _ = _saved_input(tmp_path, _document())
    output = tmp_path / "bundle"
    import_saved_public_source(
        input_manifest=manifest, expected_manifest_sha256=digest, output_dir=output
    )
    path = output / "source-fetch-result.json"
    payload = json.loads(path.read_text())
    payload["request"]["operation"] = operation
    _rehash_result(path, payload)
    report = sf.validate_source_fetch(path)
    assert not report["valid"]
    assert any("operation must be" in e for e in report["errors"])


@pytest.mark.parametrize("raw", [_document(), b"text\x00binary"])
def test_rehashed_terminal_fulltext_identity_promotion_is_rejected(tmp_path, raw):
    manifest, digest, _ = _saved_input(tmp_path, raw)
    output = tmp_path / "bundle"
    import_saved_public_source(
        input_manifest=manifest, expected_manifest_sha256=digest, output_dir=output
    )
    path = output / "source-fetch-result.json"
    payload = json.loads(path.read_text())
    payload.update(
        status="parse-error",
        evidence_level="full-text",
        identity_status="verified",
        locators=[],
    )
    for key in (
        "raw_path",
        "raw_sha256",
        "extracted_text_path",
        "extracted_text_sha256",
    ):
        payload[key] = None
    payload["attempts"][1]["outcome"] = "parsed"
    _rehash_result(path, payload)
    report = sf.validate_source_fetch(path)
    assert not report["valid"]
    assert any("parser replay" in e for e in report["errors"])


@pytest.mark.parametrize("content_type", ["   ", "text/plain\n", "text/plain\t"])
def test_content_type_controls_and_empty_normalization_reject_before_writes(
    tmp_path, content_type
):
    manifest, digest, _ = _saved_input(tmp_path, _document(), content_type=content_type)
    with pytest.raises(ValueError, match="content_type"):
        import_saved_public_source(
            input_manifest=manifest,
            expected_manifest_sha256=digest,
            output_dir=tmp_path / "bundle",
        )
    assert not (tmp_path / "bundle").exists()


@pytest.mark.skipif(os.name == "nt", reason="FIFO replacement requires POSIX")
def test_checked_file_replaced_with_fifo_cannot_block_or_be_read(tmp_path, monkeypatch):
    path = tmp_path / "raw.txt"
    path.write_bytes(b"original")
    real_open = saved.os.open

    def replace_before_open(target, flags):
        path.unlink()
        os.mkfifo(path)
        return real_open(target, flags)

    with monkeypatch.context() as scoped:
        scoped.setattr(saved.os, "open", replace_before_open)
        with pytest.raises(ValueError, match="not a regular file"):
            saved._read_bounded(path, 1024, "saved source")

    assert saved.os.open is real_open
    assert path.is_fifo()
    shutil.rmtree(tmp_path)
    assert not tmp_path.exists()


@pytest.mark.parametrize("change_purposes", [False, True])
def test_operation_downgrade_cannot_certify_terminal_fulltext(
    tmp_path, change_purposes
):
    manifest, digest, _ = _saved_input(tmp_path, b"text\x00binary")
    output = tmp_path / "bundle"
    import_saved_public_source(
        input_manifest=manifest, expected_manifest_sha256=digest, output_dir=output
    )
    path = output / "source-fetch-result.json"
    payload = json.loads(path.read_text())
    payload["request"]["operation"] = "source fetch"
    payload["diagnostics"].pop("saved_import")
    payload.update(evidence_level="full-text", identity_status="verified")
    if change_purposes:
        for attempt in payload["attempts"]:
            attempt["purpose"] = "provided-url"
    _rehash_result(path, payload)
    report = sf.validate_source_fetch(path)
    assert not report["valid"]
    assert any("terminal result must" in error for error in report["errors"])
    if not change_purposes:
        assert any(
            "saved import attempts require" in error for error in report["errors"]
        )
