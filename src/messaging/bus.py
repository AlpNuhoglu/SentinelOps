"""In-memory pub/sub bus simulating Kafka / Redis Pub-Sub.

Lightweight, synchronous, and dependency-free so the pipeline can be exercised without
running a real broker. Publishing a message immediately invokes all subscribers of the
topic in registration order.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Callable, DefaultDict, List

# A handler receives the message payload (a single log line).
Handler = Callable[[str], None]


class MessageBus:
    """A minimal synchronous topic-based pub/sub bus."""

    def __init__(self) -> None:
        self._subscribers: DefaultDict[str, List[Handler]] = defaultdict(list)

    def subscribe(self, topic: str, handler: Handler) -> None:
        """Register ``handler`` to receive messages published to ``topic``."""
        self._subscribers[topic].append(handler)

    def publish(self, topic: str, message: str) -> None:
        """Publish ``message`` to ``topic``, invoking each subscriber synchronously."""
        for handler in self._subscribers[topic]:
            handler(message)
