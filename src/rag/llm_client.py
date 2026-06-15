"""Local OpenAI-compatible chat client.

The client talks to a local ``/v1/chat/completions`` endpoint (the built-in mock server
or a local Ollama/vLLM instance). It never calls an external cloud provider.

For tests and the default ``mock`` mode it can also invoke the mock decision function
in-process, avoiding the need to spin up a network server.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List

import httpx

from src.rag.mock_llm import _decide


@dataclass
class LLMResponse:
    """Parsed LLM reply."""

    raw_content: str
    data: Dict[str, Any]


def _parse_choice(payload: Dict[str, Any]) -> LLMResponse:
    content = payload["choices"][0]["message"]["content"]
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        data = {"action": "UNKNOWN", "reason": "Kök neden bilinmiyor"}
    return LLMResponse(raw_content=content, data=data)


class LLMClient:
    """OpenAI-compatible chat client with an in-process mock fast-path."""

    def __init__(
        self,
        mode: str = "mock",
        base_url: str = "http://127.0.0.1:8088/v1",
        model: str = "qwen2.5-7b-instruct",
        timeout: float = 30.0,
    ) -> None:
        self.mode = mode
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def chat(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        """Send a chat request and return the parsed response."""
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        if self.mode == "mock":
            # In-process deterministic decision; no network required.
            prompt = f"{system_prompt}\n{user_prompt}"
            decision = _decide(prompt)
            content = json.dumps(decision, ensure_ascii=False)
            return LLMResponse(raw_content=content, data=decision)

        resp = httpx.post(
            f"{self.base_url}/chat/completions",
            json={"model": self.model, "messages": messages, "temperature": 0.0},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return _parse_choice(resp.json())
