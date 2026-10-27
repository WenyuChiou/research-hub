import { useState } from "react";
import type { Translate } from "./i18n";
/** Parking is not cancellation, retry, or completion. Separate work is another action. */
export function RecoveryParkControls({
  entry,
  recovery,
  t,
  onSeparate,
}: {
  entry: {
    key: string;
    phase: string;
    parked?: boolean;
    parkStorageFailed?: boolean;
    parkSessionOnly?: boolean;
  };
  recovery: {
    blocked: boolean;
    park: (key: string, sessionOnly?: boolean) => boolean;
  };
  t: Translate;
  onSeparate?: () => void;
}) {
  const [confirm, setConfirm] = useState(false);
  if (entry.parked)
    return (
      <div>
        <p role="status">{t("recoveryParked")}</p>
        {entry.parkSessionOnly && <p>{t("recoveryParkSessionWarning")}</p>}
        {onSeparate && (
          <button
            className="button secondary"
            disabled={
              recovery.blocked || ["sending", "checking"].includes(entry.phase)
            }
            onClick={onSeparate}
          >
            {t("recoverySeparate")}
          </button>
        )}
      </div>
    );
  if (["sending", "checking", "unsent", "found"].includes(entry.phase))
    return null;
  return (
    <div>
      {!confirm ? (
        <button className="button text-button" onClick={() => setConfirm(true)}>
          {t("recoveryPark")}
        </button>
      ) : (
        <>
          <p>{t("recoveryParkWarning")}</p>
          {entry.parkStorageFailed ? (
            <>
              <p role="alert">{t("recoveryParkSessionWarning")}</p>
              <button
                className="button secondary"
                onClick={() => recovery.park(entry.key, true)}
              >
                {t("recoveryParkSession")}
              </button>
            </>
          ) : (
            <button
              className="button secondary"
              onClick={() => recovery.park(entry.key)}
            >
              {t("recoveryParkConfirm")}
            </button>
          )}
          <button
            className="button text-button"
            onClick={() => setConfirm(false)}
          >
            {t("cancel")}
          </button>
        </>
      )}
    </div>
  );
}
