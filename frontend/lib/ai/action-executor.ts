"use client";

import type { AIAction } from "./types";
import { clearSession, getApiBase, getToken } from "@/lib/api";
import {
  markPropertyCreationFailed,
  markPropertyCreationStarted,
  syncCreatePropertyStreamEvent,
} from "@/lib/properties/list-sync";
import { getRegisteredQueryClient } from "@/lib/query-client-holder";
import {
  logCreatePropertyFailure,
  logCreatePropertyPayload,
  logCreatePropertyStreamEvent,
} from "@/lib/properties/create-property-debug";
import { queryKeys } from "@/lib/queries";
import {
  buildCreatePropertyApiPayload,
  tokenSalePriceEthForPayload,
} from "@/components/properties/property-form-shared";
import type { Property } from "@/lib/types";

const delay = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms));

const MODAL_RETRIES = 6;
const MODAL_RETRY_DELAY = 220;

const ACTION_EVENT = "estatechain:ai-action";
const COMPLETION_EVENT = "estatechain:ai-completion";
const PENDING_TTL = 8000;
const CREATE_PROPERTY_MODAL = "CREATE_PROPERTY";
const EDIT_PROPERTY_MODAL = "EDIT_PROPERTY";
export const CREATE_PROPERTY_CHAT_ONLY_EVENT = "estatechain:create-property-chat-only";

export type AICompletionStatus = "success" | "error";

export type AICompletionEvent = {
  modal: string;
  status: AICompletionStatus;
  message?: string;
};

type PendingOpen = {
  action: AIAction;
  expiresAt: number;
};

const pendingModalOpens = new Map<string, PendingOpen>();
const workflowFormValues = new Map<string, Record<string, string>>();
const workflowPropertyIds = new Map<string, number | string>();

declare global {
  interface Window {
    __estatechainPendingModalActions?: Record<string, PendingOpen[]>;
  }
}

function nowMs() {
  return typeof performance !== "undefined" ? performance.now() : Date.now();
}

function rememberPendingOpen(action: AIAction) {
  if (!action.modal || action.type !== "OPEN_MODAL") return;
  pendingModalOpens.set(action.modal, { action, expiresAt: nowMs() + PENDING_TTL });
}

function rememberPendingAction(action: AIAction) {
  if (!action.modal) return;
  if (action.property_id !== undefined && action.property_id !== null) {
    workflowPropertyIds.set(action.modal, action.property_id);
  }
  window.__estatechainPendingModalActions ??= {};
  const queued = window.__estatechainPendingModalActions[action.modal] ?? [];
  queued.push({ action, expiresAt: nowMs() + PENDING_TTL });
  window.__estatechainPendingModalActions[action.modal] = queued;
}

export function emitAction(action: AIAction) {
  if (typeof window === "undefined") return;
  rememberPendingOpen(action);
  rememberPendingAction(action);
  window.dispatchEvent(new CustomEvent<AIAction>(ACTION_EVENT, { detail: action }));
}

export function subscribeAction(handler: (action: AIAction) => void) {
  if (typeof window === "undefined") return () => {};
  const listener = (e: Event) => handler((e as CustomEvent<AIAction>).detail);
  window.addEventListener(ACTION_EVENT, listener);
  return () => window.removeEventListener(ACTION_EVENT, listener);
}

export function takePendingModalOpen(modal: string, propertyId?: number | string): AIAction | null {
  const p = pendingModalOpens.get(modal);
  if (!p) return null;
  if (p.expiresAt < nowMs()) {
    pendingModalOpens.delete(modal);
    return null;
  }
  if (propertyId !== undefined) {
    if (String(p.action.property_id ?? "") !== String(propertyId)) return null;
  }
  pendingModalOpens.delete(modal);
  return p.action;
}

export function takePendingModalActions(modal: string): AIAction[] {
  const queued = window.__estatechainPendingModalActions?.[modal] ?? [];
  if (window.__estatechainPendingModalActions) {
    delete window.__estatechainPendingModalActions[modal];
  }
  const valid = queued.filter((p) => p.expiresAt >= nowMs()).map((p) => p.action);
  if (!valid.some((action) => action.type === "OPEN_MODAL")) return valid;
  return valid;
}

