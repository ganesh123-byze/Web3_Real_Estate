import {
  resolveBuildTimeApiBaseUrl,
  resolveBuildTimeChainId,
  resolveExplorerTxBase,
} from "@/lib/runtime-config-resolver";

const ttsEnabledRaw = process.env.NEXT_PUBLIC_WORKFLOW_TTS_ENABLED;
const ttsGenderRaw = (process.env.NEXT_PUBLIC_WORKFLOW_TTS_GENDER || "female").toLowerCase();

export const RUNTIME_CONFIG = {
  apiBaseUrl: resolveBuildTimeApiBaseUrl(),
  chainId: resolveBuildTimeChainId(),
  explorerTxBase: resolveExplorerTxBase(),
  /** Read assistant replies aloud (browser Speech Synthesis — pick male/female hints per OS voices). */
  workflowTtsEnabled: ttsEnabledRaw !== "false" && ttsEnabledRaw !== "0",
  workflowTtsGender: ttsGenderRaw === "male" ? ("male" as const) : ("female" as const),
  workflowTtsRate: Math.min(1.25, Math.max(0.75, Number(process.env.NEXT_PUBLIC_WORKFLOW_TTS_RATE || "1") || 1)),
  /** Pause after TTS before restarting mic (continuous voice session). */
  workflowVoiceContinuationDelayMs: Math.min(
    4000,
    Math.max(200, Number(process.env.NEXT_PUBLIC_WORKFLOW_VOICE_CONTINUE_DELAY_MS || "750") || 750),
  ),
};

export function expectedChainHex(): string {
  return "0x" + RUNTIME_CONFIG.chainId.toString(16);
}

export function txExplorerUrl(hash?: string | null): string {
  if (!hash) return "#";
  return `${RUNTIME_CONFIG.explorerTxBase}${hash}`;
}

export function addressExplorerUrl(address?: string | null): string {
  if (!address) return "#";
  const txBase = RUNTIME_CONFIG.explorerTxBase;
  const addressBase = txBase.endsWith("/tx/") ? txBase.slice(0, -4) + "/address/" : txBase;
  return `${addressBase}${address}`;
}
