"""End-to-end test: an Out-of-Memory log triggers anomaly -> RAG -> mock pod action."""

from __future__ import annotations

from pathlib import Path

from src.anonymizer.mask import Anonymizer
from src.orchestrator.audit import AuditStore
from src.orchestrator.healing import ActionType, HealingOrchestrator
from src.rag.embeddings import HashEmbedder
from src.rag.enrich_log import EnrichLogService, Verdict
from src.rag.llm_client import LLMClient
from src.rag.vector_store import VectorStore, load_documents_from_dir

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _build_service() -> EnrichLogService:
    store = VectorStore(HashEmbedder(dim=256))
    store.add(
        load_documents_from_dir(PROJECT_ROOT / "data" / "error_corpus", "error_corpus")
    )
    store.add(
        load_documents_from_dir(PROJECT_ROOT / "data" / "system_docs", "system_docs")
    )
    return EnrichLogService(store, LLMClient(mode="mock"), risk_threshold=0.35)


def test_oom_flow_triggers_rollback_and_audits(tmp_path: Path) -> None:
    anon = Anonymizer(ip_salt="test")
    service = _build_service()
    audit = AuditStore(tmp_path / "audit.db")
    healer = HealingOrchestrator(audit)

    oom_log = (
        "2026-06-15T08:05:12.003Z ERROR service=payment-v2 node=10.20.30.40 "
        'msg="java.lang.OutOfMemoryError: Java heap space" key=OOM_KILL '
        'msg="container terminated reason=OOMKilled"'
    )
    masked = anon.mask(oom_log)
    assert "10.20.30.40" not in masked  # PII masked before any inference

    # High risk score from the (mock) detector triggers Stage 2.
    result = service.process(masked, risk_score=0.97)
    assert result.verdict is Verdict.ANOMALY
    assert result.stage == 2
    assert len(result.retrieved) > 0  # RAG found supporting documents

    assert result.action is not None
    outcome = healer.execute(result.action, masked, 0.97, result.verdict.value)

    # Mock remediation actually fired.
    assert outcome.executed is True
    assert outcome.action is ActionType.ROLLBACK
    assert outcome.target == "payment-v2"
    assert any(op["op"] == "rollback" for op in healer.controller.operations)

    # Immutable audit recorded the action and the chain is intact.
    assert audit.count() == 1
    assert audit.verify_chain() is True
    record = audit.all_records()[0]
    assert record.action["resolved_action"] == "ROLLBACK"
    audit.close()


def test_audit_chain_detects_tampering(tmp_path: Path) -> None:
    db = tmp_path / "audit.db"
    audit = AuditStore(db)
    audit.append("log a key=A", 0.1, "SAFE", {"action": "NONE"})
    audit.append("log b key=OOM_KILL", 0.9, "ANOMALY", {"action": "ROLLBACK"})
    assert audit.verify_chain() is True
    audit.close()

    # Tamper with a past record directly in the DB.
    import sqlite3

    conn = sqlite3.connect(db)
    conn.execute("UPDATE audit_log SET masked_log = ? WHERE seq = ?", ("hacked", 1))
    conn.commit()
    conn.close()

    reopened = AuditStore(db)
    assert reopened.verify_chain() is False  # tampering detected
    reopened.close()
