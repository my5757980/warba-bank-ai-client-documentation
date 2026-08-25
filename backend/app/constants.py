"""Schema-level constants.

These are deliberately NOT settings. They are baked into database CHECK constraints by
the Alembic migration, so a runtime environment variable cannot change them — deriving
a constraint from config would suggest it were tunable when in fact it takes a
migration to move.

The upload limits mirror the Anthropic Files API limits (research.md R8). The settings
in `app.config` default to these same values for the pre-upload check, so the
application declines an oversized file with a clear message before the database ever
has to refuse it.
"""

from __future__ import annotations

# Anthropic Files API: 32 MB per request.
MAX_UPLOAD_BYTES = 33_554_432

# Anthropic Files API: 600 pages per PDF on 1M-context models.
MAX_UPLOAD_PAGES = 600
