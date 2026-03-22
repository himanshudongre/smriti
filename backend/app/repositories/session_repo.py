"""Repository for Session, Message, and ExtractionResult persistence."""

import uuid

from sqlalchemy.orm import Session

from app.db.models import ExtractionResultModel, MessageModel, SessionModel
from app.domain.enums import SessionStatus


class SessionRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_session(
        self,
        raw_transcript: str,
        title: str | None = None,
        source_tool: str | None = None,
    ) -> SessionModel:
        session = SessionModel(
            raw_transcript=raw_transcript,
            title=title,
            source_tool=source_tool,
            status=SessionStatus.PROCESSING,
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def get_session(self, session_id: uuid.UUID) -> SessionModel | None:
        return self.db.query(SessionModel).filter(SessionModel.id == session_id).first()

    def update_status(self, session_id: uuid.UUID, status: SessionStatus) -> None:
        self.db.query(SessionModel).filter(SessionModel.id == session_id).update(
            {"status": status}
        )
        self.db.commit()

    def create_messages(
        self, session_id: uuid.UUID, messages: list[dict]
    ) -> list[MessageModel]:
        msg_models = [
            MessageModel(session_id=session_id, **msg) for msg in messages
        ]
        self.db.add_all(msg_models)
        self.db.commit()
        return msg_models

    def create_extraction_result(
        self, session_id: uuid.UUID, extraction_data: dict
    ) -> ExtractionResultModel:
        result = ExtractionResultModel(session_id=session_id, **extraction_data)
        self.db.add(result)
        self.db.commit()
        self.db.refresh(result)
        return result

    def get_extraction_result(
        self, session_id: uuid.UUID
    ) -> ExtractionResultModel | None:
        return (
            self.db.query(ExtractionResultModel)
            .filter(ExtractionResultModel.session_id == session_id)
            .first()
        )
