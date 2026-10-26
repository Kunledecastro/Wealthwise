"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "./api";

/** Loads JSON from a GET endpoint; re-fetches when `path` changes or `reload()` is called. */
export function useLoad<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    if (!path) return;
    let active = true;
    api<T>(path)
      .then((d) => {
        if (!active) return;
        setData(d);
        setError(null);
      })
      .catch((e: unknown) => active && setError(e instanceof ApiError ? e.message : "Could not load data."));
    return () => {
      active = false;
    };
  }, [path, version]);

  const reload = useCallback(() => setVersion((v) => v + 1), []);
  return { data, error, reload, loading: data === null && error === null };
}
