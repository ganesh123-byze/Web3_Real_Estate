"use client";

import { useEffect, useState } from "react";
import { getSession, type SessionRecord } from "@/lib/api";
import { refreshMe } from "@/lib/auth";

/** Live session user for account menu components (sidebar card, header pill). */
export function useSessionAccount() {
  const [session, setSession] = useState<SessionRecord | null>(null);

  useEffect(() => {
    let cancelled = false;

    const sync = () => setSession(getSession());

    const hydrate = async () => {
      sync();
      if (!getSession()?.token) return;
      await refreshMe();
      if (!cancelled) sync();
    };

    void hydrate();
    window.addEventListener("estatechain:session-changed", sync);
    window.addEventListener("storage", sync);
    return () => {
      cancelled = true;
      window.removeEventListener("estatechain:session-changed", sync);
      window.removeEventListener("storage", sync);
    };
  }, []);

  return session;
}
