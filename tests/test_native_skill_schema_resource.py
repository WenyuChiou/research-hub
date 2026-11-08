"""The portable observations schema must travel with the loaded skill."""

from pathlib import Path
import re

from research_hub import skill_installer


ROOT = Path(__file__).resolve().parents[1]
NAME = "research-discovery-observations-1.0.json"
CANONICAL = ROOT / "src/research_hub/schemas" / NAME
SKILL_ROOTS = (
    ROOT / "skills/research-hub",
    ROOT / "src/research_hub/skills_data/research-hub",
)


def test_skill_schema_copies_match_the_canonical_schema():
    expected = CANONICAL.read_bytes()
    for skill_root in SKILL_ROOTS:
        resource = skill_root / "references" / NAME
        assert resource.is_file(), resource
        assert resource.read_bytes() == expected


def test_skill_reference_links_to_its_own_schema():
    for skill_root in SKILL_ROOTS:
        guide = skill_root / "references/native-discovery-export.md"
        links = re.findall(r"\[[^]]+\]\(([^)]+)\)", guide.read_text(encoding="utf-8"))
        targets = [link for link in links if Path(link).name == NAME]
        assert len(targets) == 1
        assert (guide.parent / targets[0]).resolve() == (skill_root / "references" / NAME).resolve()
        assert (guide.parent / targets[0]).is_file()


def test_installer_copies_schema_relative_to_loaded_skill(tmp_path, monkeypatch):
    assert Path(skill_installer.__file__).resolve() == ROOT / "src/research_hub/skill_installer.py"
    assert skill_installer.get_bundled_skill_path("research-hub").resolve() == (SKILL_ROOTS[1] / "SKILL.md").resolve()
    destination = tmp_path / "host" / "skills"
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setattr(skill_installer, "SKILL_PACK", (("research-hub", "research-hub"),))
    monkeypatch.setattr(skill_installer, "PLATFORMS", {"fixture": skill_installer.PlatformConfig("Fixture", destination)})
    monkeypatch.chdir(project)
    installed = skill_installer.install_skill("fixture")
    assert len(installed) == 1
    loaded_skill = Path(installed[0])
    assert loaded_skill.is_file()
    assert (loaded_skill.parent / "references" / NAME).read_bytes() == CANONICAL.read_bytes()
