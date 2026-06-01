"use client";

import type { QueryClient } from "@tanstack/react-query";
import { queryKeys } from "../queries";
import type { Property } from "../types";
import {
  markPropertyCreationComplete,
  markPropertyCreationPending,
} from "./visibility";

/** SSE payload shape from POST /properties/stream (shared by dialog + chatbot). */
export type PropertyStreamEvent = {
  step?: string;
  property?: Property;
  property_id?: number;
  duplicate?: boolean;
  detail?: string;
  list_refresh?: boolean;
};

function resolvePropertyId(event: PropertyStreamEvent): number | null {
  const raw = event.property?.id ?? event.property_id;
  const id = Number(raw);
  return Number.isFinite(id) && id > 0 ? id : null;
}

function resolvePropertyName(event: PropertyStreamEvent, fallback?: string | null): string | null {
  const name = String(event.property?.name ?? fallback ?? "").trim();
  return name || null;
}

function refreshAdminPropertyQueries(qc: QueryClient): void {
  void qc.invalidateQueries({ queryKey: queryKeys.properties });
  void qc.invalidateQueries({ queryKey: queryKeys.dashboardSummary });
  void qc.invalidateQueries({ queryKey: queryKeys.rentAnalytics });
  void qc.invalidateQueries({ queryKey: ["tenant"] });
}

function upsertPropertyListCache(qc: QueryClient, property: Property): void {
  qc.setQueryData<Property[]>(queryKeys.properties, (current) => {
    const list = current ?? [];
    const without = list.filter((row) => row.id !== property.id);
    return [property, ...without];
  });
}

/** Chat-only create started — hide the in-flight name until terminal SSE. */
export function markPropertyCreationStarted(
  _qc: QueryClient | null,
  name?: string | null,
): void {
  markPropertyCreationPending(undefined, name);
}

/** Clear hide flags after failure and nudge lists to reconcile. */
export function markPropertyCreationFailed(
  qc: QueryClient | null,
  id?: number | string | null,
  name?: string | null,
): void {
  markPropertyCreationComplete(id, name);
  if (qc) refreshAdminPropertyQueries(qc);
}

/**
 * Apply one create-property SSE event to visibility flags + React Query cache.
 *
 * Intermediate steps keep the row hidden; terminal ``done`` unhides, upserts
 * the final property payload, and invalidates admin dashboards immediately.
 */
export function handleCreatePropertyStreamEvent(
  qc: QueryClient | null,
  event: PropertyStreamEvent,
): void {
  const step = event.step;
  const propertyId = resolvePropertyId(event);
  const propertyName = resolvePropertyName(event);

  if (step === "error") {
    markPropertyCreationComplete(propertyId, propertyName);
    if (qc) refreshAdminPropertyQueries(qc);
    return;
  }

  if (step === "done") {
    markPropertyCreationComplete(propertyId, propertyName);
    if (qc && event.property) {
      upsertPropertyListCache(qc, event.property);
    }
    if (qc) refreshAdminPropertyQueries(qc);
    return;
  }

  if (propertyId || propertyName) {
    markPropertyCreationPending(propertyId, propertyName);
  }
}

/** Alias used by the chat action executor. */
export function syncCreatePropertyStreamEvent(
  qc: QueryClient | null,
  event: PropertyStreamEvent,
): void {
  handleCreatePropertyStreamEvent(qc, event);
}
