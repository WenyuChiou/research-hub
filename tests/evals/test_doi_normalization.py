import pytest

from research_hub.utils.doi import extract_arxiv_id, normalize_doi


@pytest.mark.evals
@pytest.mark.parametrize(
    "raw",
    [
        "10.1234/abc",
        "10.1234/ABC",
        "https://doi.org/10.1234/abc",
        "http://dx.doi.org/10.1234/abc",
        "doi:10.1234/abc",
        "10.48550/arxiv.2310.06770",
        "arxiv.org/abs/2310.06770",
        " 10.1234/abc ",
        "10.1234/abc(v1)",
        "'10.1234/abc'",
    ],
)
def test_normalize_doi_idempotent(raw):
    """normalize_doi(normalize_doi(x)) == normalize_doi(x)."""
    n1 = normalize_doi(raw)
    n2 = normalize_doi(n1)
    assert n1 == n2


@pytest.mark.evals
def test_normalize_doi_equivalence_classes():
    """Different forms of the same DOI collapse to identical normalized form."""
    canonical = normalize_doi("10.1234/abc")
    variants = [
        "10.1234/ABC",
        "https://doi.org/10.1234/abc",
        "doi:10.1234/abc",
        " 10.1234/abc ",
    ]
    for variant in variants:
        assert normalize_doi(variant) == canonical


def _paper_identity(raw: str) -> str:
    normalized = normalize_doi(raw.strip().strip("'"))
    arxiv_id = extract_arxiv_id(raw) or extract_arxiv_id(normalized)
    if arxiv_id:
        return f"arxiv:{arxiv_id.split('v', 1)[0]}"
    return normalized


@pytest.mark.evals
def test_arxiv_and_doi_collapse_for_same_paper():
    """arXiv arxiv_id, arxiv DOI, openalex DOI for same paper collapse to one paper key."""
    forms = [
        "2310.06770",
        "arxiv.org/abs/2310.06770",
        "https://arxiv.org/abs/2310.06770v1",
        "10.48550/arxiv.2310.06770",
        "https://doi.org/10.48550/arxiv.2310.06770",
    ]
    identities = {_paper_identity(form) for form in forms}
    assert identities == {"arxiv:2310.06770"}
