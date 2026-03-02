"""Sync BOE legislation into the database.

Usage:
  # Sync all 9 laws:
  docker-compose exec backend uv run python -m scripts.boe_sync

  # Sync a single law:
  docker-compose exec backend uv run python -m scripts.boe_sync BOE-A-2015-11430

  # List available laws:
  docker-compose exec backend uv run python -m scripts.boe_sync --list
"""
import asyncio
import logging
import sys

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.config import settings
from app.services.boe_client import KNOWN_LAWS
from app.services.boe_ingestion import ingest_law, ingest_all_laws

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


async def main():
    args = sys.argv[1:]

    if "--list" in args:
        print("\nAvailable BOE laws:\n")
        for law in KNOWN_LAWS:
            print(f"  {law['boe_id']:24s}  {law['short_name']:10s}  {law['title']}")
        print()
        return

    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as db:
        if args and not args[0].startswith("-"):
            boe_id = args[0]
            law = next((l for l in KNOWN_LAWS if l["boe_id"] == boe_id), None)
            if not law:
                print(f"Unknown boe_id: {boe_id}")
                print("Use --list to see available laws.")
                sys.exit(1)
            log.info("Syncing %s (%s)...", boe_id, law["short_name"])
            count = await ingest_law(db, boe_id, law["title"], law["short_name"])
            await db.commit()
            log.info("Done: %d chunks ingested for %s", count, law["short_name"])
        else:
            log.info("Syncing all %d BOE laws...", len(KNOWN_LAWS))
            results = await ingest_all_laws(db)
            await db.commit()
            total = sum(v for v in results.values() if v > 0)
            for boe_id, count in results.items():
                status = f"{count} chunks" if count >= 0 else "FAILED"
                log.info("  %s: %s", boe_id, status)
            log.info("Done: %d total chunks across %d laws", total, len(results))

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
