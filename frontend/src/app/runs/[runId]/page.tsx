import { Suspense } from "react";
import { RunScreen } from "@/components/run-screen";

async function Run({ params }: { params: PageProps<"/runs/[runId]">["params"] }) {
  const { runId } = await params;
  return <RunScreen runId={runId} />;
}

export default function RunPage(props: PageProps<"/runs/[runId]">) {
  return (
    <Suspense fallback={<p className="p-8 text-center text-sm text-muted-foreground">Loading…</p>}>
      <Run params={props.params} />
    </Suspense>
  );
}
