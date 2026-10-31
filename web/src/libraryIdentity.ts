import type { ResearchRecord } from "./types";

export function libraryIdentity(record: ResearchRecord): string | null {
  const doi = typeof record.data.doi === "string" ? record.data.doi.trim().replace(/^https?:\/\/(?:dx\.)?doi\.org\//i, "").replace(/^doi:\s*/i, "").toLowerCase() : "";
  if (/^10\.\d{4,9}\/\S+$/.test(doi)) return `doi:${doi}`;
  if (typeof record.data.locator !== "string") return null;
  try {
    const url = new URL(record.data.locator);
    if (!["http:", "https:"].includes(url.protocol)) return null;
    if (/^(dx\.)?doi\.org$/i.test(url.hostname)) {
      const path = decodeURIComponent(url.pathname.slice(1)).toLowerCase();
      if (/^10\.\d{4,9}\/\S+$/.test(path)) return `doi:${path}`;
    }
    url.hash = "";
    return `url:${url.href}`;
  } catch { return null; }
}

export function identityMatches(records: ResearchRecord[]): Map<string, ResearchRecord[]> {
  const groups = new Map<string, ResearchRecord[]>();
  for (const record of records) {
    const identity = libraryIdentity(record);
    if (identity) groups.set(identity, [...(groups.get(identity) ?? []), record]);
  }
  return new Map(records.map((record) => [record.id, (groups.get(libraryIdentity(record) ?? "") ?? []).filter((other) => other.id !== record.id)]));
}
