"use client";

import {
  BookMarked,
  Check,
  ChevronDown,
  Compass,
  FileDown,
  Filter,
  PenLine,
  Search,
  ShieldCheck,
  UserCheck,
} from "lucide-react";
import { useState } from "react";

import { useWorkbench } from "@/lib/store";
import type { NodeStatus } from "@/lib/types";
import { NODE_LABELS, NODE_ORDER } from "@/lib/types";

const NODE_ICONS: Record<string, React.ReactNode> = {
  planner: <Compass size={15} />,
  retriever: <Search size={15} />,
  screening: <Filter size={15} />,
  writer: <PenLine size={15} />,
  verifier: <ShieldCheck size={15} />,
  bib_generator: <BookMarked size={15} />,
  pdf_ingest: <FileDown size={15} />,
  human_review: <UserCheck size={15} />,
};

function fmtDur(sec?: number): string {
  if (sec === undefined) return "";
  if (sec < 60) return `${sec}s`;
  return `${Math.floor(sec / 60)}m${String(sec % 60).padStart(2, "0")}s`;
}

function StatusDot({
  status,
  warn,
}: {
  status: NodeStatus;
  warn?: boolean;
}) {
  if (status === "running")
    return (
      <span className="node-running inline-block h-2 w-2 rounded-full bg-primary" />
    );
  if (status === "waiting")
    return <span className="dot-blink inline-block h-2 w-2 rounded-full bg-accent" />;
  if (status === "done")
    return warn ? (
      <Check size={13} className="text-warning" />
    ) : (
      <Check size={13} className="text-success" />
    );
  if (status === "error")
    return <span className="inline-block h-2 w-2 rounded-full bg-destructive" />;
  return <span className="inline-block h-2 w-2 rounded-full bg-border" />;
}

