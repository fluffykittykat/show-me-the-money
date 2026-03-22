import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class EntityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    entity_type: str
    name: str
    summary: Optional[str] = None
    metadata: dict = Field(default={}, validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime


class EntityBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    entity_type: str
    name: str
    summary: Optional[str] = None


class FlatConnectionItem(BaseModel):
    """A relationship with the connected entity embedded — flat structure for frontend."""

    id: uuid.UUID
    from_entity_id: uuid.UUID
    to_entity_id: uuid.UUID
    relationship_type: str
    amount_usd: Optional[int] = None
    amount_label: Optional[str] = None
    date_start: Optional[date] = None
    date_end: Optional[date] = None
    source_url: Optional[str] = None
    source_label: Optional[str] = None
    metadata: dict = {}
    connected_entity: Optional[EntityBrief] = None


class ConnectionsResponse(BaseModel):
    entity: EntityResponse
    connections: list[FlatConnectionItem]
    total: int


class EntityListResponse(BaseModel):
    results: list[EntityBrief]
    total: int
    limit: int
    offset: int


class SearchResponse(BaseModel):
    query: str
    entity_type: Optional[str] = None
    results: list[EntityBrief]
    total: int
    limit: int
    offset: int


class GraphNode(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    entity_type: str


class GraphEdge(BaseModel):
    source: uuid.UUID
    target: uuid.UUID
    relationship_type: str
    amount_label: Optional[str] = None


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    center_slug: str


class BriefingResponse(BaseModel):
    entity_slug: str
    entity_name: str
    briefing_text: str
    generated_at: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    version: str


class ConfigEntryResponse(BaseModel):
    key: str
    description: str
    is_secret: bool
    is_configured: bool
    masked_value: Optional[str] = None
    source: str  # "database", "env_var", "default", "not_set"


class ConfigSetRequest(BaseModel):
    value: str
