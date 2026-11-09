"use client";

import { CheckCircle2, Crosshair, Quote, Trash2, XCircle } from "lucide-react";
import { useEffect, useState } from "react";

import { useWorkbench } from "@/lib/store";

function ScoreBadge({ score }: { score?: number }) {
  const v = Math.round(score ?? 0);
  return (
    <div
      className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full font-serif text-base font-bold ${
        v >= 4
          ? "bg-accent text-accent-foreground"
          : v >= 3
            ? "bg-primary-soft text-primary"
            : "bg-muted text-muted-foreground"
      }`}
      title="LLM 三维打分（相关性/代表性/时效性）"
    >
      {v || "–"}
    </div>
  );
}

export default function PapersTab() {
  const papers = useWorkbench((s) => s.papers);
  const verifyReport = useWorkbench((s) => s.verifyReport);
  const surveyDraft = useWorkbench((s) => s.surveyDraft);
  const runStatus = useWorkbench((s) => s.runStatus);
  const selectedRef = useWorkbench((s) => s.selectedRef);
  const selectRef = useWorkbench((s) => s.selectRef);
  const setTab = useWorkbench((s) => s.setTab);
  const sendFeedback = useWorkbench((s) => s.sendFeedback);
  const pushToast = useWorkbench((s) => s.pushToast);
  const [expanded, setExpanded] = useState<number | null>(null);

  useEffect(() => {
    if (selectedRef === null) return;
    const el = document.getElementById(`paper-${selectedRef}`);
    el?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [selectedRef]);

  const verifyMap = new Map(verifyReport.map((v) => [v.ref, v]));
  const paused = runStatus === "paused";

  const drop = async (idx: number) => {
    if (!paused) return;
    await sendFeedback("drop", { drop: [idx] });
    pushToast(`已剔除 [${idx}]，智能体将重写综述`, "info");
  };

  const locate = (idx: number) => {
    selectRef(idx);
    setTab("survey");
  };

  if (papers.length === 0) {
    return (
      <div className="py-24 text-center text-muted-foreground">
        文献筛选完成后在此展示
      </div>
    );
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-3 px-6 py-6">
      <div className="text-xs text-muted-foreground">
        共 {papers.length} 篇 · 按打分排序 · 剔除操作仅在待审核状态可用
      </div>
      {papers.map((p, i) => {
        const v = verifyMap.get(i);
        const cited = surveyDraft.includes(`[${i}]`);
        return (
          <article
            key={i}
            id={`paper-${i}`}
            className={`rounded-xl border bg-card p-4 transition-all duration-200 ${
              selectedRef === i
                ? "border-accent ring-2 ring-accent/30"
                : "border-border"
            }`}
          >
            <div className="flex items-start gap-3.5">
              <ScoreBadge score={p.score} />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-serif text-[15px] font-semibold leading-snug text-foreground">
                    {p.title}
                  </span>
                  {p.locked && (
                    <span className="rounded bg-primary-soft px-1.5 py-0.5 text-[10px] font-bold text-primary">
                      已锁定
                    </span>
                  )}
                </div>
                <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                  <span>{p.authors.slice(0, 3).join(", ")}
                    {p.authors.length > 3 && " et al."}</span>
                  <span>{p.year}</span>
                  {p.venue && <span className="truncate">{p.venue}</span>}
                  <span className="rounded bg-muted px-1.5 py-0.5 font-bold uppercase">
                    {p.source}
                  </span>
                  {p.citationCount > 0 && <span>被引 {p.citationCount}</span>}
                </div>
                {p.score_reason && (
                  <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
                    {p.score_reason}
                  </p>
                )}

                <div className="mt-2.5 flex flex-wrap items-center gap-2">
                  {v && (
                    <span
                      className={`inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-bold ${
                        v.ok
                          ? "bg-success/10 text-success"
                          : "bg-destructive/10 text-destructive"
                      }`}
                      title={v.detail}
                    >
                      {v.ok ? (
                        <CheckCircle2 size={12} />
                      ) : (
                        <XCircle size={12} />
                      )}
                      核验{v.ok ? "通过" : "未通过"}
                    </span>
                  )}
                  {cited && (
                    <button
                      onClick={() => locate(i)}
                      className="inline-flex cursor-pointer items-center gap-1 rounded px-2 py-0.5 text-xs font-bold text-primary transition-colors hover:bg-primary-soft"
                    >
                      <Crosshair size={12} />
                      定位引用
                    </button>
                  )}
                  <button
                    onClick={() => setExpanded(expanded === i ? null : i)}
                    className="inline-flex cursor-pointer items-center gap-1 rounded px-2 py-0.5 text-xs font-bold text-muted-foreground transition-colors hover:bg-muted"
                  >
                    <Quote size={12} />
                    {expanded === i ? "收起摘要" : "查看摘要"}
                  </button>
                  <button
                    onClick={() => drop(i)}
                    disabled={!paused}
                    title={paused ? "剔除该文献并重写综述" : "仅在待审核状态可用"}
                    className="inline-flex cursor-pointer items-center gap-1 rounded px-2 py-0.5 text-xs font-bold text-destructive transition-colors hover:bg-destructive/10 disabled:cursor-not-allowed disabled:opacity-35"
                  >
                    <Trash2 size={12} />
                    剔除
                  </button>
                </div>

                {expanded === i && (
                  <p className="mt-3 rounded-lg bg-muted px-3.5 py-3 text-sm leading-relaxed text-card-foreground">
                    {p.abstract || "（无摘要）"}
                  </p>
                )}
              </div>
            </div>
          </article>
        );
      })}
    </div>
  );
}
