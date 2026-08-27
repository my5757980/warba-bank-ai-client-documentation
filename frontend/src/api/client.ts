/**
 * API client (task T078).
 *
 * Error handling is deliberate: the backend returns plain, non-technical messages
 * (FR-038, NFR-UX-02), so this client surfaces the backend's message rather than
 * substituting its own. Two status codes carry specific meaning the UI must not
 * flatten into "something went wrong":
 *
 *   451 — the draft was blocked by Shariah screening. No document exists.
 *   422 — validation rejected the draft, usually an unsupported figure. No document.
 *
 * In both cases the system caught something. Telling the RM "an error occurred" would
 * hide the fact that a control worked.
 */

import type {
  ApiError,
  ApprovalRecord,
  AssembledContext,
  ClientSummary,
  DocumentDetail,
  DocumentType,
  Evidence,
  LoginResponse,
} from "@/types/api";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";
const TOKEN_KEY = "warba.token";

export class RequestError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly detail?: Record<string, unknown>,
  ) {
    super(message);
    this.name = "RequestError";
  }

  /** The draft was blocked by Shariah screening. No document was produced. */
  get isScreeningBlocked(): boolean {
    return this.status === 451;
  }

  /** Validation rejected the draft — typically an unsupported figure. */
  get isValidationFailure(): boolean {
    return this.status === 422 && this.code === "GENERATION_VALIDATION_FAILED";
  }

  /** The document changed since it was loaded (FR-040). */
  get isStale(): boolean {
    return this.status === 412;
  }

  get hasUnresolvedGaps(): boolean {
    return this.code === "UNRESOLVED_GAPS";
  }
}

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* private browsing — the session simply does not persist across reloads */
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();

  const response = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init.headers,
    },
  });

  if (response.status === 204) return undefined as T;

  const body = await response.json().catch(() => null);

  if (!response.ok) {
    // Two error shapes reach us. Our own handlers return the error flat —
    // `{ code, message, detail }` — where `detail` carries the payload the UI needs
    // (the Shariah findings, for instance). FastAPI's built-in HTTPException instead
    // nests the whole error under `detail`.
    //
    // Unwrap only the nested shape, and identify it by the presence of `code` inside
    // `detail`. Unwrapping unconditionally discards our own `code` and `message` and
    // hands the UI the findings object in their place — which is how a Shariah block
    // came to read "The request could not be completed."
    const nested =
      body?.detail && typeof body.detail === "object" && "code" in body.detail;
    const payload: ApiError = (nested ? body.detail : body) ?? {};
    throw new RequestError(
      response.status,
      payload.code ?? "UNKNOWN",
      payload.message ?? "The request could not be completed.",
      payload.detail,
    );
  }

  return body as T;
}

export const api = {
  login: (email: string, password: string) =>
    request<LoginResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  me: () => request<import("@/types/api").User>("/auth/me"),

  listClients: (search?: string) =>
    request<ClientSummary[]>(`/clients${search ? `?search=${encodeURIComponent(search)}` : ""}`),

  getContext: (clientId: string, documentType: DocumentType) =>
    request<AssembledContext>(`/clients/${clientId}/context?document_type=${documentType}`),

  generate: (payload: {
    client_id: string;
    document_type: DocumentType;
    meeting_notes?: string;
    client_record_ids?: string[];
    source_document_ids?: string[];
    rm_instruction?: string;
  }) => request<DocumentDetail>("/documents", { method: "POST", body: JSON.stringify(payload) }),

  getDocument: (id: string) => request<DocumentDetail>(`/documents/${id}`),

  getEvidence: (documentId: string, claimId: string) =>
    request<Evidence>(`/documents/${documentId}/evidence/${claimId}`),

  editSection: (
    documentId: string,
    sectionKey: string,
    contentHash: string,
    payload: { content: string | null; resolved_gaps?: Array<{ field: string; resolution_note: string }> },
  ) =>
    request<DocumentDetail>(`/documents/${documentId}/sections/${sectionKey}`, {
      method: "PATCH",
      // Optimistic concurrency: the server refuses if the document moved (FR-040).
      headers: { "If-Match": contentHash },
      body: JSON.stringify(payload),
    }),

  regenerateSection: (documentId: string, sectionKey: string, instruction?: string) =>
    request<DocumentDetail>(`/documents/${documentId}/sections/${sectionKey}/regenerate`, {
      method: "POST",
      body: JSON.stringify({ instruction }),
    }),

  reject: (documentId: string, reason?: string) =>
    request<DocumentDetail>(`/documents/${documentId}/reject`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),

  /**
   * Download an approved document.
   *
   * Only APPROVED documents export, so this is never offered on a draft. The blob is
   * handed to the browser rather than opened, because the file carries the approval
   * record and is meant to be filed, not skimmed.
   */
  exportDocument: async (documentId: string): Promise<{ blob: Blob; filename: string }> => {
    const token = getToken();
    const response = await fetch(`${BASE_URL}/documents/${documentId}/export?format=docx`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });

    if (!response.ok) {
      const body = await response.json().catch(() => null);
      const payload: ApiError = body?.detail ?? body ?? {};
      throw new RequestError(
        response.status,
        payload.code ?? "UNKNOWN",
        payload.message ?? "The document could not be exported.",
      );
    }

    const disposition = response.headers.get("Content-Disposition") ?? "";
    const match = /filename="([^"]+)"/.exec(disposition);

    return { blob: await response.blob(), filename: match?.[1] ?? "document.docx" };
  },

  /**
   * Approve a document — the only transition into APPROVED.
   *
   * `confirm_reviewed` is passed as a literal true and `content_hash` names the exact
   * version. Both are required by the server; neither has a default. The UI must never
   * send these without the RM having actually clicked through the confirmation.
   */
  approve: (
    documentId: string,
    contentHash: string,
    acknowledgeGaps: Array<{ section_key: string; field: string; note: string }> = [],
  ) =>
    request<ApprovalRecord>(`/documents/${documentId}/approve`, {
      method: "POST",
      body: JSON.stringify({
        content_hash: contentHash,
        confirm_reviewed: true,
        acknowledge_gaps: acknowledgeGaps,
      }),
    }),
};
