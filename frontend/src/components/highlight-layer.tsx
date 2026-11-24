"use client";

import { useEffect, useRef } from "react";
import type { BBox } from "@/lib/api";

interface HighlightLayerProps {
  bboxes: BBox[];
  /** rendered page width divided by the page's original width in PDF points */
  scale: number;
}

/**
 * Boxes are PyMuPDF rectangles: PDF points, origin top left, which matches the
 * rendered viewport. With no boxes the whole page gets a border instead.
 */
export function HighlightLayer({ bboxes, scale }: HighlightLayerProps) {
  const firstBox = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const box = firstBox.current;
    const scroller = box?.closest<HTMLElement>("[data-scroll-container]");
    if (!box || !scroller) return;
    const offset = box.getBoundingClientRect().top - scroller.getBoundingClientRect().top;
    scroller.scrollTo({
      top: scroller.scrollTop + offset - scroller.clientHeight / 2,
      behavior: "smooth",
    });
  }, [bboxes, scale]);

  if (bboxes.length === 0) {
    return (
      <div
        data-testid="page-highlight"
        className="pointer-events-none absolute inset-0 border-4 border-amber-400/80"
      />
    );
  }
  return (
    <div className="pointer-events-none absolute inset-0">
      {bboxes.map(([x0, y0, x1, y1], index) => (
        <div
          key={index}
          ref={index === 0 ? firstBox : undefined}
          data-testid="quote-highlight"
          className="absolute rounded-sm bg-amber-300/40 ring-1 ring-amber-500/70"
          style={{
            left: x0 * scale,
            top: y0 * scale,
            width: (x1 - x0) * scale,
            height: (y1 - y0) * scale,
          }}
        />
      ))}
    </div>
  );
}
