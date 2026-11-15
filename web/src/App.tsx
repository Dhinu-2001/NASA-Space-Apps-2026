import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { api, ApiError, type Health, type VersionInfo } from "./api/client";
import type { SitesResponse } from "./api/types";
import { LearnProvider, LearnTab, LearnToggle } from "./learn";
import { CapabilitiesContext, CapabilityStrip, Loading } from "./ui";
import { AboutTab } from "./views/AboutTab";
import { CompareTab } from "./views/CompareTab";
import { DelayTab } from "./views/DelayTab";
import { SitesTab } from "./views/SitesTab";
import { ViewTab } from "./views/ViewTab";

type State =
  | { phase: "loading"; startedAt: number }
  | { phase: "error"; message: string }
  | { phase: "ready"; health: Health; version: VersionInfo; sites: SitesResponse };

const TABS = [
  { id: "view", label: "Site & time" },
  { id: "compare", label: "Compare" },
  { id: "sites", label: "Landing sites" },
  { id: "delay", label: "Delay simulator" },
  { id: "learn", label: "Learn" },
  { id: "about", label: "Data & assumptions" },
] as const;
type TabId = (typeof TABS)[number]["id"];

export default function App() {
  const [state, setState] = useState<State>({ phase: "loading", startedAt: Date.now() });
  const [tab, setTabState] = useState<TabId>(() => {
    const h = window.location.hash.replace("#", "");
    return (TABS.find((x) => x.id === h)?.id ?? "view") as TabId;
  });
  const tabRefs = useRef<Record<string, HTMLButtonElement | null>>({});
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

  // WAI-ARIA tabs pattern: arrow keys move between tabs, Home/End jump, only the selected tab is in the tab order.
  const onTabKey = (e: KeyboardEvent<HTMLButtonElement>, i: number) => {
    let n = -1;
    if (e.key === "ArrowRight") n = (i + 1) % TABS.length;
    else if (e.key === "ArrowLeft") n = (i - 1 + TABS.length) % TABS.length;
    else if (e.key === "Home") n = 0;
    else if (e.key === "End") n = TABS.length - 1;
    if (n < 0) return;
    e.preventDefault();
    setTab(TABS[n].id);
    tabRefs.current[TABS[n].id]?.focus();
  };

  return (
    <LearnProvider>
      <a className="skip-link" href={`#panel-${tab}`}>Skip to the main content</a>
      <main className="app">
        <header className="top">
          <h1>Lunar Landing Site Navigator</h1>
          <div className="top-right">
            <span className="sub">
              {state.phase === "ready" ? <>backend <span data-testid="health-status">{state.health.status}</span> · model {state.health.model_version} · API {state.version.api_version} · stage {state.version.stage}</> : "NASA Space Apps 2026"}
            </span>
            <LearnToggle />
          </div>
        </header>

        {state.phase === "loading" && <Loading startedAt={state.startedAt} label="Connecting to backend" />}
        {state.phase === "error" && (
          <p role="alert" className="error">Backend unavailable: {state.message} Start it with the commands in docs/DEV_SETUP.md.</p>
        )}

        {state.phase === "ready" && (
          <CapabilitiesContext.Provider value={state.version.capabilities}>
            <CapabilityStrip capabilities={state.version.capabilities} notice={state.version.notice} />
            <div className="tabs" role="tablist" aria-label="Views">
              {TABS.map((t, i) => (
                <button
                  key={t.id}
                  id={`tab-${t.id}`}
                  ref={(el) => { tabRefs.current[t.id] = el; }}
                  role="tab"
                  aria-selected={tab === t.id}
                  aria-controls={`panel-${t.id}`}
                  tabIndex={tab === t.id ? 0 : -1}
                  onClick={() => setTab(t.id)}
                  onKeyDown={(e) => onTabKey(e, i)}
                >
                  {t.label}
                </button>
              ))}
            </div>
            <div id={`panel-${tab}`} tabIndex={-1} role="tabpanel" aria-labelledby={`tab-${tab}`}>
              {tab === "view" && <ViewTab sites={state.sites.sites} />}
              {tab === "compare" && <CompareTab sites={state.sites.sites} />}
              {tab === "sites" && <SitesTab sites={state.sites.sites} />}
              {tab === "delay" && <DelayTab sites={state.sites.sites} />}
              {tab === "learn" && <LearnTab />}
              {tab === "about" && <AboutTab sites={state.sites} />}
            </div>
          </CapabilitiesContext.Provider>
        )}
      </main>
    </LearnProvider>
  );
}
