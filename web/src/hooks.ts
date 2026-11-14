import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "./api/client";

export type Async<T> =
  | { phase: "idle" }
  | { phase: "loading"; startedAt: number }
  | { phase: "error"; error: ApiError | Error }
  | { phase: "ready"; data: T };

/** Run an async loader whenever `key` changes (key === null keeps it idle). Aborts stale requests. */
export function useAsync<T>(loader: ((signal: AbortSignal) => Promise<T>) | null, key: string | null): Async<T> {
  const [state, setState] = useState<Async<T>>({ phase: "idle" });
  const loaderRef = useRef(loader);
  loaderRef.current = loader;
  useEffect(() => {
    if (key === null || loaderRef.current === null) {
      setState({ phase: "idle" });
      return;
    }
    const ctl = new AbortController();
    setState({ phase: "loading", startedAt: Date.now() });
    loaderRef.current(ctl.signal)
      .then((data) => setState({ phase: "ready", data }))
      .catch((e: unknown) => {
        if ((e as Error).name === "AbortError") return;
        setState({ phase: "error", error: e instanceof Error ? e : new Error("Unexpected error") });
      });
    return () => ctl.abort();
  }, [key]);
  return state;
}

/** Seconds elapsed since `startedAt`, ticking once a second. */
export function useElapsed(startedAt: number | null): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (startedAt === null) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [startedAt]);
  return startedAt === null ? 0 : Math.max(0, Math.floor((now - startedAt) / 1000));
}

export function useToggle(initial = false): [boolean, () => void] {
  const [v, setV] = useState(initial);
  return [v, useCallback(() => setV((x) => !x), [])];
}
