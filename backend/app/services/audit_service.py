from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


async def log_event(
    db: AsyncSession,
    event_type: str,
    detail: dict,
    user_id: str | None = None,
    ip_address: str | None = None,
) -> None:
    """Log an audit event."""
    log = AuditLog(
        event_type=event_type,
        detail=detail,
        user_id=user_id,
        ip_address=ip_address,
    )
    db.add(log)
    await db.commit()
