// Mirrors the API's Pydantic models (src/app/research/schemas.py, src/app/routes/research.py).

export type RunStatus = "queued" | "running" | "succeeded" | "failed";

export type ProgressStep =
  | "queued"
  | "planning"
  | "finding_competitors"
  | "researching"
  | "verifying"
  | "analyzing_gaps"
  | "done"
  | "failed";

export interface Progress {
  step: ProgressStep;
  message: string;
  completed: number;
  total: number;
}

export type ClaimCategory =
  | "product"
  | "target_customer"
  | "positioning"
  | "feature"
  | "strength"
  | "weakness"
  | "customer_praise"
  | "customer_complaint"
  | "other";

interface Cited {
  id: string;
  source_url: string;
  quote: string;
  verified: boolean;
  note: string;
}

export interface Claim extends Cited {
  category: ClaimCategory;
  text: string;
}

export interface PricePlan extends Cited {
  plan_name: string;
  price: string;
}

export interface Source {
  url: string;
  title: string | null;
  kind: "site" | "review";
}

export interface Competitor {
  rank: number;
  name: string;
  homepage_url: string;
  why_competitor: string;
  pricing: PricePlan[];
  claims: Claim[];
  sources: Source[];
}

export interface MarketGap {
  title: string;
  description: string;
  how_to_stand_out: string;
  evidence_ids: string[];
  supported: boolean;
}

export interface Report {
  idea: string;
  generated_at: string;
  model: string;
  search_queries: string[];
  competitors: Competitor[];
  gaps: MarketGap[];
  stats: {
    claims_total: number;
    claims_verified: number;
    prices_total: number;
    prices_verified: number;
    gaps_supported: number;
    gaps_unsupported: number;
  };
  usage: { latency_s: number; llm_calls: number; trace_url: string | null } | null;
  errors: string[];
}

export interface Run {
  id: string;
  idea: string;
  status: RunStatus;
  progress: Progress | null;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  report?: Report | null;
}
