"""Document read capability without claiming intake or installed-host acceptance."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_support():
    guide = (ROOT / "docs/native-source-summary.md").read_text(encoding="utf-8")
    assert "## Safe file-read support\n" in guide
    section = guide.split("## Safe file-read support\n", 1)[1].split("\n## Operations", 1)[0]
    return " ".join(section.split())


def test_read_support_names_both_native_backends_and_bounds():
    text = read_support()
    for boundary in (
        "POSIX", "no-follow", "Windows", "handle-relative", "fixed local drive",
        "every ancestor", "regular file", "workspace-relative", "fail closed",
        "recheck the selected directory's location",
    ):
        assert boundary in text
    assert "UNC" in text and "mapped network drives" in text
    assert "reparse points" in text and "sharing conflicts" in text
    assert "no permissive path-open fallback" in text


def test_read_support_does_not_expand_publication_or_acceptance():
    text = read_support()
    for boundary in (
        "does not enable Windows source-text/file-drop publication",
        "does not enable or migrate BLOB storage",
        "not evidence that a user's installed host has been upgraded or accepted",
    ):
        assert boundary in text


def test_cli_points_to_platform_specific_read_contract():
    reference = (ROOT / "docs/cli-reference.md").read_text(encoding="utf-8")
    assert "platform-specific safe-read limits" in reference
    assert "POSIX file-access limits" not in reference
    assert "[native source summaries](native-source-summary.md)" in reference
