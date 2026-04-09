"""Tests for SQLAlchemy ORM models."""

import uuid

import pytest
from sqlalchemy import select

from app.models.chat import ChatMessage, ChatSession
from app.models.document import Document
from app.models.user import User


class TestUserModel:
    async def test_create_user(self, db_session):
        user = User(id=uuid.uuid4(), username="admin", email="admin@corp.com")
        db_session.add(user)
        await db_session.commit()

        result = await db_session.execute(select(User))
        users = result.scalars().all()
        assert len(users) == 1
        assert users[0].username == "admin"
        assert users[0].email == "admin@corp.com"

    async def test_username_required(self, db_session):
        """Username should not be nullable."""
        from sqlalchemy.exc import IntegrityError

        user = User(id=uuid.uuid4(), username=None)
        db_session.add(user)
        with pytest.raises(IntegrityError):
            await db_session.commit()


class TestDocumentModel:
    async def test_create_document(self, db_session):
        doc = Document(
            id=uuid.uuid4(),
            filename="security_policy.pdf",
            file_type="pdf",
            file_size=102400,
            chunk_count=10,
            status="ready",
        )
        db_session.add(doc)
        await db_session.commit()

        result = await db_session.execute(select(Document))
        docs = result.scalars().all()
        assert len(docs) == 1
        assert docs[0].filename == "security_policy.pdf"
        assert docs[0].chunk_count == 10
        assert docs[0].status == "ready"

    async def test_document_default_status(self, db_session):
        doc = Document(
            id=uuid.uuid4(),
            filename="test.txt",
            file_type="txt",
            file_size=100,
        )
        db_session.add(doc)
        await db_session.commit()
        await db_session.refresh(doc)

        assert doc.status == "processing"
        assert doc.chunk_count == 0


class TestChatSessionModel:
    async def test_create_session(self, db_session):
        session = ChatSession(id=uuid.uuid4(), title="Security Q&A")
        db_session.add(session)
        await db_session.commit()

        result = await db_session.execute(select(ChatSession))
        sessions = result.scalars().all()
        assert len(sessions) == 1
        assert sessions[0].title == "Security Q&A"

    async def test_session_nullable_title(self, db_session):
        session = ChatSession(id=uuid.uuid4(), title=None)
        db_session.add(session)
        await db_session.commit()

        result = await db_session.execute(select(ChatSession))
        assert result.scalar_one().title is None


class TestChatMessageModel:
    async def test_create_message_with_session(self, db_session):
        session = ChatSession(id=uuid.uuid4(), title="Test")
        db_session.add(session)
        await db_session.commit()

        msg = ChatMessage(
            id=uuid.uuid4(),
            session_id=session.id,
            role="user",
            content="What is OWASP?",
        )
        db_session.add(msg)
        await db_session.commit()

        result = await db_session.execute(select(ChatMessage))
        messages = result.scalars().all()
        assert len(messages) == 1
        assert messages[0].role == "user"
        assert messages[0].content == "What is OWASP?"
        assert messages[0].sources is None

    async def test_message_with_sources_json(self, db_session):
        session = ChatSession(id=uuid.uuid4())
        db_session.add(session)
        await db_session.commit()

        sources = [{"filename": "guide.pdf", "page": 3}]
        msg = ChatMessage(
            id=uuid.uuid4(),
            session_id=session.id,
            role="assistant",
            content="OWASP is...",
            sources=sources,
        )
        db_session.add(msg)
        await db_session.commit()
        await db_session.refresh(msg)

        assert msg.sources == sources

    async def test_multiple_messages_in_session(self, db_session):
        session = ChatSession(id=uuid.uuid4())
        db_session.add(session)
        await db_session.commit()

        for i, (role, content) in enumerate([
            ("user", "What is XSS?"),
            ("assistant", "XSS is a web vulnerability..."),
            ("user", "How to prevent it?"),
            ("assistant", "Use output encoding..."),
        ]):
            msg = ChatMessage(
                id=uuid.uuid4(),
                session_id=session.id,
                role=role,
                content=content,
            )
            db_session.add(msg)

        await db_session.commit()

        result = await db_session.execute(
            select(ChatMessage).where(ChatMessage.session_id == session.id)
        )
        messages = result.scalars().all()
        assert len(messages) == 4
