/** Local disposition only. Original v1 pending identities remain authoritative. */
export type RecoveryKind = "prepare" | "text-intake";
export function dispositionKey(
  origin: string,
  namespace: string,
  project: string,
  type: RecoveryKind,
  key: string,
) {
  return `research-hub:disposition:v1:${encodeURIComponent(origin)}:${namespace}:${encodeURIComponent(project)}:${type}:${key}`;
}
function marker(
  origin: string,
  namespace: string,
  project: string,
  type: RecoveryKind,
  key: string,
) {
  return {
    version: 1,
    origin,
    workspace_instance_id: namespace,
    project_id: project,
    type,
    key,
    disposition: "parked",
  };
}
export function readParked(
  origin: string,
  namespace: string,
  project: string,
  type: RecoveryKind,
  key: string,
): boolean {
  const expected = marker(origin, namespace, project, type, key);
  const raw = localStorage.getItem(
    dispositionKey(origin, namespace, project, type, key),
  );
  if (!raw || raw.length > JSON.stringify(expected).length + 128) return false;
  const value = JSON.parse(raw);
  return (
    !!value &&
    typeof value === "object" &&
    Object.keys(value).sort().join() === Object.keys(expected).sort().join() &&
    Object.entries(expected).every(([name, field]) => value[name] === field)
  );
}
export function writeParked(
  origin: string,
  namespace: string,
  project: string,
  type: RecoveryKind,
  key: string,
) {
  localStorage.setItem(
    dispositionKey(origin, namespace, project, type, key),
    JSON.stringify(marker(origin, namespace, project, type, key)),
  );
}
