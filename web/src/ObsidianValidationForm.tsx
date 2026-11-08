import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, ApiError } from "./api";
import type { MessageKey, Translate } from "./i18n";
import type { Workspace } from "./types";

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

export function ObsidianValidationForm({ capability, t }: {capability?: Capability; t: Translate}) {
  const scope = capability?.version === 1 && capability.read_only === true &&
    capability.scope === "startup_selected_exact_vault" && capability.status === "available"
    ? capability.authorized_vault ?? "" : "";
  const [path, setPath] = useState(scope);
  const [state, setState] = useState<State>({kind:"unknown"});
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
    } catch (failure) {
      if (intent !== generation.current) return;
      setState({kind:"error",code:failure instanceof ApiError ? failure.code : "validation_error"});
    } finally {
      clearTimeout(timer);
      if (intent === generation.current) pending.current = null;
    }
  }
  const errorMessage = state.kind === "error" && state.code === "vault_scope_denied" ? "obsidianScopeDenied"
    : state.kind === "error" && state.code === "vault_validation_unavailable" ? "obsidianUnavailable"
    : state.kind === "error" && state.code === "validation_timeout" ? "obsidianTimeout" : "obsidianError";
  return <form className="obsidian-validation" onSubmit={(event)=>void validate(event)} aria-label={t("obsidianValidation")}>
    <label>{t("obsidianVaultPath")}<input name="vault_path" type="text" value={path} autoComplete="off" spellCheck={false}
      disabled={!scope || state.kind === "loading"} onChange={(event)=>{setPath(event.target.value);setState({kind:"unknown"});}} /></label>
    <p className="small">{t("obsidianScopeHelp")}</p>
    {!scope && <p role="status">{t("obsidianUnavailable")}</p>}
    <div className="obsidian-validation-actions">
      <button className="button secondary" type="submit" disabled={!scope || !path.trim() || state.kind === "loading"}>{t("obsidianValidate")}</button>
      <button className="button text-button" type="button" onClick={cancel}>{t("cancel")}</button>
    </div>
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
