"""Document template registry (tasks T086, T089).

This module is where NFR-SCA-01 is realised. Adding a document type requires:

  1. a YAML file in ``config/templates/``
  2. a prompt artifact directory in ``config/prompts/``
  3. a Pydantic schema registered in ``SCHEMA_REGISTRY`` below

and no change to the generation engine, the validators, the screening layer, or the
audit layer. If a new document type ever requires touching one of those, that is a
design regression worth raising rather than working around.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.documents.models import DocumentTemplate
from app.documents.schemas.call_report import CallReportSections
from app.documents.schemas.client_profile import ClientProfileSections
from app.enums import DocumentType

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "config" / "templates"

# The one place a document type is bound to its structured-output schema.
SCHEMA_REGISTRY: dict[DocumentType, type[BaseModel]] = {
    DocumentType.CALL_REPORT: CallReportSections,
    DocumentType.CLIENT_PROFILE: ClientProfileSections,
}


class TemplateNotRegisteredError(LookupError):
    """A document type has a template row but no schema, or vice versa."""


def schema_for(document_type: DocumentType) -> type[BaseModel]:
    """The structured-output schema for a document type."""
    schema = SCHEMA_REGISTRY.get(document_type)
    if schema is None:
        raise TemplateNotRegisteredError(
            f"No composition schema registered for {document_type.value}. "
            "Add it to SCHEMA_REGISTRY in app/documents/templates.py."
        )
    return schema


def load_template_file(path: Path) -> dict:
    """Read and validate one template YAML file."""
    spec = yaml.safe_load(path.read_text(encoding="utf-8"))

    for required in ("document_type", "version", "display_name", "sections"):
        if required not in spec:
            raise ValueError(f"{path.name} is missing required key '{required}'.")

    if not spec["sections"]:
        raise ValueError(f"{path.name} defines no sections.")

    keys = [s["key"] for s in spec["sections"]]
    if len(keys) != len(set(keys)):
        raise ValueError(f"{path.name} has duplicate section keys.")

    return spec


def register_template(db: Session, path: Path) -> DocumentTemplate | None:
    """Insert a template row from a YAML file.

    Returns None when the exact `(document_type, version)` already exists. Templates
    are immutable once used by a document — changing one means publishing a new
    version, so an approved document always links to the definition that produced it.
    """
    spec = load_template_file(path)
    document_type = DocumentType(spec["document_type"])

    existing = db.execute(
        select(DocumentTemplate).where(
            DocumentTemplate.document_type == document_type,
            DocumentTemplate.version == spec["version"],
        )
    ).scalar_one_or_none()

    if existing:
        return None

    template = DocumentTemplate(
        document_type=document_type,
        version=spec["version"],
        display_name=spec["display_name"],
        section_definitions=spec["sections"],
        required_inputs=spec.get("required_inputs", []),
        screening_profile=spec.get("screening_profile", "standard"),
        prompt_template_ref=spec["prompt_template_ref"],
        is_active=True,
    )
    db.add(template)
    db.flush()

    logger.info(
        "template_registered",
        extra={"document_type": document_type.value, "template_version": spec["version"]},
    )
    return template


def register_all_templates(db: Session) -> int:
    """Register every template file that has a registered schema.

    A template file without a schema is skipped with a warning rather than failing the
    seed: it means the document type is half-built, and the right response is to say so
    clearly, not to abort seeding everything else.
    """
    count = 0

    for path in sorted(TEMPLATE_DIR.glob("*.yaml")):
        spec = load_template_file(path)
        document_type = DocumentType(spec["document_type"])

        if document_type not in SCHEMA_REGISTRY:
            logger.warning(
                "template_skipped_no_schema",
                extra={"document_type": document_type.value, "file": path.name},
            )
            continue

        if register_template(db, path) is not None:
            count += 1

    return count


def active_template(db: Session, document_type: DocumentType) -> DocumentTemplate:
    """The current active template for a document type — highest version wins."""
    template = db.execute(
        select(DocumentTemplate)
        .where(
            DocumentTemplate.document_type == document_type,
            DocumentTemplate.is_active.is_(True),
        )
        .order_by(DocumentTemplate.version.desc())
        .limit(1)
    ).scalar_one_or_none()

    if template is None:
        raise TemplateNotRegisteredError(
            f"No active template for {document_type.value}. Run: python -m app.fixtures.seed"
        )

    return template
