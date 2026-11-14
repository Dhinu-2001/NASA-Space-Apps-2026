import { useEffect, useState } from "react";
import { api, ApiError, type Health, type VersionInfo } from "./api/client";
import type { SitesResponse } from "./api/types";
import { CapabilitiesContext, CapabilityStrip, Loading } from "./ui";
import { AboutTab } from "./views/AboutTab";
import { CompareTab } from "./views/CompareTab";
import { DelayTab } from "./views/DelayTab";
import { ViewTab } from "./views/ViewTab";

type State =
  | { phase: "loading"; startedAt: number }
  | { phase: "error"; message: string }
  | { phase: "ready"; health: Health; version: VersionInfo; sites: SitesResponse };

const TABS = [
  { id: "view", label: "Site & time" },
  { id: "compare", label: "Compare" },
  { id: "delay", label: "Delay simulator" },
  { id: "about", label: "Data & assumptions" },
] as const;
type TabId = (typeof TABS)[number]["id"];

export default function App() {
  const [state, setState] = useState<State>({ phase: "loading", startedAt: Date.now() });
  const [tab, setTabState] = useState<TabId>(() => {
    const h = window.location.hash.replace("#", "");
    return (TABS.find((x) => x.id === h)?.id ?? "view") as TabId;
  });
  const setTab = (id: TabId) => {
    setTabState(id);
    window.history.replaceState(null, "", `#${id}`);
  };

  useEffect(() => {
    const ctl = new AbortController();
    Promise.all([api.health(ctl.signal), api.version(ctl.signal), api.sites(ctl.signal)])
      .then(([health, version, sites]) => setState({ phase: "ready", health, version, sites }))
      .catch((e: unknown) => {
        if ((e as Error).name === "AbortError") return;
        setState({ phase: "error", message: e instanceof ApiError ? e.message : "Unexpected error contacting the backend." });
      });
    return () => ctl.abort();
  }, []);

  return (
    <main className="app">
      <header className="top">
        <h1>Lunar Landing Site Navigator</h1>
        <span className="sub">
          {state.phase === "ready" ? <>backend <span data-testid="health-status">{state.health.status}</span> · model {state.health.model_version} · API {state.version.api_version} · stage {state.version.stage}</> : "NASA Space Apps 2026"}
        </span>
      </header>

      {state.phase === "loading" && <Loading startedAt={state.startedAt} label="Connecting to backend" />}
      {state.phase === "error" && (
        <p role="alert" className="error">Backend unavailable: {state.message} Start it with the commands in docs/DEV_SETUP.md.</p>
      )}

      {state.phase === "ready" && (
        <CapabilitiesContext.Provider value={state.version.capabilities}>
          <CapabilityStrip capabilities={state.version.capabilities} notice={state.version.notice} />
          <div className="tabs" role="tablist" aria-label="Views">
            {TABS.map((t) => (
              <button key={t.id} role="tab" aria-selected={tab === t.id} onClick={() => setTab(t.id)}>{t.label}</button>
            ))}
          </div>
          {tab === "view" && <ViewTab sites={state.sites.sites} />}
          {tab === "compare" && <CompareTab sites={state.sites.sites} />}
          {tab === "delay" && <DelayTab sites={state.sites.sites} />}
          {tab === "about" && <AboutTab sites={state.sites} />}
        </CapabilitiesContext.Provider>
      )}
    </main>
  );
}
