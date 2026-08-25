"""Audit payload guard (task T031).

FR-042 / NFR-SEC-04: audit records carry identifiers and counts, never document
content, client-bearing prompt text, or credentials. The guard raises rather than
sanitising — silently stripping a field would let the caller believe it had recorded
something it had not.
"""

from __future__ import annotations

import pytest

from app.audit.recorder import AuditPayloadError, _payload_guard


class TestAcceptsIdentifiers:
    def test_plain_identifiers_pass(self):
        _payload_guard(
            {
                "section_count": 8,
                "gap_count": 2,
                "template_id": "b3f1c2d4",
                "duration_ms": 24_500,
            }
        )

    def test_nested_identifiers_pass(self):
        _payload_guard({"screening": {"finding_count": 1, "rule_ids": ["SH-002"]}})

    def test_list_of_identifiers_passes(self):
        _payload_guard({"source_ids": ["a1", "b2", "c3"]})

    def test_short_status_string_passes(self):
        _payload_guard({"outcome": "BLOCKED"})


class TestRejectsContent:
    @pytest.mark.parametrize(
        "key",
        [
            "content",
            "section_content",
            "prompt",
            "prompt_text",
            "meeting_notes",
            "notes",
            "body",
            "verbatim_excerpt",
        ],
    )
    def test_content_bearing_keys_rejected(self, key: str):
        with pytest.raises(AuditPayloadError):
            _payload_guard({key: "anything"})

    def test_long_value_treated_as_content(self):
        """A long free-text value is document content whatever the key is called."""
        with pytest.raises(AuditPayloadError, match="content"):
            _payload_guard({"summary_label": "x" * 500})

    def test_nested_content_rejected(self):
        with pytest.raises(AuditPayloadError):
            _payload_guard({"section": {"content": "the drafted paragraph"}})

    def test_content_inside_list_rejected(self):
        with pytest.raises(AuditPayloadError):
            _payload_guard({"sections": [{"content": "drafted text"}]})


class TestRejectsCredentials:
    @pytest.mark.parametrize(
        "key",
        ["api_key", "apiKey", "ANTHROPIC_API_KEY", "password", "secret", "token", "authorization"],
    )
    def test_credential_keys_rejected(self, key: str):
        with pytest.raises(AuditPayloadError):
            _payload_guard({key: "value"})

    def test_case_insensitive_detection(self):
        with pytest.raises(AuditPayloadError):
            _payload_guard({"Prompt_Text": "value"})


class TestErrorMessageIsActionable:
    def test_message_names_the_offending_path(self):
        with pytest.raises(AuditPayloadError, match=r"detail\.screening\.content"):
            _payload_guard({"screening": {"content": "text"}})

    def test_message_cites_the_requirement(self):
        with pytest.raises(AuditPayloadError, match="FR-042"):
            _payload_guard({"content": "text"})
