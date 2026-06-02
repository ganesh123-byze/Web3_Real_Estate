import { ApiError } from "@/lib/api";

const INSUFFICIENT_FUNDS_MESSAGE =
  "Your wallet funds are insufficient for this transaction. Please check your ETH balance or reduce the amount, then try again.";

const USER_REJECTED_MESSAGE = "Transaction cancelled in MetaMask.";
const PENDING_WALLET_REQUEST_MESSAGE =
  "A MetaMask request is already open. Please finish or close it in MetaMask, then try again.";

function collectErrorText(err: unknown): string {
  if (!err) return "";
  if (typeof err === "string") return err;
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  if (typeof err === "object") {
    const obj = err as Record<string, unknown>;
    const parts = [
      obj.message,
      obj.reason,
      obj.shortMessage,
      obj.code,
      obj.detail,
    ]
      .filter((v) => typeof v === "string" && v.trim())
      .map((v) => String(v));
    if (parts.length) return parts.join(" ");
  }
  return String(err);
}

function looksLikeInsufficientFunds(text: string): boolean {
  const lower = text.toLowerCase();
  return (
    lower.includes("outoffunds") ||
    lower.includes("insufficient funds") ||
    lower.includes("insufficient balance") ||
    lower.includes("insufficient eth") ||
    lower.includes("not enough eth") ||
    lower.includes("exceeds balance") ||
    (lower.includes("estimategas") && lower.includes("call_exception")) ||
    (lower.includes("missing revert data") && lower.includes("estimategas"))
  );
}

function looksLikeUserRejected(text: string, err: unknown): boolean {
  const lower = text.toLowerCase();
  const code = (err as { code?: unknown })?.code;
  return (
    lower.includes("user rejected") ||
    lower.includes("user denied") ||
    lower.includes("rejected the request") ||
    code === 4001 ||
    code === "ACTION_REJECTED"
  );
}

function looksLikePendingWalletRequest(text: string, err: unknown): boolean {
  const lower = text.toLowerCase();
  const code = (err as { code?: unknown })?.code;
  return (
    code === -32002 ||
    lower.includes("already pending") ||
    lower.includes("wallet_requestpermissions") ||
    lower.includes("request of type") && lower.includes("already pending")
  );
}

function looksLikeRawRpcPayload(text: string): boolean {
  return text.length > 220 || text.includes('"transaction":') || text.includes("CALL_EXCEPTION");
}

/** Map MetaMask / ethers / API errors to concise user-facing copy. */
export function formatWalletTransactionError(
  err: unknown,
  fallback = "Transaction failed. Please try again.",
): string {
  const text = collectErrorText(err).trim();
  const lower = text.toLowerCase();

  if (err instanceof ApiError && (err.status === 402 || looksLikeInsufficientFunds(lower))) {
    return text || INSUFFICIENT_FUNDS_MESSAGE;
  }

  if (looksLikeUserRejected(text, err)) {
    return USER_REJECTED_MESSAGE;
  }

  if (looksLikePendingWalletRequest(text, err)) {
    return PENDING_WALLET_REQUEST_MESSAGE;
  }

  if (looksLikeInsufficientFunds(lower)) {
    return INSUFFICIENT_FUNDS_MESSAGE;
  }

  if (!text || looksLikeRawRpcPayload(text)) {
    return fallback;
  }

  return text;
}
