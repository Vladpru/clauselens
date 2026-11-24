import { CheckCircle2, Loader2 } from "lucide-react";

const STEP_LABELS: Record<string, string> = {
  retrieve: "Retrieving passages",
  extract: "Extracting the quote",
  verify: "Verifying the quote",
  locate: "Locating it on the page",
  assess: "Checking against the playbook",
  suggest: "Drafting safer wording",
  done: "Done",
};

export function clauseName(clauseId: string): string {
  const spaced = clauseId.replaceAll("_", " ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

export function RunProgress({ progress }: { progress: Record<string, string> }) {
  const entries = Object.entries(progress);
  return (
    <div className="mx-auto flex w-full max-w-md flex-col gap-3" aria-live="polite">
      <h2 className="text-lg font-medium">Analyzing the contract…</h2>
      {entries.length === 0 && (
        <p className="text-sm text-muted-foreground">Waiting for the run to start…</p>
      )}
      <ul className="flex flex-col gap-2">
        {entries.map(([clauseId, step]) => (
          <li key={clauseId} className="flex items-center justify-between rounded-lg border px-3 py-2 text-sm">
            <span className="font-medium">{clauseName(clauseId)}</span>
            <span className="flex items-center gap-2 text-muted-foreground">
              {step === "done" ? (
                <CheckCircle2 className="size-4 text-emerald-600" />
              ) : (
                <Loader2 className="size-4 animate-spin" />
              )}
              {STEP_LABELS[step] ?? step}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
