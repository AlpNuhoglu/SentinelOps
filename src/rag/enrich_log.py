"""EnrichLog: Two-Step Inference RAG service.

Stage 1 (lightweight): a pure threshold comparison on the model's risk score. Logs
below the threshold are marked "Safe (Normal)" and never reach the LLM/RAG path. This
stage is intentionally trivial so it stays well under the 10 ms/log latency budget.

Stage 2 (EnrichLog RAG): for logs above the threshold, retrieve the top-k most similar
historical error logs (corpus-specific) and system architecture docs (sample-specific),
build an enriched prompt, and ask the local LLM for a Root-Cause Analysis (RCA) and a
structured remediation action.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from src.rag.llm_client import LLMClient, LLMResponse
from src.rag.vector_store import RetrievedDocument, VectorStore

SYSTEM_PROMPT = (
    "You are an SRE root-cause analysis assistant for a bank. You receive an anomalous, "
    "PII-masked log line and retrieved context (historical incidents and architecture "
    "docs). Determine the root cause and a remediation action. STRICT RULE: if the "
    "retrieved context contains no clear reference matching this log, DO NOT invent a "
    'solution. Instead return exactly {"action": "UNKNOWN", "reason": "Kök neden '
    'bilinmiyor"}. Respond with a single JSON object only.'
)


class Verdict(str, Enum):
    """Classification outcome of the two-step pipeline."""

    SAFE = "SAFE"
    ANOMALY = "ANOMALY"


@dataclass
class EnrichmentResult:
    """Outcome of processing a single log line."""

    verdict: Verdict
    risk_score: float
    masked_log: str
    stage: int
    rca: Optional[str] = None
    action: Optional[Dict[str, Any]] = None
    retrieved: List[RetrievedDocument] = field(default_factory=list)


class EnrichLogService:
    """Implements the two-step inference + RAG enrichment pipeline."""

    def __init__(
        self,
        vector_store: VectorStore,
        llm_client: LLMClient,
        risk_threshold: float = 0.35,
        top_k: int = 3,
    ) -> None:
        self._store = vector_store
        self._llm = llm_client
        self._threshold = risk_threshold
        self._top_k = top_k

    def _build_prompt(
        self, masked_log: str, retrieved: List[RetrievedDocument]
    ) -> str:
        context_blocks: List[str] = []
        for item in retrieved:
            context_blocks.append(
                f"[source={item.document.source} id={item.document.doc_id} "
                f"score={item.score:.3f}]\n{item.document.text}"
            )
        context = "\n\n".join(context_blocks) if context_blocks else "(none)"
        return (
            f"Anomalous log line (PII-masked):\n{masked_log}\n\n"
            f"Retrieved context:\n{context}\n\n"
            "Return a single JSON object with keys: action, target (if any), rca, "
            "confidence. If no proven remediation reference matches, return "
            '{"action": "UNKNOWN", "reason": "Kök neden bilinmiyor"}.'
        )

    def process(self, masked_log: str, risk_score: float) -> EnrichmentResult:
        """Run the two-step pipeline for a single PII-masked log line.

        Args:
            masked_log: The log line *after* PII masking.
            risk_score: Anomaly probability in ``[0, 1]`` from the model.
        """
        # --- Stage 1: lightweight threshold filter (sub-millisecond) ---
        if risk_score < self._threshold:
            return EnrichmentResult(
                verdict=Verdict.SAFE,
                risk_score=risk_score,
                masked_log=masked_log,
                stage=1,
            )

        # --- Stage 2: EnrichLog RAG ---
        retrieved = self._store.query(masked_log, top_k=self._top_k)
        prompt = self._build_prompt(masked_log, retrieved)
        response: LLMResponse = self._llm.chat(SYSTEM_PROMPT, prompt)
        action = response.data
        rca = action.get("rca") or action.get("reason")
        return EnrichmentResult(
            verdict=Verdict.ANOMALY,
            risk_score=risk_score,
            masked_log=masked_log,
            stage=2,
            rca=rca,
            action=action,
            retrieved=retrieved,
        )
