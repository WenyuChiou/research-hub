import { useEffect, useId, useLayoutEffect, useRef, useState, type FormEvent } from "react";
import { createPortal } from "react-dom";
import { ApiError, api, recoverCsrfIfForbidden, segment } from "./api";
import { acquireModalBackgroundLock } from "./CommandPalette";
import type { Locale } from "./types";

export interface AgentEngineInfo {
  id: string;
  label: string;
  available: boolean;
}

export interface AgentProposedAction {
  type: string;
  source_id?: string;
  title?: string;
  tags?: string[];
  category?: string;
  decision?: string;
  dry_run?: boolean;
  summary: string;
}

interface AgentMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  engine?: string;
}

const COPY = {
  "zh-TW": {
    title: "AI 研究助理主控台",
    subtitle: "下達中文或英文指令批次整理文獻、貼標籤、刪除或觸發 Zotero / NotebookLM 同步。",
    engineLabel: "執行引擎",
    placeholder: "例如：幫我刪除 Calibration Limits 這篇文獻，或「為 2024 論文加上 #review」…",
    send: "傳送指令",
    sending: "分析中…",
    pendingPlanTitle: "待人類確認的變更提案",
    confirmApply: "✓ 確認執行",
    applying: "套用中…",
    cancelPlan: "✕ 取消提案",
    appliedDone: (n: number) => `✓ 已成功套用 ${n} 項變更並重新同步工作區。`,
    appliedPartial: (failed: number) => `⚠ 整合執行部分失敗（共 ${failed} 筆項目未能完成，請檢查上方錯誤或明細）。`,
    close: "關閉",
    unavailableSuffix: "（未安裝）",
    sendHint: "Enter 傳送 · Shift+Enter 換行",
    chips: [
      "列出目前文獻狀態",
      "產生 NLM 匯入包",
      "預覽同步 Zotero",
      "產生 Obsidian 筆記",
    ],
  },
  en: {
    title: "AI Research Assistant Console",
    subtitle: "Curate papers, manage tags, archive/restore entries, or trigger Zotero / NotebookLM sync.",
    engineLabel: "Engine",
    placeholder: "e.g. Delete the paper Calibration Limits, or Add #review tag to 2024 papers…",
    send: "Send",
    sending: "Planning…",
    pendingPlanTitle: "Proposed changes awaiting confirmation",
    confirmApply: "✓ Confirm & Apply",
    applying: "Applying…",
    cancelPlan: "✕ Dismiss",
    appliedDone: (n: number) => `✓ Applied ${n} action(s) and refreshed workspace.`,
    appliedPartial: (failed: number) => `⚠ Integration finished with ${failed} failed item(s). Check source diagnostics before retrying.`,
    close: "Close",
    unavailableSuffix: " (not installed)",
    sendHint: "Enter to send · Shift+Enter for newline",
    chips: [
      "List current paper inventory",
      "Bundle NotebookLM pack",
      "Preview sync Zotero",
      "Generate Obsidian pack",
    ],
  },
} as const;