/** Drop queued modal events only — keeps accumulated FILL_FIELD values. */
export function clearPendingModalQueues(modal: string) {
  if (window.__estatechainPendingModalActions) {
    delete window.__estatechainPendingModalActions[modal];
  }
  pendingModalOpens.delete(modal);
}

/** Full reset after submit / error — queues and cached field values. */
export function clearPendingModalActions(modal: string) {
  clearPendingModalQueues(modal);
  workflowFormValues.delete(modal);
  workflowPropertyIds.delete(modal);
}

/**
 * Snapshot of every FILL_FIELD value the agent has written for the given
 * modal in the current workflow. Submitted forms should prefer this over
 * the React form state: it's untouched by render races, and it's exactly
 * what the agent intended to submit.
 */
export function getWorkflowFormValues(modal: string): Record<string, string> {
  return { ...(workflowFormValues.get(modal) ?? {}) };
}

function focusChatInput() {
  if (typeof document === "undefined") return;
  const focus = () => {
    const chatInput = document.querySelector<HTMLTextAreaElement>("[data-ai-chat-input]");
    if (chatInput && !chatInput.disabled) {
      chatInput.focus({ preventScroll: true });
    }
  };
  window.setTimeout(focus, 0);
  window.setTimeout(focus, 80);
  window.setTimeout(focus, 220);
}

function notifyAIDataChanged() {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent("estatechain:ai-data-changed"));
}

function enterCreatePropertyChatOnlyMode() {
  if (typeof window === "undefined") return;
  clearPendingModalQueues(CREATE_PROPERTY_MODAL);
  window.dispatchEvent(new CustomEvent(CREATE_PROPERTY_CHAT_ONLY_EVENT));
  focusChatInput();
}

function enterEditPropertyChatOnlyMode() {
  if (typeof window === "undefined") return;
  clearPendingModalQueues(EDIT_PROPERTY_MODAL);
  focusChatInput();
}

export function emitCompletion(event: AICompletionEvent) {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent<AICompletionEvent>(COMPLETION_EVENT, { detail: event }));
}

export function subscribeCompletion(handler: (event: AICompletionEvent) => void) {
  if (typeof window === "undefined") return () => {};
  const listener = (e: Event) => handler((e as CustomEvent<AICompletionEvent>).detail);
  window.addEventListener(COMPLETION_EVENT, listener);
  return () => window.removeEventListener(COMPLETION_EVENT, listener);
}

export function waitForCompletion(modal: string, timeoutMs = 120_000): Promise<AICompletionEvent | null> {
  if (typeof window === "undefined") return Promise.resolve(null);
  return new Promise((resolve) => {
    let timer = 0;
    const unsub = subscribeCompletion((ev) => {
      if (ev.modal !== modal) return;
      window.clearTimeout(timer);
      unsub();
      resolve(ev);
    });
    timer = window.setTimeout(() => {
      unsub();
      resolve(null);
    }, timeoutMs);
  });
}

export function focusField(modal: string, field: string) {
  if (typeof document === "undefined") return;
  // Never steal focus from the AI chat textbox — if the user is mid-
  // conversation their next keystroke must land in chat, not in the
  // form the agent is filling out. (Voice mode renders no chat input,
  // so this guard naturally no-ops there and we focus normally.)
  const chatInput = document.querySelector<HTMLTextAreaElement>(
    "[data-ai-chat-input]",
  );
  if (chatInput && !chatInput.disabled) return;
  const node = document.querySelector<HTMLInputElement | HTMLTextAreaElement | HTMLButtonElement>(
    `[data-workflow-field="${modal}.${field}"]`,
  );
  node?.focus();
  if (node instanceof HTMLInputElement) node.select();
}

async function waitForModalField(modal: string, timeoutMs = 5000) {
  if (typeof document === "undefined") return;
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    if (document.querySelector(`[data-workflow-field^="${modal}."]`)) return;
    await delay(100);
  }
}

