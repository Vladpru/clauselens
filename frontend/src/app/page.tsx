import { UploadPanel } from "@/components/upload-panel";

export default function Home() {
  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-6 px-6 py-16">
      <div className="text-center">
        <h1 className="text-2xl font-semibold tracking-tight">ClauseLens</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Upload a contract. Check five key clauses against your playbook.
        </p>
      </div>
      <UploadPanel />
    </main>
  );
}
