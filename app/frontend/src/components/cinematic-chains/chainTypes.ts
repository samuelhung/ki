export interface GlobalShare {
  c: string;
  p: number; p_export_global: number; p_export_ratio: number; p_export_national: number;
  d: number; d_import_global: number; d_import_ratio: number; d_import_national: number;
}

export interface Substitute {
  node: string; maturity: string; trigger: string; advantage: string; bottleneck: string;
}

export interface ChainNode {
  id: string; chain: string; name: string; node_type: string; description: string;
  global_shares: GlobalShare[]; substitutes: Substitute[]; upstream_ids: string[];
  data_sources: Record<string, string>; sort_order: number; last_updated?: string;
}

export interface ChainHint {
  id: string; event_id: string; node_id: string; chain: string; field: string;
  current_value: string; suggested_value: string; source_quote: string;
  confidence: number; status: string; node_name: string;
}

export interface ChainSuggestionNode {
  name?: string;
  node_type?: string;
  description?: string;
  initial_data?: string;
}

export interface ChainSuggestion {
  id: string; chain_name: string; event_id: string; nodes_json: ChainSuggestionNode[];
  reason: string; source_quote: string; confidence: number; status: string;
  created_at: string;
}
