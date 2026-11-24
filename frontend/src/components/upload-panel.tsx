"use client";

import { useMutation } from "@tanstack/react-query";
import { FileText, Loader2, Upload } from "lucide-react";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { analyze, ApiError, uploadContract } from "@/lib/api";
import { cn } from "@/lib/utils";

export function UploadPanel() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [fileName, setFileName] = useState<string | null>(null);

  const upload = useMutation({
    mutationFn: uploadContract,
  });
  const start = useMutation({
    mutationFn: analyze,
    onSuccess: ({ run_id }) => router.push(`/runs/${run_id}`),
  });

  function pick(file: File | undefined) {
    if (!file) return;
    setFileName(file.name);
    start.reset();
    upload.mutate(file);
  }

  const uploaded = upload.data;
  const error = upload.error ?? start.error;

  return (
    <div className="flex w-full max-w-xl flex-col gap-4">
      <div
        role="button"
        tabIndex={0}
        aria-label="Upload a contract PDF"
        onClick={() => inputRef.current?.click()}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") inputRef.current?.click();
        }}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          pick(event.dataTransfer.files[0]);
        }}
        className={cn(
          "flex cursor-pointer flex-col items-center gap-2 rounded-xl border-2 border-dashed px-6 py-12 text-center transition-colors",
          dragging ? "border-primary bg-muted" : "border-border hover:bg-muted/50",
        )}
      >
        {upload.isPending ? (
          <Loader2 className="size-8 animate-spin text-muted-foreground" />
        ) : (
          <Upload className="size-8 text-muted-foreground" />
        )}
        <p className="text-sm font-medium">
          {upload.isPending ? `Uploading ${fileName}…` : "Drop a contract PDF here, or click to choose"}
        </p>
        <p className="text-xs text-muted-foreground">
          Text-based PDF, up to 20 MB and 100 pages. Use public contracts only.
        </p>
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf"
          className="hidden"
          onChange={(event) => {
            pick(event.target.files?.[0]);
            event.target.value = "";
          }}
        />
      </div>

      {error && (
        <p role="alert" className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error instanceof ApiError ? error.detail : error.message}
        </p>
      )}

      {uploaded && !upload.isPending && (
        <div className="flex items-center justify-between gap-4 rounded-xl border px-4 py-3">
          <div className="flex min-w-0 items-center gap-3">
            <FileText className="size-5 shrink-0 text-muted-foreground" />
            <div className="min-w-0">
              <p className="truncate text-sm font-medium">{fileName}</p>
              <p className="text-xs text-muted-foreground">{uploaded.page_count} pages</p>
            </div>
          </div>
          <Button
            onClick={() => start.mutate(uploaded.contract_id)}
            disabled={start.isPending}
          >
            {start.isPending ? "Starting…" : "Analyze"}
          </Button>
        </div>
      )}
    </div>
  );
}
