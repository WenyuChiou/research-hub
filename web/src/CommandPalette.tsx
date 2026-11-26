import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { sourceTags } from "./LiteratureLibrary";
import type { Locale, Page, Project, ResearchRecord } from "./types";

const asText = (value: unknown): string =>
  typeof value === "string" || typeof value === "number" ? String(value) : "";

function extractAuthorString(authors: unknown): string {
  if (typeof authors === "string") return authors.trim();
  if (!Array.isArray(authors)) return "";
  return authors
    .map((item) => {
      if (typeof item === "string") return item.trim();
      if (item && typeof item === "object") {
        const obj = item as Record<string, unknown>;
        return [asText(obj.family), asText(obj.given), asText(obj.name)]
          .filter(Boolean)
          .join(" ")
          .trim();
      }
      return "";
    })
    .filter(Boolean)
    .join(", ");
}

/**
 * Reference-counted background isolation for stacked/nested portal dialogs
 * (e.g. Ctrl+K CommandPalette opened on top of AgentHandoffModal) so closing
 * multiple modals in any order deterministically restores document.body children.
 */
export function acquireModalBackgroundLock(excludeEl: HTMLElement | null): () => void {
  const lockedElements: HTMLElement[] = [];
  for (const child of Array.from(document.body.children)) {
    if (child === excludeEl || !(child instanceof HTMLElement)) continue;
    // Never mark another active modal portal backdrop inert when opening a top-most overlay,
    // wait — hiding underlying modal + app shell while the top-most modal is open is desired,
    // and reference counting guarantees exact restoration when each modal closes!
    const count = Number.parseInt(child.dataset.hubModalLocks || "0", 10) || 0;
    if (count === 0) {
      const prevAria = child.getAttribute("aria-hidden");
      child.dataset.hubPrevAriaHidden = prevAria === null ? "__none__" : prevAria;
      const prevInert =
        child.hasAttribute("inert") ||
        Boolean((child as HTMLElement & { inert?: boolean }).inert);
      child.dataset.hubPrevInert = prevInert ? "1" : "0";
      child.setAttribute("aria-hidden", "true");
      child.setAttribute("inert", "");
      (child as HTMLElement & { inert?: boolean }).inert = true;
    }
    child.dataset.hubModalLocks = String(count + 1);
    lockedElements.push(child);
  }

  let released = false;
  return () => {
    if (released) return;
    released = true;
    for (const el of lockedElements) {
      const current = Number.parseInt(el.dataset.hubModalLocks || "1", 10) || 1;
      const next = Math.max(0, current - 1);
      if (next > 0) {
        el.dataset.hubModalLocks = String(next);
        el.setAttribute("aria-hidden", "true");
        el.setAttribute("inert", "");
        (el as HTMLElement & { inert?: boolean }).inert = true;
      } else {
        delete el.dataset.hubModalLocks;
        const savedAria = el.dataset.hubPrevAriaHidden;
        delete el.dataset.hubPrevAriaHidden;
        if (!savedAria || savedAria === "__none__") {
          el.removeAttribute("aria-hidden");
        } else {
          el.setAttribute("aria-hidden", savedAria);
        }
        const savedInert = el.dataset.hubPrevInert === "1";
        delete el.dataset.hubPrevInert;
        if (!savedInert) {
          el.removeAttribute("inert");
          (el as HTMLElement & { inert?: boolean }).inert = false;
        } else {
          el.setAttribute("inert", "");
          (el as HTMLElement & { inert?: boolean }).inert = true;
        }
      }
    }
  };
}

/**
 * Global keyboard shortcut listener (`Ctrl+K` / `⌘K`).
 */
export function useCommandPaletteShortcut(onToggle: () => void): void {
  const callbackRef = useRef(onToggle);
  callbackRef.current = onToggle;

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (
        (event.ctrlKey || event.metaKey) &&
        !event.altKey &&
        event.key.toLowerCase() === "k"
      ) {
        event.preventDefault();
        callbackRef.current();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);
}