export function AgentChatDrawer({
  open,
  onClose,
  projectId,
  projectTitle,
  locale,
  onApplied,
}: {
  open: boolean;
  onClose: () => void;
  projectId: string;
  projectTitle?: string;
  locale: Locale;
  onApplied: (notice: string) => Promise<void>;
}) {
  const c = COPY[locale === "zh-TW" ? "zh-TW" : "en"];
  const titleId = useId();
  const backdropRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const [engines, setEngines] = useState<AgentEngineInfo[]>([
    { id: "auto", label: "Auto (Fast + CLI)", available: true },
    { id: "fast", label: "Workspace Fast Commander", available: true },
  ]);
  const [engine, setEngine] = useState("auto");
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [pendingPlan, setPendingPlan] = useState<{
    actions: AgentProposedAction[];
    planDigest: string;
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const projectIdRef = useRef(projectId);
  projectIdRef.current = projectId;
  const epochRef = useRef(0);

  useEffect(() => {
    epochRef.current += 1;
    setMessages([]);
    setPendingPlan(null);
    setError(null);
    setBusy(false);
    setApplying(false);
  }, [projectId]);

  useLayoutEffect(() => {
    if (!open) return;
    inputRef.current?.focus();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const release = acquireModalBackgroundLock(backdropRef.current);
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      release();
    };
  }, [open, onClose]);

  useEffect(() => {
    if (!open || !projectId) return;
    const controller = new AbortController();
    api<{ ok: boolean; available_engines?: AgentEngineInfo[] }>(
      `/projects/${segment(projectId)}/integrations/agent/status`,
      undefined,
      controller.signal,
    )
      .then((res) => {
        if (Array.isArray(res.available_engines) && res.available_engines.length > 0) {
          setEngines(res.available_engines);
        }
      })
      .catch(() => {
        /* Fallback defaults remain active. */
      });
    return () => controller.abort();
  }, [open, projectId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, pendingPlan]);

  if (!open) return null;

  async function sendText(rawText: string) {
    const trimmed = rawText.trim();
    if (!trimmed || !projectId || busy || applying) return;
    const reqProject = projectId;
    const reqEpoch = epochRef.current;
    setError(null);
    setBusy(true);
    setPendingPlan(null);
    const userMsg: AgentMessage = {
      id: `u-${Date.now()}`,
      role: "user",
      text: trimmed,
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");

    try {
      const res = await api<{
        ok: true;
        engine_used: string;
        reply: string;
        proposed_actions: AgentProposedAction[];
        plan_digest: string;
      }>(`/projects/${segment(reqProject)}/integrations/agent/chat`, {
        message: trimmed,
        engine,
      });
      if (epochRef.current !== reqEpoch || projectIdRef.current !== reqProject) return;
      setMessages((prev) => [
        ...prev,
        {
          id: `a-${Date.now()}`,
          role: "assistant",
          text: res.reply,
          engine: res.engine_used,
        },
      ]);
      if (Array.isArray(res.proposed_actions) && res.proposed_actions.length > 0) {
        setPendingPlan({
          actions: res.proposed_actions,
          planDigest: res.plan_digest,
        });
      }
    } catch (err) {
      if (epochRef.current !== reqEpoch || projectIdRef.current !== reqProject) return;
      void recoverCsrfIfForbidden(err);
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      if (epochRef.current === reqEpoch && projectIdRef.current === reqProject) {
        setBusy(false);
      }
    }
  }

  async function confirmPlan() {
    if (!pendingPlan || !projectId || applying) return;
    const reqProject = projectId;
    const reqEpoch = epochRef.current;
    setApplying(true);
    setError(null);
    try {
      const res = await api<{
        ok: true;
        applied_count: number;
        results?: { type: string; ok: boolean; detail?: { status?: string; failed_count?: number } }[];
      }>(
        `/projects/${segment(reqProject)}/integrations/agent/apply`,
        {
          proposed_actions: pendingPlan.actions,
          expected_plan_digest: pendingPlan.planDigest,
        },
      );
      if (epochRef.current !== reqEpoch || projectIdRef.current !== reqProject) return;
      const failedTotal = (res.results ?? []).reduce((sum, item) => {
        const st = item.detail?.status;
        if (st === "failed" || st === "partial_failure") {
          return sum + Math.max(1, Number(item.detail?.failed_count ?? 1));
        }
        return sum;
      }, 0);
      const msg = failedTotal > 0 ? c.appliedPartial(failedTotal) : c.appliedDone(res.applied_count);
      setMessages((prev) => [
        ...prev,
        { id: `sys-${Date.now()}`, role: "assistant", text: msg },
      ]);
      setPendingPlan(null);
      await onApplied(msg);
    } catch (err) {
      if (epochRef.current !== reqEpoch || projectIdRef.current !== reqProject) return;
      void recoverCsrfIfForbidden(err);
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      if (epochRef.current === reqEpoch && projectIdRef.current === reqProject) {
        setApplying(false);
      }
    }
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    void sendText(input);
  }

  return createPortal(
    <div
      ref={backdropRef}
      className="agent-drawer-backdrop"
      role="presentation"
      onClick={(event) => {
        if (event.target === backdropRef.current) onClose();
      }}
    >
      <section
        className="agent-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
      >
        <header className="agent-drawer-header">
          <div>
            <h2 id={titleId} className="agent-drawer-title">
              <span className="agent-sparkle" aria-hidden="true">✦</span>
              <span>{c.title}</span>
            </h2>
            {projectTitle && <p className="small muted">{projectTitle}</p>}
          </div>
          <button
            type="button"
            className="button text-button small"
            onClick={onClose}
            aria-label={c.close}
          >
            ✕
          </button>
        </header>

        <div className="agent-toolbar">
          <span className="small muted">{c.subtitle}</span>
          <label className="small" style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem" }}>
            <span>{c.engineLabel}</span>
            <select
              className="agent-engine-select"
              value={engine}
              onChange={(event) => setEngine(event.target.value)}
            >
              {engines.map((item) => (
                <option key={item.id} value={item.id} disabled={!item.available}>
                  {item.label}
                  {!item.available ? c.unavailableSuffix : ""}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="agent-quick-chips">
          {c.chips.map((chip) => (
            <button
              key={chip}
              type="button"
              className="agent-chip-btn"
              disabled={busy || applying}
              onClick={() => void sendText(chip)}
            >
              {chip}
            </button>
          ))}
        </div>

        <div className="agent-messages" aria-live="polite">
          {messages.map((msg) => (
            <div key={msg.id} className={`agent-msg is-${msg.role}`}>
              <div>{msg.text}</div>
              {msg.engine && <span className="agent-msg-meta">engine: {msg.engine}</span>}
            </div>
          ))}
          {error && (
            <div className="sync-receipt is-error" role="alert">
              {error}
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {pendingPlan && (
          <div className="agent-plan-card" role="region" aria-label={c.pendingPlanTitle}>
            <div className="agent-plan-header">
              <span>{c.pendingPlanTitle} ({pendingPlan.actions.length})</span>
            </div>
            <ol className="agent-plan-list">
              {pendingPlan.actions.map((act, idx) => (
                <li key={idx}>
                  <code>{act.type}</code> — {act.summary}
                </li>
              ))}
            </ol>
            <div className="agent-plan-actions">
              <button
                type="button"
                className="button primary small"
                disabled={applying}
                onClick={() => void confirmPlan()}
              >
                {applying ? c.applying : c.confirmApply}
              </button>
              <button
                type="button"
                className="button secondary small"
                disabled={applying}
                onClick={() => setPendingPlan(null)}
              >
                {c.cancelPlan}
              </button>
            </div>
          </div>
        )}

        <form className="agent-composer" onSubmit={handleSubmit}>
          <textarea
            ref={inputRef}
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder={c.placeholder}
            disabled={busy || applying}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault();
                void sendText(input);
              }
            }}
          />
          <div className="agent-composer-footer">
            <span className="small muted">{c.sendHint}</span>
            <button
              type="submit"
              className="button primary small"
              disabled={!input.trim() || busy || applying}
            >
              {busy ? c.sending : c.send}
            </button>
          </div>
        </form>
      </section>
    </div>,
    document.body,
  );
}
