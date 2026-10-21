from __future__ import annotations

import os
from pathlib import Path

import pytest

from research_hub import skill_installer


def _patch_platform_paths(monkeypatch, home: Path) -> None:
    """v0.53: PlatformConfig now takes `skills_root` (shared dir for all skills
    in the pack) instead of `skill_dir` (one dir per skill)."""
    monkeypatch.setitem(
        skill_installer.PLATFORMS,
        "claude-code",
        skill_installer.PlatformConfig(
            name="Claude Code",
            skills_root=home / ".claude" / "skills",
        ),
    )
    monkeypatch.setitem(
        skill_installer.PLATFORMS,
        "codex",
        skill_installer.PlatformConfig(
            name="Codex (OpenAI)",
            skills_root=home / ".codex" / "skills",
        ),
    )
    monkeypatch.setitem(
        skill_installer.PLATFORMS,
        "cursor",
        skill_installer.PlatformConfig(
            name="Cursor",
            skills_root=home / ".cursor" / "skills",
        ),
    )
    monkeypatch.setitem(
        skill_installer.PLATFORMS,
        "gemini",
        skill_installer.PlatformConfig(
            name="Gemini CLI",
            skills_root=home / ".gemini" / "skills",
        ),
    )


def test_install_skill_pack_writes_every_pack_member(tmp_path, monkeypatch):
    _patch_platform_paths(monkeypatch, tmp_path)

    installed = skill_installer.install_skill("claude-code")

    # v0.53: returns a list (one entry per skill in SKILL_PACK)
    assert isinstance(installed, list)
    assert len(installed) == len(skill_installer.SKILL_PACK)
    # Each target dir was created with SKILL.md inside
    for _source, target in skill_installer.SKILL_PACK:
        dest = tmp_path / ".claude" / "skills" / target / "SKILL.md"
        assert dest.is_file(), f"missing skill at {dest}"


def test_install_skill_content_matches_source(tmp_path, monkeypatch):
    _patch_platform_paths(monkeypatch, tmp_path)

    skill_installer.install_skill("claude-code")

    for source_name, target_name in skill_installer.SKILL_PACK:
        source = skill_installer.get_bundled_skill_path(source_name)
        dest = tmp_path / ".claude" / "skills" / target_name / "SKILL.md"
        assert dest.read_text(encoding="utf-8") == source.read_text(encoding="utf-8")


def test_install_copies_complete_bundles(tmp_path, monkeypatch):
    _patch_platform_paths(monkeypatch, tmp_path)
    installed = skill_installer.install_skill("claude-code")
    root = tmp_path / ".claude" / "skills"
    expected = set()
    for source_name, target_name in skill_installer.SKILL_PACK:
        source_dir = skill_installer.get_bundled_skill_path(source_name).parent
        for source in source_dir.rglob("*"):
            if source.is_file():
                relative = Path(target_name) / source.relative_to(source_dir)
                expected.add(relative)
                assert (root / relative).read_bytes() == source.read_bytes()
    assert {p.relative_to(root) for p in root.rglob("*") if p.is_file()} == expected
    assert len(installed) == len(skill_installer.SKILL_PACK)
    # Shared sibling references keep their original relative layout.
    orchestrator = root / "research-workflow-orchestrator"
    assert (orchestrator / "references/workflow-contract.md").is_file()
    assert (orchestrator / "../research-hub/references/research-protocol.md").is_file()
    assert (root / "gap-to-topic/scripts/dossier_to_docx.js").is_file()


def test_list_platforms_rejects_skill_md_only_install(tmp_path, monkeypatch):
    _patch_platform_paths(monkeypatch, tmp_path)
    for _source, target in skill_installer.SKILL_PACK:
        path = tmp_path / ".claude" / "skills" / target / "SKILL.md"
        path.parent.mkdir(parents=True)
        path.write_text("old partial install", encoding="utf-8")
    assert not dict((k, ok) for k, _, ok in skill_installer.list_platforms())["claude-code"]


def test_missing_support_file_is_reported_and_repaired(tmp_path, monkeypatch):
    _patch_platform_paths(monkeypatch, tmp_path)
    skill_installer.install_skill("claude-code")
    support = tmp_path / ".claude/skills/research-hub/references/research-protocol.md"
    assert support.is_file()
    support.unlink()
    assert not dict((k, ok) for k, _, ok in skill_installer.list_platforms())["claude-code"]
    skill_installer.install_skill("claude-code")
    assert support.is_file()
    assert dict((k, ok) for k, _, ok in skill_installer.list_platforms())["claude-code"]


