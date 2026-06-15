"""Tests for the two-step EnrichLog inference + RAG pipeline."""

from __future__ import annotations

import time
from typing import List

from src.rag.embeddings import HashEmbedder
from src.rag.enrich_log import EnrichLogService, Verdict
from src.rag.llm_client import LLMClient, LLMResponse
from src.rag.vector_store import Document, VectorStore


class SpyLLM(LLMClient):
    """LLM client that records whether it was called."""

    def __init__(self) -> None:
        super().__init__(mode="mock")
        self.calls = 0

    def chat(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        self.calls += 1
        return super().chat(system_prompt, user_prompt)


def _store_with_docs() -> VectorStore:
    store = VectorStore(HashEmbedder(dim=256))
    store.add(
        [
            Document(
                doc_id="oom.md",
                source="error_corpus",
                text=(
                    "OOMKilled payment-v2 java.lang.OutOfMemoryError proven remediation "
                    "ROLLBACK target payment-v2 INC-2026-0042"
                ),
            )
        ]
    )
    return store


def test_stage1_skips_llm_for_low_risk() -> None:
    spy = SpyLLM()
    service = EnrichLogService(_store_with_docs(), spy, risk_threshold=0.35)
    result = service.process("normal log line key=RESP_SENT", risk_score=0.10)
    assert result.verdict is Verdict.SAFE
    assert result.stage == 1
    assert spy.calls == 0  # LLM must NOT be called for safe logs


def test_stage1_latency_under_10ms() -> None:
    spy = SpyLLM()
    service = EnrichLogService(_store_with_docs(), spy, risk_threshold=0.35)
    timings: List[float] = []
    for _ in range(200):
        start = time.perf_counter()
        service.process("normal log key=AUTH_OK", risk_score=0.05)
        timings.append((time.perf_counter() - start) * 1000.0)
    # Stage-1 must comfortably beat the 10 ms/log budget.
    assert max(timings) < 10.0


def test_stage2_invokes_llm_for_high_risk() -> None:
    spy = SpyLLM()
    service = EnrichLogService(_store_with_docs(), spy, risk_threshold=0.35)
    result = service.process(
        "ERROR java.lang.OutOfMemoryError container OOMKilled payment-v2 key=OOM_KILL",
        risk_score=0.95,
    )
    assert result.verdict is Verdict.ANOMALY
    assert result.stage == 2
    assert spy.calls == 1
    assert result.action is not None
    assert result.action["action"] == "ROLLBACK"
    assert result.action["target"] == "payment-v2"


def test_zero_hallucination_without_matching_context() -> None:
    spy = SpyLLM()
    # Empty store -> no supporting reference.
    empty = VectorStore(HashEmbedder(dim=256))
    service = EnrichLogService(empty, spy, risk_threshold=0.35)
    result = service.process("mysterious unknown anomaly key=WEIRD", risk_score=0.9)
    assert result.action is not None
    assert result.action["action"] == "UNKNOWN"
    assert result.action["reason"] == "Kök neden bilinmiyor"
