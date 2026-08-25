"""Generation orchestration (research.md R3).

The pipeline, in order:

    assemble context → Pass A (ground) → build ledger → Pass B (compose)
        → deterministic validation → deterministic screening → persist

Every stage after grounding can refuse. When any of them does, **no document is
returned** — the failure is recorded in the audit trail and an error is raised
(FR-037, NFR-SEC-07). There is no partial-draft path, because a partially validated
document shown to an RM is a document the RM will reasonably assume was validated.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.audit.chain import content_hash
from app.audit.recorder import AuditRecorder
from app.clients.models import Client
from app.documents.models import (
    Document,
    DocumentSection,
    DocumentTemplate,
    DocumentVersion,
)
from app.documents.state_machine import TransitionError, can_edit
from app.documents.validators import SectionDraft, ValidationResult, validate_composition
from app.enums import (
    Confidence,
    DocumentStatus,
    ScreeningLayer,
    ScreeningOutcome,
    VersionOrigin,
)
from app.evidence.ledger_builder import load_ledger, persist_ledger
from app.ports.generation_port import GenerationPort
from app.ports.types import GenerationError, GenerationRequest, GroundingScope, Ledger, Source
from app.screening.deterministic import Finding, has_blocking_findings, screen_sections
from app.screening.models import ScreeningResult
from app.screening.vocabulary import get_vocabulary

logger = logging.getLogger(__name__)

# Document types whose output must contain no ratings, recommendations, or pricing.
_DECISIONING_EXCLUDED = {"CREDIT_MEMO_NARRATIVE"}


class ScreeningBlockedError(Exception):
    """Deterministic screening refused to let this draft be displayed."""

    def __init__(self, findings: list[Finding], vocabulary_version: str) -> None:
        super().__init__("Draft blocked by Shariah screening.")
        self.findings = findings
        self.vocabulary_version = vocabulary_version


class ValidationFailedError(Exception):
    """Deterministic validation rejected the composed document."""

    def __init__(self, result: ValidationResult) -> None:
        super().__init__("Composed document failed validation.")
        self.result = result


@dataclass
class GenerationOutcome:
    document: Document
    version: DocumentVersion
    sections: list[DocumentSection]
    screening: ScreeningResult


class GenerationService:
    """Orchestrates two-pass generation.

    Depends on `GenerationPort`, never on a vendor SDK — which is what lets every
    integration test run this exact pipeline against a deterministic stub.
    """

    def __init__(self, db: Session, port: GenerationPort | None = None) -> None:
        """`port` is optional because `edit_section` needs no model call.

        An RM edit re-screens and re-versions but composes nothing, so requiring a
        configured provider for it would make editing fail whenever generation is
        unavailable — the wrong coupling for the one operation that is purely human.
        """
        self._db = db
        self._port = port
        self._audit = AuditRecorder(db)

    @property
    def port(self) -> GenerationPort:
        """The generation port, or a clear error if this service was built without one."""
        if self._port is None:
            raise GenerationError(
                "This operation requires the generation service, which is not configured.",
                stage="configuration",
                retryable=False,
            )
        return self._port

    # -----------------------------------------------------------------
    # Generate
    # -----------------------------------------------------------------

    def generate(
        self,
        *,
        client: Client,
        template: DocumentTemplate,
        schema: type[BaseModel],
        sources: list[Source],
        actor_id: uuid.UUID,
        actor_name: str,
        rm_instruction: str | None = None,
    ) -> GenerationOutcome:
        """Run the full pipeline. Fails closed at every stage after grounding."""
        document = Document(
            client_id=client.id,
            document_type=template.document_type,
            template_id=template.id,
            created_by=actor_id,
            status=DocumentStatus.DRAFT,
            # PENDING_REVIEW by column default. Never set to CLEARED anywhere.
        )
        self._db.add(document)
        self._db.flush()

        prompt_version = template.prompt_template_ref.rsplit("/", 1)[-1] or "v1.0.0"
        source_ids = [s.source_id for s in sources]

        self._audit.generation_started(
            actor_id=actor_id,
            actor_name=actor_name,
            client_reference=client.client_reference,
            document_id=document.id,
            document_type=template.document_type.value,
            input_source_ids=source_ids,
            template_version=template.version,
            prompt_version=prompt_version,
            detail={"source_count": len(sources)},
        )

        # `BaseException` deliberately, not just the domain errors.
        #
        # FR-039 requires every failure to reach the audit trail. Catching only the
        # domain errors meant an unexpected exception — an SDK signature change, a
        # driver fault — rolled the transaction back and took the audit record with it,
        # so the loudest failures were the ones that left no trace. The bare re-raise
        # keeps the caller's behaviour identical; only the recording changes.
        try:
            ledger = self._ground(document, client, template, sources)
            drafts = self._compose(ledger, template, schema, rm_instruction)
            validation = self._validate(drafts, ledger, template)
            findings = self._screen(drafts, template)
        except BaseException as exc:
            self._record_failure(
                exc,
                document=document,
                client=client,
                actor_id=actor_id,
                actor_name=actor_name,
                template=template,
                prompt_version=prompt_version,
                source_ids=source_ids,
            )
            # Re-raised after the audit write. The caller returns an error and no
            # document; nothing partial is ever surfaced.
            raise

        outcome = self._persist(
            document=document,
            template=template,
            ledger=ledger,
            validation=validation,
            findings=findings,
            actor_id=actor_id,
            prompt_version=prompt_version,
            origin=VersionOrigin.GENERATED,
        )

        self._audit.generation_completed(
            actor_id=actor_id,
            actor_name=actor_name,
            client_reference=client.client_reference,
            document_id=document.id,
            version_id=outcome.version.id,
            document_type=template.document_type.value,
            input_source_ids=source_ids,
            model_id=ledger.model_id,
            model_version=ledger.model_id,
            prompt_version=prompt_version,
            template_version=template.version,
            output_hash=outcome.version.content_hash,
            detail={
                "claim_count": len(ledger.claims),
                "section_count": len(outcome.sections),
                "gap_count": len(outcome.version.unresolved_gaps),
                "screening_outcome": outcome.screening.outcome.value,
            },
        )

        return outcome

    # -----------------------------------------------------------------
    # Edit & regenerate
    # -----------------------------------------------------------------

    def edit_section(
        self,
        *,
        document: Document,
        version: DocumentVersion,
        section_key: str,
        expected_hash: str,
        content: str | None,
        resolved_gaps: list[dict],
        actor_id: uuid.UUID,
        actor_name: str,
        client_reference: str,
    ) -> GenerationOutcome:
        """Apply an RM edit, creating a new `RM_EDITED` version.

        The edit is screened like any generated content: an RM can introduce prohibited
        terminology just as a model can, and a gate that only ran on machine output
        would be a gate with an obvious hole in it.
        """
        can_edit(document)
        self._require_current_hash(version, expected_hash)

        drafts = self._drafts_from_version(version)
        resolved_keys = {(g["field"]) for g in resolved_gaps}

        for draft in drafts:
            if draft.section_key != section_key:
                continue
            draft.content = content
            draft.is_rm_edited = True
            for gap in draft.gaps:
                if gap.get("field") in resolved_keys:
                    note = next(
                        (g["resolution_note"] for g in resolved_gaps if g["field"] == gap["field"]),
                        None,
                    )
                    gap["resolved"] = True
                    gap["resolution_note"] = note

        template = document.template
        findings = self._screen(drafts, template)

        outcome = self._persist(
            document=document,
            template=template,
            ledger=Ledger(model_id=version.model_id or ""),
            validation=ValidationResult(sections=drafts),
            findings=findings,
            actor_id=actor_id,
            prompt_version=version.prompt_version,
            origin=VersionOrigin.RM_EDITED,
            existing_ledger_id=version.ledger_id,
        )

        # The edited section is flagged so the audit trail can distinguish RM prose
        # from AI prose (FR-022).
        for section in outcome.sections:
            if section.section_key == section_key:
                section.is_rm_edited = True

        self._audit.section_edited(
            actor_id=actor_id,
            actor_name=actor_name,
            client_reference=client_reference,
            document_id=document.id,
            version_id=outcome.version.id,
            document_type=template.document_type.value,
            template_version=template.version,
            prompt_version=version.prompt_version,
            output_hash=outcome.version.content_hash,
            detail={
                "section_key": section_key,
                "gaps_resolved": len(resolved_gaps),
                "previous_version": version.version_number,
            },
        )

        return outcome

    def regenerate_section(
        self,
        *,
        document: Document,
        version: DocumentVersion,
        section_key: str,
        schema: type[BaseModel],
        actor_id: uuid.UUID,
        actor_name: str,
        client_reference: str,
        instruction: str | None = None,
    ) -> GenerationOutcome:
        """Regenerate one section against the existing ledger (FR-023).

        Two properties matter here:

        1. **The ledger is reused, never rebuilt.** Re-grounding would let the evidence
           change underneath sections the RM has already accepted.
        2. **Accepted work elsewhere survives.** Only the named section is replaced; if
           the regenerated section fails validation or screening, the prior version
           stands and nothing is lost.
        """
        can_edit(document)

        if version.ledger_id is None:
            raise GenerationError(
                "This document has no evidence ledger to regenerate from.",
                stage="regeneration",
                retryable=False,
            )

        template = document.template
        ledger = load_ledger(self._db, version.ledger_id)

        recomposed = self._compose(ledger, template, schema, instruction)
        replacement = next((d for d in recomposed if d.section_key == section_key), None)

        if replacement is None:
            raise GenerationError(
                f"The regenerated document did not contain section '{section_key}'.",
                stage="regeneration",
                retryable=True,
            )

        drafts = self._drafts_from_version(version)
        merged = [replacement if d.section_key == section_key else d for d in drafts]

        validation = self._validate(merged, ledger, template)
        findings = self._screen(validation.sections, template)

        outcome = self._persist(
            document=document,
            template=template,
            ledger=ledger,
            validation=validation,
            findings=findings,
            actor_id=actor_id,
            prompt_version=version.prompt_version,
            origin=VersionOrigin.REGENERATED_SECTION,
            existing_ledger_id=version.ledger_id,
        )

        self._audit.section_regenerated(
            actor_id=actor_id,
            actor_name=actor_name,
            client_reference=client_reference,
            document_id=document.id,
            version_id=outcome.version.id,
            document_type=template.document_type.value,
            model_id=ledger.model_id,
            template_version=template.version,
            prompt_version=version.prompt_version,
            output_hash=outcome.version.content_hash,
            detail={
                "section_key": section_key,
                "had_instruction": instruction is not None,
                "previous_version": version.version_number,
            },
        )

        return outcome

    @staticmethod
    def _require_current_hash(version: DocumentVersion, expected_hash: str) -> None:
        """Optimistic concurrency (FR-040).

        Two RMs — or one RM in two tabs — must not silently overwrite each other. The
        caller supplies the hash of the version it read; a mismatch means the document
        moved and the write is refused rather than applied on top of unseen changes.
        """
        if expected_hash != version.content_hash:
            raise TransitionError(
                "This document changed since you opened it. Reload to see the current "
                "version before making further changes.",
                code="STALE_CONTENT_HASH",
                detail={"expected": version.content_hash},
            )

    @staticmethod
    def _drafts_from_version(version: DocumentVersion) -> list[SectionDraft]:
        """Rebuild section drafts from a persisted version."""
        return [
            SectionDraft(
                section_key=s.section_key,
                title=s.title,
                ordinal=s.ordinal,
                content=s.content,
                evidence_refs=list(s.evidence_refs or []),
                gaps=[dict(g) for g in (s.gaps or [])],
                confidence=s.confidence.value,
                contains_external_data=s.contains_external_data,
                is_rm_edited=s.is_rm_edited,
            )
            for s in version.sections
        ]

    # -----------------------------------------------------------------
    # Pipeline stages
    # -----------------------------------------------------------------

    def _ground(
        self,
        document: Document,
        client: Client,
        template: DocumentTemplate,
        sources: list[Source],
    ) -> Ledger:
        """Pass A."""
        request = GenerationRequest(
            document_id=document.id,
            document_type=template.document_type.value,
            client_reference=client.client_reference,
            sources=sources,
            scope=GroundingScope(
                document_type=template.document_type.value,
                client_reference=client.client_reference,
                section_titles=[s["title"] for s in template.section_definitions],
            ),
        )
        return self.port.ground(request)

    def _compose(
        self,
        ledger: Ledger,
        template: DocumentTemplate,
        schema: type[BaseModel],
        rm_instruction: str | None,
    ) -> list[SectionDraft]:
        """Pass B. Receives the ledger; raw sources are not in scope here."""
        vocabulary = get_vocabulary()

        composed = self.port.compose(
            ledger,
            schema=schema,
            template_guidance=self._render_guidance(template),
            approved_terminology=vocabulary.approved_terminology,
            rm_instruction=rm_instruction,
        )

        return self._to_drafts(composed, template)

    def _validate(
        self,
        drafts: list[SectionDraft],
        ledger: Ledger,
        template: DocumentTemplate,
    ) -> ValidationResult:
        """Deterministic validation. Raises on a fatal issue."""
        result = validate_composition(drafts, ledger.claims, template.required_section_keys)

        if result.failed:
            fatal = [
                i
                for i in result.issues
                if i.code in {"UNTRACEABLE_NUMERIC", "MISSING_REQUIRED_SECTION"}
            ]
            logger.warning(
                "validation_failed",
                extra={"issue_codes": [i.code for i in fatal], "issue_count": len(fatal)},
            )
            raise ValidationFailedError(result)

        return result

    def _screen(self, drafts: list[SectionDraft], template: DocumentTemplate) -> list[Finding]:
        """Deterministic screening. Raises before the draft can be displayed."""
        vocabulary = get_vocabulary()
        include_decisioning = template.document_type.value in _DECISIONING_EXCLUDED

        findings = screen_sections(
            {d.section_key: d.content for d in drafts},
            vocabulary=vocabulary,
            include_decisioning=include_decisioning,
        )

        if has_blocking_findings(findings):
            raise ScreeningBlockedError(findings, vocabulary.version)

        return findings

    # -----------------------------------------------------------------
    # Persistence
    # -----------------------------------------------------------------

    def _persist(
        self,
        *,
        document: Document,
        template: DocumentTemplate,
        ledger: Ledger,
        validation: ValidationResult,
        findings: list[Finding],
        actor_id: uuid.UUID,
        prompt_version: str,
        origin: VersionOrigin,
        existing_ledger_id: uuid.UUID | None = None,
    ) -> GenerationOutcome:
        # A regeneration reuses the ledger the original generation produced. Writing a
        # new one would let the evidence shift underneath a document the RM has already
        # partly accepted, so an earlier version's citations could come to mean
        # something different.
        if existing_ledger_id is not None:
            ledger_id = existing_ledger_id
        else:
            ledger_id = persist_ledger(self._db, document.id, ledger).id

        next_number = len(document.versions) + 1
        hash_value = content_hash({d.section_key: d.content or "" for d in validation.sections})

        version = DocumentVersion(
            document_id=document.id,
            version_number=next_number,
            origin=origin,
            created_by=actor_id,
            content_hash=hash_value,
            model_id=ledger.model_id,
            template_version=template.version,
            prompt_version=prompt_version,
            ledger_id=ledger_id,
        )
        self._db.add(version)
        self._db.flush()

        sections = []
        for draft in validation.sections:
            section = DocumentSection(
                version_id=version.id,
                section_key=draft.section_key,
                title=draft.title,
                ordinal=draft.ordinal,
                content=draft.content,
                evidence_refs=draft.evidence_refs,
                gaps=draft.gaps,
                confidence=Confidence(draft.confidence),
                contains_external_data=draft.contains_external_data,
                is_rm_edited=draft.is_rm_edited,
            )
            self._db.add(section)
            sections.append(section)

        screening = ScreeningResult(
            version_id=version.id,
            layer=ScreeningLayer.DETERMINISTIC,
            outcome=ScreeningOutcome.FLAGGED if findings else ScreeningOutcome.PASS,
            findings=[f.to_dict() for f in findings],
            vocabulary_version=get_vocabulary().version,
        )
        self._db.add(screening)

        document.current_version_id = version.id
        self._db.flush()

        return GenerationOutcome(
            document=document, version=version, sections=sections, screening=screening
        )

    # -----------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------

    def _record_failure(
        self,
        exc: BaseException,
        *,
        document: Document,
        client: Client,
        actor_id: uuid.UUID,
        actor_name: str,
        template: DocumentTemplate,
        prompt_version: str,
        source_ids: list[str],
    ) -> None:
        """Record the failure in its **own** transaction.

        FR-037 and FR-039 pull in opposite directions here, and both must hold:

          * fail closed — the half-built document must NOT survive;
          * audit everything — the failure record MUST survive.

        Writing both in one transaction satisfies only one of them: rolling back to
        discard the document also discards the audit event. So the failed transaction is
        rolled back first, and the audit record is then written and committed on a fresh
        session. The document disappears; the record of its attempt does not.

        Only codes, counts, and rule identifiers are recorded — the payload guard would
        reject anything else, and it should.
        """
        from app.db import get_session_factory

        # Read every value out of the ORM objects BEFORE rolling back. A rollback
        # expires them, and a later attribute access would try to refresh a row that no
        # longer exists — turning the audit write into a second, more confusing failure.
        context = {
            "actor_id": actor_id,
            "actor_name": actor_name,
            "client_reference": client.client_reference,
            "document_id": document.id,
            "document_type": template.document_type.value,
            "input_source_ids": source_ids,
            "template_version": template.version,
            "prompt_version": prompt_version,
        }

        # Discard the half-built document. Whatever happens next, no partial document
        # reaches the RM.
        try:
            self._db.rollback()
        except Exception:  # pragma: no cover - defensive
            logger.exception("rollback_failed_during_failure_audit")

        try:
            with get_session_factory()() as audit_session:
                self._write_failure_event(AuditRecorder(audit_session), exc, context)
                audit_session.commit()
        except Exception:  # pragma: no cover - never mask the original failure
            # A failure to audit must not replace the error the RM needs to see.
            logger.exception("failure_audit_write_failed")

    @staticmethod
    def _write_failure_event(
        audit: AuditRecorder,
        exc: BaseException,
        common: dict,
    ) -> None:
        """Write the appropriate failure event for this exception type."""

        if isinstance(exc, ScreeningBlockedError):
            audit.screening_blocked(
                **common,
                detail={
                    "rule_ids": sorted({f.rule_id for f in exc.findings if f.blocks}),
                    "finding_count": len(exc.findings),
                    "vocabulary_version": exc.vocabulary_version,
                },
            )
            return

        if isinstance(exc, ValidationFailedError):
            audit.generation_failed(
                **common,
                detail={
                    "stage": "validation",
                    "issue_codes": sorted({i.code for i in exc.result.issues}),
                    "issue_count": len(exc.result.issues),
                },
            )
            return

        audit.generation_failed(
            **common,
            detail={
                "stage": getattr(exc, "stage", "unknown"),
                "retryable": getattr(exc, "retryable", False),
                "error_type": type(exc).__name__,
            },
        )

    @staticmethod
    def _render_guidance(template: DocumentTemplate) -> str:
        lines = [f"Draft a {template.display_name} with these sections:\n"]
        for definition in template.section_definitions:
            lines.append(f"- {definition['title']} (key: {definition['key']})")
            if definition.get("guidance"):
                lines.append(f"  {definition['guidance']}")
        return "\n".join(lines)

    @staticmethod
    def _to_drafts(composed: BaseModel, template: DocumentTemplate) -> list[SectionDraft]:
        """Convert the validated schema object into section drafts.

        The composed model exposes one attribute per section key, each carrying
        content, evidence_refs, gaps, and confidence.
        """
        drafts: list[SectionDraft] = []

        for ordinal, definition in enumerate(template.section_definitions):
            key = definition["key"]
            section = getattr(composed, key, None)
            if section is None:
                # Absent from the response. Coverage validation turns this into a
                # missing-section issue rather than silently dropping it.
                continue

            drafts.append(
                SectionDraft(
                    section_key=key,
                    title=definition["title"],
                    ordinal=ordinal,
                    content=getattr(section, "content", None),
                    evidence_refs=list(getattr(section, "evidence_refs", []) or []),
                    gaps=[
                        g if isinstance(g, dict) else g.model_dump()
                        for g in (getattr(section, "gaps", []) or [])
                    ],
                    confidence=str(getattr(section, "confidence", "MEDIUM")),
                    contains_external_data=bool(getattr(section, "contains_external_data", False)),
                )
            )

        return drafts
