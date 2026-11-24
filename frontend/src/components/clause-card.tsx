"use client";

import { DecisionControls } from "@/components/decision-controls";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { BBox, FindingStatus, FindingView } from "@/lib/api";
import { cn } from "@/lib/utils";

const BADGES: Record<FindingStatus, { label: string; className: string }> = {
  ok: { label: "OK", className: "bg-emerald-100 text-emerald-900" },
  risky: { label: "Risky", className: "bg-amber-100 text-amber-900" },
  missing: { label: "Missing", className: "bg-red-100 text-red-900" },
  uncertain: { label: "Uncertain", className: "bg-zinc-200 text-zinc-800" },
};

const SNIPPET_CHARS = 120;

interface ClauseCardProps {
  finding: FindingView;
  runId: string;
  selected: boolean;
  onSelect: (page: number, bboxes: BBox[]) => void;
}

export function ClauseCard({ finding, runId, selected, onSelect }: ClauseCardProps) {
  const badge = BADGES[finding.status];
  const notFound = finding.quote === null && (finding.status === "missing" || finding.status === "ok");
  const selectable = finding.page !== null;

  return (
    <Card
      data-testid={`card-${finding.clause_id}`}
      className={cn("shrink-0", selectable && "cursor-pointer", selected && "ring-2 ring-amber-400")}
      onClick={() => finding.page !== null && onSelect(finding.page, finding.bboxes)}
    >
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          {finding.clause_title}
          <Badge className={badge.className}>{badge.label}</Badge>
          {finding.status === "missing" && finding.severity && (
            <span className="text-xs font-normal text-muted-foreground">{finding.severity} severity</span>
          )}
        </CardTitle>
        <p className="text-sm text-muted-foreground">Playbook: {finding.playbook_rule}</p>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 text-sm">
        {finding.quote && (
          <figure>
            <blockquote className="border-l-2 pl-3 italic">{finding.quote}</blockquote>
            <figcaption className="mt-1 text-xs text-muted-foreground">Page {finding.page}</figcaption>
          </figure>
        )}

        {finding.status === "uncertain" && (
          <p className="text-muted-foreground">{finding.error ?? "The quote could not be verified."}</p>
        )}

        {finding.issues.length > 0 && (
          <ul className="list-disc pl-5">
            {finding.issues.map((issue) => (
              <li key={issue}>{issue}</li>
            ))}
          </ul>
        )}
        {finding.rationale && <p>{finding.rationale}</p>}

        {notFound && (
          <details onClick={(event) => event.stopPropagation()}>
            <summary className="cursor-pointer text-muted-foreground">
              Sections examined ({finding.candidates.length})
            </summary>
            <ul className="mt-2 flex flex-col gap-1 text-xs">
              {finding.candidates.map((candidate) => (
                <li key={candidate.chunk_id}>
                  <span className="font-medium">Page {candidate.page}:</span>{" "}
                  {candidate.text.slice(0, SNIPPET_CHARS)}
                  {candidate.text.length > SNIPPET_CHARS && "…"}
                </li>
              ))}
              {finding.candidates.length === 0 && <li>No passages were retrieved.</li>}
            </ul>
          </details>
        )}

        {finding.suggestion_text && (
          <div className="flex flex-col gap-1 rounded-md bg-muted/60 p-3">
            <p className="text-xs font-medium uppercase text-muted-foreground">Suggested wording</p>
            <p className="whitespace-pre-wrap">{finding.suggestion_text}</p>
            {finding.suggestion_explanation && (
              <p className="text-xs text-muted-foreground">{finding.suggestion_explanation}</p>
            )}
          </div>
        )}

        {finding.suggestion_text && <DecisionControls finding={finding} runId={runId} />}
      </CardContent>
    </Card>
  );
}
