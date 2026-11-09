"use client";

import {
  BookOpen,
  ChevronDown,
  FilePlus2,
  FileDown,
  FileText,
  History,
  LogOut,
  Table2,
  TriangleAlert,
} from "lucide-react";
import { useState } from "react";

import BibTab from "@/components/BibTab";
import NodePanel from "@/components/NodePanel";
import PapersTab from "@/components/PapersTab";
import ReviewBar from "@/components/ReviewBar";
import SurveyTab from "@/components/SurveyTab";
import ThemeToggle from "@/components/ThemeToggle";
import VerifyTab from "@/components/VerifyTab";
import { useWorkbench } from "@/lib/store";
import type { RunStatus, Tab } from "@/lib/types";

function StatusBadge({ status }: { status: RunStatus }) {
  const map: Record<RunStatus, { label: string; cls: string; dot: string }> = {
    idle: { label: "空闲", cls: "bg-muted text-muted-foreground", dot: "bg-border" },
    created: { label: "启动中", cls: "bg-muted text-muted-foreground", dot: "bg-muted-foreground" },
    running: { label: "运行中", cls: "bg-primary-soft text-primary", dot: "bg-primary dot-blink" },
    paused: { label: "待审核", cls: "bg-accent/15 text-accent", dot: "bg-accent dot-blink" },
    finished: { label: "已完成", cls: "bg-success/10 text-success", dot: "bg-success" },
    error: { label: "出错", cls: "bg-destructive/10 text-destructive", dot: "bg-destructive" },
  };
  const s = map[status] ?? map.idle;
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-bold ${s.cls}`}
    >
      <span className={`inline-block h-1.5 w-1.5 rounded-full ${s.dot}`} />
      {s.label}
    </span>
  );
}

const EXPORT_ITEMS = [
  { fmt: "md", icon: <FileText size={14} />, label: "Markdown 综述" },
  { fmt: "bib", icon: <FileDown size={14} />, label: "BibTeX 文件" },
  { fmt: "xlsx", icon: <Table2 size={14} />, label: "Excel 文献矩阵" },
];

export default function Workbench() {
  const sessionId = useWorkbench((s) => s.sessionId);
  const topic = useWorkbench((s) => s.topic);
  const runStatus = useWorkbench((s) => s.runStatus);
  const errorMsg = useWorkbench((s) => s.errorMsg);
  const activeTab = useWorkbench((s) => s.activeTab);
  const setTab = useWorkbench((s) => s.setTab);
  const reset = useWorkbench((s) => s.reset);
  const papers = useWorkbench((s) => s.papers);
  const verifyReport = useWorkbench((s) => s.verifyReport);
  const bibEntries = useWorkbench((s) => s.bibEntries);
  const pushToast = useWorkbench((s) => s.pushToast);
  const setHistoryOpen = useWorkbench((s) => s.setHistoryOpen);
  const authUser = useWorkbench((s) => s.authUser);
  const logout = useWorkbench((s) => s.logout);
  const [exportOpen, setExportOpen] = useState(false);

  const canExport = papers.length > 0;
  const pass = verifyReport.filter((v) => v.ok).length;
  const failCount = verifyReport.length - pass;
  // 核验未全过 → 一级警告信号；待审核状态导出为草稿
  const verifyWarn = failCount > 0;
  const draftExport = runStatus === "paused";

  const tabs: {
    key: Tab;
    label: string;
    badge?: string;
    tone?: "muted" | "warn" | "ok";
  }[] = [
    { key: "survey", label: "综述草稿" },
    { key: "papers", label: "文献", badge: papers.length > 0 ? String(papers.length) : undefined },
    {
      key: "verify",
      label: "核验报告",
      badge: verifyReport.length > 0 ? `${pass}/${verifyReport.length}` : undefined,
      tone: verifyReport.length === 0 ? undefined : verifyWarn ? "warn" : "ok",
    },
    { key: "bib", label: "BibTeX", badge: bibEntries.length > 0 ? String(bibEntries.length) : undefined },
  ];

  const badgeCls = (tone: string | undefined, active: boolean) => {
    if (tone === "warn") return "bg-warning/20 text-warning";
    if (tone === "ok") return "bg-success/15 text-success";
    return active ? "bg-primary-soft text-primary" : "bg-muted text-muted-foreground";
  };

  const pushZotero = async () => {
    if (!sessionId) return;
    try {
      const resp = await fetch(`/api/sessions/${sessionId}/zotero`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail ?? "推送失败");
      pushToast(`Zotero：成功创建 ${data.created} 条，失败 ${data.failed} 条`, "success");
    } catch (e) {
      pushToast(e instanceof Error ? e.message : String(e), "error");
    }
  };

  return (
    <div className="flex h-screen flex-col">
      {/* 顶栏 */}
      <header className="flex h-14 shrink-0 items-center gap-4 border-b border-border bg-card px-5">
        <button
          onClick={() => setHistoryOpen(true)}
          title="历史调研记录"
          className="flex h-9 w-9 cursor-pointer items-center justify-center rounded-lg border border-border text-muted-foreground transition-colors hover:text-foreground"
        >
          <History size={16} />
        </button>
        <button
          onClick={reset}
          title="新建调研任务"
          className="flex h-9 w-9 cursor-pointer items-center justify-center rounded-lg border border-border text-muted-foreground transition-colors hover:text-foreground"
        >
          <FilePlus2 size={16} />
        </button>
        <div className="min-w-0 flex-1">
          <div
            className="truncate font-serif text-base font-semibold text-foreground"
            title={`会话 ${sessionId}`}
          >
            {topic || "文献调研任务"}
          </div>
        </div>
        <StatusBadge status={runStatus} />

        {/* Zotero 推送：动作类独立入口 */}
        <button
          onClick={pushZotero}
          disabled={!canExport}
          title="推送到 Zotero 文献库"
          className="inline-flex h-9 cursor-pointer items-center gap-1.5 rounded-lg border border-border bg-card px-3 text-xs font-bold text-foreground transition-colors hover:bg-muted disabled:cursor-not-allowed disabled:opacity-40"
        >
          <BookOpen size={14} />
          <span className="hidden lg:inline">Zotero</span>
        </button>

        {/* 导出下拉：合并文件格式导出 */}
        <div className="relative">
          <button
            onClick={() => setExportOpen((v) => !v)}
            className="inline-flex h-9 cursor-pointer items-center gap-1.5 rounded-lg border border-border bg-card px-3 text-xs font-bold text-foreground transition-colors hover:bg-muted"
          >
            <FileDown size={14} />
            导出
            <ChevronDown
              size={13}
              className={`transition-transform ${exportOpen ? "rotate-180" : ""}`}
            />
          </button>
          {exportOpen && (
            <>
              <div
                className="fixed inset-0 z-40"
                onClick={() => setExportOpen(false)}
              />
              <div className="absolute right-0 top-10 z-50 w-60 overflow-hidden rounded-xl border border-border bg-card shadow-xl">
                {draftExport && (
                  <div className="flex items-center gap-1.5 border-b border-border bg-warning/10 px-3.5 py-2 text-xs text-warning">
                    <TriangleAlert size={13} />
                    当前为草稿导出，审核通过后即为终稿
                  </div>
                )}
                {EXPORT_ITEMS.map((x) => (
                  <a
                    key={x.fmt}
                    href={
                      canExport
                        ? `/api/sessions/${sessionId}/export?format=${x.fmt}`
                        : undefined
                    }
                    onClick={(e) => {
                      if (!canExport) {
                        e.preventDefault();
                        pushToast("文献筛选完成后才能导出", "info");
                      } else {
                        setExportOpen(false);
                      }
                    }}
                    download
                    className={`flex items-center gap-2.5 px-3.5 py-2.5 text-sm font-bold transition-colors ${
                      canExport
                        ? "text-foreground hover:bg-muted"
                        : "cursor-not-allowed text-muted-foreground/50"
                    }`}
                  >
                    {x.icon}
                    {x.label}
                  </a>
                ))}
                <div className="truncate border-t border-border px-3.5 py-2 text-[10px] text-muted-foreground/80">
                  会话 {sessionId}
                </div>
              </div>
            </>
          )}
        </div>
        <ThemeToggle />
        {/* 用户与登出 */}
        <div className="flex items-center gap-1.5 border-l border-border pl-3">
          <span
            className="hidden max-w-32 truncate text-xs font-bold text-muted-foreground sm:inline"
            title={`当前用户：${authUser}`}
          >
            {authUser}
          </span>
          <button
            onClick={logout}
            title="退出登录"
            className="flex h-9 w-9 cursor-pointer items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <LogOut size={15} />
          </button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        {/* 左侧：流程面板 */}
        <aside className="w-[290px] shrink-0 overflow-y-auto border-r border-border bg-card">
          <div className="border-b border-border px-4 py-3 text-xs font-bold tracking-wider text-muted-foreground uppercase">
            执行流程
          </div>
          <NodePanel />
          {runStatus === "error" && errorMsg && (
            <div className="mx-4 mb-4 rounded-lg bg-destructive/10 px-3 py-2.5 text-xs leading-relaxed text-destructive">
              {errorMsg}
            </div>
          )}
        </aside>

        {/* 右侧：内容区 */}
        <main className="flex min-w-0 flex-1 flex-col">
          <nav className="flex h-11 shrink-0 items-stretch border-b border-border bg-card px-5">
            {tabs.map((t) => (
              <button
                key={t.key}
                onClick={() => setTab(t.key)}
                className={`relative cursor-pointer px-4 text-sm font-bold transition-colors ${
                  activeTab === t.key
                    ? "text-primary"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                <span className="flex items-center gap-2">
                  {t.label}
                  {t.badge && (
                    <span
                      className={`rounded-full px-1.5 py-0.5 text-[10px] ${badgeCls(t.tone, activeTab === t.key)}`}
                    >
                      {t.badge}
                    </span>
                  )}
                </span>
                {activeTab === t.key && (
                  <span className="absolute inset-x-3 bottom-0 h-0.5 rounded-full bg-accent" />
                )}
              </button>
            ))}
          </nav>

          {/* 核验警告横幅：一级信号，引导用户先处理未通过文献 */}
          {verifyWarn && (
            <button
              onClick={() => setTab("verify")}
              className="flex w-full shrink-0 cursor-pointer items-center gap-2.5 border-b border-warning/30 bg-warning/10 px-5 py-2.5 text-left text-sm text-warning transition-colors hover:bg-warning/15"
            >
              <TriangleAlert size={16} className="shrink-0" />
              <span className="min-w-0 flex-1">
                <b>
                  {verifyReport.length} 篇入选文献中仅 {pass} 篇通过 CrossRef
                  核验，{failCount} 篇待处理
                </b>
                ——建议先查看核验报告，未通过的引用已在正文中标黄。
              </span>
              <span className="shrink-0 text-xs font-bold underline underline-offset-2">
                查看核验报告 →
              </span>
            </button>
          )}

          <div className="min-h-0 flex-1 overflow-y-auto">
            {activeTab === "survey" && <SurveyTab />}
            {activeTab === "papers" && <PapersTab />}
            {activeTab === "verify" && <VerifyTab />}
            {activeTab === "bib" && <BibTab />}
          </div>

          {runStatus === "paused" && <ReviewBar />}
        </main>
      </div>
    </div>
  );
}
