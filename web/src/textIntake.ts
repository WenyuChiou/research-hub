import { isBlobArtifact, previewMatchesArtifact } from "./sourceStorage";
import { ApiError } from "./api";
import type { TextPreview } from "./AbstractDraft";
import type { Artifact, ResearchRecord, Workspace } from "./types";

export const TEXT_LIMIT = 40000;
export const requestUUID =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
export interface IntakePayload {
  title: string;
  locator: string;
  reading_scope: "abstract" | "unknown";
  input_kind: "paste" | "file";
  format: "txt" | "md";
  content_base64: string;
}
export interface SavedText {
  record: ResearchRecord;
  artifact: Artifact & {
    project_id: string;
    source_record_id: string;
    origin: string;
  };
  preview: TextPreview | null;
  preview_status: "available" | "stale" | "unavailable";
}
export interface EncodedText {
  text: string;
  content_base64: string;
  bytes: number;
  format: "txt" | "md";
}
export function intakeSupported(
  cap: Workspace["capabilities"]["text_intake"],
): boolean {
  return Boolean(
    cap?.version === 1 &&
    cap.status === "available" &&
    typeof cap.workspace_instance_id === "string" &&
    requestUUID.test(cap.workspace_instance_id) &&
    cap.max_source_bytes === TEXT_LIMIT &&
    Array.isArray(cap.formats) &&
    cap.formats.includes("txt") &&
    cap.formats.includes("md") &&
    (!("storage" in cap) ||
      (cap.storage?.kind === "workspace_blob" &&
        cap.storage.version === 1 &&
        Object.keys(cap.storage).length === 2 &&
        cap.experimental === true)),
  );
}
export function validUnicode(value: string): boolean {
  for (let i = 0; i < value.length; i++) {
    const c = value.charCodeAt(i);
    if (c >= 0xd800 && c <= 0xdbff) {
      const next = value.charCodeAt(++i);
      if (!(next >= 0xdc00 && next <= 0xdfff)) return false;
    } else if (c >= 0xdc00 && c <= 0xdfff) return false;
  }
  return true;
}
export function encodeTextBytes(
  bytes: Uint8Array,
  format: "txt" | "md",
): EncodedText {
  if (!bytes.length || bytes.length > TEXT_LIMIT)
    throw new ApiError(
      "Choose 1–40,000 bytes of text; nothing is truncated.",
      "context_limit",
      400,
    );
  let text: string;
  try {
    text = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(
      bytes,
    );
  } catch {
    throw new ApiError(
      "This file is not strict UTF-8. No replacement characters or converted copy were saved.",
      "invalid_source",
      400,
    );
  }
  if (!text.replace(/^\ufeff+/, "").trim() || text.includes("\0"))
    throw new ApiError(
      "Choose nonempty text without NUL bytes.",
      "invalid_source",
      400,
    );
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return { text, bytes: bytes.length, format, content_base64: btoa(binary) };
}
export function encodePaste(text: string): EncodedText {
  if (!validUnicode(text))
    throw new ApiError(
      "Pasted text contains an invalid Unicode surrogate; no text was saved.",
      "invalid_source",
      400,
    );
  return encodeTextBytes(new TextEncoder().encode(text), "txt");
}
export async function readTextFile(
  file: File,
  signal: AbortSignal,
): Promise<EncodedText> {
  const extension = /\.(txt|md)$/i.exec(file.name)?.[1].toLowerCase() as
    | "txt"
    | "md"
    | undefined;
  if (!extension)
    throw new ApiError(
      "Choose an existing .txt or .md file, not a PDF.",
      "unsupported_source",
      400,
    );
  if (!file.size || file.size > TEXT_LIMIT)
    throw new ApiError(
      "Choose 1–40,000 bytes; the original file is not changed or truncated.",
      "context_limit",
      400,
    );
  const bytes = await new Promise<ArrayBuffer>((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException("Cancelled", "AbortError"));
      return;
    }
    const reader = new FileReader();
    const abort = () => {
      reader.abort();
      reject(new DOMException("Cancelled", "AbortError"));
    };
    signal.addEventListener("abort", abort, { once: true });
    reader.onload = () => {
      signal.removeEventListener("abort", abort);
      if (reader.result instanceof ArrayBuffer) resolve(reader.result);
      else reject(new Error("File bytes unavailable"));
    };
    reader.onerror = () => {
      signal.removeEventListener("abort", abort);
      reject(new Error("Could not read the selected file; nothing was saved"));
    };
    reader.readAsArrayBuffer(file);
  });
  if (signal.aborted) throw new DOMException("Cancelled", "AbortError");
  return encodeTextBytes(new Uint8Array(bytes), extension);
}
export function validSavedText(
  value: unknown,
  projectId: string,
  key: string,
): value is SavedText {
  if (!value || typeof value !== "object") return false;
  const v = value as SavedText;
  const a = v.artifact,
    r = v.record;
  const binding = r?.data?.intake as Record<string, unknown> | undefined;
  if (
    !r ||
    typeof r.id !== "string" ||
    !r.id ||
    r.kind !== "source" ||
    !a ||
    typeof a.id !== "string" ||
    !a.id ||
    a.project_id !== projectId ||
    a.source_record_id !== r.id ||
    a.origin !== "hub-text-intake" ||
    a.role !== "evidence" ||
    !/^[0-9a-f]{64}$/.test(a.sha256) ||
    binding?.version !== 1 ||
    binding.key !== key ||
    binding.artifact_id !== a.id ||
    binding.sha256 !== a.sha256 ||
    ("storage" in a && (!isBlobArtifact(a) || binding.format !== a.format))
  )
    return false;
  if (v.preview_status === "unavailable" || v.preview_status === "stale")
    return v.preview === null && a.current === false;
  const p = v.preview;
  return Boolean(
    v.preview_status === "available" &&
    a.current === true &&
    p &&
    p.artifact_id === a.id &&
    p.sha256 === a.sha256 &&
    previewMatchesArtifact(p, a) &&
    p.truncated === false &&
    typeof p.text === "string" &&
    validUnicode(p.text) &&
    p.codepoint_length === Array.from(p.text).length &&
    p.bytes_read === new TextEncoder().encode(p.text).length &&
    p.bytes_read > 0 &&
    p.bytes_read <= TEXT_LIMIT,
  );
}
