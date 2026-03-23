"""
Hidden Connections Router — The connections the public doesn't know to look for.
Revolving door, family finances, speaking fees, contractor-donors, insider timing.
"""
import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, and_, or_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Entity, Relationship
from app.schemas import (
    RevolvingDoorItem,
    FamilyConnectionItem,
    OutsideIncomeItem,
    ContractorDonorItem,
    TradeTimingItem,
    TradeTimingSummary,
    InsiderTimingResponse,
    HiddenConnectionsSummary,
    HiddenConnectionsFeedItem,
)
from app.services.conflict_engine import (
    _sanitize,
    _extract_industry_keywords,
    _industries_for_committee,
    _keyword_overlap,
)

router = APIRouter(prefix="/hidden", tags=["hidden-connections"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _load_entity(db: AsyncSession, slug: str) -> Entity:
    """Load entity by slug or raise 404."""
    result = await db.execute(select(Entity).where(Entity.slug == slug))
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    return entity


async def _get_committee_names(db: AsyncSession, entity: Entity) -> list[str]:
    """Return committee names for an official."""
    rels = await db.execute(
        select(Relationship).where(
            and_(
                or_(
                    Relationship.from_entity_id == entity.id,
                    Relationship.to_entity_id == entity.id,
                ),
                Relationship.relationship_type == "committee_member",
            )
        )
    )
    committee_rels = rels.scalars().all()
    committee_ids = set()
    for r in committee_rels:
        other_id = r.to_entity_id if r.from_entity_id == entity.id else r.from_entity_id
        committee_ids.add(other_id)
    if not committee_ids:
        return []
    ent_result = await db.execute(select(Entity).where(Entity.id.in_(committee_ids)))
    return [_sanitize(e.name) for e in ent_result.scalars().all()]


def _build_revolving_door_matter(lobbyist_name: str, former_pos: str, committee: str) -> str:
    return (
        f"{lobbyist_name} used to be a {former_pos} in government. "
        f"Now they get paid to lobby {committee if committee else 'Congress'} on behalf of private clients. "
        f"They know every trick, every shortcut, and every person who matters. "
        f"The question is simple: should former insiders be allowed to sell that access?"
    )


def _build_family_matter(member: str, employer: str, overlap: str | None) -> str:
    if overlap:
        return (
            f"{member} gets a paycheck from {employer}. Meanwhile, their family member "
            f"sits on {overlap}, which has power over {employer}'s industry. "
            f"Even if the official tries to be fair, the family income creates a reason "
            f"to go easy. You do the math."
        )
    return (
        f"{member} works at {employer}. Their family member is a government official. "
        f"No direct committee overlap was found, but the financial tie between the "
        f"family and this company is something the public should know about."
    )


def _build_income_matter(payer: str, amount_str: str, overlap: str | None) -> str:
    if overlap:
        return (
            f"This official got paid {amount_str} by {payer}. {payer} operates in an "
            f"industry regulated by {overlap}, where this official sits. If someone "
            f"paid you that much for a speech, would you feel completely neutral "
            f"about them the next time they needed a favor?"
        )
    return (
        f"This official received {amount_str} from {payer}. Speaking fees and outside "
        f"income create personal financial relationships between officials and the "
        f"organizations paying them. It does not prove bias, but it is worth knowing."
    )


# ---------------------------------------------------------------------------
# 1. Revolving Door
# ---------------------------------------------------------------------------

@router.get("/{slug}/revolving-door", response_model=list[RevolvingDoorItem])
async def get_revolving_door(slug: str, db: AsyncSession = Depends(get_db)):
    """Find lobbyists who used to work in government and now lobby this official."""
    entity = await _load_entity(db, slug)
    committee_names = await _get_committee_names(db, entity)

    # Find revolving_door_lobbyist relationships pointing to this official
    rels_result = await db.execute(
        select(Relationship).where(
            and_(
                Relationship.to_entity_id == entity.id,
                Relationship.relationship_type == "revolving_door_lobbyist",
            )
        )
    )
    rels = rels_result.scalars().all()

    # Also check relationships where official is from_entity
    rels_result2 = await db.execute(
        select(Relationship).where(
            and_(
                Relationship.from_entity_id == entity.id,
                Relationship.relationship_type == "revolving_door_lobbyist",
            )
        )
    )
    rels.extend(rels_result2.scalars().all())

    if not rels:
        return []

    # Load lobbyist entities
    lobbyist_ids = set()
    for r in rels:
        lobbyist_ids.add(r.from_entity_id if r.to_entity_id == entity.id else r.to_entity_id)
    ent_result = await db.execute(select(Entity).where(Entity.id.in_(lobbyist_ids)))
    lobbyists_map = {e.id: e for e in ent_result.scalars().all()}

    items: list[RevolvingDoorItem] = []
    for r in rels:
        lobbyist_id = r.from_entity_id if r.to_entity_id == entity.id else r.to_entity_id
        lobbyist = lobbyists_map.get(lobbyist_id)
        if not lobbyist:
            continue
        meta = r.metadata_ or {}
        l_meta = lobbyist.metadata_ or {}
        former_position = meta.get("former_position", l_meta.get("former_position", "government official"))
        current_role = meta.get("current_role", l_meta.get("role", "lobbyist"))
        # Bug fix: entity metadata uses "current_employer", not "employer"
        current_employer = meta.get("current_employer", l_meta.get("current_employer", "a lobbying firm"))
        lobbies_committee = meta.get("lobbies_committee", "")
        clients = meta.get("clients", l_meta.get("clients", []))
        lobbies_for = l_meta.get("lobbies_for", [])
        if isinstance(clients, str):
            clients = [clients]
        left_government = meta.get("left_government", l_meta.get("left_government"))
        registration_url = meta.get("registration_url", l_meta.get("registration_url"))

        # Enrichment: compute years_in_government from former_position dates or default
        years_in_gov = meta.get("years_in_government", "4 years")
        # Try to parse from former_position pattern like "(2017-2021)"
        year_match = re.search(r"\((\d{4})-(\d{4})\)", former_position)
        if year_match:
            y1, y2 = int(year_match.group(1)), int(year_match.group(2))
            years_in_gov = f"{y2 - y1} years"

        # Enrichment: access_level based on seniority keywords
        pos_lower = former_position.lower()
        if any(kw in pos_lower for kw in ["chief of staff", "general counsel", "director", "chairman"]):
            access_level = "high"
        elif any(kw in pos_lower for kw in ["legislative", "senior", "counsel", "advisor"]):
            access_level = "high"
        else:
            access_level = "medium"

        # Enrichment: what_they_lobbied — specific issues from metadata
        what_they_lobbied = meta.get("what_they_lobbied") or lobbies_for or clients or []

        # Enrichment: conflict_score
        score = 5  # baseline
        if access_level == "high":
            score += 2
        if lobbies_committee:
            for cn in committee_names:
                if cn.lower() in lobbies_committee.lower() or lobbies_committee.lower() in cn.lower():
                    score += 2
                    break
        if len(clients) > 2:
            score += 1
        conflict_score = min(score, 10)

        items.append(RevolvingDoorItem(
            lobbyist_name=_sanitize(lobbyist.name),
            lobbyist_slug=lobbyist.slug,
            former_position=_sanitize(former_position),
            current_role=_sanitize(current_role),
            current_employer=_sanitize(current_employer),
            lobbies_committee=_sanitize(lobbies_committee),
            clients=[_sanitize(c) for c in clients],
            left_government=left_government,
            registration_url=registration_url,
            why_this_matters=_build_revolving_door_matter(
                _sanitize(lobbyist.name), _sanitize(former_position), _sanitize(lobbies_committee)
            ),
            years_in_government=years_in_gov,
            access_level=access_level,
            what_they_lobbied=[_sanitize(c) for c in what_they_lobbied] if what_they_lobbied else None,
            conflict_score=conflict_score,
        ))

    return items


# ---------------------------------------------------------------------------
# 2. Family Connections
# ---------------------------------------------------------------------------

@router.get("/{slug}/family-connections", response_model=list[FamilyConnectionItem])
async def get_family_connections(slug: str, db: AsyncSession = Depends(get_db)):
    """Find family members employed by companies in regulated industries."""
    entity = await _load_entity(db, slug)
    committee_names = await _get_committee_names(db, entity)

    family_types = ["spouse_income_from", "family_employed_by"]
    rels_result = await db.execute(
        select(Relationship).where(
            and_(
                or_(
                    Relationship.from_entity_id == entity.id,
                    Relationship.to_entity_id == entity.id,
                ),
                Relationship.relationship_type.in_(family_types),
            )
        )
    )
    rels = rels_result.scalars().all()
    if not rels:
        return []

    employer_ids = set()
    for r in rels:
        employer_ids.add(r.to_entity_id if r.from_entity_id == entity.id else r.from_entity_id)
    ent_result = await db.execute(select(Entity).where(Entity.id.in_(employer_ids)))
    employers_map = {e.id: e for e in ent_result.scalars().all()}

    items: list[FamilyConnectionItem] = []
    for r in rels:
        employer_id = r.to_entity_id if r.from_entity_id == entity.id else r.from_entity_id
        employer = employers_map.get(employer_id)
        if not employer:
            continue
        meta = r.metadata_ or {}
        family_member = meta.get("family_member", "A family member")
        # Bug fix: seed data uses "relationship_to_official", not "relationship"
        relationship_label = meta.get("relationship_to_official", meta.get("relationship", "family member"))
        role = meta.get("role", "employee")
        annual_income = meta.get("annual_income") or r.amount_usd

        employer_kws = _extract_industry_keywords(employer)
        overlap_committee = meta.get("committee_overlap")
        if not overlap_committee:
            for cn in committee_names:
                c_industries = _industries_for_committee(cn)
                if _keyword_overlap(c_industries, employer_kws):
                    overlap_committee = cn
                    break

        # Enrichment: potential_benefit
        if overlap_committee:
            potential_benefit = (
                f"As a member of {overlap_committee}, the official could influence "
                f"regulations, oversight, and funding that directly affect "
                f"{_sanitize(employer.name)}, where their {relationship_label} works."
            )
        else:
            potential_benefit = (
                f"The official's {relationship_label} earns income from {_sanitize(employer.name)}. "
                f"While no direct committee overlap was found, legislative actions could "
                f"still indirectly benefit the employer."
            )

        items.append(FamilyConnectionItem(
            family_member=_sanitize(family_member),
            relationship=_sanitize(relationship_label),
            employer_name=_sanitize(employer.name),
            employer_slug=employer.slug,
            role=_sanitize(role),
            annual_income=annual_income,
            committee_overlap=_sanitize(overlap_committee) if overlap_committee else None,
            why_this_matters=_build_family_matter(
                _sanitize(family_member), _sanitize(employer.name),
                _sanitize(overlap_committee) if overlap_committee else None
            ),
            potential_benefit=potential_benefit,
        ))

    return items


# ---------------------------------------------------------------------------
# 3. Outside Income
# ---------------------------------------------------------------------------

@router.get("/{slug}/outside-income", response_model=list[OutsideIncomeItem])
async def get_outside_income(slug: str, db: AsyncSession = Depends(get_db)):
    """Find speaking fees, book deals, and other outside income."""
    entity = await _load_entity(db, slug)
    committee_names = await _get_committee_names(db, entity)

    income_types = ["speaking_fee_from", "outside_income_from", "book_deal_with"]
    rels_result = await db.execute(
        select(Relationship).where(
            and_(
                or_(
                    Relationship.from_entity_id == entity.id,
                    Relationship.to_entity_id == entity.id,
                ),
                Relationship.relationship_type.in_(income_types),
            )
        )
    )
    rels = rels_result.scalars().all()
    if not rels:
        return []

    payer_ids = set()
    for r in rels:
        payer_ids.add(r.to_entity_id if r.from_entity_id == entity.id else r.from_entity_id)
    ent_result = await db.execute(select(Entity).where(Entity.id.in_(payer_ids)))
    payers_map = {e.id: e for e in ent_result.scalars().all()}

    items: list[OutsideIncomeItem] = []
    for r in rels:
        payer_id = r.to_entity_id if r.from_entity_id == entity.id else r.from_entity_id
        payer = payers_map.get(payer_id)
        if not payer:
            continue
        meta = r.metadata_ or {}
        amount = r.amount_usd or meta.get("amount_usd", 0)
        income_type = meta.get("income_type", r.relationship_type.replace("_from", "").replace("_with", ""))
        # Bug fix: seed data uses "event", not "event_description"
        event_desc = meta.get("event_description") or meta.get("event", "")
        date_str = str(r.date_start) if r.date_start else meta.get("date")

        payer_kws = _extract_industry_keywords(payer)
        payer_meta = payer.metadata_ or {}
        has_lobbying = payer_meta.get("lobbying", {}).get("filing_count", 0) > 0
        is_regulated = False
        overlap_committee = None
        for cn in committee_names:
            c_industries = _industries_for_committee(cn)
            if _keyword_overlap(c_industries, payer_kws):
                is_regulated = True
                overlap_committee = cn
                break

        amount_str = f"${amount / 100:,.0f}" if amount else "an undisclosed amount"
        items.append(OutsideIncomeItem(
            payer_name=_sanitize(payer.name),
            payer_slug=payer.slug,
            income_type=income_type,
            amount_usd=amount or 0,
            date=date_str,
            event_description=_sanitize(event_desc) if event_desc else None,
            is_regulated_industry=is_regulated or has_lobbying,
            committee_overlap=_sanitize(overlap_committee) if overlap_committee else None,
            why_this_matters=_build_income_matter(
                _sanitize(payer.name), amount_str,
                _sanitize(overlap_committee) if overlap_committee else None
            ),
        ))

    return items


# ---------------------------------------------------------------------------
# 4. Contractor Donors
# ---------------------------------------------------------------------------

@router.get("/{slug}/contractor-donors", response_model=list[ContractorDonorItem])
async def get_contractor_donors(slug: str, db: AsyncSession = Depends(get_db)):
    """Find companies that donated to the official and then got government contracts."""
    entity = await _load_entity(db, slug)

    rels_result = await db.execute(
        select(Relationship).where(
            and_(
                or_(
                    Relationship.from_entity_id == entity.id,
                    Relationship.to_entity_id == entity.id,
                ),
                Relationship.relationship_type == "contractor_donor",
            )
        )
    )
    rels = rels_result.scalars().all()
    if not rels:
        return []

    contractor_ids = set()
    for r in rels:
        contractor_ids.add(r.from_entity_id if r.to_entity_id == entity.id else r.to_entity_id)
    ent_result = await db.execute(select(Entity).where(Entity.id.in_(contractor_ids)))
    contractors_map = {e.id: e for e in ent_result.scalars().all()}

    items: list[ContractorDonorItem] = []
    for r in rels:
        contractor_id = r.from_entity_id if r.to_entity_id == entity.id else r.to_entity_id
        contractor = contractors_map.get(contractor_id)
        if not contractor:
            continue
        meta = r.metadata_ or {}
        c_meta = contractor.metadata_ or {}
        donation_amount = meta.get("donation_amount", r.amount_usd or 0)
        contract_amount = meta.get("contract_amount", 0)
        contract_agency = meta.get("contract_agency", "a government agency")
        contract_desc = meta.get("contract_description", "government services")
        donation_date = meta.get("donation_date", str(r.date_start) if r.date_start else None)
        contract_date = meta.get("contract_date", str(r.date_end) if r.date_end else None)
        state = c_meta.get("state", meta.get("state"))

        ratio = round(contract_amount / donation_amount, 1) if donation_amount and donation_amount > 0 else None
        donation_str = f"${donation_amount / 100:,.0f}" if donation_amount else "an unknown amount"
        contract_str = f"${contract_amount / 100:,.0f}" if contract_amount else "an unknown amount"

        items.append(ContractorDonorItem(
            contractor_name=_sanitize(contractor.name),
            contractor_slug=contractor.slug,
            state=state,
            donation_amount=donation_amount,
            donation_date=donation_date,
            contract_amount=contract_amount,
            contract_date=contract_date,
            contract_agency=_sanitize(contract_agency),
            contract_description=_sanitize(contract_desc),
            dollars_per_donation_dollar=ratio,
            why_this_matters=(
                f"{_sanitize(contractor.name)} donated {donation_str} to this official. "
                f"Then they got a {contract_str} government contract from {_sanitize(contract_agency)}. "
                + (f"That is ${ratio:.0f} back for every $1 donated. " if ratio else "")
                + f"Coincidence? Maybe. But it is the kind of pattern that makes people wonder."
            ),
        ))

    return items


# ---------------------------------------------------------------------------
# 5. Trade Timing
# ---------------------------------------------------------------------------

@router.get("/{slug}/trade-timing", response_model=InsiderTimingResponse)
async def get_trade_timing(slug: str, db: AsyncSession = Depends(get_db)):
    """Analyze stock trades for suspicious timing relative to committee actions."""
    entity = await _load_entity(db, slug)

    rels_result = await db.execute(
        select(Relationship).where(
            and_(
                Relationship.from_entity_id == entity.id,
                Relationship.relationship_type == "holds_stock",
            )
        )
    )
    rels = rels_result.scalars().all()

    stock_ids = {r.to_entity_id for r in rels}
    stocks_map: dict = {}
    if stock_ids:
        ent_result = await db.execute(select(Entity).where(Entity.id.in_(stock_ids)))
        stocks_map = {e.id: e for e in ent_result.scalars().all()}

    trades: list[TradeTimingItem] = []
    total_score = 0
    within_30 = 0
    favorable = 0
    unfavorable = 0

    for r in rels:
        stock_ent = stocks_map.get(r.to_entity_id)
        if not stock_ent:
            continue
        meta = r.metadata_ or {}
        info_score = meta.get("information_access_score", 0)
        if not isinstance(info_score, (int, float)):
            try:
                info_score = int(info_score)
            except (ValueError, TypeError):
                info_score = 0

        transaction_type = meta.get("transaction_type", "unknown")
        transaction_date = meta.get("transaction_date", str(r.date_start) if r.date_start else "unknown")
        amount_range = meta.get("amount_range", r.amount_label or "undisclosed")
        days_before_hearing = meta.get("days_before_committee_hearing")
        hearing_topic = meta.get("hearing_topic")
        hearing_date = meta.get("hearing_date")
        days_before_vote = meta.get("days_before_related_vote")
        vote_topic = meta.get("vote_topic")
        stock_movement = meta.get("stock_movement_after")
        pattern_flag = meta.get("pattern_flag")
        pattern_desc = meta.get("pattern_description", "Standard trade")

        total_score += info_score

        if days_before_hearing and isinstance(days_before_hearing, (int, float)) and days_before_hearing <= 30:
            within_30 += 1
        if days_before_vote and isinstance(days_before_vote, (int, float)) and days_before_vote <= 30:
            within_30 += 1

        if stock_movement:
            mv = str(stock_movement).lower()
            if "went up" in mv or "rose" in mv or "gained" in mv or "increased" in mv:
                if transaction_type == "buy":
                    favorable += 1
                else:
                    unfavorable += 1
            elif "went down" in mv or "fell" in mv or "dropped" in mv or "decreased" in mv:
                if transaction_type == "sell":
                    favorable += 1
                else:
                    unfavorable += 1

        timing_detail = ""
        if days_before_hearing:
            timing_detail = f"Trade made {days_before_hearing} days before committee hearing"
        elif days_before_vote:
            timing_detail = f"Trade made {days_before_vote} days before a related vote"
        else:
            timing_detail = "No specific timing event identified"

        trades.append(TradeTimingItem(
            stock_name=_sanitize(stock_ent.name),
            stock_slug=stock_ent.slug,
            transaction_type=transaction_type,
            transaction_date=transaction_date,
            amount_range=amount_range,
            days_before_committee_hearing=days_before_hearing,
            hearing_topic=hearing_topic,
            hearing_date=hearing_date,
            days_before_related_vote=days_before_vote,
            vote_topic=vote_topic,
            stock_movement_after=stock_movement,
            information_access_score=info_score,
            pattern_flag=pattern_flag,
            pattern_description=_sanitize(pattern_desc),
            why_this_matters=(
                f"This official traded {_sanitize(stock_ent.name)} stock. {timing_detail}. "
                f"Members of Congress get briefings that regular people never see. "
                f"This trade has an information access score of {info_score}/10."
            ),
        ))

    avg_score = round(total_score / len(trades), 1) if trades else 0.0
    flagged = sum(1 for t in trades if t.information_access_score >= 7)

    if flagged > 2:
        overall = (
            f"Out of {len(trades)} trades analyzed, {flagged} were flagged with high "
            f"information access scores. {within_30} happened within 30 days of committee "
            f"activity. This pattern suggests this official may be trading on information "
            f"they get through their government role."
        )
    elif flagged > 0:
        overall = (
            f"{flagged} out of {len(trades)} trades were flagged for timing near "
            f"committee actions. Not necessarily suspicious on its own, but worth "
            f"watching over time."
        )
    else:
        overall = (
            f"{len(trades)} trades analyzed. No trades flagged with high information "
            f"access scores. Trading activity appears routine."
        )

    summary = TradeTimingSummary(
        total_trades_analyzed=len(trades),
        trades_within_30_days_of_hearing=within_30,
        trades_before_favorable_outcome=favorable,
        trades_before_unfavorable_outcome=unfavorable,
        average_information_access_score=avg_score,
        overall_pattern=overall,
        why_this_matters=(
            f"Members of Congress sit on committees that make decisions affecting "
            f"billions of dollars in stock value. They get private briefings, early "
            f"warnings, and inside information. When they trade stocks in companies "
            f"their committees oversee, the timing of those trades tells a story."
        ),
    )

    return InsiderTimingResponse(
        entity_slug=entity.slug,
        entity_name=_sanitize(entity.name),
        trades=trades,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# 6. Summary — all 5 types aggregated
# ---------------------------------------------------------------------------

@router.get("/{slug}/summary", response_model=HiddenConnectionsSummary)
async def get_hidden_connections_summary(slug: str, db: AsyncSession = Depends(get_db)):
    """Aggregate all hidden connection types into one intelligence briefing."""
    entity = await _load_entity(db, slug)

    revolving_door = await get_revolving_door(slug, db)
    family = await get_family_connections(slug, db)
    income = await get_outside_income(slug, db)
    contractors = await get_contractor_donors(slug, db)
    timing_resp = await get_trade_timing(slug, db)

    income_total = sum(i.amount_usd for i in income)
    contractor_donations = sum(c.donation_amount for c in contractors)
    contractor_contracts = sum(c.contract_amount for c in contractors)
    flagged_trades = sum(1 for t in timing_resp.trades if t.information_access_score >= 7)
    total_trades = len(timing_resp.trades)
    within_30 = timing_resp.summary.trades_within_30_days_of_hearing if timing_resp.summary else 0

    # Build highlight strings
    if revolving_door:
        rd_highlight = f"{len(revolving_door)} former staffer{'s' if len(revolving_door) != 1 else ''} now lobby{'s' if len(revolving_door) == 1 else ''} your office"
    else:
        rd_highlight = None

    if family:
        top_family = max(family, key=lambda f: f.annual_income or 0)
        income_str = f"${top_family.annual_income:,}/year" if top_family.annual_income else "income"
        family_highlight = f"{top_family.relationship.title()} earns {income_str} from {top_family.employer_name}"
    else:
        family_highlight = None

    if income:
        top_income = max(income, key=lambda i: i.amount_usd or 0)
        amt_str = f"${top_income.amount_usd / 100:,.0f}" if top_income.amount_usd else "undisclosed"
        regulated_str = " from regulated financial industry group" if top_income.is_regulated_industry else ""
        outside_income_highlight = f"{amt_str} {top_income.income_type.replace('_', ' ')}{regulated_str}"
    else:
        outside_income_highlight = None

    if contractors:
        d_str = f"${contractor_donations / 100:,.0f}" if contractor_donations else "money"
        c_str = f"${contractor_contracts / 100:,.0f}" if contractor_contracts else "contracts"
        contractor_donor_highlight = f"Companies donated {d_str}, received {c_str} in contracts"
    else:
        contractor_donor_highlight = None

    if total_trades > 0:
        trade_timing_highlight = f"{within_30} of {total_trades} trades within 30 days of committee activity"
    else:
        trade_timing_highlight = None

    trade_score = round(timing_resp.summary.average_information_access_score) if timing_resp.summary else 0

    total_signals = len(revolving_door) + len(family) + len(income) + len(contractors) + flagged_trades

    return HiddenConnectionsSummary(
        entity_slug=entity.slug,
        entity_name=_sanitize(entity.name),
        revolving_door=revolving_door,
        revolving_door_count=len(revolving_door),
        revolving_door_highlight=rd_highlight,
        family_connections=family,
        family_connections_count=len(family),
        family_highlight=family_highlight,
        outside_income=income,
        outside_income_total=income_total,
        outside_income_count=len(income),
        outside_income_highlight=outside_income_highlight,
        contractor_donors=contractors,
        contractor_donors_count=len(contractors),
        contractor_total_donations=contractor_donations,
        contractor_total_contracts=contractor_contracts,
        contractor_donor_highlight=contractor_donor_highlight,
        trade_timing=timing_resp.summary if timing_resp.trades else None,
        trade_timing_flagged_count=flagged_trades,
        trade_timing_score=trade_score,
        trade_timing_highlight=trade_timing_highlight,
        total_hidden_signals=total_signals,
    )


# ---------------------------------------------------------------------------
# 7. Feed — recent hidden connection alerts across all officials
# ---------------------------------------------------------------------------

ALERT_ICONS = {
    "revolving_door": "🚪",
    "family_conflict": "👨‍👩‍👧",
    "speaking_fee": "🎤",
    "contractor_donor": "📋",
    "trade_timing": "📈",
}

SEVERITY_ORDER = {
    "high_concern": 4,
    "notable_pattern": 3,
    "structural_relationship": 2,
    "connection_noted": 1,
}


@router.get("/feed", response_model=list[HiddenConnectionsFeedItem])
async def get_hidden_connections_feed(
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
):
    """Return recent hidden connection alerts across all officials for the homepage feed."""

    # Get all person entities
    persons_result = await db.execute(
        select(Entity).where(Entity.entity_type == "person").limit(50)
    )
    persons = persons_result.scalars().all()

    feed_items: list[HiddenConnectionsFeedItem] = []

    # Relationship types to scan and their alert categories
    alert_type_map = {
        "revolving_door_lobbyist": "revolving_door",
        "spouse_income_from": "family_conflict",
        "family_employed_by": "family_conflict",
        "speaking_fee_from": "speaking_fee",
        "outside_income_from": "speaking_fee",
        "book_deal_with": "speaking_fee",
        "contractor_donor": "contractor_donor",
    }

    hidden_rel_types = list(alert_type_map.keys())

    # Query all hidden-connection relationships across all persons
    rels_result = await db.execute(
        select(Relationship)
        .where(Relationship.relationship_type.in_(hidden_rel_types))
        .limit(200)
    )
    all_rels = rels_result.scalars().all()

    # Collect all entity IDs involved
    all_entity_ids = set()
    for r in all_rels:
        all_entity_ids.add(r.from_entity_id)
        all_entity_ids.add(r.to_entity_id)

    entities_map: dict = {}
    if all_entity_ids:
        ent_result = await db.execute(select(Entity).where(Entity.id.in_(all_entity_ids)))
        entities_map = {e.id: e for e in ent_result.scalars().all()}

    for r in all_rels:
        from_ent = entities_map.get(r.from_entity_id)
        to_ent = entities_map.get(r.to_entity_id)
        if not from_ent or not to_ent:
            continue

        # Determine which entity is the official vs the other entity
        # For revolving_door_lobbyist: from=lobbyist, to=official
        # For family/outside_income: from=official, to=company
        # For contractor_donor: from=company, to=official
        rel_type = r.relationship_type
        if rel_type == "revolving_door_lobbyist":
            official = to_ent
            other = from_ent
        elif rel_type in ("spouse_income_from", "family_employed_by", "speaking_fee_from", "outside_income_from", "book_deal_with"):
            official = from_ent
            other = to_ent
        elif rel_type == "contractor_donor":
            # from=company, to=official
            official = to_ent
            other = from_ent
        elif from_ent.entity_type == "person" and to_ent.entity_type != "person":
            official = from_ent
            other = to_ent
        elif to_ent.entity_type == "person" and from_ent.entity_type != "person":
            official = to_ent
            other = from_ent
        else:
            continue

        alert_type = alert_type_map.get(r.relationship_type, "connection_noted")
        meta = r.metadata_ or {}
        date_str = str(r.date_start) if r.date_start else meta.get("date")

        # Build headline, description, and plain_english based on type
        if alert_type == "revolving_door":
            former_pos = meta.get("former_position", "a government role")
            current_emp = meta.get("current_employer") or (other.metadata_ or {}).get("current_employer", other.name)
            clients = meta.get("clients") or (other.metadata_ or {}).get("clients", [])
            clients_str = ", ".join(clients[:3]) if clients else current_emp
            headline = (
                f"Former {_sanitize(former_pos).split(',')[0]} now lobbies for {_sanitize(clients_str)}"
            )
            description = (
                f"{_sanitize(other.name)} used to work in government as {_sanitize(former_pos)}. "
                f"Now at {_sanitize(current_emp)}, they lobby on behalf of {_sanitize(clients_str)}. "
                f"They have a direct connection to {_sanitize(official.name)}."
            )
            plain_english = (
                f"{_sanitize(official.name)}'s former staffer now lobbies for the companies "
                f"their committee is supposed to oversee."
            )
            severity = "notable_pattern"
        elif alert_type == "family_conflict":
            family_member = meta.get("family_member", "A family member")
            rel_label = meta.get("relationship_to_official", meta.get("relationship", "family"))
            headline = f"Family Tie: {_sanitize(official.name)}'s {rel_label} at {_sanitize(other.name)}"
            description = (
                f"{_sanitize(family_member)} of {_sanitize(official.name)} works at "
                f"{_sanitize(other.name)}. This creates a financial tie between the "
                f"official's family and a company that may be affected by their work."
            )
            plain_english = (
                f"Their {rel_label} gets a paycheck from {_sanitize(other.name)} while "
                f"they write the rules that company has to follow."
            )
            severity = "structural_relationship"
        elif alert_type == "speaking_fee":
            amount = r.amount_usd or meta.get("amount_usd", 0)
            amount_str = f"${amount / 100:,.0f}" if amount else "an undisclosed amount"
            headline = f"Speaking Fee: {_sanitize(official.name)} paid {amount_str} by {_sanitize(other.name)}"
            description = (
                f"{_sanitize(official.name)} received {amount_str} from {_sanitize(other.name)}. "
                f"When officials get paid by organizations they regulate, it creates a "
                f"personal financial relationship worth watching."
            )
            plain_english = (
                f"They got paid {amount_str} by a group that needs their vote. "
                f"Legal? Yes. Worth knowing? Absolutely."
            )
            severity = "connection_noted"
        elif alert_type == "contractor_donor":
            donation_amount = meta.get("donation_amount", r.amount_usd or 0)
            contract_amount = meta.get("contract_amount", 0)
            d_str = f"${donation_amount / 100:,.0f}" if donation_amount else "money"
            c_str = f"${contract_amount / 100:,.0f}" if contract_amount else "a government contract"
            headline = f"Donor-Contract: {_sanitize(other.name)} donated {d_str}, got {c_str} contract"
            description = (
                f"{_sanitize(other.name)} donated to {_sanitize(official.name)}'s campaign "
                f"and later received a government contract. The pattern is worth noting."
            )
            plain_english = (
                f"They donated {d_str} and then got a {c_str} government contract. "
                f"Coincidence? You decide."
            )
            severity = "notable_pattern"
        else:
            headline = f"Connection: {_sanitize(official.name)} and {_sanitize(other.name)}"
            description = f"A financial relationship was found between these entities."
            plain_english = f"A financial relationship that the public should know about."
            severity = "connection_noted"

        feed_items.append(HiddenConnectionsFeedItem(
            alert_type=alert_type,
            icon=ALERT_ICONS.get(alert_type, "🔍"),
            headline=headline,
            description=description,
            plain_english=plain_english,
            official_name=_sanitize(official.name),
            official_slug=official.slug,
            entity_slug=official.slug,
            entity_name=_sanitize(official.name),
            severity=severity,
            timestamp=date_str,
        ))

    # Also scan for suspicious trade timing (holds_stock with high info score)
    trade_rels_result = await db.execute(
        select(Relationship).where(
            Relationship.relationship_type == "holds_stock",
        ).limit(100)
    )
    trade_rels = trade_rels_result.scalars().all()

    trade_entity_ids = set()
    for r in trade_rels:
        trade_entity_ids.add(r.from_entity_id)
        trade_entity_ids.add(r.to_entity_id)
    trade_entity_ids -= set(entities_map.keys())
    if trade_entity_ids:
        ent_result = await db.execute(select(Entity).where(Entity.id.in_(trade_entity_ids)))
        for e in ent_result.scalars().all():
            entities_map[e.id] = e

    for r in trade_rels:
        meta = r.metadata_ or {}
        info_score = meta.get("information_access_score", 0)
        try:
            info_score = int(info_score)
        except (ValueError, TypeError):
            continue
        if info_score < 7:
            continue

        official = entities_map.get(r.from_entity_id)
        stock = entities_map.get(r.to_entity_id)
        if not official or not stock:
            continue

        tx_type = meta.get("transaction_type", "traded")
        tx_date = meta.get("transaction_date", str(r.date_start) if r.date_start else None)

        feed_items.append(HiddenConnectionsFeedItem(
            alert_type="trade_timing",
            icon=ALERT_ICONS["trade_timing"],
            headline=f"Suspicious Trade: {_sanitize(official.name)} {tx_type} {_sanitize(stock.name)}",
            description=(
                f"{_sanitize(official.name)} {tx_type} stock in {_sanitize(stock.name)} "
                f"with an information access score of {info_score}/10. This trade happened "
                f"when the official likely had inside information."
            ),
            plain_english=(
                f"They traded stock in a company their committee oversees, "
                f"right when they had inside information. Score: {info_score}/10."
            ),
            official_name=_sanitize(official.name),
            official_slug=official.slug,
            entity_slug=official.slug,
            entity_name=_sanitize(official.name),
            severity="high_concern" if info_score >= 9 else "notable_pattern",
            timestamp=tx_date,
        ))

    # Sort by severity (descending) then timestamp (descending)
    feed_items.sort(
        key=lambda x: (
            -SEVERITY_ORDER.get(x.severity, 0),
            x.timestamp or "",
        ),
        reverse=False,
    )
    # Actually we want highest severity first, then most recent
    feed_items.sort(
        key=lambda x: (
            SEVERITY_ORDER.get(x.severity, 0),
            x.timestamp or "0000-00-00",
        ),
        reverse=True,
    )

    return feed_items[:limit]
