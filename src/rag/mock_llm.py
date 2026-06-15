"""Local OpenAI-compatible mock LLM endpoint.

Exposes ``POST /v1/chat/completions`` and returns a *deterministic* response derived
from the prompt content. This keeps all inference local (no external cloud calls) and
makes tests reproducible.

Zero-hallucination rule: if the prompt's retrieved context contains no clear match for
the log, the model returns ``{"action": "UNKNOWN", "reason": "Kök neden bilinmiyor"}``
instead of inventing a fix.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from fastapi import FastAPI
from pydantic import BaseModel

UNKNOWN_REASON = "Kök neden bilinmiyor"


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    temperature: float = 0.0


def _decide(prompt: str) -> Dict[str, Any]:
    """Map prompt content to a deterministic RCA + structured action.

    The decision is driven purely by signals present in the retrieved context, so the
    model never fabricates a remediation that the documents do not support.
    """
    text = prompt.lower()
    has_context = "retrieved context" in text and "proven remediation" in text

    if has_context and "oomkilled" in text and "payment-v2" in text:
        return {
            "action": "ROLLBACK",
            "target": "payment-v2",
            "rca": (
                "payment-v2 exhausted JVM heap under sustained load (unbounded ledger "
                "cache), triggering OOMKilled and CrashLoopBackOff. History INC-2026-0042 "
                "and the architecture doc confirm rollback as the proven remediation."
            ),
            "confidence": 0.92,
        }
    if has_context and "readiness probe failed" in text and "oomkilled" not in text:
        return {
            "action": "RESTART",
            "target": "affected-pod",
            "rca": (
                "Transient readiness-probe failure during slow startup. History "
                "INC-2025-0904 confirms a pod restart as the proven remediation."
            ),
            "confidence": 0.80,
        }
    # No supporting reference -> refuse to hallucinate.
    return {"action": "UNKNOWN", "reason": UNKNOWN_REASON}


def create_app() -> FastAPI:
    """Build the FastAPI app exposing the OpenAI-compatible endpoint."""
    app = FastAPI(title="SentinelOps Mock LLM")

    @app.get("/health")
    def health() -> Dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/chat/completions")
    def chat_completions(req: ChatCompletionRequest) -> Dict[str, Any]:
        prompt = "\n".join(m.content for m in req.messages)
        decision = _decide(prompt)
        content = json.dumps(decision, ensure_ascii=False)
        return {
            "id": "chatcmpl-mock",
            "object": "chat.completion",
            "model": req.model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
        }

    return app


app = create_app()
