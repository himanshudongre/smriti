"""Repository for ContextPack persistence."""

import uuid

from sqlalchemy.orm import Session

from app.db.models import ContextPackModel


class ContextPackRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_pack(
        self, session_id: uuid.UUID, target_tool: str, content: str, format: str = "markdown"
    ) -> ContextPackModel:
        pack = ContextPackModel(
            session_id=session_id,
            target_tool=target_tool,
            content=content,
            format=format,
        )
        self.db.add(pack)
        self.db.commit()
        self.db.refresh(pack)
        return pack

    def get_pack(self, pack_id: uuid.UUID) -> ContextPackModel | None:
        return self.db.query(ContextPackModel).filter(ContextPackModel.id == pack_id).first()

    def get_packs_for_session(self, session_id: uuid.UUID) -> list[ContextPackModel]:
        return (
            self.db.query(ContextPackModel)
            .filter(ContextPackModel.session_id == session_id)
            .all()
        )
