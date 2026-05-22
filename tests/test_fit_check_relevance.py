"""BM25 relevance gate (the no-LLM fit-check tier).

History — two failure modes this gate has had to survive:

  1. The legacy gate (`term_overlap >= 0.1` over independent unigrams) kept
     any paper sharing one common word, so an LLM cluster filled 88% with
     generic hydrology papers.
  2. The first redesign used a "must match a distinctive term" hard gate.
     It over-rejected genuinely on-topic papers in a focused-search batch
     (no single term is in every paper, so the gate always found a
     "distinctive" term and rejected papers using other vocabulary).

The current gate scores every paper with BM25 (IDF self-calibrated on the
batch) and rejects a paper ONLY when the sorted scores show a clear
bimodal split -- a gap where the cluster above out-scores the cluster
below by >= 2x. A focused, uniformly-relevant batch rises smoothly and is
kept whole.
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
    assert "large language model" in terms
    assert "water resources" in terms
    assert "language" in terms


def test_topic_terms_drop_stopwords_and_short_words():
    terms = extract_topic_terms("a study using the large language model")
    assert "study" not in terms
    assert "using" not in terms
    assert "the" not in terms
    assert "large language model" in terms


def test_topic_terms_empty_definition():
    assert extract_topic_terms("") == []


# ---------------------------------------------------------------------------
# bm25_scores -- IDF self-calibration + plural-tolerant matching
# ---------------------------------------------------------------------------

def test_bm25_distinctive_term_outweighs_common_term():
    docs = [
        "water water water large language model",
        "water water water hydrology model",
        "water water water streamflow model",
        "water water water irrigation model",
    ]
    scores, doc_freq = bm25_scores(docs, ["water", "large language model"])
    assert doc_freq["water"] == 4
    assert doc_freq["large language model"] == 1
    assert scores[0] == max(scores)
    assert scores[0] > 2 * scores[1]


def test_bm25_matches_plural_form():
    """Papers write "Large Language Models" (plural); the singular topic
    term must still match it, or document-frequency counts go wrong."""
    docs = [
        "we study large language models for tasks",   # plural
        "a large language model is used here",        # singular
        "hydrology and streamflow only",              # neither
    ]
    _scores, doc_freq = bm25_scores(docs, ["large language model"])
    assert doc_freq["large language model"] == 2     # both plural & singular


def test_bm25_empty_docs():
    scores, doc_freq = bm25_scores([], ["term"])
    assert scores == []
    assert doc_freq == {}


# ---------------------------------------------------------------------------
# screen_relevance -- the gap-split gate
# ---------------------------------------------------------------------------

# 3 genuine LLM x water-resources papers ...
_GENUINE = [
    {
        "title": "Large Language Models as Calibration Agents in Hydrological Modeling",
        "abstract": "We employ a large language model to calibrate a "
                    "hydrological model for streamflow in water resources.",
    },
    {
        "title": "Retrieval-augmented large language models for water resources decisions",
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


def test_contaminated_batch_rejects_the_off_topic_cluster():
    """The core regression: a contaminated batch (a few LLM-water papers
    far out-scoring many generic hydrology papers) shows a clear >=2x gap
    -> the hydrology cluster is rejected, the LLM papers kept."""
    batch = _GENUINE + _HYDROLOGY        # 10 papers
    verdicts = screen_relevance(batch, _TOPIC)

    genuine = verdicts[: len(_GENUINE)]
    hydrology = verdicts[len(_GENUINE):]
    assert all(v["kept"] for v in genuine), "LLM-water papers must be kept"
    assert not any(v["kept"] for v in hydrology), "hydrology papers must be rejected"
    assert min(v["score"] for v in genuine) > max(v["score"] for v in hydrology)
    assert all(v["tier"] == "bm25" for v in verdicts)
    assert "below the relevance gap" in hydrology[0]["reason"]
    assert "above the relevance gap" in genuine[0]["reason"]


def test_focused_uniform_batch_is_kept_whole():
    """A focused search returns an all-relevant batch whose BM25 scores
    rise smoothly -- no adjacent >=2x jump -- so nothing is rejected."""
    batch = [
        {"title": f"Large language model water resources study {i}",
         "abstract": "A large language model applied to water resources "
                     f"and hydrological modeling, case {i}."}
        for i in range(8)
    ]
    verdicts = screen_relevance(batch, _TOPIC)
    assert all(v["kept"] for v in verdicts)
    assert all(v["tier"] == "cold-start" for v in verdicts)
    assert all("relevance_unverified" in v["reason"] for v in verdicts)


def test_small_batch_defers_not_rejects():
    """Fewer than 5 candidates is too few to read a score distribution --
    keep all, flag cold-start, never blanket-reject."""
    verdicts = screen_relevance(_GENUINE, _TOPIC)      # 3 papers
    assert all(v["kept"] for v in verdicts)
    assert all(v["tier"] == "cold-start" for v in verdicts)
    assert all("relevance_unverified" in v["reason"] for v in verdicts)


def test_identical_scores_batch_defers():
    """Every candidate identical -> no gap is possible -> keep all."""
    batch = [
        {"title": "Large language model water resources",
         "abstract": "A large language model for water resources."}
        for _ in range(6)
    ]
    verdicts = screen_relevance(batch, _TOPIC)
    assert all(v["kept"] for v in verdicts)
    assert all(v["tier"] == "cold-start" for v in verdicts)


def test_empty_definition_defers_all():
    verdicts = screen_relevance(_GENUINE + _HYDROLOGY, "")
    assert all(v["kept"] for v in verdicts)
    assert all(v["tier"] == "cold-start" for v in verdicts)


def test_empty_candidate_list():
    assert screen_relevance([], _TOPIC) == []


def test_verdict_shape():
    [verdict] = screen_relevance([_GENUINE[0]], "")
    assert set(verdict) == {"kept", "score", "tier", "reason"}
    assert isinstance(verdict["kept"], bool)
    assert isinstance(verdict["score"], float)
