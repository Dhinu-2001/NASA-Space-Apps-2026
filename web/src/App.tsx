import { useEffect, useState } from "react";
import { api, ApiError, type Health, type VersionInfo } from "./api/client";

type State =
  | { phase: "loading" }
  | { phase: "error"; message: string }
  | { phase: "ready"; health: Health; version: VersionInfo };

export default function App() {
  const [state, setState] = useState<State>({ phase: "loading" });

  useEffect(() => {
    const ctl = new AbortController();
    Promise.all([api.health(ctl.signal), api.version(ctl.signal)])
      .then(([health, version]) => setState({ phase: "ready", health, version }))
      .catch((e: unknown) => {
        if ((e as Error).name === "AbortError") return;
        setState({
          phase: "error",
          message: e instanceof ApiError ? e.message : "Unexpected error contacting the backend.",
        });
      });
    return () => ctl.abort();
  }, []);

  return (
    <main style={{ fontFamily: "system-ui, sans-serif", maxWidth: 760, margin: "2rem auto", padding: "0 16px" }}>
      <h1>Lunar Landing Site Navigator</h1>
      <p role="note" style={{ border: "1px solid #b58900", padding: "0.75rem", borderRadius: 6 }}>
        <strong>Development build.</strong>{" "}
        {state.phase === "ready"
          ? state.version.notice
          : "Scientific capabilities are listed with their real status once the backend responds."}
      </p>

      {state.phase === "loading" && <p>Connecting to backend…</p>}
      {state.phase === "error" && (
        <p role="alert">Backend unavailable: {state.message} Start it with the commands in docs/DEV_SETUP.md.</p>
      )}
      {state.phase === "ready" && (
        <>
          <h2>Backend status</h2>
          <p>
            <strong data-testid="health-status">{state.health.status}</strong> · model{" "}
            {state.health.model_version} · API {state.version.api_version} · stage {state.version.stage}
          </p>
          <h2>Scientific capabilities</h2>
          <table>
            <thead>
              <tr>
                <th align="left">Capability</th>
                <th align="left">Stage</th>
                <th align="left">Status</th>
              </tr>
            </thead>
            <tbody>
              {state.version.capabilities.map((c) => (
                <tr key={c.key}>
                  <td>{c.title}</td>
                  <td>{c.stage}</td>
                  <td>{c.status.replaceAll("_", " ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </main>
  );
}
