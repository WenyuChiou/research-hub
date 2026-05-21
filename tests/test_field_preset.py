from __future__ import annotations

import pytest

from research_hub.search.fallback import FIELD_PRESETS, _BACKEND_REGISTRY, resolve_backends_for_field


def test_resolve_field_cs_returns_6_backends():
    """Wave 3 added google-scholar; cs preset now has 6 backends."""
    assert resolve_backends_for_field("cs") == (
        "openalex",
        "arxiv",
        "semantic-scholar",
        "dblp",
        "crossref",
        "google-scholar",
    )


def test_resolve_field_bio_includes_pubmed_and_biorxiv():
    resolved = resolve_backends_for_field("bio")
    assert "pubmed" in resolved
    assert "biorxiv" in resolved


def test_resolve_field_med_includes_pubmed():
    assert "pubmed" in resolve_backends_for_field("med")


def test_resolve_field_social_includes_repec():
    assert "repec" in resolve_backends_for_field("social")


def test_resolve_field_econ_includes_repec():
    assert "repec" in resolve_backends_for_field("econ")


def test_resolve_field_chem_includes_chemrxiv():
    assert "chemrxiv" in resolve_backends_for_field("chem")


def test_resolve_field_astro_includes_nasa_ads():
    assert "nasa-ads" in resolve_backends_for_field("astro")


def test_resolve_field_edu_includes_eric():
    assert "eric" in resolve_backends_for_field("edu")


def test_resolve_field_general_returns_all_13_backends():
    """Wave 3 added ssrn and google-scholar; general preset now has 13 backends."""
    assert resolve_backends_for_field("general") == (
        "openalex",
        "arxiv",
        "semantic-scholar",
        "crossref",
        "dblp",
        "pubmed",
        "biorxiv",
        "repec",
        "ssrn",
        "chemrxiv",
        "nasa-ads",
        "eric",
        "google-scholar",
    )


def test_resolve_field_unknown_raises_valueerror_with_valid_list():
    with pytest.raises(
        ValueError,
        match="valid: astro, bio, chem, cs, econ, edu, general, math, med, physics, social",
    ):
        resolve_backends_for_field("unknown")


def test_field_presets_constants_match_registered_backends():
    preset_backends = {backend for backends in FIELD_PRESETS.values() for backend in backends}
    assert preset_backends <= set(_BACKEND_REGISTRY.keys())
