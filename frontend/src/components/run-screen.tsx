"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import dynamic from "next/dynamic";
import { useState } from "react";
import { ClauseCard } from "@/components/clause-card";
import { RunProgress } from "@/components/run-progress";
import type { HighlightTarget } from "@/components/pdf-viewer";
import { ApiError, getRun, pdfUrl, type RunStatus } from "@/lib/api";

const PdfViewer = dynamic(
  () => import("@/components/pdf-viewer").then((m) => m.PdfViewer),
  { ssr: false, loading: () => <p className="p-4 text-sm text-muted-foreground">Loading viewer…</p> },
);

const ACTIVE: RunStatus[] = ["queued", "running"];

export function RunScreen({ runId }: { runId: string }) {
  const [target, setTarget] = useState<HighlightTarget | null>(null);
  const [selectedClause, setSelectedClause] = useState<string | null>(null);
  const { data, error } = useQuery({
    queryKey: ["run", runId],
    queryFn: () => getRun(runId),
    refetchInterval: (query) =>
      query.state.data && ACTIVE.includes(query.state.data.status) ? 1000 : false,
    retry: (count, err) => !(err instanceof ApiError && err.status === 404) && count < 2,
  });

  if (error) {
    return (
      <Problem title="Could not load this run">
        {error instanceof ApiError ? error.detail : error.message}
      </Problem>
    );
  }
  if (!data) return <p className="p-8 text-center text-sm text-muted-foreground">Loading…</p>;
  if (ACTIVE.includes(data.status)) {
    return (
      <div className="flex flex-1 items-center justify-center p-8">
        <RunProgress progress={data.progress} />
      </div>
    );
  }
  if (data.status === "failed") {
    return (
      <Problem title="The analysis failed">
        The run stopped before it finished. Go back and try again.
      </Problem>
    );
  }

  return (
    <div className="grid h-[calc(100dvh-2.5rem)] grid-cols-1 grid-rows-[minmax(0,1fr)] gap-4 p-4 lg:grid-cols-2">
      <PdfViewer url={pdfUrl(data.contract_id)} target={target} />
      <div className="flex min-h-0 flex-col gap-3 overflow-auto">
        {data.status === "completed_with_errors" && (
          <p className="rounded-lg bg-amber-100 px-3 py-2 text-sm text-amber-900">
            Some clauses could not be checked. They are marked Uncertain.
          </p>
        )}
        {data.findings.map((finding) => (
          <ClauseCard
            key={finding.id}
            finding={finding}
            runId={runId}
            selected={selectedClause === finding.clause_id}
            onSelect={(page, bboxes) => {
              setSelectedClause(finding.clause_id);
              setTarget((current) => ({ id: (current?.id ?? 0) + 1, page, bboxes }));
            }}
          />
        ))}
      </div>
    </div>
  );
}

function Problem({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-2 p-8 text-center">
      <h2 className="text-lg font-medium">{title}</h2>
      <p className="max-w-md text-sm text-muted-foreground">{children}</p>
      <Link href="/" className="text-sm underline underline-offset-4">
        Back to upload
      </Link>
    </div>
  );
}
