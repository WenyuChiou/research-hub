import { useId, useState, type FormEvent, type ReactNode } from "react";
import { ApiError, safeSourceUrl } from "./api";
import { statusLabel, statusTone, type Translate } from "./i18n";

export interface FieldSpec {
  name: string;
  label: string;
  hint?: string;
  required?: boolean;
  textarea?: boolean;
  options?: { value: string; label: string }[];
  multiple?: boolean;
  defaultValue?: string;
  pattern?: string;
  maxLength?: number;
}
export interface FieldProps extends FieldSpec {
  disabled?: boolean;
}
export function Field({
  name,
  label,
  hint,
  required = true,
  textarea,
  options,
  multiple,
  defaultValue,
  pattern,
  maxLength,
  disabled,
}: FieldProps) {
  const id = useId();
  const shared = {
    id,
    name,
    required,
    disabled,
    "aria-describedby": hint ? `${id}-hint` : undefined,
  };
  return (
    <div className={`field ${textarea ? "field-wide" : ""}`}>
      <label htmlFor={id}>
        {label}
        {required && (
          <span aria-hidden="true" className="required-dot">
            {" "}
            ·
          </span>
        )}
      </label>
      {options ? (
        <select
          {...shared}
          multiple={multiple}
          defaultValue={multiple ? [] : defaultValue}
        >
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      ) : textarea ? (
        <textarea
          {...shared}
          rows={3}
          defaultValue={defaultValue}
          maxLength={maxLength ?? 40000}
        />
      ) : (
        <input
          {...shared}
          defaultValue={defaultValue}
          pattern={pattern}
          maxLength={maxLength ?? 2000}
        />
      )}
      {hint && <small id={`${id}-hint`}>{hint}</small>}
    </div>
  );
}

export function ErrorMessage({ error, t }: { error: unknown; t: Translate }) {
  return (
    <div role="alert" className="notice notice-error">
      <strong>{error instanceof Error ? error.message : String(error)}</strong>
      {error instanceof ApiError && <code>{error.code}</code>}
      <span>{t("errorHelp")}</span>
    </div>
  );
}

export interface MutationFormProps {
  fields: FieldSpec[];
  submit: string;
  onSubmit: (data: FormData) => Promise<void>;
  t: Translate;
  note?: string;
  className?: string;
  children?: ReactNode;
  disabled?: boolean;
  reset?: boolean;
  successMessage?: string | false;
}
/** Usage: <MutationForm fields={questionFields} submit={t('addQuestion')} onSubmit={save} t={t} /> */
export function MutationForm({
  fields,
  submit,
  onSubmit,
  t,
  note,
  className = "",
  children,
  disabled,
  reset = true,
  successMessage,
}: MutationFormProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState(false);
  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      await onSubmit(new FormData(form));
      if (reset) form.reset();
      setSaved(true);
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  }
  return (
    <form
      className={`record-form ${className}`}
      onSubmit={handleSubmit}
      aria-busy={busy}
    >
      {note && <p className="form-note">{note}</p>}
      <fieldset disabled={busy || disabled}>
        <div className="form-grid">
          {fields.map((field) => (
            <Field key={field.name} {...field} />
          ))}
          {children}
        </div>
        <button className="button primary" type="submit">
          {busy ? t("saving") : submit}
          <span aria-hidden="true">↗</span>
        </button>
      </fieldset>
      {error !== null && <ErrorMessage error={error} t={t} />}
      {saved && successMessage !== false && (
        <p role="status" className="saved-note">
          ✓ {successMessage ?? t("saved")}
        </p>
      )}
    </form>
  );
}

export function StatusBadge({ status, t }: { status: string; t: Translate }) {
  return (
    <span className={`badge ${statusTone(status)}`}>
      <span aria-hidden="true" className="badge-dot" />
      {statusLabel(status, t)}
    </span>
  );
}
export function EmptyState({
  children,
  compact = false,
}: {
  children: ReactNode;
  compact?: boolean;
}) {
  return (
    <div className={`empty-state ${compact ? "compact" : ""}`}>
      <span className="empty-mark" aria-hidden="true">
        ＋
      </span>
      <p>{children}</p>
    </div>
  );
}
export function Panel({
  title,
  children,
  meta,
  className = "",
}: {
  title: string;
  children: ReactNode;
  meta?: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      <div className="panel-heading">
        <h2>{title}</h2>
        {meta}
      </div>
      {children}
    </section>
  );
}
export function Disclosure({
  title,
  children,
  open = false,
}: {
  title: string;
  children: ReactNode;
  open?: boolean;
}) {
  return (
    <details className="disclosure" open={open || undefined}>
      <summary>
        {title}
        <span aria-hidden="true">＋</span>
      </summary>
      {children}
    </details>
  );
}
export function SourceLink({
  locator,
  title,
}: {
  locator: unknown;
  title?: string;
}) {
  const safe = safeSourceUrl(locator);
  return safe ? (
    <a
      className="source-link"
      href={safe}
      target="_blank"
      rel="noopener noreferrer"
    >
      {title || String(locator)} <span aria-hidden="true">↗</span>
    </a>
  ) : (
    <span className="muted break-word">{String(locator ?? "")}</span>
  );
}
export function InspectJson({
  title,
  value,
}: {
  title: string;
  value: unknown;
}) {
  return (
    <details className="inspect">
      <summary>{title}</summary>
      <pre>
        {typeof value === "string" ? value : JSON.stringify(value, null, 2)}
      </pre>
    </details>
  );
}
export function ReadText({ value }: { value: unknown }) {
  return (
    <p className="preserve-lines">
      {Array.isArray(value)
        ? value.map(String).join(", ")
        : typeof value === "object" && value !== null
          ? JSON.stringify(value, null, 2)
          : String(value ?? "")}
    </p>
  );
}
export function SmallLabel({ children }: { children: ReactNode }) {
  return <span className="small-label">{children}</span>;
}