const PALETTE_COPY = {
  "zh-TW": {
    dialogTitle: "全域指令面板",
    placeholder: "搜尋指令、切換研究主題，或輸入標題 / 作者 / 年份 / DOI / #標籤…",
    groupQuick: "快速動作",
    groupProjects: "切換研究主題",
    groupPapers: "跳轉至文獻閱讀台",
    toggleDark: "切換為深色模式",
    toggleLight: "切換為淺色模式",
    openSettings: "開啟設定與軟體連線",
    navOverview: "前往：研究總覽 (Overview)",
    navLiterature: "前往：文獻庫 (Literature)",
    navEvidence: "前往：證據主張 (Evidence)",
    navManuscript: "前往：文稿交付 (Manuscript)",
    navReview: "前往：審核與任務佇列 (Review)",
    activeBadge: "目前主題",
    noMatches: "沒有符合搜尋條件的指令或文獻",
    footerNav: "↑↓ 選擇",
    footerRun: "↵ 執行",
    footerClose: "Esc 關閉",
    untitledPaper: "未命名文獻",
  },
  en: {
    dialogTitle: "Command Palette",
    placeholder: "Type a command, switch project, or search paper title / author / year / DOI / #tag…",
    groupQuick: "Quick Actions",
    groupProjects: "Switch Project",
    groupPapers: "Jump to Paper",
    toggleDark: "Switch to Dark Mode",
    toggleLight: "Switch to Light Mode",
    openSettings: "Open Settings & Connections",
    navOverview: "Go to Overview",
    navLiterature: "Go to Literature",
    navEvidence: "Go to Evidence",
    navManuscript: "Go to Manuscript",
    navReview: "Go to Review",
    activeBadge: "Active",
    noMatches: "No matching commands, projects, or papers",
    footerNav: "↑↓ Navigate",
    footerRun: "↵ Select",
    footerClose: "Esc Close",
    untitledPaper: "Untitled source",
  },
} as const;

type CommandGroupKey = "quick" | "projects" | "papers";

interface CommandEntry {
  id: string;
  group: CommandGroupKey;
  label: string;
  sublabel?: string;
  badge?: string;
  searchText: string;
  tagsLower?: string[];
  onSelect: () => void;
}

