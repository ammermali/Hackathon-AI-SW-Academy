"""Idempotent CLI helper to ensure demo OrganizationUser profiles exist in local SQLite."""

from __future__ import annotations

import uuid

from operator_copilot.config.settings import get_settings
from operator_copilot.db.database import get_db_manager
from operator_copilot.db.models import OrganizationUser


DEMO_DIRECTORY = [
    {
        "user_id": "operatore_01",
        "display_name": "Maria Rossi",
        "amministrazione": "Comune di Rimini",
        "role": "operatore",
    },
    {
        "user_id": "operatore_02",
        "display_name": "Luca Bianchi",
        "amministrazione": "Comune di Cesena",
        "role": "operatore",
    },
    {
        "user_id": "owner_demo",
        "display_name": "Elena Conti (Owner)",
        "amministrazione": "Ente Pilota PA",
        "role": "owner",
    },
    {
        "user_id": "km_paolo",
        "display_name": "Paolo Ferri (Knowledge Manager)",
        "amministrazione": "Ente Pilota PA",
        "role": "knowledge_manager",
    },
]


def main() -> None:
    settings = get_settings()
    db = get_db_manager(settings)
    inserted = 0
    with db.session() as session:
        for entry in DEMO_DIRECTORY:
            existing = (
                session.query(OrganizationUser)
                .filter_by(tenant_id="default", user_id=entry["user_id"])
                .first()
            )
            if existing is None:
                session.add(
                    OrganizationUser(
                        id=f"orgu_{uuid.uuid4().hex[:12]}",
                        tenant_id="default",
                        user_id=entry["user_id"],
                        display_name=entry["display_name"],
                        amministrazione=entry["amministrazione"],
                        role=entry["role"],
                    )
                )
                inserted += 1
        session.commit()
    print(f"Seeded {inserted} new OrganizationUser records (total directory entries: {len(DEMO_DIRECTORY)}).")


if __name__ == "__main__":
    main()