/**
 * Try to open the modal on the current page.
 *
 * Returns true if either the modal is already open OR a trigger button was
 * found and clicked. Returns false when the modal can't be opened from the
 * current route (e.g. the user is on a different dashboard page).
 *
 * The previous implementation always blocked for ~3s waiting for the field
 * to appear, even when no trigger existed — that caused multi-second hangs
 * on every FILL_FIELD action coming in from the AI. We now only wait when
 * we actually clicked something.
 */
async function openWorkflowModal(modal: string): Promise<boolean> {
  if (typeof document === "undefined") return false;
  if (document.querySelector(`[data-workflow-field^="${modal}."]`)) return true;
  const trigger = document.querySelector<HTMLButtonElement>(`[data-workflow-modal-trigger="${modal}"]`);
  if (!trigger) return false;
  trigger.click();
  await waitForModalField(modal, 3000);
  return Boolean(document.querySelector(`[data-workflow-field^="${modal}."]`));
}

function setWorkflowInputValue(modal: string, field: string, value: string) {
  if (typeof document === "undefined") return;
  const input = document.querySelector<HTMLInputElement | HTMLTextAreaElement>(
    `[data-workflow-field="${modal}.${field}"]`,
  );
  if (!input) return;
  const descriptor = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(input), "value");
  descriptor?.set?.call(input, value);
  input.dispatchEvent(new Event("input", { bubbles: true }));
  input.dispatchEvent(new Event("change", { bubbles: true }));
}

/**
 * Brief visual pulse on the submit button so the user can SEE the agent
 * clicking it. We add a temporary outline + scale class, focus the button
 * (which paints the focus ring), then dispatch a real ``click`` so the
 * form's normal onSubmit handler runs — same code path a human user takes
 * when they tap "Create" themselves.
 */
async function clickWorkflowSubmitVisibly(modal: string): Promise<boolean> {
  if (typeof document === "undefined") return false;
  const opened = await openWorkflowModal(modal);
  if (!opened) {
    console.info(
      "[AI Action] Workflow form not on this page; cannot submit:",
      modal,
    );
    return false;
  }
  await waitForModalField(modal);

  // Hydrate any cached field values into the DOM (and React state) so the
  // mutation receives the values the user dictated, even on the first
  // mount after a navigation.
  const values = workflowFormValues.get(modal) ?? {};
  for (const [field, value] of Object.entries(values)) {
    setWorkflowInputValue(modal, field, value);
  }
  await delay(250); // let React flush state

  const form = document.querySelector<HTMLFormElement>(`form[data-workflow-form="${modal}"]`);
  if (!form) {
    console.info("[AI Action] Workflow form node missing after open:", modal);
    return false;
  }
  const submitBtn = form.querySelector<HTMLButtonElement>('button[type="submit"]');
  if (!submitBtn || submitBtn.disabled) {
    // Fallback — submit programmatically. Less visual but still triggers
    // the form's onSubmit (which is what runs the mutation).
    console.log("[AI Action] Submit button missing/disabled; falling back to requestSubmit:", modal);
    form.requestSubmit();
    return true;
  }

  // Visual "press" effect: focus → highlight class → click → release.
  submitBtn.scrollIntoView({ block: "nearest", behavior: "smooth" });
  submitBtn.focus({ preventScroll: true });
  submitBtn.classList.add("ai-agent-clicking");
  await delay(220); // long enough for the human eye to see the ring/pulse
  console.log("[AI Action] Visibly clicking submit button:", modal);
  submitBtn.click();
  // Keep the highlight on briefly so the click is unmistakable, then drop it.
  window.setTimeout(() => submitBtn.classList.remove("ai-agent-clicking"), 600);
  return true;
}

