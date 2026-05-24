"""Regression tests for Semantic Scholar API-key normalization."""

from __future__ import annotations

import logging

from research_hub.search.semantic_scholar import (
    DEFAULT_AUTHENTICATED_DELAY_SECONDS,
    SemanticScholarClient,
)


def test_non_latin1_env_api_key_is_ignored(monkeypatch, caplog) -> None:
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "\u96ff\ueea0?_SS_API_KEY")

    with caplog.at_level(
        logging.WARNING,
        logger="research_hub.search.semantic_scholar",
    ):
        client = SemanticScholarClient()

    assert client.api_key is None
    assert client._headers() == {}
    assert "SEMANTIC_SCHOLAR_API_KEY is not ASCII/latin-1" in caplog.text
    assert "querying Semantic Scholar anonymously" in caplog.text


def test_valid_ascii_env_api_key_is_sent(monkeypatch) -> None:
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "valid-key-123")

    client = SemanticScholarClient()

    assert client.api_key == "valid-key-123"
    assert client._headers()["x-api-key"] == "valid-key-123"


def test_whitespace_only_env_api_key_is_anonymous(monkeypatch) -> None:
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "  \t  ")

    client = SemanticScholarClient()

    assert client.api_key is None
    assert client._headers() == {}


def test_unset_env_api_key_is_anonymous(monkeypatch) -> None:
    monkeypatch.delenv("SEMANTIC_SCHOLAR_API_KEY", raising=False)
    monkeypatch.delenv("SEMANTIC_SCHOLAR_RPS", raising=False)

    client = SemanticScholarClient()

    assert client.api_key is None
    assert client._headers() == {}


def test_invalid_rps_env_falls_back_to_authenticated_default(monkeypatch, caplog) -> None:
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "valid-key-123")
    monkeypatch.setenv("SEMANTIC_SCHOLAR_RPS", "fast")

    with caplog.at_level(
        logging.WARNING,
        logger="research_hub.search.semantic_scholar",
    ):
        client = SemanticScholarClient()

    assert client.delay == DEFAULT_AUTHENTICATED_DELAY_SECONDS
    assert "SEMANTIC_SCHOLAR_RPS='fast' is not a number" in caplog.text


def test_non_latin1_explicit_arg_api_key_is_ignored(monkeypatch, caplog) -> None:
    """Direct constructor arg path (not env): non-latin-1 key must also
    be ignored with a warning, not crash when requests encodes headers."""
    monkeypatch.delenv("SEMANTIC_SCHOLAR_API_KEY", raising=False)

    with caplog.at_level(
        logging.WARNING,
        logger="research_hub.search.semantic_scholar",
    ):
        client = SemanticScholarClient(api_key="雿bad")

    assert client.api_key is None
    assert client._headers() == {}
    assert "SEMANTIC_SCHOLAR_API_KEY is not ASCII/latin-1" in caplog.text