@pytest.fixture
def small_bundle(tmp_path, monkeypatch):
    source = tmp_path / "source" / "research-hub"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text("current skill", encoding="utf-8")
    (source / "references").mkdir()
    (source / "references" / "contract.md").write_text("contract", encoding="utf-8")
    (source / "scripts").mkdir()
    (source / "scripts" / "helper.py").write_text("# helper\n", encoding="utf-8")
    (source / "scripts" / "helper.py").chmod(0o755)
    root = tmp_path / "installed"
    monkeypatch.setattr(skill_installer, "SKILL_PACK", (("research-hub", "research-hub"),))
    monkeypatch.setattr(skill_installer, "get_bundled_skill_path", lambda _name: source / "SKILL.md")
    monkeypatch.setattr(
        skill_installer, "PLATFORMS", {"fixture": skill_installer.PlatformConfig("Fixture", root)}
    )
    return source, root


def test_bundle_reinstall_preserves_unrelated_files(small_bundle):
    source, root = small_bundle
    skill_installer.install_skill("fixture")
    own_file = root / "research-hub/references/my-notes.md"
    own_file.write_text("user content", encoding="utf-8")
    other_skill = root / "other-skill/SKILL.md"
    other_skill.parent.mkdir()
    other_skill.write_text("other skill", encoding="utf-8")
    (source / "SKILL.md").write_text("updated skill", encoding="utf-8")
    first = skill_installer.install_skill("fixture")
    assert skill_installer.install_skill("fixture") == first
    assert (root / "research-hub/SKILL.md").read_text() == "updated skill"
    assert own_file.read_text() == "user content"
    assert other_skill.read_text() == "other skill"
    assert (root / "research-hub/scripts/helper.py").stat().st_mode == (
        source / "scripts/helper.py"
    ).stat().st_mode


def _symlink(link, target, *, directory=False):
    try:
        link.symlink_to(target, target_is_directory=directory)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"Symlink creation is unavailable: {exc}")


@pytest.mark.parametrize("location", ["root", "directory", "file", "dangling"])
def test_source_links_rejected_before_any_install(small_bundle, location):
    source, root = small_bundle
    if location == "root":
        moved = source.with_name("real-source")
        source.rename(moved)
        _symlink(source, moved, directory=True)
    elif location == "directory":
        _symlink(source / "linked-directory", source / "references", directory=True)
    else:
        target = source / ("SKILL.md" if location == "file" else "missing")
        _symlink(source / "linked-file", target)
    with pytest.raises(ValueError, match="symlinks or junctions"):
        skill_installer.install_skill("fixture")
    assert not root.exists()


@pytest.mark.parametrize("location", ["root", "skill", "directory", "file", "dangling"])
def test_destination_links_rejected_without_external_writes(small_bundle, tmp_path, location):
    _source, root = small_bundle
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel"
    sentinel.write_text("preserve", encoding="utf-8")
    if location == "root":
        link = root
    elif location == "skill":
        link = root / "research-hub"
    elif location == "directory":
        link = root / "research-hub/references"
    else:
        link = root / "research-hub/SKILL.md"
    link.parent.mkdir(parents=True, exist_ok=True)
    target = sentinel if location == "file" else (
        outside / "missing" if location == "dangling" else outside
    )
    _symlink(link, target, directory=location in {"root", "skill", "directory"})
    with pytest.raises(ValueError, match="symlinks or junctions"):
        skill_installer.install_skill("fixture")
    assert sentinel.read_text() == "preserve"
    assert list(outside.iterdir()) == [sentinel]
    assert not skill_installer.list_platforms()[0][2]
    assert not (root / "research-hub/scripts").exists()


@pytest.mark.parametrize("location", ["SKILL.md", "references/contract.md"])
def test_directory_in_place_of_required_file_is_incomplete(small_bundle, location):
    _source, root = small_bundle
    skill_installer.install_skill("fixture")
    path = root / "research-hub" / location
    path.unlink()
    path.mkdir()
    assert not skill_installer.list_platforms()[0][2]
    with pytest.raises(ValueError, match="wrong file type"):
        skill_installer.install_skill("fixture")
    assert path.is_dir()


@pytest.mark.parametrize("name", ["../escape", "/absolute", "C:\\escape", "x/y", ".", ""])
def test_unsafe_source_names_rejected(name):
    with pytest.raises(ValueError, match="Unsafe skill path component"):
        skill_installer.get_bundled_skill_path(name)


