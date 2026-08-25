"""Seed synthetic data (task T077).

Run with: ``python -m app.fixtures.seed``

Every client written here is fictitious, and the database enforces that independently:
`client.is_synthetic` carries a CHECK constraint a non-synthetic row cannot satisfy
(Constitution Principle VII).

The seed is idempotent — re-running updates nothing and inserts nothing that already
exists — so a demo can be reset without dropping the database.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import User
from app.auth.security import hash_password
from app.clients.models import Client, ClientRecord
from app.db import get_session_factory
from app.enums import KycStatus, RecordType, SourceSystem, UserRole

logger = logging.getLogger(__name__)

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "synthetic"

# Demo password. Acceptable only because every account is fictitious and the prototype
# holds no real data; a real deployment provisions accounts through the bank's IAM.
DEMO_PASSWORD = "Demo!2026"

TEAM_CORPORATE = "11111111-1111-1111-1111-111111111111"

DEMO_USERS = [
    {
        "email": "sara.rm@warba.demo",
        "full_name": "Sara Al-Mutairi",
        "role": UserRole.RM,
        "team_id": TEAM_CORPORATE,
    },
    {
        "email": "khalid.rm@warba.demo",
        "full_name": "Khalid Al-Rashid",
        "role": UserRole.RM,
        "team_id": TEAM_CORPORATE,
    },
    {
        "email": "omar.lead@warba.demo",
        "full_name": "Omar Al-Fahad",
        "role": UserRole.TEAM_LEAD,
        "team_id": TEAM_CORPORATE,
    },
    {
        "email": "layla.compliance@warba.demo",
        "full_name": "Layla Al-Otaibi",
        "role": UserRole.COMPLIANCE,
        "team_id": None,
    },
    {
        "email": "yusuf.shariah@warba.demo",
        "full_name": "Yusuf Al-Hamad",
        "role": UserRole.SHARIAH_REVIEWER,
        "team_id": None,
    },
]


def seed_users(db: Session) -> dict[str, User]:
    """Create the four demo roles.

    Only the RM role can approve. The Team Lead is seeded specifically so the demo can
    show that a *more senior* user still cannot approve — accountability under
    Principle III does not travel up the hierarchy.
    """
    users: dict[str, User] = {}

    for spec in DEMO_USERS:
        existing = db.execute(select(User).where(User.email == spec["email"])).scalar_one_or_none()

        if existing:
            users[spec["email"]] = existing
            continue

        user = User(
            email=spec["email"],
            full_name=spec["full_name"],
            password_hash=hash_password(DEMO_PASSWORD),
            role=spec["role"],
            team_id=spec["team_id"],
            is_active=True,
        )
        db.add(user)
        db.flush()
        users[spec["email"]] = user
        logger.info("seeded_user", extra={"role": spec["role"].value})

    return users


def seed_clients(db: Session, users: dict[str, User]) -> int:
    """Load synthetic clients and their records."""
    path = FIXTURES / "clients" / "clients.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))

    created = 0

    for spec in data["clients"]:
        existing = db.execute(
            select(Client).where(Client.client_reference == spec["client_reference"])
        ).scalar_one_or_none()
        if existing:
            continue

        owner = users.get(spec["owning_rm"])
        if owner is None:
            logger.warning(
                "skipping_client_unknown_rm", extra={"reference": spec["client_reference"]}
            )
            continue

        client = Client(
            client_reference=spec["client_reference"],
            legal_name=spec["legal_name"],
            trade_name=spec.get("trade_name"),
            commercial_registration=spec.get("commercial_registration"),
            sector=spec["sector"],
            incorporation_date=_as_date(spec.get("incorporation_date")),
            relationship_since=_as_date(spec.get("relationship_since")),
            owning_rm_id=owner.id,
            kyc_status=KycStatus(spec["kyc_status"]),
            is_synthetic=True,  # The CHECK constraint permits nothing else.
        )
        db.add(client)
        db.flush()

        for record in spec.get("records", []):
            db.add(
                ClientRecord(
                    client_id=client.id,
                    record_type=RecordType(record["record_type"]),
                    source_system=SourceSystem(record["source_system"]),
                    payload=record["payload"],
                    effective_date=_as_date(record.get("effective_date")),
                    is_external=record.get("is_external", False),
                )
            )

        created += 1

    return created


def _as_date(value: str | date | None) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(value)


def main() -> None:
    from app.documents.templates import register_all_templates
    from app.logging import configure_logging

    configure_logging()

    session_factory = get_session_factory()
    with session_factory() as db:
        users = seed_users(db)
        clients = seed_clients(db, users)
        templates = register_all_templates(db)
        db.commit()

    print(f"Seeded {len(users)} users, {clients} synthetic clients, {templates} templates.")
    print(f"Demo password for every account: {DEMO_PASSWORD}")
    print("All client data is synthetic (Constitution Principle VII).")


if __name__ == "__main__":
    main()
