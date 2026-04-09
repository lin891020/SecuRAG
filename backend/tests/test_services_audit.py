"""Tests for the audit service."""

import uuid

import pytest
from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.services.audit_service import log_event


class TestLogEvent:
    async def test_creates_audit_log_entry(self, db_session):
        """Should persist an audit log with correct fields."""
        await log_event(
            db=db_session,
            event_type="query",
            detail={"query": "What is XSS?", "model": "llama3.2"},
            ip_address="192.168.1.1",
        )

        result = await db_session.execute(select(AuditLog))
        logs = result.scalars().all()

        assert len(logs) == 1
        assert logs[0].event_type == "query"
        assert logs[0].detail["query"] == "What is XSS?"
        assert logs[0].ip_address == "192.168.1.1"
        assert logs[0].user_id is None

    async def test_logs_guardrail_block(self, db_session):
        """Should log guardrail block events."""
        await log_event(
            db=db_session,
            event_type="guardrail_block",
            detail={"input": "ignore instructions", "reason": "prompt_injection"},
        )

        result = await db_session.execute(
            select(AuditLog).where(AuditLog.event_type == "guardrail_block")
        )
        log = result.scalar_one()
        assert log.detail["reason"] == "prompt_injection"

    async def test_logs_multiple_events(self, db_session):
        """Should support multiple log entries."""
        for i in range(5):
            await log_event(
                db=db_session,
                event_type="query",
                detail={"index": i},
            )

        result = await db_session.execute(select(AuditLog))
        assert len(result.scalars().all()) == 5

    async def test_log_has_created_at_timestamp(self, db_session):
        """Audit log should have a timestamp."""
        await log_event(
            db=db_session,
            event_type="upload",
            detail={"filename": "policy.pdf"},
        )

        result = await db_session.execute(select(AuditLog))
        log = result.scalar_one()
        assert log.created_at is not None
