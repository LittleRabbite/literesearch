"use client";

import { CheckCircle2, XCircle } from "lucide-react";

import { useWorkbench } from "@/lib/store";

export default function VerifyTab() {
  const verifyReport = useWorkbench((s) => s.verifyReport);
  const papers = useWorkbench((s) => s.papers);
  const selectRef = useWorkbench((s) => s.selectRef);
  const setTab = useWorkbench((s) => s.setTab);

  if (verifyReport.length === 0) {
    return (
      <div className="py-24 text-center text-muted-foreground">
        核验完成后在此展示逐条比对结果
      </div>
    );
  }

  const pass = verifyReport.filter((v) => v.ok).length;
  const warn = pass < verifyReport.length;

  return (
    <div className="mx-auto max-w-3xl px-6 py-6">
      <div
        className={`mb-4 flex items-center gap-3 rounded-xl border px-4 py-3 ${
          warn
            ? "border-warning/40 bg-warning/10"
            : "border-border bg-card"
        }`}
      >
        <span
          className={`font-serif text-lg font-semibold ${
            warn ? "text-warning" : ""
          }`}
        >
          {pass}/{verifyReport.length}
        </span>
        <span
          className={`text-sm ${warn ? "text-warning" : "text-muted-foreground"}`}
        >
          {warn
            ? "条引用通过 CrossRef 核验，未通过条目建议人工确认或剔除"
            : "条引用全部通过 CrossRef 核验"}
        </span>
      </div>

      <div className="flex flex-col gap-2">
        {verifyReport.map((v) => {
          const title = papers[v.ref]?.title ?? "";
          return (
            <div
              key={v.ref}
              className={`flex items-start gap-3 rounded-xl border px-4 py-3 transition-colors ${
                v.ok
                  ? "border-border bg-card"
                  : "border-destructive/30 bg-destructive/5"
              }`}
            >
              <div className="mt-0.5">
                {v.ok ? (
                  <CheckCircle2 size={16} className="text-success" />
                ) : (
                  <XCircle size={16} className="text-destructive" />
                )}
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-baseline gap-2">
                  <button
                    onClick={() => {
                      selectRef(v.ref);
                      setTab("papers");
                    }}
                    className="refchip"
                    title="定位到文献卡片"
                  >
                    {v.ref}
                  </button>
                  <span className="text-sm font-bold text-foreground">
                    {title}
                  </span>
                </div>
                <div className="mt-1 text-xs leading-relaxed text-muted-foreground">
                  {v.detail}
                  {v.matched_title && v.matched_title !== title && (
                    <span className="mt-0.5 block">
                      CrossRef 匹配：《{v.matched_title}》
                      {v.matched_year ? `（${v.matched_year}）` : ""}
                    </span>
                  )}
                </div>
                {v.doi && (
                  <a
                    href={`https://doi.org/${v.doi}`}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-1 inline-block text-xs font-bold text-primary underline-offset-2 hover:underline"
                  >
                    doi.org/{v.doi}
                  </a>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
