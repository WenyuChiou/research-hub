"""Discover open-access PDFs and attach them to Zotero items."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Iterable

import requests

UNPAYWALL_BASE = "https://api.unpaywall.org/v2"


@dataclass
class PdfAttachPlan:
    item_key: str
    title: str
    doi: str
    arxiv_id: str
    pdf_url: str = ""
    source: str = ""
    error: str = ""


def find_pdf_url(doi: str = "", arxiv_id: str = "", *, unpaywall_email: str = "") -> tuple[str, str]:
    """Return (pdf_url, source) or ("", "") if none found."""
    if arxiv_id:
        return (f"https://arxiv.org/pdf/{arxiv_id}.pdf", "arxiv")
    if doi and unpaywall_email:
        try:
            response = requests.get(
                f"{UNPAYWALL_BASE}/{doi}",
                params={"email": unpaywall_email},
                timeout=15,
            )
            if response.ok:
                data = response.json()
                best = data.get("best_oa_location") or {}
                pdf = str(best.get("url_for_pdf") or "").strip()
                if pdf:
                    return (pdf, "unpaywall")
        except Exception:
            pass
    return ("", "")


def _extract_arxiv_id(data: dict) -> str:
    doi = str(data.get("DOI", "") or "").strip().lower()
    match = re.match(r"10\.48550/arxiv\.(.+)", doi)
    if match:
        return match.group(1)
    url = str(data.get("url", "") or "").strip()
    match = re.search(r"arxiv\.org/(?:abs|pdf)/([^\s/?]+?)(?:\.pdf)?$", url)
    if match:
        return match.group(1)
    return ""


def plan_attach_for_items(items: list[dict], *, unpaywall_email: str = "") -> list[PdfAttachPlan]:
    """Build PDF attach plans for the provided Zotero items."""
    plans: list[PdfAttachPlan] = []
    for item in items:
        data = item.get("data", {})
        doi = str(data.get("DOI", "") or "").strip()
        arxiv_id = _extract_arxiv_id(data)
        pdf_url, source = find_pdf_url(doi=doi, arxiv_id=arxiv_id, unpaywall_email=unpaywall_email)
        plans.append(
            PdfAttachPlan(
                item_key=item.get("key", ""),
                title=str(data.get("title", "") or "")[:60],
                doi=doi,
                arxiv_id=arxiv_id,
                pdf_url=pdf_url,
                source=source,
            )
        )
    return plans


def attach_pdfs(
    zot,
    plans: Iterable[PdfAttachPlan],
    *,
    rate_limit_rps: float = 2.0,
) -> dict[str, str]:
    """Create linked-PDF attachment items for each plan with a discovered PDF URL."""
    sleep_s = 1.0 / max(rate_limit_rps, 0.1)
    results: dict[str, str] = {}
    for plan in plans:
        if not plan.pdf_url:
            results[plan.item_key] = "skip:no-source"
            continue
        try:
            template = zot.item_template("attachment", "imported_url")
            template["parentItem"] = plan.item_key
            template["url"] = plan.pdf_url
            template["title"] = "Full Text PDF"
            template["contentType"] = "application/pdf"
            zot.create_items([template])
            results[plan.item_key] = "ok"
            time.sleep(sleep_s)
        except Exception as exc:
            results[plan.item_key] = str(exc)[:80]
    return results
