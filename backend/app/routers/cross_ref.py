"""Cross-reference router for entity network queries."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Entity
from app.schemas import (
    BillBadgeResponse,
    CommitteeDetailResponse,
    CommitteeMemberInfo,
    CommitteeJurisdiction,
    DonorBadgeResponse,
    DonorProfileResponse,
    DonorRecipientDetail,
    DonorRecipientInfo,
    EntityResponse,
    IndustryConnectionResponse,
    LegislationInfluenced,
    LobbyingData,
    RelationshipSpotlight,
    SharedInterestsResponse,
    StockBadgeResponse,
    StockHolderInfo,
)
from app.services.cross_reference import (
    count_cosponsors,
    count_other_holders,
    count_other_recipients,
    get_bill_donor_industries,
    get_committee_details,
    get_donor_profile,
    get_entity_with_connections_summary,
    get_industry_connections,
    get_shared_interests,
    who_else_holds_stock,
    who_else_receives_from_donor,
)

router = APIRouter(prefix="/xref", tags=["cross-reference"])


@router.get("/stock-holders/{company_slug}", response_model=list[StockHolderInfo])
async def stock_holders(company_slug: str, db: AsyncSession = Depends(get_db)):
    """List all officials who hold stock in this company."""
    return await who_else_holds_stock(db, company_slug)


@router.get(
    "/donor-recipients/{donor_slug}", response_model=list[DonorRecipientInfo]
)
async def donor_recipients(donor_slug: str, db: AsyncSession = Depends(get_db)):
    """List all officials who receive donations from this donor."""
    return await who_else_receives_from_donor(db, donor_slug)


@router.get(
    "/committee/{committee_slug}", response_model=CommitteeDetailResponse
)
async def committee_detail(
    committee_slug: str, db: AsyncSession = Depends(get_db)
):
    """Get committee details including jurisdiction and members."""
    result = await get_committee_details(db, committee_slug)
    if not result:
        raise HTTPException(status_code=404, detail="Committee not found")
    return CommitteeDetailResponse(
        entity=EntityResponse.model_validate(result["entity"]),
        members=[CommitteeMemberInfo(**m) for m in result["members"]],
        jurisdiction=CommitteeJurisdiction(**result["jurisdiction"]),
        member_count=result["member_count"],
    )


@router.get(
    "/industry/{industry}", response_model=IndustryConnectionResponse
)
async def industry_connections(
    industry: str, db: AsyncSession = Depends(get_db)
):
    """Get all officials connected to an industry via donations."""
    safe_industry = industry.encode("ascii", errors="ignore").decode("ascii")
    result = await get_industry_connections(db, safe_industry)
    return IndustryConnectionResponse(
        industry=result["industry"],
        entity_count=result["entity_count"],
        official_count=result["official_count"],
        total_donated=result["total_donated"],
        donations_to_officials=[
            DonorRecipientInfo(**d) for d in result["donations_to_officials"]
        ],
        related_entities=result["related_entities"],
    )


@router.get(
    "/shared-interests/{slug}", response_model=SharedInterestsResponse
)
async def shared_interests(slug: str, db: AsyncSession = Depends(get_db)):
    """Get officials who share financial interests with this official."""
    result = await get_shared_interests(db, slug)
    return SharedInterestsResponse(**result)


@router.get("/entity-summary/{slug}")
async def entity_summary(slug: str, db: AsyncSession = Depends(get_db)):
    """Get entity with connection counts and summary stats."""
    result = await get_entity_with_connections_summary(db, slug)
    if not result:
        raise HTTPException(status_code=404, detail="Entity not found")
    return {
        "entity": EntityResponse.model_validate(result["entity"]),
        "connection_counts": result["connection_counts"],
        "connected_officials": result["connected_officials"],
        "total_money_in": result["total_money_in"],
        "total_money_out": result["total_money_out"],
    }


@router.get(
    "/bill-badges/{bill_slug}", response_model=BillBadgeResponse
)
async def bill_badges(bill_slug: str, db: AsyncSession = Depends(get_db)):
    """Lightweight badge data for a bill: cosponsor count + donor industries."""
    bill = (
        await db.execute(select(Entity).where(Entity.slug == bill_slug))
    ).scalar_one_or_none()
    if not bill:
        return BillBadgeResponse(cosponsor_count=0, donor_industries=[])
    cosponsor_count = await count_cosponsors(db, bill.id)
    donor_industries = await get_bill_donor_industries(db, bill.id)
    return BillBadgeResponse(
        cosponsor_count=cosponsor_count,
        donor_industries=donor_industries,
    )


@router.get(
    "/stock-badge/{company_slug}", response_model=StockBadgeResponse
)
async def stock_badge(
    company_slug: str, db: AsyncSession = Depends(get_db)
):
    """Lightweight badge: how many officials hold this stock."""
    company = (
        await db.execute(
            select(Entity).where(Entity.slug == company_slug)
        )
    ).scalar_one_or_none()
    if not company:
        return StockBadgeResponse(holder_count=0)
    holder_count = await count_other_holders(db, company.id)
    return StockBadgeResponse(holder_count=holder_count)


@router.get(
    "/donor-badge/{donor_slug}", response_model=DonorBadgeResponse
)
async def donor_badge(donor_slug: str, db: AsyncSession = Depends(get_db)):
    """Lightweight badge: how many officials receive from this donor."""
    donor = (
        await db.execute(
            select(Entity).where(Entity.slug == donor_slug)
        )
    ).scalar_one_or_none()
    if not donor:
        return DonorBadgeResponse(recipient_count=0)
    recipient_count = await count_other_recipients(db, donor.id)
    return DonorBadgeResponse(recipient_count=recipient_count)


@router.get("/donor-profile/{donor_slug}", response_model=DonorProfileResponse)
async def donor_profile(donor_slug: str, db: AsyncSession = Depends(get_db)):
    """Complete donor perspective: who they fund, what legislation, which committees."""
    result = await get_donor_profile(db, donor_slug)
    if not result:
        raise HTTPException(status_code=404, detail="Donor not found")
    return DonorProfileResponse(
        entity=EntityResponse.model_validate(result["entity"]),
        total_political_spend=result["total_political_spend"],
        recipient_count=result["recipient_count"],
        recipients=[DonorRecipientDetail(**r) for r in result["recipients"]],
        committees_covered=result["committees_covered"],
        legislation_influenced=[
            LegislationInfluenced(**li) for li in result["legislation_influenced"]
        ],
        industry=result["industry"],
    )


@router.get("/lobbying/{company_slug}", response_model=LobbyingData)
async def company_lobbying(company_slug: str, db: AsyncSession = Depends(get_db)):
    """Get lobbying data for a company from entity metadata."""
    company = (
        await db.execute(select(Entity).where(Entity.slug == company_slug))
    ).scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    meta = company.metadata_ or {}
    lobbying = meta.get("lobbying", {})
    return LobbyingData(
        total_spend=lobbying.get("total_spend", 0),
        filing_count=lobbying.get("filing_count", 0),
        firm_count=lobbying.get("firm_count", 0),
        lobbyist_count=lobbying.get("lobbyist_count", 0),
        issues=lobbying.get("issues", []),
    )


@router.get("/relationship-spotlight/{slug}", response_model=list[RelationshipSpotlight])
async def relationship_spotlight(slug: str, db: AsyncSession = Depends(get_db)):
    """Get entities with 3+ connection signals to this person."""
    from app.services.conflict_engine import detect_relationship_spotlight
    spotlights = await detect_relationship_spotlight(db, slug)
    return [RelationshipSpotlight(**s) for s in spotlights]