@pytest.mark.parametrize("name", ["../escape", "/absolute", "C:\\escape", "x/y", ".", ""])
def test_unsafe_target_names_rejected(small_bundle, monkeypatch, name):
    _source, root = small_bundle
    monkeypatch.setattr(skill_installer, "SKILL_PACK", (("research-hub", name),))
    with pytest.raises(ValueError, match="Unsafe skill path component"):
        skill_installer.install_skill("fixture")
    assert not root.exists()


def test_copy_failure_preserves_existing_file_and_cleans_temporary(small_bundle, monkeypatch):
    _source, root = small_bundle
    skill_installer.install_skill("fixture")
    destination = root / "research-hub/SKILL.md"
    destination.write_text("old installed skill", encoding="utf-8")

    def fail_copy(_source, temporary):
        Path(temporary).write_bytes(b"partial")
        raise OSError("simulated disk failure")

    monkeypatch.setattr(skill_installer.shutil, "copy2", fail_copy)
    with pytest.raises(OSError, match="simulated disk failure"):
        skill_installer.install_skill("fixture")
    assert destination.read_text() == "old installed skill"
    assert not list(root.rglob(".hub-skill-*"))


def test_update_does_not_modify_external_hardlink(small_bundle, tmp_path):
    _source, root = small_bundle
    destination = root / "research-hub/SKILL.md"
    destination.parent.mkdir(parents=True)
    outside = tmp_path / "outside.txt"
    outside.write_text("preserve", encoding="utf-8")
    os.link(outside, destination)
    skill_installer.install_skill("fixture")
    assert destination.read_text() == "current skill"
    assert outside.read_text() == "preserve"


def test_trusted_root_ancestor_may_be_symlinked(small_bundle, tmp_path, monkeypatch):
    _source, root = small_bundle
    alias = tmp_path / "alias"
    _symlink(alias, tmp_path, directory=True)
    config = skill_installer.PlatformConfig("Fixture", alias / root.name)
    monkeypatch.setitem(skill_installer.PLATFORMS, "fixture", config)
    assert skill_installer.install_skill("fixture") == [str(config.skill_path("research-hub"))]
    assert (root / "research-hub/references/contract.md").is_file()
    assert skill_installer.list_platforms()[0][2]


def test_unresolvable_platform_does_not_break_other_statuses(small_bundle, tmp_path, monkeypatch):
    skill_installer.install_skill("fixture")
    loop = tmp_path / "loop"
    _symlink(loop, loop, directory=True)
    monkeypatch.setitem(
        skill_installer.PLATFORMS, "loop", skill_installer.PlatformConfig("Loop", loop / "skills")
    )
    statuses = {key: installed for key, _name, installed in skill_installer.list_platforms()}
    assert statuses == {"fixture": True, "loop": False}


def test_later_invalid_bundle_does_not_update_earlier_skill(small_bundle, monkeypatch):
    source, root = small_bundle
    installed = root / "research-hub/SKILL.md"
    installed.parent.mkdir(parents=True)
    installed.write_text("preserve existing", encoding="utf-8")
    unsafe = source.with_name("unsafe")
    unsafe.mkdir()
    (unsafe / "SKILL.md").write_text("unsafe skill", encoding="utf-8")
    _symlink(unsafe / "link", source / "SKILL.md")
    monkeypatch.setattr(
        skill_installer, "SKILL_PACK", (("research-hub", "research-hub"), ("unsafe", "unsafe"))
    )
    monkeypatch.setattr(
        skill_installer, "get_bundled_skill_path",
        lambda name: (source if name == "research-hub" else unsafe) / "SKILL.md",
    )
    with pytest.raises(ValueError, match="symlinks or junctions"):
        skill_installer.install_skill("fixture")
    assert installed.read_text() == "preserve existing"
    assert not (root / "research-hub/references").exists()


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO creation is POSIX-only")
def test_source_special_file_rejected_without_reading(small_bundle):
    source, root = small_bundle
    os.mkfifo(source / "pipe")
    with pytest.raises(ValueError, match="non-regular file"):
        skill_installer.install_skill("fixture")
    assert not root.exists()


def test_missing_optional_source_remains_incomplete(small_bundle, monkeypatch):
    source, root = small_bundle
    monkeypatch.setattr(
        skill_installer, "SKILL_PACK",
        (("research-hub", "research-hub"), ("missing-optional", "missing-optional")),
    )

    def find(name):
        if name == "missing-optional":
            raise FileNotFoundError(name)
        return source / "SKILL.md"

    monkeypatch.setattr(skill_installer, "get_bundled_skill_path", find)
    assert skill_installer.install_skill("fixture") == [str(root / "research-hub/SKILL.md")]
    assert not skill_installer.list_platforms()[0][2]


