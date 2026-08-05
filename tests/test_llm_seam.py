"""
The LLM seam.

These tests are the reason `llm.py` exists as a separate file. They prove:

  * with no key configured, nothing crashes and every caller gets a real
    fallback (the offline guarantee the product is built on);
  * with a fake provider substituted, the SAME code paths produce
    model-generated output - so swapping Claude for GPT or a local Llama is a
    change to one file and nothing else.

No network is touched. `FakeLLM` is a stand-in for a provider, exactly like a
mock database in any other test suite.
"""

from __future__ import annotations

import json

import pytest

from ai import evaluator, llm as llm_module, question_gen
from ai.llm import LLM, LLMError, extract_json


class FakeLLM(LLM):
    """A provider that returns canned JSON instead of calling anyone."""

    def __init__(self, payload):
        super().__init__(provider="offline")
        self.provider = "fake"          # makes `available` True
        self.model = "fake-model-1"
        self.payload = payload
        self.calls: list[tuple[str, str]] = []

    def complete(self, system, user, *, max_tokens=1200, temperature=0.4):
        self.calls.append((system, user))
        if isinstance(self.payload, Exception):
            raise self.payload
        return json.dumps(self.payload)


@pytest.fixture(autouse=True)
def _reset_llm_singleton():
    llm_module.reset_llm()
    yield
    llm_module.reset_llm()


# --------------------------------------------------------------------------- #
# Offline behaviour
# --------------------------------------------------------------------------- #


def test_no_key_means_offline_not_broken(monkeypatch):
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "auto")

    client = LLM()
    assert client.provider == "offline"
    assert client.available is False


def test_complete_raises_offline_but_complete_json_returns_the_fallback():
    client = LLM(provider="offline")
    with pytest.raises(LLMError):
        client.complete("system", "user")
    assert client.complete_json("system", "user", fallback={"ok": True}) == {"ok": True}


def test_a_named_provider_without_its_key_degrades_instead_of_crashing(monkeypatch):
    """Starting the API server must not fail because someone typo'd a key name."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    client = LLM(provider="anthropic")
    assert client.provider == "offline"


def test_auto_detection_prefers_anthropic_then_openai(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "auto")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert LLM().provider == "openai"

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    assert LLM().provider == "anthropic"


# --------------------------------------------------------------------------- #
# JSON extraction - models wrap JSON in prose and fences
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("raw", [
    '{"a": 1}',
    '```json\n{"a": 1}\n```',
    'Sure! Here is the JSON you asked for:\n{"a": 1}\nLet me know if that helps.',
    '```\n{"a": 1}\n```',
])
def test_extract_json_survives_the_usual_model_wrapping(raw):
    assert extract_json(raw) == {"a": 1}


def test_extract_json_returns_none_for_prose():
    assert extract_json("I'd rather not answer that.") is None
    assert extract_json("") is None


def test_unparseable_output_falls_back_rather_than_exploding():
    class Prose(FakeLLM):
        def complete(self, system, user, **kwargs):
            return "Sorry, I cannot help with that."

    client = Prose({})
    assert client.complete_json("s", "u", fallback=["safe"]) == ["safe"]


# --------------------------------------------------------------------------- #
# The swap actually works end to end
# --------------------------------------------------------------------------- #


def test_question_generation_uses_the_llm_when_one_is_available(monkeypatch):
    fake = FakeLLM([
        {"category": "technical", "skill": "React", "difficulty": "hard",
         "text": "Why does useEffect run twice in StrictMode?",
         "expected_points": ["double-invoking", "development only", "cleanup"]},
        {"category": "resume", "skill": None, "difficulty": "medium",
         "text": "Tell me about MediTrack.", "expected_points": ["architecture"]},
    ])
    monkeypatch.setattr(question_gen, "get_llm", lambda: fake)

    questions = question_gen.generate_questions(None, "frontend-developer", count=2)

    assert [q["source"] for q in questions] == ["llm", "llm"]
    assert questions[0]["text"].startswith("Why does useEffect")
    assert fake.calls, "the provider should have been called"


def test_evaluation_uses_the_llm_scores_when_available(monkeypatch):
    fake = FakeLLM({
        "scores": {"relevance": 9, "depth": 8, "structure": 9, "specificity": 7, "clarity": 8},
        "reasons": {d: "because" for d in evaluator.DIMENSIONS},
        "covered_points": ["indexing"], "missed_points": [],
        "strengths": ["Named the exact index"], "improvements": ["Mention the trade-off"],
        "model_answer": "A strong answer would...",
    })
    monkeypatch.setattr(evaluator, "get_llm", lambda: fake)

    result = evaluator.evaluate_answer(
        {"text": "How do you speed up a slow query?", "category": "technical",
         "expected_points": ["EXPLAIN", "index"]},
        "I would run EXPLAIN, look at the plan, and add a composite index on the filter columns.",
        duration_sec=30,
    )

    assert result["source"] == "llm"
    assert result["scores"]["relevance"] == 9.0
    assert result["overall"] >= 80


def test_a_provider_failure_falls_back_to_the_heuristic_scorer(monkeypatch):
    monkeypatch.setattr(evaluator, "get_llm", lambda: FakeLLM(RuntimeError("429 rate limited")))

    result = evaluator.evaluate_answer(
        {"text": "Explain indexing.", "category": "technical", "expected_points": ["b-tree"]},
        "An index is a b-tree that lets the database find rows without scanning the table.",
    )

    assert result["source"] == "heuristic"
    assert result["overall"] > 0  # an interview must not stop because a vendor is down
