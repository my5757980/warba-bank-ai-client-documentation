"""Log redaction filter (FR-042, NFR-SEC-04).

Logs ship wherever they ship. A client's financial position in a log line is a data
incident regardless of how that log is later handled.
"""

from __future__ import annotations

import logging

from app.logging import ContentRedactionFilter, JsonFormatter


def record_with(**extras) -> logging.LogRecord:
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="generation_complete",
        args=(),
        exc_info=None,
    )
    for key, value in extras.items():
        setattr(record, key, value)
    return record


class TestRedaction:
    def test_identifiers_survive(self):
        record = record_with(document_id="abc-123", claim_count=7, duration_ms=2400)
        ContentRedactionFilter().filter(record)

        assert record.document_id == "abc-123"
        assert record.claim_count == 7
        assert record.duration_ms == 2400

    def test_content_field_is_redacted(self):
        record = record_with(section_content="The client reported turnover of KWD 4.5m")
        ContentRedactionFilter().filter(record)
        assert record.section_content == "[redacted]"

    def test_prompt_field_is_redacted(self):
        record = record_with(prompt_text="You are an assistant...")
        ContentRedactionFilter().filter(record)
        assert record.prompt_text == "[redacted]"

    def test_meeting_notes_redacted(self):
        record = record_with(meeting_notes="Met CFO, discussed expansion")
        ContentRedactionFilter().filter(record)
        assert record.meeting_notes == "[redacted]"

    def test_credentials_redacted(self):
        record = record_with(api_key="sk-ant-real-value", password="hunter2")
        ContentRedactionFilter().filter(record)
        assert record.api_key == "[redacted]"
        assert record.password == "[redacted]"

    def test_long_value_redacted_regardless_of_key_name(self):
        """A long free-text value is content whatever it is called."""
        record = record_with(label="x" * 500)
        ContentRedactionFilter().filter(record)
        assert record.label.startswith("[redacted:")

    def test_short_label_survives(self):
        record = record_with(label="CALL_REPORT")
        ContentRedactionFilter().filter(record)
        assert record.label == "CALL_REPORT"


class TestFormatter:
    def test_emits_valid_json(self):
        import json

        output = JsonFormatter().format(record_with(document_id="abc-123"))
        parsed = json.loads(output)

        assert parsed["event"] == "generation_complete"
        assert parsed["level"] == "INFO"
        assert parsed["document_id"] == "abc-123"

    def test_exception_traceback_is_not_emitted(self):
        """Tracebacks can carry local variables, and locals here carry client data."""
        import json

        try:
            raise ValueError("turnover was KWD 4,500,000")
        except ValueError:
            import sys

            record = logging.LogRecord(
                name="test",
                level=logging.ERROR,
                pathname=__file__,
                lineno=1,
                msg="generation_failed",
                args=(),
                exc_info=sys.exc_info(),
            )

        parsed = json.loads(JsonFormatter().format(record))

        assert parsed["error_type"] == "ValueError"
        assert "traceback" not in parsed
        assert "Traceback" not in json.dumps(parsed)
