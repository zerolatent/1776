export type RuleCard = {
  id: number;
  agency: string;
  title: string;
  tac_citation: string;
  action_type: string;
  status: string;
  summary: string;
  why_matters: string;
  heard_signal: string;
  source_url: string;
  forecast_count: number;
  watched: boolean;
};

export type CommentResponse = {
  id: number;
  concern: string;
  agency_response: string;
  disposition: string;
  evidence_source_id?: number;
};

export type Finding = {
  id: number;
  label: string;
  summary: string;
  source_id?: number;
};

export type AuthorityLink = {
  id: number;
  citation: string;
  url: string;
  summary: string;
};

export type RuleDetail = RuleCard & {
  affected_groups: string[];
  top_concerns: CommentResponse[];
  findings: Finding[];
  authority_links: AuthorityLink[];
};

export type Brief = {
  rule_id: number;
  plain_summary: string;
  affected_groups: string[];
  status_text: string;
  public_heard_signal: string;
  body: string;
  source_ids: number[];
};

export type SourceRef = {
  id: number;
  label: string;
  url: string;
  snippet: string;
};

export type ForecastCard = {
  id: number;
  rule_id: number;
  question: string;
  resolution_criteria: string;
  source_of_truth: string;
  status: string;
  aggregate_probability: number;
  user_probability?: number;
};

export type AlertItem = {
  id: number;
  title: string;
  body: string;
  source_url: string;
  read: boolean;
  created_at: string;
};

export type Session = {
  token: string;
  user_id: number;
  name: string;
  email: string;
};
