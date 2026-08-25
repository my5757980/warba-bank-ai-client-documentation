"""Audit hash chain (task T030).

The chain is what makes the audit trail tamper-*evident* rather than merely
tamper-discouraged. The database privilege stops the application from rewriting
history; these tests cover detection of anyone who bypasses the application.
"""

from __future__ import annotations

from app.audit.chain import (
    GENESIS_HASH,
    canonical_json,
    compute_event_hash,
    content_hash,
)


class TestCanonicalJson:
    def test_key_order_does_not_change_output(self):
        """Without sorted keys, two identical payloads could hash differently."""
        a = canonical_json({"b": 2, "a": 1})
        b = canonical_json({"a": 1, "b": 2})
        assert a == b

    def test_no_incidental_whitespace(self):
        assert " " not in canonical_json({"a": 1, "b": 2})

    def test_nested_structures_are_ordered(self):
        a = canonical_json({"outer": {"z": 1, "a": 2}})
        b = canonical_json({"outer": {"a": 2, "z": 1}})
        assert a == b

    def test_non_ascii_preserved(self):
        assert "Ijara" in canonical_json({"structure": "Ijara"})


class TestEventHash:
    def test_hash_is_deterministic(self):
        payload = {"event_type": "DOCUMENT_APPROVED", "actor_id": "u1"}
        assert compute_event_hash(GENESIS_HASH, payload) == compute_event_hash(
            GENESIS_HASH, payload
        )

    def test_hash_is_sha256_hex(self):
        digest = compute_event_hash(None, {"a": 1})
        assert len(digest) == 64
        assert all(c in "0123456789abcdef" for c in digest)

    def test_payload_change_changes_hash(self):
        base = compute_event_hash(GENESIS_HASH, {"actor_id": "u1"})
        altered = compute_event_hash(GENESIS_HASH, {"actor_id": "u2"})
        assert base != altered

    def test_prev_hash_change_changes_hash(self):
        """This is the property that makes the chain a chain."""
        payload = {"event_type": "DOCUMENT_APPROVED"}
        first = compute_event_hash("a" * 64, payload)
        second = compute_event_hash("b" * 64, payload)
        assert first != second

    def test_none_prev_hash_uses_genesis(self):
        payload = {"event_type": "GENERATION_STARTED"}
        assert compute_event_hash(None, payload) == compute_event_hash(GENESIS_HASH, payload)


class TestChainPropagation:
    def test_tampering_breaks_every_downstream_link(self):
        """Altering one historical event invalidates all events after it.

        This is why the chain detects tampering rather than merely recording it: an
        attacker must rewrite every subsequent event, and the verifier walks from the
        genesis anchor.
        """
        e1 = compute_event_hash(GENESIS_HASH, {"seq": 1, "detail": "original"})
        e2 = compute_event_hash(e1, {"seq": 2})
        e3 = compute_event_hash(e2, {"seq": 3})

        tampered_e1 = compute_event_hash(GENESIS_HASH, {"seq": 1, "detail": "tampered"})
        tampered_e2 = compute_event_hash(tampered_e1, {"seq": 2})
        tampered_e3 = compute_event_hash(tampered_e2, {"seq": 3})

        assert tampered_e1 != e1
        assert tampered_e2 != e2
        assert tampered_e3 != e3

    def test_intact_chain_recomputes_identically(self):
        payloads = [{"seq": i} for i in range(1, 6)]
        prev = GENESIS_HASH
        hashes = []
        for payload in payloads:
            digest = compute_event_hash(prev, payload)
            hashes.append(digest)
            prev = digest

        prev = GENESIS_HASH
        for payload, expected in zip(payloads, hashes, strict=True):
            assert compute_event_hash(prev, payload) == expected
            prev = expected


class TestContentHash:
    def test_content_hash_is_stable_across_key_order(self):
        a = content_hash({"section_a": "text", "section_b": "more"})
        b = content_hash({"section_b": "more", "section_a": "text"})
        assert a == b

    def test_content_change_changes_hash(self):
        """Approval binds to a content hash — edited content must not match."""
        approved = content_hash({"summary": "Client requested KWD 500,000."})
        edited = content_hash({"summary": "Client requested KWD 900,000."})
        assert approved != edited
