"use client";

import { useLayoutEffect, useRef, type RefObject } from "react";
import {
  scheduleChatTranscriptScrollToBottom,
  type ChatTranscriptScrollTarget,
} from "./chat-transcript-scroll";

type UseChatTranscriptScrollOptions = {
  /** Transcript scroll container (overflow-y-auto). */
  containerRef: RefObject<HTMLElement | null>;
  /** Sentinel at the bottom of the message list. */
  endRef: RefObject<HTMLElement | null>;
  /** Panel is visible — when false the DOM node is usually unmounted. */
  active: boolean;
  /** Bumps when messages/streaming/state should re-anchor to the bottom. */
  revision: string;
  /** Match panel enter animation so scroll runs after height settles. */
  panelEnterAnimationMs?: number;
};

/**
 * Keeps the copilot transcript pinned to the latest message while open,
 * and restores bottom position when the user closes and reopens the panel.
 */
export function useChatTranscriptScroll({
  containerRef,
  endRef,
  active,
  revision,
  panelEnterAnimationMs = 240,
}: UseChatTranscriptScrollOptions): void {
  const wasActiveRef = useRef(false);

  useLayoutEffect(() => {
    if (!active) {
      wasActiveRef.current = false;
      return;
    }

    const target: ChatTranscriptScrollTarget = {
      container: containerRef.current,
      endMarker: endRef.current,
    };

    const justOpened = !wasActiveRef.current;
    wasActiveRef.current = true;

    return scheduleChatTranscriptScrollToBottom(target, {
      behavior: "auto",
      afterMs: justOpened ? panelEnterAnimationMs : undefined,
    });
  }, [active, revision, containerRef, endRef, panelEnterAnimationMs]);
}
