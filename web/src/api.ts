export class ApiError extends Error {
  constructor(
    message: string,
    public code: string,
    public status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function metaToken(name: string): string {
  return (
    document.querySelector<HTMLMetaElement>(`meta[name="${name}"]`)?.content ??
    ""
  );
}

/** Tokens are read from this server-rendered document, never persisted or included in URLs. */
export async function api<T>(
  path: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  return request<T>(path, body, signal);
}

export interface AuditReport {
  ok: boolean;
  operation: string;
  report: unknown;
  exit_code: number;
  adapter_sha256: string;
  semantic_acceptance: "not_performed";
}

/** Only the audit endpoint treats an explicit report with ok:false as findings. */
export async function auditProject(
  projectId: string,
  body: unknown,
): Promise<AuditReport> {
  return request<AuditReport>(
    `/projects/${segment(projectId)}/audit`,
    body,
    undefined,
    true,
  );
}

async function request<T>(
  path: string,
  body?: unknown,
  signal?: AbortSignal,
  allowAuditFindings = false,
): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    headers["X-CSRF-Token"] = metaToken("research-hub-csrf-token");
    if (/^\/(tasks|actions)\/[^/]+\/decision$/.test(path)) {
      const token = metaToken("research-hub-human-token");
      if (token) headers["X-Human-Token"] = token;
    }
  }
  const response = await fetch(`/api/v1${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers,
    credentials: "same-origin",
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  });
  let value: {
    ok?: boolean;
    error?: string;
    code?: string;
    report?: unknown;
    operation?: string;
    exit_code?: number;
    adapter_sha256?: string;
    semantic_acceptance?: string;
  };
  try {
    value = await response.json();
  } catch {
    throw new ApiError(
      `The server returned an unreadable response (HTTP ${response.status}).`,
      "invalid_response",
      response.status,
    );
  }
  if (!value || typeof value !== "object")
    throw new ApiError(
      "The server returned an invalid response.",
      "invalid_response",
      response.status,
    );
  const auditFindings =
    allowAuditFindings &&
    value.ok === false &&
    Object.hasOwn(value, "report") &&
    typeof value.exit_code === "number" &&
    typeof value.operation === "string" &&
    typeof value.adapter_sha256 === "string" &&
    value.semantic_acceptance === "not_performed";
  if ((!response.ok && !(response.status === 400 && auditFindings)) || (value.ok !== true && !auditFindings)) {
    throw new ApiError(
      value.error || `The request failed (HTTP ${response.status}).`,
      value.code || "request_failed",
      response.status,
    );
  }
  return value as T;
}

export const segment = (value: string): string => encodeURIComponent(value);
export function safeSourceUrl(locator: unknown): string | undefined {
  if (typeof locator !== "string") return;
  try {
    const url = new URL(locator);
    if (url.protocol === "https:" || url.protocol === "http:") return url.href;
  } catch {
    /* A plain locator remains visible as text. */
  }
}
export function downloadPacket(packet: unknown, taskId: string): void {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(packet, null, 2)], { type: "application/json" }),
  );
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `research-task-${taskId.replace(/[^a-zA-Z0-9_-]/g, "_")}.json`;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
