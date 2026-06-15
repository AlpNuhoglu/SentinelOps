"""KVKK/BDDK-compliant PII masking for log lines.

The :class:`Anonymizer` removes sensitive data (IP addresses, e-mails, credit-card
numbers, IBANs, UUIDs) from log lines *before* they ever reach the LLM. IP addresses
are pseudonymised deterministically (salted SHA-256) so that the temporal correlation
of attacks originating from the same IP is preserved across log lines.

Timestamps are never modified: the millisecond deltas between events are critical for
detecting bot / brute-force attacks.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Dict, Pattern

# --- Regex patterns -----------------------------------------------------------------

# IPv4 with simple octet validation (0-255).
_IPV4 = (
    r"\b(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}"
    r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\b"
)
# IPv6 (compressed and full forms).
_IPV6 = r"\b(?:[A-Fa-f0-9]{1,4}:){2,7}[A-Fa-f0-9]{1,4}\b"

_EMAIL = r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"

# Credit-card-like sequences (13-19 digits, optional spaces/dashes). Luhn-validated below.
_CARD = r"\b(?:\d[ -]?){13,19}\b"

# IBAN: 2 letters + 2 check digits + up to 30 alphanumerics (covers TR and generic).
_IBAN = r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"

_UUID = (
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)

_IPV4_RE: Pattern[str] = re.compile(_IPV4)
_IPV6_RE: Pattern[str] = re.compile(_IPV6)
_EMAIL_RE: Pattern[str] = re.compile(_EMAIL)
_CARD_RE: Pattern[str] = re.compile(_CARD)
_IBAN_RE: Pattern[str] = re.compile(_IBAN)
_UUID_RE: Pattern[str] = re.compile(_UUID)


def _luhn_valid(digits: str) -> bool:
    """Return True if ``digits`` (only the digit characters) passes the Luhn checksum."""
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    parity = len(digits) % 2
    for idx, ch in enumerate(digits):
        d = ord(ch) - 48
        if idx % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


@dataclass
class Anonymizer:
    """Deterministic, offline PII masker.

    Args:
        ip_salt: Secret salt mixed into the IP hash. The same IP always maps to the
            same pseudonym for a given salt, preserving temporal correlation.
    """

    ip_salt: str = "sentinelops-default-salt"
    # Cache so repeated IPs in a session reuse the computed pseudonym (perf + clarity).
    _ip_cache: Dict[str, str] = field(default_factory=dict, repr=False)

    def pseudonymize_ip(self, ip: str) -> str:
        """Map an IP to a deterministic pseudonym like ``IP_a1b2c3d4``."""
        cached = self._ip_cache.get(ip)
        if cached is not None:
            return cached
        digest = hashlib.sha256(f"{self.ip_salt}:{ip}".encode("utf-8")).hexdigest()
        token = f"IP_{digest[:8]}"
        self._ip_cache[ip] = token
        return token

    def mask(self, line: str) -> str:
        """Return ``line`` with all detected PII replaced by safe tokens.

        Timestamps are left untouched. IPs become deterministic pseudonyms; other PII
        is replaced with category tokens.
        """
        # IPs first (before card/IBAN, since dotted quads contain digits).
        line = _IPV4_RE.sub(lambda m: self.pseudonymize_ip(m.group(0)), line)
        line = _IPV6_RE.sub(lambda m: self.pseudonymize_ip(m.group(0)), line)
        line = _EMAIL_RE.sub("[EMAIL]", line)
        line = _UUID_RE.sub("[UUID]", line)
        line = _IBAN_RE.sub("[IBAN]", line)

        def _mask_card(m: "re.Match[str]") -> str:
            raw = m.group(0)
            digits = re.sub(r"\D", "", raw)
            return "[CARD]" if _luhn_valid(digits) else raw

        line = _CARD_RE.sub(_mask_card, line)
        return line
