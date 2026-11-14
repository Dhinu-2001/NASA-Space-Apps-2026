import { useCallback, useState } from "react";
import { Explain } from "./learn";

// Configurable mission profiles: named bundles of EXISTING form parameters (window length, observer height, position
// uncertainty). They only fill in the form. The built-in ones are illustrative assumptions for exploring the tool, never
// real mission requirements; users can save their own. Saved profiles live in this browser only (a per-viewer convenience).

export interface Profile {
  id: string;
  name: string;
  days: number;
  height: string; // "" = the 2.0 m default assumption
  band: number;
  builtin?: boolean;
}

export interface FormValues {
  days: string;
  height: string;
  band: string;
}

export const BUILTIN_PROFILES: Profile[] = [
  { id: "one-lunar-day", name: "One lunar day of operations (14 days)", days: 14, height: "", band: 100, builtin: true },
  { id: "extended", name: "Extended surface stay (30 days)", days: 30, height: "", band: 100, builtin: true },
  { id: "long", name: "Long stay (60 days)", days: 60, height: "", band: 100, builtin: true },
  { id: "tight-position", name: "30 days, tight position knowledge (±20 m)", days: 30, height: "", band: 20, builtin: true },
  { id: "loose-position", name: "30 days, loose position knowledge (±200 m)", days: 30, height: "", band: 200, builtin: true },
];

const KEY = "lunarnav.profiles";

function isProfile(p: unknown): p is Profile {
  const o = p as Profile;
  return !!o && typeof o.id === "string" && typeof o.name === "string" && typeof o.days === "number" && Number.isFinite(o.days) &&
    o.days > 0 && o.days <= 60 && typeof o.height === "string" && typeof o.band === "number" && Number.isFinite(o.band) && o.band > 0;
}

export function loadSaved(): Profile[] {
  try {
    const raw = window.localStorage.getItem(KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter(isProfile).map((p) => ({ ...p, builtin: false })) : [];
  } catch {
    return []; // unavailable or corrupt storage: start with no saved profiles
  }
}

function persist(list: Profile[]): void {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(list));
  } catch {
    /* ignore: the in-memory list still works for this session */
  }
}

export function useProfiles() {
  const [saved, setSaved] = useState<Profile[]>(() => loadSaved());
  const add = useCallback((p: Omit<Profile, "id" | "builtin">) => {
    setSaved((cur) => {
      const next = [...cur.filter((x) => x.name !== p.name), { ...p, id: `custom-${Date.now()}-${cur.length}` }];
      persist(next);
      return next;
    });
  }, []);
  const remove = useCallback((id: string) => {
    setSaved((cur) => {
      const next = cur.filter((x) => x.id !== id);
      persist(next);
      return next;
    });
  }, []);
  return { saved, add, remove };
}

export function ProfilePicker({
  current,
  onApply,
  showHeight = true,
  idPrefix = "profile",
}: {
  current: FormValues;
  onApply: (v: FormValues) => void;
  showHeight?: boolean;
  idPrefix?: string;
}) {
  const { saved, add, remove } = useProfiles();
  const [sel, setSel] = useState<string>(BUILTIN_PROFILES[0].id);
  const [name, setName] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const all = [...BUILTIN_PROFILES, ...saved];
  const chosen = all.find((p) => p.id === sel) ?? null;

  const apply = () => {
    if (!chosen) return;
    onApply({ days: String(chosen.days), height: showHeight ? chosen.height : current.height, band: String(chosen.band) });
  };
  const save = () => {
    const d = Number(current.days);
    const b = Number(current.band);
    const h = current.height.trim();
    if (name.trim() === "") return setErr("Give the profile a name.");
    if (!Number.isFinite(d) || d <= 0 || d > 60) return setErr("The window length must be between 0 and 60 days to save a profile.");
    if (!Number.isFinite(b) || b <= 0) return setErr("The position uncertainty must be above 0 m to save a profile.");
    if (h !== "" && !Number.isFinite(Number(h))) return setErr("The observer height must be a number (or empty) to save a profile.");
    setErr(null);
    add({ name: name.trim(), days: d, height: h, band: b });
    setName("");
  };

  return (
    <fieldset className="profiles">
      <legend>Mission profile (illustrative)</legend>
      <Explain id="profiles" />
      <label htmlFor={`${idPrefix}-select`}>Profile</label>
      <select id={`${idPrefix}-select`} value={sel} onChange={(e) => setSel(e.target.value)}>
        <optgroup label="Built-in (illustrative)">
          {BUILTIN_PROFILES.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </optgroup>
        {saved.length > 0 && (
          <optgroup label="Saved in this browser">
            {saved.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </optgroup>
        )}
      </select>
      <div className="row" style={{ marginTop: 6 }}>
        <button className="btn secondary" style={{ flex: "0 0 auto" }} onClick={apply}>Apply profile</button>
        {chosen && !chosen.builtin && (
          <button className="btn secondary" style={{ flex: "0 0 auto" }} onClick={() => { remove(chosen.id); setSel(BUILTIN_PROFILES[0].id); }}>Delete this saved profile</button>
        )}
      </div>
      <div className="row" style={{ marginTop: 6 }}>
        <div>
          <label htmlFor={`${idPrefix}-name`}>Save the current settings as</label>
          <input id={`${idPrefix}-name`} value={name} placeholder="profile name" onChange={(e) => setName(e.target.value)} />
        </div>
        <button className="btn secondary" style={{ flex: "0 0 auto", alignSelf: "end" }} onClick={save}>Save</button>
      </div>
      {err && <p className="error" role="alert">{err}</p>}
      <p className="help">
        Profiles only fill in the form below. The built-in ones are <span className="assump">illustrative assumptions</span>, not real mission requirements; an empty observer height means the 2.0 m default assumption.
      </p>
    </fieldset>
  );
}
