import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Entity(Base):
    __tablename__ = "entities"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    slug: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )

    outgoing_relationships: Mapped[list["Relationship"]] = relationship(
        "Relationship",
        foreign_keys="Relationship.from_entity_id",
        back_populates="from_entity",
        cascade="all, delete-orphan",
    )
    incoming_relationships: Mapped[list["Relationship"]] = relationship(
        "Relationship",
        foreign_keys="Relationship.to_entity_id",
        back_populates="to_entity",
        cascade="all, delete-orphan",
    )
    data_sources: Mapped[list["DataSource"]] = relationship(
        "DataSource", back_populates="entity", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_entities_slug", "slug"),
        Index("ix_entities_entity_type", "entity_type"),
    )


class Relationship(Base):
    __tablename__ = "relationships"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    from_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    to_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    relationship_type: Mapped[str] = mapped_column(String(100), nullable=False)
    amount_usd: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    amount_label: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    date_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    date_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_label: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, server_default=text("'{}'::jsonb")
    )

    from_entity: Mapped["Entity"] = relationship(
        "Entity", foreign_keys=[from_entity_id], back_populates="outgoing_relationships"
    )
    to_entity: Mapped["Entity"] = relationship(
        "Entity", foreign_keys=[to_entity_id], back_populates="incoming_relationships"
    )

    __table_args__ = (
        Index("ix_relationships_from_entity_id", "from_entity_id"),
        Index("ix_relationships_to_entity_id", "to_entity_id"),
        Index("ix_relationships_relationship_type", "relationship_type"),
    )


class DataSource(Base):
    __tablename__ = "data_sources"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_type: Mapped[str] = mapped_column(String(100), nullable=False)
    external_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    raw_payload: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    fetched_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )

    entity: Mapped["Entity"] = relationship("Entity", back_populates="data_sources")


class AppConfig(Base):
    __tablename__ = "app_config"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_secret: Mapped[bool] = mapped_column(
        server_default=text("true"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    job_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), server_default=text("'pending'"), nullable=False
    )
    progress: Mapped[int] = mapped_column(
        server_default=text("0"), nullable=False
    )
    total: Mapped[int] = mapped_column(
        server_default=text("0"), nullable=False
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    errors: Mapped[list] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )

    __table_args__ = (
        Index("ix_ingestion_jobs_status", "status"),
        Index("ix_ingestion_jobs_job_type_status", "job_type", "status"),
    )


class MoneyTrail(Base):
    """Pre-computed money trail for an official, grouped by industry."""
    __tablename__ = "money_trails"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    official_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id"), index=True
    )
    industry: Mapped[str] = mapped_column(String(200))
    verdict: Mapped[str] = mapped_column(String(20))  # NORMAL, CONNECTED, INFLUENCED, OWNED
    dot_count: Mapped[int] = mapped_column(Integer, default=0)
    narrative: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    chain: Mapped[dict] = mapped_column(
        "chain_data", JSONB, server_default=text("'{}'::jsonb")
    )
    total_amount: Mapped[int] = mapped_column(BigInteger, default=0)  # cents
    computed_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )


class BillInfluenceSignal(Base):
    """Pre-computed influence signal for a bill."""
    __tablename__ = "bill_influence_signals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    bill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id"), index=True
    )
    signal_type: Mapped[str] = mapped_column(String(30))
    found: Mapped[bool] = mapped_column(Boolean, default=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    rarity_pct: Mapped[float] = mapped_column(Float, nullable=True)
    rarity_label: Mapped[str] = mapped_column(String(20), nullable=True)
    p_value: Mapped[float] = mapped_column(Float, nullable=True)
    baseline_rate: Mapped[float] = mapped_column(Float, nullable=True)
    observed_rate: Mapped[float] = mapped_column(Float, nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    evidence: Mapped[dict] = mapped_column(
        "evidence_data", JSONB, server_default=text("'{}'::jsonb")
    )
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class OfficialInfluenceSignal(Base):
    """Pre-computed influence signal for an official."""
    __tablename__ = "official_influence_signals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    official_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id"), index=True
    )
    signal_type: Mapped[str] = mapped_column(String(30))
    found: Mapped[bool] = mapped_column(Boolean, default=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    rarity_pct: Mapped[float] = mapped_column(Float, nullable=True)
    rarity_label: Mapped[str] = mapped_column(String(20), nullable=True)
    p_value: Mapped[float] = mapped_column(Float, nullable=True)
    baseline_rate: Mapped[float] = mapped_column(Float, nullable=True)
    observed_rate: Mapped[float] = mapped_column(Float, nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    evidence: Mapped[dict] = mapped_column(
        "evidence_data", JSONB, server_default=text("'{}'::jsonb")
    )
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TradeAlert(Base):
    __tablename__ = "trade_alerts"
    __table_args__ = (
        Index("ix_trade_alerts_official_id", "official_id"),
        Index("ix_trade_alerts_ticker", "ticker"),
        Index("ix_trade_alerts_status", "status"),
        Index("ix_trade_alerts_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    relationship_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("relationships.id"), unique=True, nullable=False,
    )
    official_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id"), nullable=False,
    )
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    transaction_type: Mapped[Optional[str]] = mapped_column(String(50))
    amount_label: Mapped[Optional[str]] = mapped_column(String(100))
    trade_date: Mapped[Optional[date]] = mapped_column(Date)
    filed_date: Mapped[Optional[date]] = mapped_column(Date)
    alert_level: Mapped[str] = mapped_column(String(30), default="ROUTINE")
    narrative: Mapped[Optional[str]] = mapped_column(Text)
    signals: Mapped[dict] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    context: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    source: Mapped[str] = mapped_column(String(30), default="senate_efd")
    status: Mapped[str] = mapped_column(String(20), default="new")
    notified_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"),
    )


class AlertSubscription(Base):
    __tablename__ = "alert_subscriptions"
    __table_args__ = (
        Index("ix_alert_subs_type_target", "sub_type", "target_value"),
        Index("ix_alert_subs_channel_active", "channel", "is_active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    sub_type: Mapped[str] = mapped_column(String(20), nullable=False)
    target_value: Mapped[str] = mapped_column(String(200), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), default="feed")
    channel_target: Mapped[Optional[str]] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"),
    )