export default function NodePanel() {
  const nodeStatus = useWorkbench((s) => s.nodeStatus);
  const nodeMeta = useWorkbench((s) => s.nodeMeta);
  const nodeLogs = useWorkbench((s) => s.nodeLogs);
  const nodeDuration = useWorkbench((s) => s.nodeDuration);
  const subQueries = useWorkbench((s) => s.subQueries);
  const papers = useWorkbench((s) => s.papers);
  const rawCount = useWorkbench((s) => s.rawCount);
  const verifyReport = useWorkbench((s) => s.verifyReport);
  const bibEntries = useWorkbench((s) => s.bibEntries);
  const pdfIngested = useWorkbench((s) => s.pdfIngested);
  const retryCount = useWorkbench((s) => s.retryCount);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const verifyPass = verifyReport.filter((v) => v.ok).length;
  const verifyWarn = verifyReport.length > 0 && verifyPass < verifyReport.length;

  const summary = (node: string): string => {
    switch (node) {
      case "planner":
        return subQueries.length > 0 ? `${subQueries.length} 个子查询` : "";
      case "retriever":
        return rawCount > 0 ? `原始 ${rawCount} 篇` : "";
      case "screening":
        // 漏斗数据全程可见：63 → 15
        return rawCount > 0 && papers.length > 0
          ? `${rawCount} → ${papers.length} 篇`
          : papers.length > 0
            ? `入选 ${papers.length} 篇`
            : "";
      case "verifier":
        if (verifyReport.length === 0) return "";
        return `${verifyPass}/${verifyReport.length} 通过`;
      case "bib_generator":
        return bibEntries.length > 0 ? `${bibEntries.length} 条` : "";
      case "pdf_ingest":
        if (pdfIngested === null) return "";
        return pdfIngested === 0 ? "已跳过" : `${pdfIngested} 篇入库`;
      case "human_review":
        return nodeStatus.human_review === "waiting" ? "等待审核" : "";
      default:
        return "";
    }
  };

  const metaHint = (node: string): string | undefined => {
    if (node === "screening" && rawCount > 0 && papers.length > 0)
      return `原始检索 ${rawCount} 篇，去重与筛选后入选 ${papers.length} 篇`;
    if (node === "pdf_ingest" && pdfIngested === 0)
      return "本次运行未启用 PDF 入库（未勾选「下载 PDF 全文」或无可用的 arXiv 来源）";
    return undefined;
  };

  return (
    <div className="flex flex-col gap-1 p-4">
      {NODE_ORDER.map((node) => {
        const status = nodeStatus[node] ?? "pending";
        const meta = summary(node) || (status === "running" ? nodeMeta[node] : "");
        const dur = nodeDuration[node];
        const logs = nodeLogs[node] ?? [];
        const open = expanded[node];
        const active = status === "running" || status === "waiting";
        const warnNode = node === "verifier" && verifyWarn;
        const hasDetail =
          node === "planner" ? subQueries.length > 0 : logs.length > 0;
        return (
          <div key={node}>
            <div
              onClick={() =>
                hasDetail && setExpanded((p) => ({ ...p, [node]: !p[node] }))
              }
              className={`flex items-center gap-3 rounded-lg px-3 py-2.5 transition-colors duration-200 ${
                active ? "bg-primary-soft" : ""
              } ${hasDetail ? "cursor-pointer hover:bg-muted/60" : ""}`}
            >
              <div
                className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full border transition-colors duration-200 ${
                  status === "done"
                    ? warnNode
                      ? "border-warning/50 bg-warning/10 text-warning"
                      : "border-success/50 bg-success/10 text-success"
                    : status === "running"
                      ? "border-primary bg-primary text-primary-foreground"
                      : status === "waiting"
                        ? "border-accent bg-accent text-accent-foreground"
                        : status === "error"
                          ? "border-destructive bg-destructive/10 text-destructive"
                          : "border-border text-muted-foreground"
                }`}
              >
                {NODE_ICONS[node]}
              </div>
              <div className="min-w-0 flex-1">
                <div
                  className={`text-sm font-bold ${
                    status === "pending"
                      ? "text-muted-foreground"
                      : "text-foreground"
                  }`}
                >
                  {NODE_LABELS[node]}
                  {dur !== undefined && (
                    <span
                      className="ml-2 text-xs font-normal text-muted-foreground"
                      title="该步骤耗时"
                    >
                      · {fmtDur(dur)}
                    </span>
                  )}
                </div>
                {meta && (
                  <div
                    className={`truncate text-xs ${
                      warnNode ? "font-bold text-warning" : "text-muted-foreground"
                    }`}
                    title={metaHint(node)}
                  >
                    {meta}
                  </div>
                )}
              </div>
              {hasDetail && (
                <ChevronDown
                  size={14}
                  className={`shrink-0 text-muted-foreground transition-transform ${
                    open ? "rotate-180" : ""
                  }`}
                />
              )}
              <StatusDot status={status} warn={warnNode} />
            </div>
            {/* 展开区：该步日志（检索式、命中数、剔除原因等） */}
            {open && hasDetail && (
              <div className="ml-13 mt-1 mb-2 flex flex-col gap-1 border-l border-border pl-3">
                {node === "planner"
                  ? subQueries.map((q, i) => (
                      <span
                        key={i}
                        className="truncate text-xs text-muted-foreground"
                        title={q}
                      >
                        {i + 1}. {q}
                      </span>
                    ))
                  : logs.map((line, i) => (
                      <span
                        key={i}
                        className="text-xs leading-relaxed text-muted-foreground"
                      >
                        {line}
                      </span>
                    ))}
              </div>
            )}
          </div>
        );
      })}
      {/* 漏斗统计条：轮次 + 全程数据漏斗收尾 */}
      {(rawCount > 0 || papers.length > 0) && (
        <div
          className="mt-3 rounded-lg bg-muted px-3 py-2.5 text-xs text-muted-foreground"
          title="漏斗：原始检索 → 去重入选 → 引用核验通过"
        >
          <div className="flex items-center justify-between font-bold text-foreground">
            <span>第 {retryCount + 1} 轮</span>
            <span className="font-normal text-muted-foreground">
              {retryCount > 0 ? `已重试 ${retryCount} 次` : "首次执行"}
            </span>
          </div>
          <div className="mt-1.5 flex items-center gap-1 tabular-nums">
            <span className="rounded bg-background px-1.5 py-0.5">
              原始 {rawCount}
            </span>
            <span>→</span>
            <span className="rounded bg-background px-1.5 py-0.5">
              入选 {papers.length}
            </span>
            {verifyReport.length > 0 && (
              <>
                <span>→</span>
                <span
                  className={`rounded px-1.5 py-0.5 ${
                    verifyWarn
                      ? "bg-warning/15 font-bold text-warning"
                      : "bg-success/10 text-success"
                  }`}
                >
                  通过 {verifyPass}/{verifyReport.length}
                </span>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