function matchesQuery(entry: CommandEntry, rawQuery: string): boolean {
  const q = rawQuery.trim().toLocaleLowerCase();
  if (!q) return true;
  if (q.startsWith("#")) {
    const tagNeedle = q.replace(/^#+/, "").trim();
    if (!tagNeedle) return Boolean(entry.tagsLower && entry.tagsLower.length > 0);
    return Boolean(entry.tagsLower?.some((t) => t.includes(tagNeedle)));
  }
  const tokens = q.split(/\s+/).filter(Boolean);
  return tokens.every((tok) => {
    if (tok.startsWith("#")) {
      const clean = tok.replace(/^#+/, "");
      return Boolean(clean && entry.tagsLower?.some((t) => t.includes(clean)));
    }
    return entry.searchText.includes(tok);
  });
}

export interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
  projects: Project[];
  currentProjectId?: string;
  onSelectProject: (projectId: string) => void;
  sources?: ResearchRecord[];
  onOpenPaper?: (paper: ResearchRecord) => void;
  onNavigate: (page: Page) => void;
  onOpenSettings?: () => void;
  onToggleTheme?: () => void;
  resolvedTheme?: "light" | "dark";
  locale?: Locale;
}

export function CommandPalette({
  open,
  onClose,
  projects,
  currentProjectId,
  onSelectProject,
  sources = [],
  onOpenPaper,
  onNavigate,
  onOpenSettings,
  onToggleTheme,
  resolvedTheme = "light",
  locale = "en",
}: CommandPaletteProps) {
  const c = PALETTE_COPY[locale === "zh-TW" ? "zh-TW" : "en"];
  const titleId = useId();
  const listboxId = useId();
  const backdropRef = useRef<HTMLDivElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);

  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);

  useLayoutEffect(() => {
    if (!open) return;
    previousFocusRef.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setQuery("");
    setActiveIndex(0);
    inputRef.current?.focus();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const releaseBackground = acquireModalBackgroundLock(backdropRef.current);
    const onFocusIn = (event: FocusEvent) => {
      const dialogEl = dialogRef.current;
      if (dialogEl && event.target instanceof Node && !dialogEl.contains(event.target)) {
        inputRef.current?.focus();
      }
    };
    document.addEventListener("focusin", onFocusIn);
    return () => {
      document.removeEventListener("focusin", onFocusIn);
      releaseBackground();
    };
  }, [open]);

  const closeAndRestoreFocus = () => {
    const prev = previousFocusRef.current;
    onClose();
    if (prev && prev.isConnected) {
      queueMicrotask(() => prev.focus());
    }
  };

  const runSelectionAndClose = (action: () => void) => {
    const prev = previousFocusRef.current;
    const backdropEl = backdropRef.current;
    action();
    onClose();
    queueMicrotask(() => {
      const active = document.activeElement;
      const lostFocus =
        !active ||
        active === document.body ||
        active === document.documentElement ||
        Boolean(backdropEl?.contains(active));
      if (lostFocus && prev && prev.isConnected) {
        prev.focus();
      }
    });
  };

  const allEntries = useMemo<CommandEntry[]>(() => {
    if (!open) return [];
    const items: CommandEntry[] = [];

    if (onToggleTheme) {
      const toDark = resolvedTheme !== "dark";
      items.push({
        id: "quick-theme",
        group: "quick",
        label: toDark ? c.toggleDark : c.toggleLight,
        badge: toDark ? "Dark" : "Light",
        searchText: `${c.toggleDark} ${c.toggleLight} theme dark light mode 深色 淺色 主題 外觀`.toLocaleLowerCase(),
        onSelect: () => {
          runSelectionAndClose(() => onToggleTheme());
        },
      });
    }

    if (onOpenSettings) {
      items.push({
        id: "quick-settings",
        group: "quick",
        label: c.openSettings,
        searchText: `${c.openSettings} settings integrations obsidian zotero notebooklm sync 設定 連線 同步`.toLocaleLowerCase(),
        onSelect: () => {
          runSelectionAndClose(() => onOpenSettings());
        },
      });
    }

    const navTargets: [Page, string, string][] = [
      ["overview", c.navOverview, "overview dashboard stage radar 總覽 進度 雷達"],
      ["literature", c.navLiterature, "literature papers library matrix 文獻 閱讀 總表 矩陣"],
      ["evidence", c.navEvidence, "evidence claims citations 證據 主張 引用"],
      ["manuscript", c.navManuscript, "manuscript outline draft 文稿 大綱 草稿"],
      ["review", c.navReview, "review tasks approval delivery 審核 任務 交付"],
    ];

    for (const [page, label, extraKeywords] of navTargets) {
      items.push({
        id: `nav-${page}`,
        group: "quick",
        label,
        searchText: `${label} ${extraKeywords}`.toLocaleLowerCase(),
        onSelect: () => {
          runSelectionAndClose(() => onNavigate(page));
        },
      });
    }

    for (const proj of projects) {
      const isCurrent = proj.id === currentProjectId;
      items.push({
        id: `project-${proj.id}`,
        group: "projects",
        label: proj.title || proj.id,
        sublabel: proj.goal || proj.id,
        badge: isCurrent ? c.activeBadge : undefined,
        searchText: `${proj.title} ${proj.id} ${proj.goal} project 主題 專案`.toLocaleLowerCase(),
        onSelect: () => {
          runSelectionAndClose(() => onSelectProject(proj.id));
        },
      });
    }

    if (onOpenPaper) {
      const activePapers = sources.filter((s) => s.data.archived !== true);
      for (const paper of activePapers) {
        const title = asText(paper.data.title).trim() || c.untitledPaper;
        const year = asText(paper.data.year).trim();
        const doi = asText(paper.data.doi).trim();
        const authors = extractAuthorString(paper.data.authors);
        const tags = sourceTags(paper);
        const tagsLower = tags.map((t) => t.toLocaleLowerCase());
        const metaParts = [year, authors, doi, ...tags.slice(0, 3).map((t) => `#${t}`)].filter(
          Boolean,
        );
        items.push({
          id: `paper-${paper.id}`,
          group: "papers",
          label: title,
          sublabel: metaParts.join(" · "),
          badge: year || undefined,
          tagsLower,
          searchText: [title, authors, year, doi, ...tags.map((t) => `#${t}`), ...tags]
            .join(" ")
            .toLocaleLowerCase(),
          onSelect: () => {
            runSelectionAndClose(() => onOpenPaper(paper));
          },
        });
      }
    }

    return items;
  }, [
    c,
    currentProjectId,
    onClose,
    onNavigate,
    onOpenPaper,
    onOpenSettings,
    onSelectProject,
    onToggleTheme,
    open,
    projects,
    resolvedTheme,
    sources,
  ]);

  const filteredEntries = useMemo(() => {
    const trimmed = query.trim();
    const matched = allEntries.filter((entry) => matchesQuery(entry, trimmed));
    if (!trimmed) {
      let paperCount = 0;
      return matched.filter((entry) => {
        if (entry.group !== "papers") return true;
        paperCount++;
        return paperCount <= 8;
      });
    }
    let paperCount = 0;
    return matched.filter((entry) => {
      if (entry.group !== "papers") return true;
      paperCount++;
      return paperCount <= 20;
    });
  }, [allEntries, query]);

  const safeIndex =
    filteredEntries.length === 0 ? -1 : Math.min(activeIndex, filteredEntries.length - 1);

  const activeItemId =
    safeIndex >= 0 && filteredEntries[safeIndex]
      ? `${listboxId}-opt-${filteredEntries[safeIndex].id}`
      : undefined;

  useEffect(() => {
    if (!open || !activeItemId) return;
    const activeEl = document.getElementById(activeItemId);
    if (activeEl && typeof activeEl.scrollIntoView === "function") {
      activeEl.scrollIntoView({ block: "nearest" });
    }
  }, [open, activeItemId]);

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (event.nativeEvent.isComposing || event.keyCode === 229) {
      return;
    }
    if (event.key === "Tab") {
      const container = dialogRef.current;
      if (!container) return;
      const focusables = Array.from(
        container.querySelectorAll<HTMLElement>(
          'input:not([disabled]), button:not([disabled]), [href], select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
      );
      if (focusables.length <= 1) {
        event.preventDefault();
        (focusables[0] ?? inputRef.current)?.focus();
        return;
      }
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      closeAndRestoreFocus();
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (filteredEntries.length > 0) {
        setActiveIndex((prev) => (prev + 1) % filteredEntries.length);
      }
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      if (filteredEntries.length > 0) {
        setActiveIndex((prev) => (prev - 1 + filteredEntries.length) % filteredEntries.length);
      }
      return;
    }
    if (event.key === "Enter") {
      if (safeIndex >= 0 && filteredEntries[safeIndex]) {
        event.preventDefault();
        filteredEntries[safeIndex].onSelect();
      }
    }
  };

  if (!open) return null;

  const groupMeta: { key: CommandGroupKey; label: string }[] = [
    { key: "quick", label: c.groupQuick },
    { key: "projects", label: c.groupProjects },
    { key: "papers", label: c.groupPapers },
  ];

  return createPortal(
    <div
      ref={backdropRef}
      className="vr-cmd-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          closeAndRestoreFocus();
        }
      }}
    >
      <div
        ref={dialogRef}
        tabIndex={-1}
        className="vr-cmd-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onKeyDown={handleKeyDown}
      >
        <h2 id={titleId} className="sr-only">
          {c.dialogTitle}
        </h2>

        <div className="vr-cmd-search-bar">
          <svg
            className="vr-cmd-search-icon"
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <circle cx="11" cy="11" r="7" />
            <path d="m20 20-3.5-3.5" />
          </svg>
          <input
            ref={inputRef}
            type="text"
            className="vr-cmd-input"
            value={query}
            aria-label={c.dialogTitle}
            aria-controls={listboxId}
            aria-activedescendant={activeItemId}
            placeholder={c.placeholder}
            onChange={(event) => {
              setQuery(event.target.value);
              setActiveIndex(0);
            }}
          />
          <kbd className="vr-cmd-kbd" aria-hidden="true">
            Esc
          </kbd>
        </div>

        <div id={listboxId} role="listbox" aria-label={c.dialogTitle} className="vr-cmd-list">
          {filteredEntries.length === 0 ? (
            <p className="vr-cmd-empty">{c.noMatches}</p>
          ) : (
            groupMeta.map((group) => {
              const groupItems = filteredEntries.filter((e) => e.group === group.key);
              if (groupItems.length === 0) return null;
              return (
                <div key={group.key} className="vr-cmd-group" role="group" aria-label={group.label}>
                  <div className="vr-cmd-group-heading">{group.label}</div>
                  {groupItems.map((item) => {
                    const flatIdx = filteredEntries.indexOf(item);
                    const isActive = flatIdx === safeIndex;
                    return (
                      <div
                        key={item.id}
                        id={`${listboxId}-opt-${item.id}`}
                        role="option"
                        aria-selected={isActive}
                        className={`vr-cmd-item${isActive ? " is-active" : ""}`}
                        onMouseEnter={() => setActiveIndex(flatIdx)}
                        onClick={() => item.onSelect()}
                      >
                        <div className="vr-cmd-item-main">
                          <span className="vr-cmd-item-label">{item.label}</span>
                          {item.sublabel && (
                            <span className="vr-cmd-item-sub">{item.sublabel}</span>
                          )}
                        </div>
                        {item.badge && <span className="vr-cmd-item-badge">{item.badge}</span>}
                      </div>
                    );
                  })}
                </div>
              );
            })
          )}
        </div>

        <footer className="vr-cmd-footer" aria-hidden="true">
          <span>{c.footerNav}</span>
          <span>{c.footerRun}</span>
          <span>{c.footerClose}</span>
        </footer>
      </div>
    </div>,
    document.body,
  );
}
