#!/usr/bin/env python3
"""Backfill knowledge graph entities for all existing completed events.

Usage:
    cd app && python -m backend.scripts.backfill_entities [--dry-run] [--batch-size 5]
"""

from __future__ import annotations

import argparse
import json as _json
import logging
import sys
import os as _os
from pathlib import Path

# Ensure the project root is on sys.path
_KI_HOME = _os.getenv("KI_HOME", "").strip()
if _KI_HOME:
    PROJECT_ROOT = Path(_KI_HOME).expanduser().resolve()
else:
    PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT / "app"))

# Load .env before importing backend modules that need API keys
from dotenv import load_dotenv
_env_path = PROJECT_ROOT / ".env"
if _env_path.exists():
    load_dotenv(_env_path, override=True)

from backend.db import connect
from backend.summarizer import _extract_entities
from backend.routes.entity_routes import _store_entities

logger = logging.getLogger("backfill_entities")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)-7s] %(message)s")


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill knowledge graph entities")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--batch-size", type=int, default=5, help="Events per batch")
    parser.add_argument("--start-after", type=str, default="", help="Resume after this event ID")
    args = parser.parse_args()

    with connect() as conn:
        # Get all completed events that don't have entities yet
        query = """
            SELECT e.id, e.title, e.raw_summary, e.topic
            FROM events e
            LEFT JOIN sources s ON e.source_id = s.id
            WHERE e.status = 'completed'
              AND e.raw_summary IS NOT NULL
              AND e.raw_summary != ''
              AND (s.type IS NULL OR s.type != 'rss')
              AND NOT EXISTS (
                SELECT 1 FROM event_entities ee WHERE ee.event_id = e.id
              )
        """
        params: tuple = ()
        if args.start_after:
            query += " AND e.id > ?"
            params = (args.start_after,)
        query += " ORDER BY e.id LIMIT 200"

        events = conn.execute(query, params).fetchall()

    if not events:
        logger.info("No events need backfilling")
        return

    logger.info("Found %d events to backfill", len(events))

    total_entities = 0
    total_relations = 0
    skipped = 0

    for i, ev in enumerate(events):
        event_id = ev["id"]
        title = ev["title"] or ""
        text = ev["raw_summary"] or ""

        if len(text.strip()) < 200:
            logger.info("[%d/%d] %s — too short, skipping", i + 1, len(events), event_id)
            skipped += 1
            continue

        logger.info("[%d/%d] %s — extracting entities from %d chars...", i + 1, len(events), event_id, len(text))

        if args.dry_run:
            logger.info("  [DRY RUN] Would extract entities for: %s", title)
            continue

        try:
            entities, relations = _extract_entities(text, title, timeout=60)
            if entities:
                _store_entities(event_id, entities, relations)
                total_entities += len(entities)
                total_relations += len(relations)
                logger.info("  Stored %d entities + %d relations", len(entities), len(relations))
            else:
                logger.info("  No entities extracted")
        except Exception as e:
            logger.error("  Failed: %s", e)

        # Rate limit: small pause between batches
        if (i + 1) % args.batch_size == 0:
            logger.info("Batch %d/%d complete — pausing 3s...", (i + 1) // args.batch_size,
                        (len(events) + args.batch_size - 1) // args.batch_size)
            import time
            time.sleep(3)

    logger.info("DONE: %d entities, %d relations, %d skipped, %d events processed",
                total_entities, total_relations, skipped, len(events))


if __name__ == "__main__":
    main()
