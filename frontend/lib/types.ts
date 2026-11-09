export interface Paper {
  title: string;
  authors: string[];
  year: number;
  venue: string;
  abstract: string;
  url: string;
  source: string;
  doi?: string;
  arxiv_id?: string;
  citationCount: number;
  score?: number;
  score_reason?: string;
  locked?: boolean;
  aliases?: string[];
}

export interface VerifyItem {
  ref: number;
  ok: boolean;
  matched_title?: string;
  doi?: string;
  matched_year?: number;
  ratio?: number;
  detail?: string;
}

export type Tab = "survey" | "papers" | "verify" | "bib";

export type RunStatus =
  | "idle"
  | "created"
  | "running"
  | "paused"
  | "finished"
  | "error";

export type NodeStatus = "pending" | "running" | "waiting" | "done" | "error";

export const NODE_ORDER = [
  "planner",
  "retriever",
  "screening",
  "writer",
  "verifier",
  "bib_generator",
  "pdf_ingest",
  "human_review",
] as const;

export const NODE_LABELS: Record<string, string> = {
  planner: "主题规划",
  retriever: "多源检索",
  screening: "去重筛选",
  writer: "综述撰写",
  verifier: "引用核验",
  bib_generator: "BibTeX 生成",
  pdf_ingest: "PDF 入库",
  human_review: "人工审核",
};

export interface SSEEvent {
  type: string;
  node?: string;
  message?: string;
  content?: string;
  status?: string;
  data?: Record<string, unknown>;
  session_id?: string;
  topic?: string;
  state?: Record<string, unknown>;
}
