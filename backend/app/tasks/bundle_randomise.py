import asyncio
import logging

from ..celery_app import celery_app
from ..celery_db import SessionLocal as AsyncSessionLocal

logger = logging.getLogger(__name__)


@celery_app.task(name="services.randomise_system_bundles")
def randomise_system_bundles_task() -> dict:
    """Re-randomise every active curated bundle's membership in the background.

    Called by ``POST /admin/bundles/randomise``. Picks a fresh themed set of
    approved, licence-verified books per curated bundle, replaces the bundle's
    current membership, then queues a ZIP rebuild for each changed bundle so
    the published archives stay in sync. Custom bundles are untouched.
    """
    return asyncio.run(_run())

async def _run() -> dict:
    from ..services.bundle_randomise import randomise_curated_bundles
    from ..models.bundle import Bundle
    from ..services.audit import log_action
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        result = await randomise_curated_bundles(session)
        updated_slugs = [s.split(":")[0] for s in result.get("updated", [])]

        queued: list[dict] = []
        if updated_slugs:
            rows = (await session.execute(
                select(Bundle.id, Bundle.slug).where(Bundle.slug.in_(updated_slugs))
            )).all()
            id_by_slug = {slug: bid for bid, slug in rows}
            from ..tasks.package_bundle import rebuild_bundle_task
            for slug in updated_slugs:
                bundle_id = id_by_slug.get(slug)
                if bundle_id is None:
                    continue
                t = rebuild_bundle_task.delay(bundle_id)
                queued.append({"bundle_id": bundle_id, "task_id": t.id})

        try:
            await log_action(
                session, action="bundle.randomise", entity_type="bundle", entity_id=None,
                user_id=None, details=result,
            )
            await session.commit()
        except Exception as e:
            logger.warning("Randomise audit log skipped: %s", e)

        return {
            "updated": result.get("updated", []),
            "skipped": result.get("skipped", []),
            "queued_rebuilds": queued,
        }