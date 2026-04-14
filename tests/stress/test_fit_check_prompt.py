from __future__ import annotations


def test_fit_check_emit_200_candidates_stays_under_context_budget():
    from research_hub.fit_check import emit_prompt

    candidates = [
        {
            "title": f"Stress Paper {i}",
            "doi": f"10.9999/paper-{i}",
            "authors": ["Stress Author"],
            "year": 2024,
            "abstract": "Synthetic abstract for stress testing the fit-check prompt builder. " * 10,
        }
        for i in range(200)
    ]

    prompt = emit_prompt("stress", candidates, definition="Test cluster for stress run.")

    assert len(prompt) < 200_000
    for i in range(200):
        assert f"### {i + 1}." in prompt
    assert '"scores":' in prompt