async function submitCreatePropertyFromChat(
  formValuesOverride?: Record<string, string>,
): Promise<boolean> {
  const stored = workflowFormValues.get(CREATE_PROPERTY_MODAL) ?? {};
  const values = { ...stored, ...(formValuesOverride ?? {}) };
  const required = ["name", "location", "total_value", "token_supply", "token_symbol"] as const;
  const missing = required.filter((field) => !String(values[field] ?? "").trim());
  if (missing.length) {
    emitCompletion({
      modal: CREATE_PROPERTY_MODAL,
      status: "error",
      message: `Missing property details: ${missing.join(", ")}.`,
    });
    focusChatInput();
    return false;
  }

  const payload = buildCreatePropertyApiPayload({
    name: String(values.name),
    location: String(values.location),
    total_value: String(values.total_value),
    token_supply: String(values.token_supply),
    token_symbol: String(values.token_symbol),
    monthly_rent_eth: values.monthly_rent_eth ? String(values.monthly_rent_eth) : undefined,
    images: [],
  });
  workflowFormValues.set(CREATE_PROPERTY_MODAL, {
    ...stored,
    name: payload.name,
    location: payload.location,
    total_value: payload.total_value,
    token_supply: payload.token_supply,
    token_symbol: payload.token_symbol,
    ...(payload.monthly_rent_eth ? { monthly_rent_eth: payload.monthly_rent_eth } : {}),
  });

  logCreatePropertyPayload("chat", payload);

  const queryClient = getRegisteredQueryClient();
  markPropertyCreationStarted(queryClient, payload.name);
  let finalPropertyName = payload.name;
  let completedPropertyId: number | string | null | undefined = null;

  try {
    const base = getApiBase();
    const token = getToken();
    const streamTimeoutMs = 10 * 60 * 1000;
    const timeoutSignal =
      typeof AbortSignal !== "undefined" && "timeout" in AbortSignal
        ? AbortSignal.timeout(streamTimeoutMs)
        : undefined;

    const res = await fetch(`${base}/properties/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(payload),
      signal: timeoutSignal,
    });

    if (!res.ok) {
      if (res.status === 401) clearSession();
      const errText = await res.text().catch(() => "");
      let detail = res.status === 401 ? "Session expired. Please log in again." : `HTTP ${res.status}`;
      try {
        const parsed = JSON.parse(errText);
        if (parsed?.detail && res.status !== 401) detail = String(parsed.detail);
      } catch {
        if (errText) detail = errText;
      }
      logCreatePropertyFailure("chat", new Error(detail), {
        httpStatus: res.status,
        responseBody: errText.slice(0, 500),
      });
      throw new Error(detail);
    }

    const reader = res.body?.getReader();
    if (!reader) throw new Error("No response body");

    const decoder = new TextDecoder();
    let sseBuffer = "";
    let finalError: string | null = null;
    let streamComplete = false;
    let lastFailedStep: string | undefined;

    while (!streamComplete) {
      const { done, value } = await reader.read();
      if (done) break;
      sseBuffer += decoder.decode(value, { stream: true });
      const parts = sseBuffer.split("\n\n");
      sseBuffer = parts.pop() || "";

      for (const part of parts) {
        for (const line of part.split("\n")) {
          if (!line.startsWith("data: ")) continue;
          const raw = line.slice(6).trim();
          if (!raw) continue;
          try {
            const event = JSON.parse(raw) as {
              step?: string;
              property?: Property;
              property_id?: number;
              detail?: string;
              failed_step?: string;
            };
            logCreatePropertyStreamEvent(event);
            const eventPropertyId = event.property?.id ?? event.property_id;
            if (event.step === "done") {
              finalPropertyName = event.property?.name || finalPropertyName;
              completedPropertyId = eventPropertyId;
              syncCreatePropertyStreamEvent(queryClient, event);
              streamComplete = true;
            } else if (event.step === "error") {
              finalError = event.detail || "Property creation failed.";
              lastFailedStep = event.failed_step;
              syncCreatePropertyStreamEvent(queryClient, event);
              streamComplete = true;
            } else if (eventPropertyId) {
              syncCreatePropertyStreamEvent(queryClient, event);
            }
          } catch {
            /* skip malformed SSE JSON */
          }
          if (streamComplete) break;
        }
        if (streamComplete) break;
      }
    }

    if (streamComplete) {
      await reader.cancel().catch(() => {
        /* stream already closed */
      });
    }
    if (finalError) {
      logCreatePropertyFailure("chat", new Error(finalError), { failedStep: lastFailedStep });
      throw new Error(finalError);
    }
    clearPendingModalActions(CREATE_PROPERTY_MODAL);
    emitCompletion({
      modal: CREATE_PROPERTY_MODAL,
      status: "success",
      message: finalPropertyName
        ? `Property '${finalPropertyName}' created successfully.`
        : "Property created successfully.",
    });
    notifyAIDataChanged();
    focusChatInput();
    return true;
  } catch (err: any) {
    logCreatePropertyFailure("chat", err, {
      propertyName: finalPropertyName || payload.name,
      propertyId: completedPropertyId,
    });
    markPropertyCreationFailed(
      queryClient,
      completedPropertyId,
      finalPropertyName || payload.name,
    );
    notifyAIDataChanged();
    emitCompletion({
      modal: CREATE_PROPERTY_MODAL,
      status: "error",
      message: err?.message || "Failed to create property.",
    });
    focusChatInput();
    return false;
  }
}

function valueFromEditField(
  values: Record<string, string>,
  field: string,
  fallback: string | number | null | undefined,
) {
  if (Object.prototype.hasOwnProperty.call(values, field)) {
    return String(values[field] ?? "").trim();
  }
  return fallback == null ? "" : String(fallback);
}

async function fetchProperty(propertyId: number | string): Promise<Property> {
  const cached = getRegisteredQueryClient()
    ?.getQueryData<Property[]>(queryKeys.properties)
    ?.find((property) => String(property.id) === String(propertyId));
  if (cached) return cached;

  const base = getApiBase();
  const token = getToken();
  const res = await fetch(`${base}/properties/${propertyId}`, {
    headers: {
      Accept: "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });
  if (!res.ok) {
    if (res.status === 401) clearSession();
    throw new Error(res.status === 404 ? "Property not found." : `HTTP ${res.status}`);
  }
  return (await res.json()) as Property;
}

async function submitEditPropertyFromChat(
  formValuesOverride?: Record<string, string>,
): Promise<boolean> {
  const propertyId = workflowPropertyIds.get(EDIT_PROPERTY_MODAL);
  if (propertyId == null) {
    emitCompletion({
      modal: EDIT_PROPERTY_MODAL,
      status: "error",
      message: "I couldn't identify which property to edit. Please include the property name again.",
    });
    focusChatInput();
    return false;
  }

  const stored = workflowFormValues.get(EDIT_PROPERTY_MODAL) ?? {};
  const values = { ...stored, ...(formValuesOverride ?? {}) };

  try {
    const property = await fetchProperty(propertyId);
    const totalValue = valueFromEditField(values, "total_value", property.total_value);
    const tokenSupply = valueFromEditField(values, "token_supply", property.token_supply);
    const tokenSalePrice = property.token_address
      ? String(property.token_sale_price_eth ?? "")
      : tokenSalePriceEthForPayload(String(totalValue), String(tokenSupply));
    const payload = {
      name: valueFromEditField(values, "name", property.name),
      location: valueFromEditField(values, "location", property.location),
      total_value: totalValue,
      token_supply: tokenSupply,
      token_symbol: valueFromEditField(values, "token_symbol", property.token_symbol),
      token_sale_price_eth: tokenSalePrice,
      monthly_rent_eth: Object.prototype.hasOwnProperty.call(values, "monthly_rent_eth")
        ? String(values.monthly_rent_eth ?? "").trim() || null
        : property.monthly_rent_eth ?? null,
      images: property.images ?? [],
    };

    const base = getApiBase();
    const token = getToken();
    const res = await fetch(`${base}/properties/${property.id}`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      if (res.status === 401) clearSession();
      const errText = await res.text().catch(() => "");
      let detail = res.status === 401 ? "Session expired. Please log in again." : `HTTP ${res.status}`;
      try {
        const parsed = JSON.parse(errText);
        if (parsed?.detail && res.status !== 401) detail = String(parsed.detail);
      } catch {
        if (errText) detail = errText;
      }
      throw new Error(detail);
    }

    const updated = (await res.json()) as Property;
    const queryClient = getRegisteredQueryClient();
    queryClient?.setQueryData<Property[]>(queryKeys.properties, (current) =>
      (current ?? []).map((property) => (property.id === updated.id ? updated : property)),
    );
    void queryClient?.invalidateQueries({ queryKey: queryKeys.properties });
    void queryClient?.invalidateQueries({ queryKey: queryKeys.property(updated.id) });
    clearPendingModalQueues(EDIT_PROPERTY_MODAL);
    workflowFormValues.delete(EDIT_PROPERTY_MODAL);
    emitCompletion({
      modal: EDIT_PROPERTY_MODAL,
      status: "success",
      message: `Property "${updated.name}" updated successfully.`,
    });
    notifyAIDataChanged();
    focusChatInput();
    return true;
  } catch (err: any) {
    clearPendingModalQueues(EDIT_PROPERTY_MODAL);
    workflowFormValues.delete(EDIT_PROPERTY_MODAL);
    emitCompletion({
      modal: EDIT_PROPERTY_MODAL,
      status: "error",
      message: err?.message || "Failed to update property.",
    });
    focusChatInput();
    return false;
  }
}

/** Execute a single UI action. */
export async function executeAction(
  action: AIAction,
  router: { push: (href: string) => void },
  opts?: { createPropertyChatOnly?: boolean; editPropertyChatOnly?: boolean },
) {
  console.log("[AI Action] Executing:", action.type, action);
  if (action.modal && action.property_id !== undefined && action.property_id !== null) {
    workflowPropertyIds.set(action.modal, action.property_id);
  }
  if (opts?.createPropertyChatOnly) {
    if (action.type === "NAVIGATE") {
      enterCreatePropertyChatOnlyMode();
      return;
    }
    if (action.modal === CREATE_PROPERTY_MODAL) {
      if (action.type === "OPEN_MODAL" || action.type === "FOCUS_FIELD") {
        enterCreatePropertyChatOnlyMode();
        return;
      }
      if (action.type === "FILL_FIELD" && action.field) {
        const values = workflowFormValues.get(CREATE_PROPERTY_MODAL) ?? {};
        values[action.field] = String(action.value ?? "");
        workflowFormValues.set(CREATE_PROPERTY_MODAL, values);
        enterCreatePropertyChatOnlyMode();
        return;
      }
      if (action.type === "SUBMIT_FORM") {
        enterCreatePropertyChatOnlyMode();
        await submitCreatePropertyFromChat(action.form_values ?? undefined);
        notifyAIDataChanged();
        return;
      }
    }
  }
  if (opts?.editPropertyChatOnly && action.type === "NAVIGATE") {
    enterEditPropertyChatOnlyMode();
    return;
  }
  if (opts?.editPropertyChatOnly && action.modal === EDIT_PROPERTY_MODAL) {
    if (action.type === "OPEN_MODAL" || action.type === "FOCUS_FIELD") {
      enterEditPropertyChatOnlyMode();
      return;
    }
    if (action.type === "FILL_FIELD" && action.field) {
      const values = workflowFormValues.get(EDIT_PROPERTY_MODAL) ?? {};
      values[action.field] = String(action.value ?? "");
      workflowFormValues.set(EDIT_PROPERTY_MODAL, values);
      enterEditPropertyChatOnlyMode();
      return;
    }
    if (action.type === "SUBMIT_FORM") {
      enterEditPropertyChatOnlyMode();
      await submitEditPropertyFromChat(action.form_values ?? undefined);
      return;
    }
  }
  if (action.type === "NAVIGATE" && action.route) {
    console.log("[AI Action] Navigating to:", action.route);
    router.push(action.route);
    await delay(600); // Wait for page to mount
    console.log("[AI Action] Navigation complete, waiting for mount...");
    return;
  }
  if (action.type === "OPEN_MODAL" && action.modal) {
    console.log("[AI Action] Opening modal:", action.modal);
    // Do not wipe workflowFormValues — OPEN_MODAL often precedes FILL_FIELD
    // in the same turn; clearing here caused empty submits on repeat opens.
    clearPendingModalQueues(action.modal);
    const opened = await openWorkflowModal(action.modal);
    // Always emit the OPEN_MODAL event so listeners that mount later (after
    // a navigation) can pick it up via takePendingModalOpen.
    for (let i = 0; i < MODAL_RETRIES; i++) {
      emitAction(action);
      await delay(MODAL_RETRY_DELAY);
    }
    if (opened) {
      await delay(400); // Extra wait for modal to fully render
      console.log("[AI Action] Modal should be open now");
    } else {
      console.info(
        "[AI Action] OPEN_MODAL emitted but no trigger on this page (modal will open on navigation):",
        action.modal,
      );
    }
    return;
  }
  if (action.type === "FOCUS_FIELD" && action.modal && action.field) {
    console.log("[AI Action] Focusing field:", action.modal, action.field);
    focusField(action.modal, action.field);
    return;
  }
  if (action.type === "FILL_FIELD" && action.modal && action.field) {
    console.log("[AI Action] Filling field:", action.modal, action.field, "=", action.value);
    // Remember the value regardless of whether the form is mounted — the
    // dialog component drains pending actions on mount, so navigating to
    // the page later will still hydrate the form with these values.
    const values = workflowFormValues.get(action.modal) ?? {};
    values[action.field] = String(action.value ?? "");
    workflowFormValues.set(action.modal, values);
    // Try to fill the live input if the modal is reachable from the
    // current page; otherwise emit-only so navigation-on-mount works.
    const opened = await openWorkflowModal(action.modal);
    if (opened) {
      await waitForModalField(action.modal);
      setWorkflowInputValue(action.modal, action.field, String(action.value ?? ""));
    }
    emitAction(action);
    await delay(opened ? 150 : 30); // Allow React state to flush
    return;
  }
  if (action.type === "SUBMIT_FORM" && action.modal) {
    console.log("[AI Action] Submitting form (visible click):", action.modal);
    const clicked = await clickWorkflowSubmitVisibly(action.modal);
    // Emit the action AFTER the click so any listener that wants to react
    // to "the agent just hit submit" can do so without colliding with the
    // form's own onSubmit handler.
    if (clicked) {
      await delay(400);
      emitAction(action);
    } else {
      // Couldn't reach the form — surface the action so the dialog (if it
      // mounts later via NAVIGATE) can pick it up from the pending queue.
      emitAction(action);
    }
    return;
  }
  console.log("[AI Action] Unknown action type or missing fields:", action);
}

export async function executeActions(actions: AIAction[], router: { push: (href: string) => void }) {
  const createPropertyChatOnly = actions.some((action) => action.modal === CREATE_PROPERTY_MODAL);
  const editPropertyChatOnly = actions.some((action) => action.modal === EDIT_PROPERTY_MODAL);
  const hasEditFieldChanges = actions.some(
    (action) => action.modal === EDIT_PROPERTY_MODAL && action.type === "FILL_FIELD" && !!action.field,
  );
  const hasEditSubmit = actions.some(
    (action) => action.modal === EDIT_PROPERTY_MODAL && action.type === "SUBMIT_FORM",
  );
  for (const action of actions) {
    await executeAction(action, router, { createPropertyChatOnly, editPropertyChatOnly });
  }
  if (editPropertyChatOnly && hasEditFieldChanges && !hasEditSubmit) {
    await submitEditPropertyFromChat();
  }
}

/* -------------------------------------------------------------------------- */
/*  Backward-compatible aliases (old action-bus API)                        */
/* -------------------------------------------------------------------------- */

export function preventCloseFromWorkflowBubble(event: { target: EventTarget | null; preventDefault: () => void }) {
  const target = event.target as Element | null;
  if (target && typeof (target as Element).closest === "function") {
    if (target.closest(`[data-workflow-bubble]`)) {
      event.preventDefault();
    }
  }
}

export function isWorkflowModalAction(action: AIAction, modal: string) {
  return "modal" in action && action.modal === modal;
}

export function workflowPropertyMatches(action: AIAction, propertyId: number | string) {
  if (!("property_id" in action) || action.property_id === undefined || action.property_id === null) return false;
  return String(action.property_id) === String(propertyId);
}

export const focusWorkflowField = focusField;
export const emitWorkflowAction = emitAction;
export const subscribeWorkflowAction = subscribeAction;
export const takePendingWorkflowActions = takePendingModalActions;
export const clearPendingWorkflowActions = clearPendingModalActions;
export const emitWorkflowCompletion = emitCompletion;
export const subscribeWorkflowCompletion = subscribeCompletion;
export const waitForWorkflowCompletion = waitForCompletion;
