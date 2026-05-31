"use client";

import type { QueryClient } from "@tanstack/react-query";

let registeredClient: QueryClient | null = null;

/** Register the app QueryClient so chat-only workflows can invalidate caches. */
export function registerQueryClient(client: QueryClient): void {
  registeredClient = client;
}

export function getRegisteredQueryClient(): QueryClient | null {
  return registeredClient;
}
