export interface Entity {
  id: string;
  slug: string;
  entity_type: 'person' | 'company' | 'bill' | 'organization' | 'industry' | 'pac';
  name: string;
  summary: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface Relationship {
  id: string;
  from_entity_id: string;
  to_entity_id: string;
  relationship_type: string;
  amount_usd: number | null;
  amount_label: string | null;
  date_start: string | null;
  date_end: string | null;
  source_url: string | null;
  source_label: string | null;
  metadata: Record<string, unknown>;
  connected_entity?: Entity;
}

export interface ConnectionsResponse {
  entity: Entity;
  connections: Relationship[];
  total: number;
}

export interface SearchResponse {
  results: Entity[];
  total: number;
  query: string;
}

export interface GraphNode {
  id: string;
  slug: string;
  name: string;
  entity_type: string;
}

export interface GraphEdge {
  source: string;
  target: string;
  relationship_type: string;
  amount_label: string | null;
}

export interface GraphResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
  center_slug: string;
}

export interface BriefingResponse {
  entity_slug: string;
  entity_name: string;
  briefing_text: string;
  generated_at: string | null;
}

export interface ConfigEntry {
  key: string;
  description: string;
  is_secret: boolean;
  is_configured: boolean;
  masked_value: string | null;
  source: 'database' | 'env_var' | 'default' | 'not_set';
}
