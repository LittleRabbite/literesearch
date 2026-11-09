"use client";

import { CheckCircle2, Info, XCircle } from "lucide-react";

import { useWorkbench } from "@/lib/store";

export default function Toasts() {
  const toasts = useWorkbench((s) => s.toasts);
  const dismiss = useWorkbench((s) => s.dismissToast);

  return (
    <div className="pointer-events-none fixed right-5 bottom-5 z-50 flex flex-col gap-2">
      {toasts.map((t) => (
        <div
          key={t.id}
          onClick={() => dismiss(t.id)}
          className={`pointer-events-auto flex max-w-sm cursor-pointer items-start gap-2.5 rounded-xl border px-4 py-3 text-sm shadow-lg backdrop-blur transition-all ${
            t.kind === "error"
              ? "border-destructive/40 bg-card text-destructive"
              : t.kind === "success"
                ? "border-success/40 bg-card text-success"
                : "border-border bg-card text-card-foreground"
          }`}
        >
          {t.kind === "error" ? (
            <XCircle size={16} className="mt-0.5 shrink-0" />
          ) : t.kind === "success" ? (
            <CheckCircle2 size={16} className="mt-0.5 shrink-0" />
          ) : (
            <Info size={16} className="mt-0.5 shrink-0" />
          )}
          <span className="leading-snug">{t.msg}</span>
        </div>
      ))}
    </div>
  );
}
