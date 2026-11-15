import { createContext, useContext, type ReactNode } from "react";
import { ApiError, type VersionInfo } from "./api/client";
import { useElapsed } from "./hooks";
import { statusLabel } from "./format";

// ---- capability status (decision: the UI may not present anything as more validated than it is) ----

type Cap = VersionInfo["capabilities"][number];
export const CapabilitiesContext = createContext<Cap[] | null>(null);

const STATUS_HELP: Record<string, string> = {
  validated: "Implemented and its stage gate was approved by the project owner.",
  implemented_unvalidated: "Implemented, but its stage gate has NOT been approved yet: treat results as provisional.",
  not_implemented: "Not built. Nothing on screen is computed for this.",
};

// Terrain from a product whose status is implemented_unvalidated (Chandrayaan-3's 60 m window): the SAME pill as a capability with that status,
// so it cannot be mistaken for the validated IM-2 terrain. The text comes from the backend's own caveat (visibility limitations).
export const UNVALIDATED_TERRAIN = /implemented_unvalidated/;
export const unvalidatedTerrainNote = (limitations?: string[]) => (limitations ?? []).find((l) => UNVALIDATED_TERRAIN.test(l));
export function UnvalidatedTerrainTag({ limitations }: { limitations?: string[] }) {
  const note = unvalidatedTerrainNote(limitations);
  if (!note) return null;
  return (
    <span className="tag tag-implemented_unvalidated" title={note} data-testid="terrain-unvalidated">
      terrain: {statusLabel("implemented_unvalidated")}
    </span>
  );
}

export function StatusTag({ cap }: { cap: string }) {
  const caps = useContext(CapabilitiesContext);
  const c = caps?.find((x) => x.key === cap);
  const status = c?.status ?? "unknown";
  return (
    <span className={`tag tag-${status}`} title={STATUS_HELP[status] ?? "Status not available from the backend."} data-testid={`status-${cap}`}>
      {c ? `${c.key}: ${statusLabel(status)}` : `${cap}: status unknown`}
    </span>
  );
}

export function CapabilityStrip({ capabilities, notice }: { capabilities: Cap[]; notice: string }) {
  return (
    <section className="cap-strip" aria-label="Capability status">
      <p role="note" className="notice">
        {notice}
      </p>
      <ul className="cap-list">
        {capabilities.map((c) => (
          <li key={c.key} className={`tag tag-${c.status}`} title={STATUS_HELP[c.status]}>
            <span className="cap-name">{c.title}</span> · stage {c.stage} · <strong>{statusLabel(c.status)}</strong>
          </li>
        ))}
      </ul>
    </section>
  );
}

// ---- loading / error ----

export function Loading({ startedAt, label, hint }: { startedAt: number | null; label: string; hint?: string }) {
  const s = useElapsed(startedAt);
  return (
    <div className="loading" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <span>
        {label}… {s > 0 ? `${s} s` : ""}
        {hint && s >= 4 ? <em className="hint"> {hint}</em> : null}
      </span>
    </div>
  );
}

export function ErrorBox({ error, what }: { error: Error; what: string }) {
  const api = error instanceof ApiError ? error : null;
  return (
    <div className="error" role="alert">
      <strong>{what} failed.</strong> {error.message}
      {api?.body ? (
        <div className="error-detail">
          {api.body.code}
          {api.body.field ? ` · field: ${api.body.field}` : ""}
        </div>
      ) : null}
      {api && api.status === 0 ? <div className="error-detail">Start the backend with the commands in docs/DEV_SETUP.md.</div> : null}
    </div>
  );
}

export function Panel({ title, tags, children, id }: { title: string; tags?: ReactNode; children: ReactNode; id?: string }) {
  return (
    <section className="panel" id={id} aria-label={title}>
      <header className="panel-head">
        <h2>{title}</h2>
        <div className="panel-tags">{tags}</div>
      </header>
      {children}
    </section>
  );
}

export function Insufficient({ reason }: { reason?: string }) {
  return (
    <div className="insufficient" data-testid="terrain-insufficient">
      <strong>Terrain data insufficient</strong>
      <p>No visibility figures are shown for this site: the available terrain data cannot support a position-sensitivity result, so nothing is ranked, scored or estimated.</p>
      {reason ? <p className="reason">{reason}</p> : null}
    </div>
  );
}
