from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Entity
from app.schemas import (
    CompanyChainsResponse,
    CompanyChainItem,
    EntityBrief,
    EntityResponse,
    EvidenceChainResponse,
)
from app.services.conflict_engine import (
    SEVERITY_DISPLAY,
    detect_conflicts,
    get_bill_money_trail,
    get_donation_timeline,
    get_industry_legislation,
    get_shared_donor_network,
)
from app.services.evidence_chain import (
    build_all_chains,
    build_evidence_chain,
    chain_to_dict,
    get_company_chains,
)

router = APIRouter(prefix="/investigate", tags=["investigation"])


@router.get("/bill/{slug}")
async def investigate_bill(slug: str, db: AsyncSession = Depends(get_db)):
    """Trace money flowing to YES/NO voters on a bill."""
    trail = await get_bill_money_trail(db, slug)
    if not trail:
        raise HTTPException(status_code=404, detail="Bill not found")
    return trail


@router.get("/conflicts/{slug}")
async def investigate_conflicts(slug: str, db: AsyncSession = Depends(get_db)):
    """Detect structural relationships for an entity."""
    result = await db.execute(select(Entity).where(Entity.slug == slug))
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    signals = await detect_conflicts(db, slug)

    # Determine overall conflict score using new severity labels
    severity_order = {
        "high_concern": 4,
        "notable_pattern": 3,
        "structural_relationship": 2,
        "connection_noted": 1,
    }
    max_severity = max(
        (severity_order.get(s.severity, 0) for s in signals), default=0
    )
    score_map = {
        4: "HIGH_CONCERN",
        3: "NOTABLE_PATTERN",
        2: "STRUCTURAL_RELATIONSHIP",
        1: "CONNECTION_NOTED",
        0: "NONE",
    }
    conflict_score = score_map.get(max_severity, "NONE")

    # Serialize signals including why_this_matters and severity_display
    serialized_signals = []
    for s in signals:
        signal_dict = asdict(s)
        signal_dict["severity_display"] = SEVERITY_DISPLAY.get(s.severity, s.severity)
        serialized_signals.append(signal_dict)

    return {
        "entity": EntityResponse.model_validate(entity).model_dump(),
        "conflicts": serialized_signals,
        "conflict_score": conflict_score,
        "total_conflicts": len(signals),
    }


@router.get("/industry/{industry}")
async def investigate_industry(industry: str, db: AsyncSession = Depends(get_db)):
    """Find bills where donors from a given industry contributed heavily to YES voters."""
    return await get_industry_legislation(db, industry)


@router.get("/timeline/{slug}")
async def investigate_timeline(slug: str, db: AsyncSession = Depends(get_db)):
    """Get donation and vote timeline for an entity."""
    result = await db.execute(select(Entity).where(Entity.slug == slug))
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    events = await get_donation_timeline(db, slug)

    suspicious_pairs = sum(1 for e in events if e.get("days_before_vote") is not None)

    return {
        "entity": EntityBrief.model_validate(entity).model_dump(),
        "events": events,
        "suspicious_pairs": suspicious_pairs,
    }


@router.get("/network/{slug}")
async def investigate_network(slug: str, db: AsyncSession = Depends(get_db)):
    """Find other entities that share donors with this entity."""
    data = await get_shared_donor_network(db, slug)
    if data.get("entity") is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    return data


@router.get("/chain/{official_slug}/{company_slug}")
async def get_evidence_chain(
    official_slug: str, company_slug: str, db: AsyncSession = Depends(get_db)
):
    """Get the full evidence chain between an official and a specific company."""
    chain = await build_evidence_chain(db, official_slug, company_slug)
    if not chain:
        raise HTTPException(
            status_code=404,
            detail="No evidence chain found between this official and company",
        )
    return chain_to_dict(chain)


@router.get("/chains/{official_slug}")
async def get_all_chains(official_slug: str, db: AsyncSession = Depends(get_db)):
    """Get all evidence chains for an official."""
    result = await db.execute(select(Entity).where(Entity.slug == official_slug))
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(status_code=404, detail="Official not found")

    chains = await build_all_chains(db, official_slug)
    return {
        "official_slug": official_slug,
        "official_name": entity.name,
        "chains": [chain_to_dict(c) for c in chains],
        "total": len(chains),
    }


@router.get("/chains/company/{company_slug}")
async def get_company_chains_endpoint(
    company_slug: str, db: AsyncSession = Depends(get_db)
):
    """Get all officials with evidence chains connecting them to this company."""
    result = await db.execute(select(Entity).where(Entity.slug == company_slug))
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    chains = await get_company_chains(db, company_slug)

    # Build response with official details
    officials: list[dict] = []
    for chain in chains:
        # Look up official entity for metadata
        off_result = await db.execute(
            select(Entity).where(Entity.slug == chain.official_slug)
        )
        off_entity = off_result.scalar_one_or_none()
        off_meta = off_entity.metadata_ if off_entity else {}

        top_desc = chain.chain[0].description if chain.chain else ""
        officials.append(
            CompanyChainItem(
                official_name=off_entity.name if off_entity else chain.official_slug,
                official_slug=chain.official_slug,
                party=(off_meta or {}).get("party"),
                state=(off_meta or {}).get("state"),
                chain_depth=chain.chain_depth,
                severity=chain.severity,
                top_chain_description=top_desc,
            ).model_dump()
        )

    return CompanyChainsResponse(
        company_slug=company_slug,
        company_name=company.name,
        officials=officials,
        total=len(officials),
    ).model_dump()
