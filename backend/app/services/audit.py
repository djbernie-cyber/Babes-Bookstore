"""Audit logging helper — records admin actions to the audit_log table."""

import logging
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.audit import AuditLog

logger = logging.getLogger(__name__)


async def log_action(
    db: AsyncSession,
    *,
    action: str,
    entity_type: str,
    entity_id: Optional[int] = None,
    user_id: Optional[int] = None,
    details: Optional[dict[str, Any]] = None,
):
    """Write a single audit record. Non-blocking — logs on failure."""
    try:
        entry = AuditLog(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            user_id=user_id,
            details=details,
        )
        db.add(entry)
        await db.flush()
    except Exception:
        logger.exception("Failed to write audit log: %s %s/%s", action, entity_type, entity_id)
