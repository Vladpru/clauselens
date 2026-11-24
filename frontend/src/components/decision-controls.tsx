"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, putDecision, type DecisionState, type FindingView } from "@/lib/api";

const STATE_LABELS: Record<DecisionState, string> = {
  pending: "Pending",
  accepted: "Accepted",
  edited: "Edited",
  rejected: "Rejected",
};

interface DecisionControlsProps {
  finding: FindingView;
  runId: string;
}

export function DecisionControls({ finding, runId }: DecisionControlsProps) {
  const queryClient = useQueryClient();
  const decision = finding.decision;
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");

  const mutation = useMutation({
    mutationFn: (body: { state: DecisionState; edited_text?: string }) =>
      putDecision(finding.id, body),
    onSuccess: async () => {
      setEditing(false);
      await queryClient.invalidateQueries({ queryKey: ["run", runId] });
    },
  });

  function startEditing() {
    setDraft(decision?.edited_text ?? finding.suggestion_text ?? "");
    setEditing(true);
  }

  return (
    <div className="flex flex-col gap-2" onClick={(event) => event.stopPropagation()}>
      <p className="text-xs text-muted-foreground">
        Decision: <span className="font-medium text-foreground">{STATE_LABELS[decision?.state ?? "pending"]}</span>
      </p>

      {decision?.state === "edited" && decision.edited_text && !editing && (
        <p className="rounded-md bg-muted px-2 py-1.5 text-sm whitespace-pre-wrap">{decision.edited_text}</p>
      )}

      {editing ? (
        <div className="flex flex-col gap-2">
          <Textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            rows={5}
            aria-label="Edit the suggested wording"
          />
          <div className="flex gap-2">
            <Button
              size="sm"
              disabled={mutation.isPending || draft.trim() === ""}
              onClick={() => mutation.mutate({ state: "edited", edited_text: draft })}
            >
              Save
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex gap-2">
          <Button
            size="sm"
            disabled={mutation.isPending}
            onClick={() => mutation.mutate({ state: "accepted" })}
          >
            Accept
          </Button>
          <Button size="sm" variant="outline" disabled={mutation.isPending} onClick={startEditing}>
            Edit
          </Button>
          <Button
            size="sm"
            variant="destructive"
            disabled={mutation.isPending}
            onClick={() => mutation.mutate({ state: "rejected" })}
          >
            Reject
          </Button>
        </div>
      )}

      {mutation.error && (
        <p role="alert" className="text-sm text-destructive">
          {mutation.error instanceof ApiError ? mutation.error.detail : mutation.error.message}
        </p>
      )}
    </div>
  );
}
