"""Versioned Shariah vocabulary loader (FR-019).

Terminology comes from a reviewable YAML artifact, never from model invention. The
loaded version is recorded on every ScreeningResult so a past decision stays
reproducible after the vocabulary is amended.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml

Severity = Literal["BLOCK", "FLAG"]

VOCABULARY_PATH = Path(__file__).resolve().parents[2] / "config" / "vocabulary.yaml"


@dataclass(frozen=True)
class ProhibitedTerm:
    term: str
    severity: Severity
    rule_id: str
    rationale: str

    @property
    def blocks(self) -> bool:
        return self.severity == "BLOCK"


@dataclass(frozen=True)
class ApprovedStructure:
    name: str
    description: str
    typical_use: str


@dataclass(frozen=True)
class Vocabulary:
    """The loaded, immutable screening vocabulary."""

    version: str
    approved_structures: tuple[ApprovedStructure, ...]
    approved_terminology: dict[str, str]
    prohibited_terms: tuple[ProhibitedTerm, ...]
    prohibited_sectors: tuple[ProhibitedTerm, ...]
    prohibited_decisioning: tuple[ProhibitedTerm, ...] = field(default_factory=tuple)

    @property
    def structure_names(self) -> set[str]:
        return {s.name.lower() for s in self.approved_structures}

    def shariah_terms(self) -> tuple[ProhibitedTerm, ...]:
        """Terms screened on every document type."""
        return self.prohibited_terms + self.prohibited_sectors

    def decisioning_terms(self) -> tuple[ProhibitedTerm, ...]:
        """Terms screened only where the document type excludes decisioning (DT3)."""
        return self.prohibited_decisioning

    def maps_to_approved_structure(self, text: str) -> bool:
        """Whether the text references at least one approved Islamic structure."""
        lowered = text.lower()
        return any(name in lowered for name in self.structure_names)


def _parse_terms(raw: list[dict] | None, key: str = "term") -> tuple[ProhibitedTerm, ...]:
    if not raw:
        return ()
    return tuple(
        ProhibitedTerm(
            term=item[key],
            severity=item.get("severity", "BLOCK"),
            rule_id=item["rule_id"],
            rationale=item.get("rationale", ""),
        )
        for item in raw
    )


def load_vocabulary(path: Path | None = None) -> Vocabulary:
    """Load and validate the vocabulary file."""
    target = path or VOCABULARY_PATH
    if not target.exists():
        raise FileNotFoundError(
            f"Shariah vocabulary not found at {target}. Screening cannot run without it, "
            "and the system fails closed rather than screening against nothing."
        )

    data = yaml.safe_load(target.read_text(encoding="utf-8"))

    version = data.get("version")
    if not version:
        raise ValueError(f"{target} is missing a `version`. Screening results must record it.")

    return Vocabulary(
        version=version,
        approved_structures=tuple(
            ApprovedStructure(
                name=s["name"],
                description=s.get("description", ""),
                typical_use=s.get("typical_use", ""),
            )
            for s in data.get("approved_structures", [])
        ),
        approved_terminology=data.get("approved_terminology", {}),
        prohibited_terms=_parse_terms(data.get("prohibited_terms")),
        prohibited_sectors=_parse_terms(data.get("prohibited_sectors"), key="name"),
        prohibited_decisioning=_parse_terms(data.get("prohibited_decisioning")),
    )


@lru_cache
def get_vocabulary() -> Vocabulary:
    """Cached vocabulary accessor.

    Cached because screening runs on every generation and the file does not change at
    runtime. A vocabulary that changed mid-process would desynchronise the recorded
    `vocabulary_version` from the terms actually applied.
    """
    return load_vocabulary()
