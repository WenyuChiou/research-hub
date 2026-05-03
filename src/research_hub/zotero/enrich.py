"""Re-enrich existing Zotero items from DOI metadata backends."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Iterable

from research_hub.search import CrossrefBackend, OpenAlexBackend

ENRICH_FIELDS = ["volume", "issue", "pages", "url", "abstractNote", "ISSN"]


@dataclass
class EnrichPlan:
    item_key: str
    title: str
    doi: str
    fields_to_fill: dict[str, str] = field(default_factory=dict)


def _to_search_field(zotero_field: str) -> str:
    """Map a Zotero field name to the normalized backend field name."""
    return {"abstractNote": "abstract", "publicationTitle": "venue"}.get(zotero_field, zotero_field)


def _result_value(result, field_name: str) -> str:
    if result is None:
        return ""
    if isinstance(result, dict):
        value = result.get(field_name, "")
        if not value and field_name == "ISSN":
            value = result.get("issn", "")
        return str(value or "").strip()
    value = getattr(result, field_name, "")
    if not value and field_name == "ISSN":
        value = getattr(result, "issn", "")
    return str(value or "").strip()


def plan_enrichment(zot_or_items, items: list[dict] | None = None) -> list[EnrichPlan]:
    """Identify empty Zotero fields and plan DOI-based metadata fill-ins."""
    if items is None:
        items = zot_or_items
    crossref = CrossrefBackend()
    openalex = OpenAlexBackend()
    plans: list[EnrichPlan] = []
    for item in items:
        data = item.get("data", {})
        doi = str(data.get("DOI", "") or "").strip()
        if not doi:
            continue
        empty_fields = [
            field_name
            for field_name in ENRICH_FIELDS
            if not str(data.get(field_name, "") or "").strip()
        ]
        if not empty_fields:
            continue

        fields_to_fill: dict[str, str] = {}
        for backend in (crossref, openalex):
            try:
                result = backend.get_paper(doi)
            except Exception:
                result = None
            if result is None:
                continue
            for field_name in empty_fields:
                if field_name in fields_to_fill:
                    continue
                value = _result_value(result, _to_search_field(field_name))
                if value:
                    fields_to_fill[field_name] = value
        if fields_to_fill:
            plans.append(
                EnrichPlan(
                    item_key=item.get("key", ""),
                    title=str(data.get("title", "") or "")[:60],
                    doi=doi,
                    fields_to_fill=fields_to_fill,
                )
            )
    return plans


def apply_enrichment(
    zot,
    plans: Iterable[EnrichPlan],
    *,
    rate_limit_rps: float = 2.0,
) -> dict[str, str]:
    """PATCH Zotero items with planned metadata, without overwriting existing values."""
    sleep_s = 1.0 / max(rate_limit_rps, 0.1)
    results: dict[str, str] = {}
    for plan in plans:
        try:
            item = zot.item(plan.item_key)
            data = item["data"]
            for field_name, value in plan.fields_to_fill.items():
                if not str(data.get(field_name, "") or "").strip():
                    data[field_name] = value
            zot.update_item(data)
            results[plan.item_key] = "ok"
            time.sleep(sleep_s)
        except Exception as exc:
            results[plan.item_key] = str(exc)[:80]
    return results
