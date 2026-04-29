"""Best-effort abstract recovery from DOI metadata services."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import quote

import requests


logger = logging.getLogger(__name__)

_USER_AGENT = "research-hub/0.72.0 (https://github.com/WenyuChiou/research-hub)"
_UNPAYWALL_EMAIL = "research-hub@anthropic.com"


@dataclass
class RecoveredAbstract:
    text: str
    source: str
    oa_url: str = ""


def recover_abstract(doi: str, *, timeout: int = 10) -> RecoveredAbstract:
    """Try Crossref first, then Unpaywall, to recover missing abstracts."""
    if not doi:
        return RecoveredAbstract(text="", source="")

    try:
        from research_hub.search.crossref import _extract_crossref_abstract

        response = requests.get(
            f"https://api.crossref.org/works/{quote(doi.strip(), safe='')}",
            timeout=timeout,
            headers={"User-Agent": _USER_AGENT},
        )
        if response.status_code == 200:
            work = (response.json().get("message") or {})
            abstract = _extract_crossref_abstract(work)
            if abstract:
                logger.info("abstract recovery: doi=%s source=crossref", doi)
                return RecoveredAbstract(text=abstract, source="crossref")
    except Exception as exc:
        logger.debug("Crossref abstract recovery failed for %s: %s", doi, exc)

    try:
        response = requests.get(
            f"https://api.unpaywall.org/v2/{quote(doi.strip(), safe='')}",
            params={"email": _UNPAYWALL_EMAIL},
            timeout=timeout,
            headers={"User-Agent": _USER_AGENT},
        )
        if response.status_code == 200:
            data = response.json() or {}
            best_oa = (data.get("best_oa_location") or {})
            oa_url = best_oa.get("url", "") or ""
            if oa_url:
                logger.info("abstract recovery: doi=%s source=unpaywall oa_url=%s", doi, oa_url)
                return RecoveredAbstract(text="", source="unpaywall", oa_url=oa_url)
    except Exception as exc:
        logger.debug("Unpaywall lookup failed for %s: %s", doi, exc)

    return RecoveredAbstract(text="", source="")
