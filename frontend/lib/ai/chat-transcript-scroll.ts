/** Scroll helpers for the copilot transcript panel. */

export type ChatTranscriptScrollTarget = {
  container: HTMLElement | null;
  endMarker?: HTMLElement | null;
};

/**
 * Jump the transcript to the latest message. Uses both scrollTop and an optional
 * end marker so reopen-after-unmount reliably lands at the bottom.
 */
export function scrollChatTranscriptToBottom(
  target: ChatTranscriptScrollTarget,
  opts?: { behavior?: ScrollBehavior },
): void {
  const { container, endMarker } = target;
  if (!container) return;

  const behavior = opts?.behavior ?? "auto";

  if (endMarker) {
    endMarker.scrollIntoView({ block: "end", behavior });
    return;
  }

  container.scrollTo({ top: container.scrollHeight, behavior });
}

/** Run after layout (and optionally again after panel enter animation). */
export function scheduleChatTranscriptScrollToBottom(
  target: ChatTranscriptScrollTarget,
  opts?: { behavior?: ScrollBehavior; afterMs?: number },
): () => void {
  const behavior = opts?.behavior ?? "auto";
  const run = () => scrollChatTranscriptToBottom(target, { behavior });

  requestAnimationFrame(() => {
    requestAnimationFrame(run);
  });

  let timer: ReturnType<typeof setTimeout> | undefined;
  if (opts?.afterMs && opts.afterMs > 0) {
    timer = setTimeout(run, opts.afterMs);
  }

  return () => {
    if (timer !== undefined) clearTimeout(timer);
  };
}
