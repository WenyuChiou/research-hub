"""v0.87.1 #2 — Crossref venue fallback chain.

V2 audit found 6 papers with blank `journal` fields because their
Crossref records put the venue in `event` / `proceedings-title` /
`publisher` / `archive` instead of `container-title`. The
`_resolve_venue` helper walks all 5 candidate fields in order.
"""

from __future__ import annotations

from research_hub.search.crossref import _resolve_venue


def test_container_title_list_takes_first_nonblank() -> None:
    assert _resolve_venue({"container-title": ["", "WaterRes"]}) == "WaterRes"


def test_container_title_string_passes_through() -> None:
    assert _resolve_venue({"container-title": "Water Research"}) == "Water Research"


def test_falls_back_to_event_dict_name() -> None:
    # 6 of the V2 hot-spots (höhn HRI '24 Companion, kim HRI '24, qiao CHI EA '25,
    # ranaweera ICIPRoB 2026) look like this from Crossref.
    assert (
        _resolve_venue({"event": {"name": "Proceedings of HRI '24 Companion"}})
        == "Proceedings of HRI '24 Companion"
    )


def test_falls_back_to_event_bare_string() -> None:
    assert _resolve_venue({"event": "EGU General Assembly 2024"}) == "EGU General Assembly 2024"


def test_falls_back_to_proceedings_title() -> None:
    assert (
        _resolve_venue({"proceedings-title": ["Proc. ICIPRoB 2026"]})
        == "Proc. ICIPRoB 2026"
    )


def test_falls_back_to_publisher() -> None:
    # ESS Open Archive (fu2025) returns this shape via Crossref.
    assert _resolve_venue({"publisher": "Authorea, Inc."}) == "Authorea, Inc."


def test_falls_back_to_archive() -> None:
    assert _resolve_venue({"archive": ["EarthArXiv"]}) == "EarthArXiv"


def test_returns_empty_when_all_blank() -> None:
    assert _resolve_venue({}) == ""
    assert _resolve_venue({"container-title": [], "event": {}, "publisher": ""}) == ""


def test_container_title_wins_over_event() -> None:
    """Order matters: a Crossref record with BOTH a journal venue and a
    conference event should prefer the journal."""
    work = {
        "container-title": ["Real Journal of Things"],
        "event": {"name": "Some Conference"},
    }
    assert _resolve_venue(work) == "Real Journal of Things"


def test_event_wins_over_proceedings_title_for_conference_records() -> None:
    work = {
        "container-title": [],
        "event": {"name": "EGU24"},
        "proceedings-title": ["EGU General Assembly 2024"],
    }
    assert _resolve_venue(work) == "EGU24"


def test_falls_back_through_full_chain_when_only_last_field_set() -> None:
    work = {"container-title": [], "event": {}, "proceedings-title": [], "publisher": "", "archive": ["EarthArXiv"]}
    assert _resolve_venue(work) == "EarthArXiv"


def test_resolver_strips_whitespace() -> None:
    assert _resolve_venue({"container-title": ["   Water Research   "]}) == "Water Research"


def test_parse_work_uses_resolver() -> None:
    """The full _parse_work pipeline picks up venue from event when
    container-title is empty."""
    from research_hub.search.crossref import CrossrefBackend

    backend = CrossrefBackend()
    work = {
        "DOI": "10.1109/iciprob69625.2026.11497793",
        "title": ["Improved Flood Management Through LLM"],
        "container-title": [],
        "event": {"name": "Proceedings of ICIPRoB 2026"},
        "publisher": "IEEE",
        "issued": {"date-parts": [[2026]]},
    }
    result = backend._parse_work(work)
    assert result.venue == "Proceedings of ICIPRoB 2026"
