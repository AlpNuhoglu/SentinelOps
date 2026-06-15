"""Tests for the KVKK/BDDK-compliant Anonymizer."""

from __future__ import annotations

from src.anonymizer.mask import Anonymizer


def test_ip_pseudonymization_is_deterministic() -> None:
    anon = Anonymizer(ip_salt="test-salt")
    first = anon.mask("attack from 192.168.1.10 detected")
    second = anon.mask("retry from 192.168.1.10 again")
    # Same IP -> same pseudonym across lines (temporal correlation preserved).
    token_first = first.split("from ")[1].split(" ")[0]
    token_second = second.split("from ")[1].split(" ")[0]
    assert token_first == token_second
    assert token_first.startswith("IP_")
    assert "192.168.1.10" not in first


def test_distinct_ips_get_distinct_pseudonyms() -> None:
    anon = Anonymizer(ip_salt="test-salt")
    masked = anon.mask("10.0.0.1 and 10.0.0.2")
    tokens = [t for t in masked.split() if t.startswith("IP_")]
    assert len(set(tokens)) == 2


def test_salt_changes_pseudonym() -> None:
    a = Anonymizer(ip_salt="salt-a")
    b = Anonymizer(ip_salt="salt-b")
    assert a.pseudonymize_ip("8.8.8.8") != b.pseudonymize_ip("8.8.8.8")


def test_email_card_iban_uuid_masked() -> None:
    anon = Anonymizer(ip_salt="s")
    line = (
        "user=jane.doe@bank.com.tr card=4242 4242 4242 4242 "
        "iban=TR330006100519786457841326 id=550e8400-e29b-41d4-a716-446655440000"
    )
    masked = anon.mask(line)
    assert "jane.doe@bank.com.tr" not in masked and "[EMAIL]" in masked
    assert "4242 4242 4242 4242" not in masked and "[CARD]" in masked
    assert "TR330006100519786457841326" not in masked and "[IBAN]" in masked
    assert "550e8400" not in masked and "[UUID]" in masked


def test_non_luhn_number_not_masked_as_card() -> None:
    anon = Anonymizer(ip_salt="s")
    # 16 digits that fail Luhn should not be flagged as a card.
    masked = anon.mask("order=1234567812345678 extra")
    # 1234567812345678 fails Luhn -> remains untouched.
    assert "1234567812345678" in masked


def test_timestamps_preserved() -> None:
    anon = Anonymizer(ip_salt="s")
    line = "2026-06-15T08:05:12.003Z ERROR from 10.20.30.40 OOM"
    masked = anon.mask(line)
    # Millisecond-precision timestamp must be untouched.
    assert "2026-06-15T08:05:12.003Z" in masked
