"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import { Button } from "@/components/ui/button";
import { HighlightLayer } from "@/components/highlight-layer";
import type { BBox } from "@/lib/api";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

export interface HighlightTarget {
  /** changes on every selection, so picking the same card again jumps back */
  id: number;
  page: number;
  bboxes: BBox[];
}

interface PdfViewerProps {
  url: string;
  target: HighlightTarget | null;
}

export function PdfViewer({ url, target }: PdfViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(600);
  const [pageCount, setPageCount] = useState(0);
  const [pageNumber, setPageNumber] = useState(1);
  const [seenTargetId, setSeenTargetId] = useState<number | null>(null);
  const [originalWidth, setOriginalWidth] = useState<number | null>(null);

  if (target && target.id !== seenTargetId) {
    setSeenTargetId(target.id);
    setPageNumber(target.page);
  }

  useEffect(() => {
    const element = containerRef.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => {
      setWidth(Math.floor(entry.contentRect.width));
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const highlighted = target !== null && target.page === pageNumber;
  const scale = originalWidth ? width / originalWidth : 0;

  return (
    <div className="flex h-full min-h-0 flex-col gap-2">
      <div className="flex items-center justify-between">
        <Button
          variant="outline"
          size="icon-sm"
          aria-label="Previous page"
          disabled={pageNumber <= 1}
          onClick={() => setPageNumber((n) => n - 1)}
        >
          <ChevronLeft />
        </Button>
        <span className="text-sm text-muted-foreground" data-testid="page-indicator">
          Page {pageNumber} of {pageCount || "…"}
        </span>
        <Button
          variant="outline"
          size="icon-sm"
          aria-label="Next page"
          disabled={pageNumber >= pageCount}
          onClick={() => setPageNumber((n) => n + 1)}
        >
          <ChevronRight />
        </Button>
      </div>
      <div ref={containerRef} data-scroll-container className="min-h-0 flex-1 overflow-auto rounded-lg border bg-muted/30">
        <Document
          file={url}
          onLoadSuccess={({ numPages }) => setPageCount(numPages)}
          loading={<p className="p-4 text-sm text-muted-foreground">Loading PDF…</p>}
          error={<p className="p-4 text-sm text-destructive">Could not load the PDF.</p>}
        >
          <div className="relative" style={{ width }}>
            <Page
              pageNumber={pageNumber}
              width={width}
              renderTextLayer={false}
              renderAnnotationLayer={false}
              onLoadSuccess={(page) => setOriginalWidth(page.originalWidth)}
            />
            {highlighted && scale > 0 && (
              <HighlightLayer bboxes={target.bboxes} scale={scale} />
            )}
          </div>
        </Document>
      </div>
    </div>
  );
}
