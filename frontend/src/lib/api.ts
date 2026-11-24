export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type FindingStatus = "ok" | "risky" | "missing" | "uncertain";
export type RunStatus =
  | "queued"
  | "running"
  | "completed"
  | "completed_with_errors"
  | "failed";
export type DecisionState = "pending" | "accepted" | "edited" | "rejected";

export type BBox = [number, number, number, number];

export interface UploadResponse {
  contract_id: string;
  page_count: number;
}

export interface DecisionView {
  state: DecisionState;
  edited_text: string | null;
  decided_at: string;
}

export interface Candidate {
  chunk_id: string;
  page: number;
  text: string;
}

export interface FindingView {
  id: string;
  clause_id: string;
  clause_title: string;
  status: FindingStatus;
  severity: string | null;
  quote: string | null;
  page: number | null;
  bboxes: BBox[];
  candidates: Candidate[];
  playbook_rule: string;
  issues: string[];
  rationale: string | null;
  suggestion_text: string | null;
  suggestion_explanation: string | null;
  error: string | null;
  verify_failures: number;
  decision: DecisionView | null;
}

export interface RunView {
  run_id: string;
  contract_id: string;
  status: RunStatus;
  model: string;
  started_at: string | null;
  finished_at: string | null;
  progress: Record<string, string>;
  findings: FindingView[];
}

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

function detailOf(body: unknown, fallback: string): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => (item as { msg?: string }).msg)
      .filter(Boolean)
      .join("; ");
  }
  return fallback;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, init);
  } catch {
    throw new ApiError(0, `Cannot reach the API at ${API_URL}`);
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(
      response.status,
      detailOf(body, `Request failed (${response.status})`),
    );
  }
  return (await response.json()) as T;
}

export function uploadContract(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  return request("/api/contracts", { method: "POST", body: form });
}

export function analyze(contractId: string): Promise<{ run_id: string }> {
  return request(`/api/contracts/${contractId}/analyze`, { method: "POST" });
}

export function getRun(runId: string): Promise<RunView> {
  return request(`/api/runs/${runId}`, { cache: "no-store" });
}

export function putDecision(
  findingId: string,
  body: { state: DecisionState; edited_text?: string },
): Promise<DecisionView> {
  return request(`/api/findings/${findingId}/decision`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function pdfUrl(contractId: string): string {
  return `${API_URL}/api/contracts/${contractId}/pdf`;
}
