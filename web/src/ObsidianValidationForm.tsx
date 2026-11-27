import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, ApiError } from "./api";
import type { MessageKey, Translate } from "./i18n";
import type { ObsidianValidationResult, Workspace } from "./types";

type Capability = Workspace["capabilities"]["obsidian_validation"];
const results = {
  valid: "obsidianValid", not_found: "obsidianNotFound", not_directory: "obsidianNotDirectory",
  not_vault: "obsidianNotVault", registry_missing: "obsidianRegistryMissing",
  invalid_registry: "obsidianRegistryInvalid", registry_mismatch: "obsidianRegistryMismatch",
  unreadable: "obsidianUnreadable", unsafe_path: "obsidianUnsafePath",
} as const satisfies Record<string, MessageKey>;
type Result = {ok: true; status: keyof typeof results; read_only: true; saved: false;
  note_bodies_read: false; observed_at: string; collection_count?: number};
type State = {kind:"unknown"} | {kind:"loading"} | {kind:"cancelled"} | {kind:"error"; code:string} | {kind:"result"; value:Result};

export function ObsidianValidationForm({
  capability,
  canSaveVault = false,
  t,
  onValidated,
  onVaultSaved,
}: {
  capability?: Capability;
  canSaveVault?: boolean;
  t: Translate;
  onValidated?: (result: ObsidianValidationResult | null) => void;
  onVaultSaved?: () => void;
}) {
  const scope = capability?.version === 1 && capability.read_only === true &&
    capability.scope === "startup_selected_exact_vault" && capability.status === "available"
    ? capability.authorized_vault ?? "" : "";
  const [path, setPath] = useState(scope);
  const [state, setState] = useState<State>({kind:"unknown"});
  const [saveNote, setSaveNote] = useState<string | null>(null);
  const [saveErr, setSaveErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const generation = useRef(0);
  const pending = useRef<AbortController | null>(null);
  useEffect(() => {
    generation.current++;
    pending.current?.abort(); pending.current = null;
    setPath(scope); setState({kind:"unknown"});
    return () => { generation.current++; pending.current?.abort(); pending.current = null; };
  }, [scope]);

  function cancel() {
    generation.current++; pending.current?.abort(); pending.current = null;
    setPath(scope); setState({kind:"cancelled"});
    setSaveNote(null); setSaveErr(null);
    onValidated?.(null);
  }
  async function saveVault() {
    if (!canSaveVault || !path.trim() || saving) return;
    setSaving(true); setSaveNote(null); setSaveErr(null);
    try {
      await api("/integrations/credentials", { obsidian_vault_path: path.trim() });
      setSaveNote(t("obsidianVaultSaved"));
      onVaultSaved?.();
    } catch (failure) {
      setSaveErr(failure instanceof ApiError ? failure.message : t("integrationSaveFailed"));
    } finally {
      setSaving(false);
    }
  }
  async function validate(event: FormEvent) {
    event.preventDefault();
    if (!scope || state.kind === "loading") return;
    const intent = ++generation.current;
    const controller = new AbortController(); pending.current = controller;
    setState({kind:"loading"});
    let timer: ReturnType<typeof setTimeout> | undefined;
    try {
      const value = await Promise.race([
        api<Result>("/integrations/obsidian/validate", {vault_path:path}, controller.signal),
        new Promise<never>((_, reject) => { timer = setTimeout(() => {
          reject(new ApiError("Local validation timed out", "validation_timeout", 408));
          controller.abort();
        }, 10000); }),
      ]);
      if (intent !== generation.current) return;
      if (!value || !Object.hasOwn(results,value.status) || value.read_only !== true || value.saved !== false || value.note_bodies_read !== false) throw new Error("Invalid validation response");
      setState({kind:"result",value});
      onValidated?.({ status: value.status, collection_count: value.collection_count, observed_at: value.observed_at });
    } catch (failure) {
      if (intent !== generation.current) return;
      const code = failure instanceof ApiError ? failure.code : "validation_error";
      setState({kind:"error", code});
      onValidated?.({
        status:
          code === "vault_scope_denied"
            ? "scope_denied"
            : code === "vault_validation_unavailable"
              ? "unavailable"
              : code === "validation_timeout"
                ? "timeout"
                : "error",
        observed_at: new Date().toISOString(),
      });
    } finally {
      clearTimeout(timer);
      if (intent === generation.current) pending.current = null;
    }
  }
  const errorMessage = state.kind === "error" && state.code === "vault_scope_denied" ? "obsidianScopeDenied"
    : state.kind === "error" && state.code === "vault_validation_unavailable" ? "obsidianUnavailable"
    : state.kind === "error" && state.code === "validation_timeout" ? "obsidianTimeout" : "obsidianError";
  const editable = Boolean(scope) || canSaveVault;
  return <form className="obsidian-validation" onSubmit={(event)=>void validate(event)} aria-label={t("obsidianValidation")}>
    <label>{t("obsidianVaultPath")}<input name="vault_path" type="text" value={path} autoComplete="off" spellCheck={false}
      disabled={!editable || state.kind === "loading" || saving} onChange={(event)=>{setPath(event.target.value);setState({kind:"unknown"});setSaveNote(null);setSaveErr(null);onValidated?.(null);}} /></label>
    <p className="small">{t("obsidianScopeHelp")}</p>
    {!scope && !canSaveVault && <p role="status">{t("obsidianUnavailable")}</p>}
    <div className="obsidian-validation-actions">
      <button className="button secondary small" type="submit" disabled={!scope || !path.trim() || state.kind === "loading"}>{t("obsidianValidate")}</button>
      {canSaveVault && (
        <button className="button primary small" type="button" disabled={!path.trim() || saving} onClick={() => void saveVault()}>
          {saving ? t("integrationSaving") : t("obsidianSaveVault")}
        </button>
      )}
      <button className="button text-button small" type="button" onClick={cancel}>{t("cancel")}</button>
    </div>
    {saveNote && <p role="status" className="small good-text">{saveNote}</p>}
    {saveErr && <p role="alert" className="small bad-text">{saveErr}</p>}
    <p role={state.kind === "error" ? "alert" : "status"}>
      {state.kind === "unknown" ? t("obsidianUnknown") : state.kind === "loading" ? t("obsidianLoading")
        : state.kind === "cancelled" ? t("obsidianCancelled") : state.kind === "error" ? t(errorMessage)
        : t(results[state.value.status])}
    </p>
    {state.kind === "result" && <p className="small">{t("obsidianResultScope")}
      {state.value.status === "valid" && Number.isInteger(state.value.collection_count) && <span> {state.value.collection_count} {t("libraryCollections")}.</span>}
    </p>}
  </form>;
}
