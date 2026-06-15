"""Immutable, hash-chained SQLite audit log for BDDK compliance.

Every action is appended as a new row. Rows are never updated or deleted (the store
exposes no such methods), and each row stores the SHA-256 hash of the previous row
together with its own content hash, forming a tamper-evident chain: altering any past
record breaks the chain and is detectable via :meth:`verify_chain`.

All SQL uses parameterized queries.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

GENESIS_HASH = "0" * 64


@dataclass
class AuditRecord:
    """A single immutable audit entry."""

    seq: int
    timestamp: float
    masked_log: str
    risk_score: float
    verdict: str
    action: Dict[str, Any]
    prev_hash: str
    record_hash: str


def _compute_hash(
    seq: int,
    timestamp: float,
    masked_log: str,
    risk_score: float,
    verdict: str,
    action: Dict[str, Any],
    prev_hash: str,
) -> str:
    payload = json.dumps(
        {
            "seq": seq,
            "timestamp": timestamp,
            "masked_log": masked_log,
            "risk_score": risk_score,
            "verdict": verdict,
            "action": action,
            "prev_hash": prev_hash,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class AuditStore:
    """Append-only, hash-chained SQLite audit store."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_log (
                seq         INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   REAL    NOT NULL,
                masked_log  TEXT    NOT NULL,
                risk_score  REAL    NOT NULL,
                verdict     TEXT    NOT NULL,
                action      TEXT    NOT NULL,
                prev_hash   TEXT    NOT NULL,
                record_hash TEXT    NOT NULL
            )
            """
        )
        self._conn.commit()

    def _last_hash(self) -> str:
        cur = self._conn.execute(
            "SELECT record_hash FROM audit_log ORDER BY seq DESC LIMIT 1"
        )
        row = cur.fetchone()
        return str(row[0]) if row else GENESIS_HASH

    def append(
        self,
        masked_log: str,
        risk_score: float,
        verdict: str,
        action: Dict[str, Any],
    ) -> AuditRecord:
        """Append a new immutable audit record and return it."""
        prev_hash = self._last_hash()
        cur = self._conn.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM audit_log")
        seq = int(cur.fetchone()[0])
        timestamp = time.time()
        record_hash = _compute_hash(
            seq, timestamp, masked_log, risk_score, verdict, action, prev_hash
        )
        self._conn.execute(
            """
            INSERT INTO audit_log
                (seq, timestamp, masked_log, risk_score, verdict, action,
                 prev_hash, record_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                seq,
                timestamp,
                masked_log,
                risk_score,
                verdict,
                json.dumps(action, ensure_ascii=False),
                prev_hash,
                record_hash,
            ),
        )
        self._conn.commit()
        return AuditRecord(
            seq=seq,
            timestamp=timestamp,
            masked_log=masked_log,
            risk_score=risk_score,
            verdict=verdict,
            action=action,
            prev_hash=prev_hash,
            record_hash=record_hash,
        )

    def all_records(self) -> List[AuditRecord]:
        """Return all audit records in sequence order."""
        cur = self._conn.execute(
            """
            SELECT seq, timestamp, masked_log, risk_score, verdict, action,
                   prev_hash, record_hash
            FROM audit_log ORDER BY seq ASC
            """
        )
        records: List[AuditRecord] = []
        for row in cur.fetchall():
            records.append(
                AuditRecord(
                    seq=int(row[0]),
                    timestamp=float(row[1]),
                    masked_log=str(row[2]),
                    risk_score=float(row[3]),
                    verdict=str(row[4]),
                    action=json.loads(row[5]),
                    prev_hash=str(row[6]),
                    record_hash=str(row[7]),
                )
            )
        return records

    def verify_chain(self) -> bool:
        """Return True if the hash chain is intact (no record was tampered with)."""
        prev_hash = GENESIS_HASH
        for rec in self.all_records():
            expected = _compute_hash(
                rec.seq,
                rec.timestamp,
                rec.masked_log,
                rec.risk_score,
                rec.verdict,
                rec.action,
                prev_hash,
            )
            if rec.prev_hash != prev_hash or rec.record_hash != expected:
                return False
            prev_hash = rec.record_hash
        return True

    def count(self) -> int:
        """Return the number of audit records."""
        cur = self._conn.execute("SELECT COUNT(*) FROM audit_log")
        return int(cur.fetchone()[0])

    def close(self) -> None:
        """Close the underlying database connection."""
        self._conn.close()
