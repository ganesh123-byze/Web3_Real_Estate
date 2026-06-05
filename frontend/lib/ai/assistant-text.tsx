import { Fragment, type ReactNode } from "react";

type InlineSegment = { kind: "plain"; text: string } | { kind: "bold"; text: string };

/** Strip unmatched markdown asterisks so users never see raw `*` in chat. */
export function sanitizeStrayAsterisks(text: string): string {
  let result = text.replace(/\*\*/g, "");
  result = result.replace(/\*([^*\n]+)\*/g, "$1");
  return result;
}

function normalizeBoldInner(text: string): string {
  return text.replace(/^\*+|\*+$/g, "").trim();
}

/**
 * Split a line into plain and **bold** segments.
 * Uses a manual scan so empty pairs (`** **`), orphans, and `***bold***` are handled safely.
 */
export function parseMarkdownBoldSegments(line: string): InlineSegment[] {
  const segments: InlineSegment[] = [];
  let index = 0;
  let plainStart = 0;

  while (index < line.length) {
    if (line[index] === "*" && line[index + 1] === "*") {
      if (index > plainStart) {
        const plain = sanitizeStrayAsterisks(line.slice(plainStart, index));
        if (plain) segments.push({ kind: "plain", text: plain });
      }

      const close = line.indexOf("**", index + 2);
      if (close === -1) {
        index += 2;
        plainStart = index;
        continue;
      }

      const boldText = normalizeBoldInner(line.slice(index + 2, close));
      if (boldText) segments.push({ kind: "bold", text: boldText });

      index = close + 2;
      plainStart = index;
      continue;
    }

    index += 1;
  }

  if (plainStart < line.length) {
    const plain = sanitizeStrayAsterisks(line.slice(plainStart));
    if (plain) segments.push({ kind: "plain", text: plain });
  }

  if (segments.length === 0) {
    const plain = sanitizeStrayAsterisks(line);
    if (plain) segments.push({ kind: "plain", text: plain });
  }

  return segments;
}

function highlightRangesForLine(line: string, highlightWholeLine: boolean) {
  const ranges: Array<{ start: number; end: number }> = [];
  if (highlightWholeLine) {
    const start = line.search(/\S/);
    const end = line.trimEnd().length;
    if (start >= 0 && end > start) ranges.push({ start, end });
  }

  const patterns = [
    /\bproperty details for\s+([A-Za-z0-9][A-Za-z0-9&'’., -]{0,80}?)(?=\s+(?:were|was)\b)/gi,
    /\bproperty\s+([A-Za-z0-9][A-Za-z0-9&'’., -]{0,80}?)(?=\s+(?:was successfully created|was created|is on|has been)\b)/gi,
    /^(?:[-•]\s*)?(?:name|property name|property):\s*([^\n.]+)/gi,
    /\b([A-Za-z0-9][A-Za-z0-9&'’., -]{1,80}?)\s+\(#\d+\)/gi,
  ];

  for (const pattern of patterns) {
    for (const match of line.matchAll(pattern)) {
      const value = match[1]?.trim();
      if (!value || /^details$/i.test(value)) continue;
      const startInMatch = match[0].indexOf(match[1]);
      if (startInMatch < 0 || match.index === undefined) continue;
      const start = match.index + startInMatch;
      ranges.push({ start, end: start + match[1].length });
    }
  }

  return ranges
    .sort((a, b) => a.start - b.start || b.end - a.end)
    .reduce<Array<{ start: number; end: number }>>((merged, range) => {
      const previous = merged[merged.length - 1];
      if (!previous || range.start > previous.end) {
        merged.push(range);
      } else {
        previous.end = Math.max(previous.end, range.end);
      }
      return merged;
    }, []);
}

function renderPlainSegment(text: string, keyPrefix: string, highlightWholeLine: boolean): ReactNode {
  const ranges = highlightRangesForLine(text, highlightWholeLine);
  if (!ranges.length) return text;

  let cursor = 0;
  const nodes: ReactNode[] = [];
  ranges.forEach((range, rangeIndex) => {
    if (range.start > cursor) {
      nodes.push(text.slice(cursor, range.start));
    }
    nodes.push(
      <strong key={`${keyPrefix}-hl-${rangeIndex}`} className="font-bold text-slate-950 dark:text-white">
        {text.slice(range.start, range.end)}
      </strong>,
    );
    cursor = range.end;
  });
  if (cursor < text.length) nodes.push(text.slice(cursor));
  return nodes;
}

export function HighlightedAssistantText({ text }: { text: string }) {
  const lines = text.split("\n");

  return (
    <>
      {lines.map((line, lineIndex) => {
        const previousLine = lines[lineIndex - 1] ?? "";
        const highlightWholeLine = /\b\d+\s+listings?:\s*$/i.test(previousLine.trim());
        const segments = parseMarkdownBoldSegments(line);

        return (
          <span key={`${lineIndex}-${line}`}>
            {segments.map((segment, segmentIndex) => {
              const key = `${lineIndex}-${segmentIndex}`;
              if (segment.kind === "bold") {
                return (
                  <strong key={key} className="font-bold text-slate-950 dark:text-white">
                    {segment.text}
                  </strong>
                );
              }
              return (
                <Fragment key={key}>
                  {renderPlainSegment(segment.text, key, highlightWholeLine)}
                </Fragment>
              );
            })}
            {lineIndex < lines.length - 1 ? <br /> : null}
          </span>
        );
      })}
    </>
  );
}
