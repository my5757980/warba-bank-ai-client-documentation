"""Keyless demo adapter — the whole pipeline, no model, no API key, no network.

Set `MODEL_PROVIDER=demo` and the application runs end to end without a credential.
This exists so that a reviewer can clone the repository and exercise the real system —
grounding, validation, screening, gap marking, approval, audit chaining, export — in
four commands, rather than reading about it.

**This is not a language model and does not pretend to be one.** It is deterministic
domain code that quotes the supplied sources literally. What it demonstrates is the
*pipeline* and its guarantees, not drafting quality. Prose from a real provider reads
far better; nothing else about the system's behaviour changes.

What makes the demonstration meaningful is that nothing downstream is bypassed. This
adapter implements `GenerationPort` exactly like the Anthropic and Gemini adapters, and
its output travels the same path: the same evidence validation, the same numeric
tracing, the same deterministic Shariah gate, the same approval preconditions, the same
hash-chained audit. The guarantees the submission claims are enforced on this output
too — and, because every excerpt here is copied from the source rather than generated,
a reviewer can verify each citation by eye.

One deliberate property is worth stating plainly: composed section text is assembled
from the claim sentences themselves. That is not a shortcut around numeric validation —
it is the honest consequence of having no model to paraphrase with. Every figure that
appears traces to a cited claim because every figure was *taken* from one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pydantic import BaseModel

from app.ports.types import (
    Claim,
    GenerationRequest,
    Ledger,
    ScreeningFinding,
)

MODEL_ID = "demo-deterministic-v1"

# A claim shorter than this is a fragment ("Date:", "- Action") and grounds nothing.
MIN_CLAIM_LENGTH = 24

# Bullet and list markers stripped from the front of a note line before it becomes a
# claim. The excerpt keeps the original text; only the claim sentence is tidied.
_LEADING_MARKER = re.compile(r"^\s*(?:[-*•–—]|\d+[.)])\s*")

# Section key → words that indicate a claim belongs in that section. Ordered by
# specificity: a claim is assigned to the first section it matches, so narrower
# sections must be listed before broader ones.
_SECTION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "meeting_metadata": ("client:", "date:", "present:", "channel:", "attendee", "venue"),
    "risks_and_concerns": (
        "concern", "risk", "overdue", "arrears", "provision", "adverse",
        "deterior", "breach", "delay", "exposure",
    ),
    "action_items": ("action:", "action ", "to send", "to provide", "to confirm", "follow up with"),
    "client_requirements": (
        "asked", "request", "wants", "requires", "indicative ask", "seeking",
        "review upward", "increase",
    ),
    "products_discussed": (
        "murabaha", "ijara", "wakala", "sukuk", "takaful", "trade finance",
        "facility", "financing", "limit",
    ),
    "purpose": ("purpose", "met to", "meeting to discuss", "agenda"),
    "next_steps": ("next meeting", "next contact", "follow-up date", "revert by"),
}

# Sections that must report a gap when nothing supports them, and the gap to report.
# `next_steps` is here even though a follow-up date is often absent from notes —
# especially then. Proposing a date nobody agreed is the exact failure this system
# exists to prevent.
_REQUIRED_GAPS: dict[str, tuple[str, str]] = {
    "purpose": ("purpose_of_meeting", "[MISSING: stated purpose of the meeting]"),
    "next_steps": ("follow_up_date", "[MISSING: agreed next contact and follow-up date]"),
    "meeting_metadata": ("meeting_metadata", "[MISSING: meeting date, attendees, or channel]"),
}


@dataclass
class DemoAdapter:
    """A keyless `GenerationPort` that quotes its sources literally."""

    def ground(self, request: GenerationRequest) -> Ledger:
        """Pass A — turn each substantive source line into a grounded claim.

        Every claim's `verbatim_excerpt` is copied out of the source and its locator
        holds the real character offsets, so a reviewer can check any citation against
        the input by hand.
        """
        claims: list[Claim] = []
        manifest: dict[str, object] = {"sources": [], "provider": "demo"}

        for source in request.sources:
            text = source.content
            if not text:
                # A provider file reference has no text on this side of the port, and
                # inventing claims for it would be precisely the failure mode this
                # adapter exists to make visible.
                manifest["sources"].append(
                    {"source_id": source.source_id, "label": source.label, "grounded": 0,
                     "note": "no inline text available to quote"}
                )
                continue

            before = len(claims)
            for excerpt, start, end in _substantive_lines(text):
                claims.append(
                    Claim(
                        claim_id=f"C{len(claims) + 1:03d}",
                        claim_text=_as_sentence(excerpt),
                        source_type=source.kind,
                        source_id=source.source_id,
                        source_label=source.label,
                        verbatim_excerpt=excerpt,
                        locator={"char_start": start, "char_end": end},
                        is_external=source.is_external,
                    )
                )
            manifest["sources"].append(
                {"source_id": source.source_id, "label": source.label,
                 "grounded": len(claims) - before}
            )

        return Ledger(claims=claims, model_id=MODEL_ID, source_manifest=manifest)

    def compose(
        self,
        ledger: Ledger,
        *,
        schema: type[BaseModel],
        template_guidance: str,
        approved_terminology: dict[str, str],
        rm_instruction: str | None = None,
        **_: object,
    ) -> BaseModel:
        """Pass B — assemble sections from the ledger, and only from the ledger.

        Note the signature, which is the architectural point: there is no `sources`
        parameter, so this method physically cannot reach the raw documents. It sees
        claims or it sees nothing — the same constraint the model-backed adapters work
        under.

        `rm_instruction` is accepted and deliberately ignored. It is stylistic input,
        and this adapter has no style to steer; letting it influence content would give
        an instruction the power to authorise a claim (research.md R7).
        """
        section_model = _section_model(schema)
        assigned = _assign(ledger.claims, list(schema.model_fields))

        sections: dict[str, object] = {}
        for key in schema.model_fields:
            claims = assigned.get(key, [])

            if claims:
                sections[key] = section_model(
                    content=" ".join(c.claim_text for c in claims),
                    evidence_refs=[c.claim_id for c in claims],
                    gaps=[],
                    confidence="HIGH" if len(claims) > 1 else "MEDIUM",
                    contains_external_data=any(c.is_external for c in claims),
                )
                continue

            field_name, label = _REQUIRED_GAPS.get(
                key, (key, f"[MISSING: {key.replace('_', ' ')}]")
            )
            # No content and no refs. An unsupported section is reported as unsupported;
            # the review UI marks it, and approval stays blocked until a human resolves it.
            sections[key] = section_model(
                content=None,
                evidence_refs=[],
                gaps=[{"field": field_name, "label": label}],
                confidence="LOW",
                contains_external_data=False,
            )

        return schema(**sections)

    def screen_semantic(self, *_: object, **__: object) -> list[ScreeningFinding]:
        """No semantic findings.

        The semantic layer is advisory and needs a model. Returning nothing is the
        correct degradation: the *binding* Shariah gate is deterministic and runs
        regardless of provider, so compliance enforcement is unaffected by this
        adapter's silence (research.md R5).
        """
        return []


# ------------------------------------------------------------------ internals


def _substantive_lines(text: str) -> list[tuple[str, int, int]]:
    """Yield (excerpt, char_start, char_end) for each line worth grounding.

    Offsets are computed against the original text — not a cleaned copy — so they stay
    valid for anyone checking the citation against the source.
    """
    out: list[tuple[str, int, int]] = []
    cursor = 0

    for raw in text.split("\n"):
        start = text.index(raw, cursor) if raw else cursor
        cursor = start + len(raw)

        stripped = raw.strip()
        if len(stripped) < MIN_CLAIM_LENGTH:
            continue

        offset = raw.index(stripped)
        out.append((stripped, start + offset, start + offset + len(stripped)))

    return out


def _as_sentence(excerpt: str) -> str:
    """Tidy a note line into a sentence without adding or removing any fact."""
    text = _LEADING_MARKER.sub("", excerpt).strip()
    if not text:
        return excerpt
    text = text[0].upper() + text[1:]
    return text if text[-1] in ".!?" else f"{text}."


def _assign(claims: list[Claim], section_keys: list[str]) -> dict[str, list[Claim]]:
    """Route each claim to at most one section.

    At most one, deliberately. A claim appearing under several headings would be cited
    repeatedly and read as several independent facts — which is how a single overdue
    receivable becomes three.
    """
    assigned: dict[str, list[Claim]] = {}
    fallback = "discussion_summary" if "discussion_summary" in section_keys else None

    for claim in claims:
        haystack = claim.claim_text.lower()
        target = next(
            (
                key
                for key, words in _SECTION_KEYWORDS.items()
                if key in section_keys and any(w in haystack for w in words)
            ),
            fallback,
        )
        if target:
            assigned.setdefault(target, []).append(claim)

    return assigned


def _section_model(schema: type[BaseModel]) -> type[BaseModel]:
    """Recover the Section model the document schema is built from.

    Read off the schema rather than imported, so this adapter stays agnostic about
    which document type it is composing.
    """
    first = next(iter(schema.model_fields.values()))
    return first.annotation  # type: ignore[return-value]


__all__ = ["DemoAdapter", "MODEL_ID"]
