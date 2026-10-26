"use client";

import { useEffect, useState } from "react";
import { fragmentParam } from "./schemas";

/**
 * Reads a one-time token from the URL fragment (e.g. #invite=...). Fragments are
 * never sent to servers, so tokens stay out of access logs. The fragment is then
 * removed from the address bar and history. Only use in client-only components.
 */
export function useFragmentToken(key: string): string | null {
  const [token] = useState(() => (typeof window === "undefined" ? null : fragmentParam(window.location.hash, key)));
  useEffect(() => {
    if (window.location.hash) window.history.replaceState(null, "", window.location.pathname);
  }, []);
  return token;
}
