"""
Orchestrate ingestion for Fetterman + all committee members.

This is the main entry point for running a full data ingestion across
all tracked politicians. It runs the Fetterman ingestion first (as the
anchor entity), then fetches and ingests all members of his committees.

Usage:
    cd /home/mansona/workspace/jerry-maguire/backend
    python -m app.services.ingestion.ingest_all
"""

import asyncio
from datetime import datetime


async def run_full_ingestion():
    """
    Full ingestion pipeline:
    1. Run Fetterman ingestion (existing)
    2. Fetch committee members for Banking, Agriculture, Joint Economic
    3. For each member, run full ingestion
    4. Enrich all bill entities with tldr, full_text_url, official_summary
    """
    print("\n" + "#" * 60)
    print("# JERRY MAGUIRE -- Full Data Ingestion Pipeline")
    print(f"# Time: {datetime.now(tz=None).isoformat()}")
    print("#" * 60 + "\n")

    # Phase 1: Run Fetterman ingestion
    print("=" * 60)
    print("PHASE 1: Ingesting John Fetterman (anchor entity)")
    print("=" * 60)
    try:
        from app.services.ingestion.ingest_fetterman import run_ingestion
        await run_ingestion()
        print("Fetterman ingestion complete.")
    except Exception as e:
        print(f"ERROR during Fetterman ingestion: {e}")
        print("Continuing with committee member ingestion...")

    # Phase 2: Run committee member ingestion
    print("\n" + "=" * 60)
    print("PHASE 2: Ingesting committee members")
    print("=" * 60)
    try:
        from app.services.ingestion.ingest_committee_members import (
            run_committee_member_ingestion,
        )
        await run_committee_member_ingestion()
        print("Committee member ingestion complete.")
    except Exception as e:
        print(f"ERROR during committee member ingestion: {e}")

    print("\n" + "#" * 60)
    print("# FULL INGESTION COMPLETE")
    print(f"# Finished at: {datetime.now(tz=None).isoformat()}")
    print("#" * 60)


if __name__ == "__main__":
    asyncio.run(run_full_ingestion())
