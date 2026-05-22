"""BM25 + distinctive-term relevance gate (the no-LLM fit-check tier).

Regression cover for the `llm-water-resources` contamination: the legacy
gate (`term_overlap >= 0.1` over independent unigrams) kept any paper
sharing one common word, so a cluster named for LLMs filled 88% with
generic hydrology papers. The new gate parses the topic into 1..3-gram
terms and requires a paper to match a *distinctive* term -- one rare
within the candidate batch.
"""

from __future__ import annotations

from research_hub.fit_check import (
    bm25_scores,
    extract_topic_terms,
    screen_relevance,
)

_TOPIC = "large language model water resources"


# ---------------------------------------------------------------------------
# extract_topic_terms -- phrase preservation
# ---------------------------------------------------------------------------

def test_topic_terms_keep_multiword_phrase():
    terms = extract_topic_terms(_TOPIC)
    # The discriminating phrase survives intact (the legacy split destroyed it).
    assert "large language model" in terms
    assert "water resources" in terms
    # ...and the unigrams are still present for fallback matching.
    assert "language" in terms


def test_topic_terms_drop_stopwords_and_short_words():
    terms = extract_topic_terms("a study using the large language model")
    assert "study" not in terms          # stoplisted
    assert "using" not in terms          # stoplisted
    assert "the" not in terms            # stoplisted
    assert "large language model" in terms


def test_topic_terms_empty_definition():
    assert extract_topic_terms("") == []


# ---------------------------------------------------------------------------
# bm25_scores -- IDF self-calibration
# ---------------------------------------------------------------------------

def test_bm25_distinctive_term_outweighs_common_term():
    """A term in every doc gets ~0 IDF; a rare term gets high IDF, so the
    doc carrying the rare term scores far higher."""
    docs = [
        "water water water large language model",  # has the rare phrase
        "water water water hydrology model",
        "water water water streamflow model",
        "water water water irrigation model",
    ]
    query = ["water", "large language model"]
    scores, doc_freq = bm25_scores(docs, query)
    assert doc_freq["water"] == 4                  # common -> in every doc
    assert doc_freq["large language model"] == 1   # rare -> one doc
    assert scores[0] == max(scores)                # rare-term doc wins
    assert scores[0] > 2 * scores[1]


def test_bm25_empty_docs():
    scores, doc_freq = bm25_scores([], ["term"])
    assert scores == []
    assert doc_freq == {}


# ---------------------------------------------------------------------------
# screen_relevance -- the gate
# ---------------------------------------------------------------------------

# 3 genuine LLM x water-resources papers ...
_GENUINE = [
    {
        "title": "Large Language Models as Calibration Agents in Hydrological Modeling",
        "abstract": "We employ a large language model to calibrate a "
                    "hydrological model for streamflow in water resources.",
    },
    {
        "title": "Retrieval-augmented large language model for water resources decisions",
        "abstract": "A large language model with retrieval augmentation "
                    "supports water resources management decisions.",
    },
    {
        "title": "Evaluating large language model agents for streamflow forecasting",
        "abstract": "Large language model agents are evaluated for streamflow "
                    "forecasting against a hydrological model baseline.",
    },
]

# ... and 7 generic hydrology / ML papers with NO LLM term.
_HYDROLOGY = [
    {
        "title": "Assessment of JULES Land Surface Model Coupled With CaMa-Flood",
        "abstract": "The JULES land surface model coupled with CaMa-Flood "
                    "routing for operational streamflow across water resources.",
    },
    {
        "title": "Groundwater level prediction using deep learning RNN",
        "abstract": "A recurrent neural network predicts groundwater level "
                    "from water resources observations with a hydrological model.",
    },
    {
        "title": "Machine learning hydrological model with deep feed forward network",
        "abstract": "A deep feed forward neural network machine learning "
                    "hydrological model for water resources management.",
    },
    {
        "title": "Flood prediction using machine learning and deep learning models",
        "abstract": "A systematic review of machine learning and deep learning "
                    "models for flood prediction in water resources.",
    },
    {
        "title": "An irrigation decision support system for water-saving farming",
        "abstract": "A decision support system optimises irrigation scheduling "
                    "for water resources efficiency on farms.",
    },
    {
        "title": "Reference evapotranspiration estimation with limited data",
        "abstract": "An empirical model estimates reference evapotranspiration "
                    "for sustainable water resources with limited data.",
    },
    {
        "title": "Streamflow drought prediction with wavelet decomposition",
        "abstract": "Integrating wavelet decomposition with a hydrological "
                    "model improves streamflow drought prediction.",
    },
]


def test_off_topic_hydrology_papers_are_rejected():
    """The core regression: in a realistic mixed batch the pure-hydrology
    papers (no LLM term) are REJECTED while the genuine LLM papers are
    KEPT -- the old gate kept everything sharing 'water'/'model'."""
    batch = _GENUINE + _HYDROLOGY        # 10 papers -> gate is active
    verdicts = screen_relevance(batch, _TOPIC)

    genuine = verdicts[: len(_GENUINE)]
    hydrology = verdicts[len(_GENUINE):]

    assert all(v["kept"] for v in genuine), "genuine LLM papers must be kept"
    assert not any(v["kept"] for v in hydrology), "hydrology papers must be rejected"
    # Every genuine paper outscores every hydrology paper.
    assert min(v["score"] for v in genuine) > max(v["score"] for v in hydrology)
    assert all(v["tier"] == "bm25" for v in verdicts)
    assert "no distinctive topic term" in hydrology[0]["reason"]


def test_genuine_paper_verdict_cites_matched_term():
    batch = _GENUINE + _HYDROLOGY
    verdicts = screen_relevance(batch, _TOPIC)
    assert "large language model" in verdicts[0]["reason"]


def test_small_batch_defers_not_rejects():
    """A handful of candidates is too few for IDF to discriminate -- the
    gate must keep them all and flag cold-start, never blanket-reject."""
    batch = _GENUINE                     # 3 papers -> below the gate floor
    verdicts = screen_relevance(batch, _TOPIC)
    assert all(v["kept"] for v in verdicts)
    assert all(v["tier"] == "cold-start" for v in verdicts)
    assert all("relevance_unverified" in v["reason"] for v in verdicts)


def test_uniform_batch_with_no_distinctive_term_defers():
    """When every candidate carries the topic phrase, nothing is
    *distinctive* within the batch -- keep all, flag cold-start, never
    blanket-reject genuine papers."""
    batch = [
        {"title": f"LLM study {i}",
         "abstract": "A large language model agent for water resources."}
        for i in range(8)
    ]
    verdicts = screen_relevance(batch, _TOPIC)
    assert all(v["kept"] for v in verdicts)
    assert all(v["tier"] == "cold-start" for v in verdicts)
    assert all("no distinctive topic term" in v["reason"] for v in verdicts)


def test_empty_definition_defers_all():
    batch = _GENUINE + _HYDROLOGY
    verdicts = screen_relevance(batch, "")
    assert all(v["kept"] for v in verdicts)
    assert all(v["tier"] == "cold-start" for v in verdicts)


def test_empty_candidate_list():
    assert screen_relevance([], _TOPIC) == []


def test_verdict_shape():
    [verdict] = screen_relevance([_GENUINE[0]], "")
    assert set(verdict) == {"kept", "score", "tier", "reason"}
    assert isinstance(verdict["kept"], bool)
    assert isinstance(verdict["score"], float)