def test_install_unknown_platform_raises():
    with pytest.raises(ValueError, match="Unknown platform"):
        skill_installer.install_skill("unknown")


def test_list_platforms_shows_all():
    platforms = skill_installer.list_platforms()

    assert len(platforms) == 4
    assert [key for key, _, _ in platforms] == ["claude-code", "codex", "cursor", "gemini"]


def test_install_idempotent(tmp_path, monkeypatch):
    _patch_platform_paths(monkeypatch, tmp_path)

    first = skill_installer.install_skill("claude-code")
    second = skill_installer.install_skill("claude-code")

    assert first == second
    for path in second:
        dest = Path(path)
        assert dest.is_file()


def test_list_platforms_reports_true_after_full_pack_install(tmp_path, monkeypatch):
    """v0.53 regression: list_platforms only reports 'installed' when ALL
    skills in the pack are present, not just the legacy knowledge-base one."""
    _patch_platform_paths(monkeypatch, tmp_path)

    before = dict((k, ok) for k, _, ok in skill_installer.list_platforms())
    assert before["claude-code"] is False

    skill_installer.install_skill("claude-code")

    after = dict((k, ok) for k, _, ok in skill_installer.list_platforms())
    assert after["claude-code"] is True


def test_multi_ai_skill_is_discoverable():
    """The v0.53 multi-AI skill must be findable from the bundled source."""
    path = skill_installer.get_bundled_skill_path("research-hub-multi-ai")
    text = path.read_text(encoding="utf-8")
    assert "research-hub-multi-ai" in text
    # Spot-check the supported bounded execution leaves.
    for name in ("Codex", "Antigravity"):
        assert name in text
    assert "archived Gemini delegate is not a supported leaf" in text


def test_bundled_skills_use_current_public_positioning():
    """Packaged skills are what `research-hub install` copies for users."""
    bad_fragments = ("??", "蝜", "銝", "", "撟")
    for source_name, _target in skill_installer.SKILL_PACK:
        text = skill_installer.get_bundled_skill_path(source_name).read_text(encoding="utf-8")
        for fragment in bad_fragments:
            assert fragment not in text
        # v0.66 relaxed: each skill must mention AT LEAST ONE product term
        # (was: must mention ALL THREE). Specialized v0.66 skills like
        # paper-memory-builder are scoped to one part of the stack.
        product_terms = ("Zotero", "Obsidian", "NotebookLM", "research-hub")
        assert any(term in text for term in product_terms), (
            f"{source_name}: SKILL.md mentions none of {product_terms} -- "
            "not anchored to research-hub product surface"
        )
    # v0.68: source dir is now `research-hub` (was `knowledge-base`).
    # Backward-compat alias is verified separately in test_v068_legacy_knowledge_base_alias.py.
    core = skill_installer.get_bundled_skill_path("research-hub").read_text(encoding="utf-8")
    assert "AI-operable" in core
    assert "--preset" not in core
    assert "notebooklm generate --cluster project-topic --type brief" in core


def test_ai_integration_docs_use_current_notebooklm_generate_flag():
    for path in (Path("docs/ai-integrations.md"), Path("docs/zh/ai-integrations.md")):
        text = path.read_text(encoding="utf-8")
        assert "--preset" not in text
        assert "notebooklm generate --cluster my-topic --type brief" in text


def test_codex_mcp_docs_separate_capability_from_release_validation():
    text = Path("docs/ai-host-support.md").read_text(encoding="utf-8")
    header = next(line for line in text.splitlines() if line.startswith("| Host / surface |"))
    row = next(line for line in text.splitlines() if line.startswith("| Codex CLI |"))
    columns = [cell.strip() for cell in header.strip("|").split("|")]
    values = [cell.strip() for cell in row.strip("|").split("|")]
    codex = dict(zip(columns, values))

    assert codex["MCP"].startswith("Yes")
    assert "STDIO" in codex["MCP"]
    assert "Streamable HTTP" in codex["MCP"]
    assert "not release-verified" in codex["Current position"]
    assert "https://learn.chatgpt.com/docs/extend/mcp?surface=cli" in text

    # Both shell walkthroughs point readers to the capability/validation boundary.
    anchor = "ai-host-support.md#codex-mcp-capability-and-validation"
    for path in (Path("docs/ai-integrations.md"), Path("docs/zh/ai-integrations.md")):
        assert anchor in path.read_text(encoding="utf-8")
