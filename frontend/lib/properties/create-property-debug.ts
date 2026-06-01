/** Browser console diagnostics for property create / deploy (filter: CreateProperty). */
const PREFIX = "[CreateProperty]";

export type CreatePropertyDebugPayload = {
  name?: string;
  location?: string;
  total_value?: string;
  token_supply?: string;
  token_symbol?: string;
  token_sale_price_eth?: string;
  monthly_rent_eth?: string | null;
};

export function logCreateProperty(message: string, data?: Record<string, unknown>) {
  if (typeof console === "undefined") return;
  if (data !== undefined) {
    console.log(PREFIX, message, data);
  } else {
    console.log(PREFIX, message);
  }
}

export function logCreatePropertyPayload(
  source: "dialog" | "chat" | "stream",
  payload: CreatePropertyDebugPayload,
) {
  const total = Number(payload.total_value ?? 0);
  const supply = Number(payload.token_supply ?? 0);
  const sale =
    payload.token_sale_price_eth ??
    (Number.isFinite(total) && Number.isFinite(supply) && supply > 0
      ? String(total / supply)
      : "");
  logCreateProperty(`submit (${source})`, {
    ...payload,
    token_sale_price_eth: sale,
    sale_price_per_token_eth: sale,
  });
}

export function logCreatePropertyStreamEvent(event: {
  step?: string;
  detail?: string;
  failed_step?: string;
  property_id?: number;
  property?: { id?: number; token_address?: string | null };
  duplicate?: boolean;
  resuming_setup?: boolean;
}) {
  const step = event.step ?? "unknown";
  if (step === "error") {
    console.error(PREFIX, "SSE error", {
      step,
      failed_step: event.failed_step,
      detail: event.detail,
      property_id: event.property_id ?? event.property?.id,
    });
    return;
  }
  logCreateProperty("SSE step", {
    step,
    failed_step: event.failed_step,
    detail: event.detail,
    property_id: event.property_id ?? event.property?.id,
    token_address: event.property?.token_address,
    duplicate: event.duplicate,
    resuming_setup: event.resuming_setup,
  });
}

export function logCreatePropertyFailure(
  source: "dialog" | "chat" | "stream",
  err: unknown,
  context?: Record<string, unknown>,
) {
  const message = err instanceof Error ? err.message : String(err);
  console.error(PREFIX, `failed (${source})`, { message, ...context, err });
}
