"""Autonomous remediation (self-healing) layer.

Reads the structured JSON action emitted by the LLM and dispatches it to mock
Docker/Kubernetes operations: ROLLBACK, RESTART (pod), or SCALE (horizontal
auto-scaling). Unknown or unsupported actions are safely refused (no-op).

The operations are mocked -- they record intent rather than touching a real cluster --
but the interface mirrors the real Docker SDK / Kubernetes API so it can be swapped in.
Every executed (or refused) action is written to the immutable audit store.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from src.orchestrator.audit import AuditStore


class ActionType(str, Enum):
    """Supported remediation actions."""

    ROLLBACK = "ROLLBACK"
    RESTART = "RESTART"
    SCALE = "SCALE"
    UNKNOWN = "UNKNOWN"


@dataclass
class HealingOutcome:
    """Result of attempting a remediation action."""

    executed: bool
    action: ActionType
    target: Optional[str]
    detail: str


class MockClusterController:
    """Mock Docker/K8s controller. Records operations instead of executing them."""

    def __init__(self) -> None:
        self.operations: List[Dict[str, Any]] = []

    def rollback(self, target: str) -> str:
        self.operations.append({"op": "rollback", "target": target})
        return f"kubectl rollout undo deployment/{target}"

    def restart(self, target: str) -> str:
        self.operations.append({"op": "restart", "target": target})
        return f"kubectl delete pod -l app={target}"

    def scale(self, target: str, replicas: int) -> str:
        self.operations.append(
            {"op": "scale", "target": target, "replicas": replicas}
        )
        return f"kubectl scale deployment/{target} --replicas={replicas}"


class HealingOrchestrator:
    """Dispatches LLM actions to the mock controller and records them in the audit log."""

    def __init__(
        self,
        audit: AuditStore,
        controller: Optional[MockClusterController] = None,
    ) -> None:
        self._audit = audit
        self.controller = controller or MockClusterController()

    def execute(
        self,
        action: Dict[str, Any],
        masked_log: str,
        risk_score: float,
        verdict: str,
    ) -> HealingOutcome:
        """Execute the remediation described by ``action`` and record it immutably."""
        raw_action = str(action.get("action", "UNKNOWN")).upper()
        target = action.get("target")
        outcome = self._dispatch(raw_action, target, action)
        # Persist every decision -- including refusals -- to the immutable audit trail.
        self._audit.append(
            masked_log=masked_log,
            risk_score=risk_score,
            verdict=verdict,
            action={
                "requested": action,
                "executed": outcome.executed,
                "resolved_action": outcome.action.value,
                "detail": outcome.detail,
            },
        )
        return outcome

    def _dispatch(
        self,
        raw_action: str,
        target: Optional[str],
        action: Dict[str, Any],
    ) -> HealingOutcome:
        try:
            action_type = ActionType(raw_action)
        except ValueError:
            return HealingOutcome(
                executed=False,
                action=ActionType.UNKNOWN,
                target=target,
                detail=f"Unsupported action '{raw_action}'; refused.",
            )

        if action_type is ActionType.UNKNOWN or target is None:
            return HealingOutcome(
                executed=False,
                action=ActionType.UNKNOWN,
                target=target,
                detail="Root cause unknown or no target; no remediation performed.",
            )

        if action_type is ActionType.ROLLBACK:
            cmd = self.controller.rollback(target)
        elif action_type is ActionType.RESTART:
            cmd = self.controller.restart(target)
        else:  # SCALE
            replicas = int(action.get("replicas", 5))
            cmd = self.controller.scale(target, replicas)

        return HealingOutcome(
            executed=True,
            action=action_type,
            target=target,
            detail=cmd,
        )
