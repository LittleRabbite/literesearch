"use client";

import {
  BookOpen,
  Check,
  FileSpreadsheet,
  FileText,
  History,
  Info,
  LibraryBig,
  Loader2,
  LogOut,
  Sparkles,
  UploadCloud,
} from "lucide-react";
import { useState } from "react";

import { useWorkbench } from "@/lib/store";

// 快速开始示例主题
const EXAMPLES = [
  "大语言模型智能体在软件工程中的应用",
  "图神经网络在药物发现中的应用",
  "检索增强生成（RAG）的幻觉缓解方法",
];

// 数据源徽标（品牌色圆点 + 名称）
const SOURCES = [
  { name: "arXiv", color: "#b31b1b" },
  { name: "Semantic Scholar", color: "#1a5fb4" },
  { name: "OpenAlex", color: "#a3622b" },
  { name: "ChinaXiv", color: "#0e7a5f" },
];

// 输出预览示意卡（静态示意，非真实数据）
const PREVIEW_PAPERS = [
  { title: "ReAct: Synergizing Reasoning and Acting in LLMs", year: 2023 },
  { title: "Toolformer: Language Models Can Teach Themselves Tools", year: 2023 },
];

function InfoHint({ text }: { text: string }) {
  return (
    <span
      title={text}
      className="inline-flex cursor-help items-center align-middle text-muted-foreground transition-colors hover:text-foreground"
    >
      <Info size={14} />
    </span>
  );
}

export default function NewTaskForm() {
  const newSession = useWorkbench((s) => s.newSession);
  const setHistoryOpen = useWorkbench((s) => s.setHistoryOpen);
  const authUser = useWorkbench((s) => s.authUser);
  const logout = useWorkbench((s) => s.logout);
  const [topic, setTopic] = useState("");
  const [yearFrom, setYearFrom] = useState(2022);
  const [yearTo, setYearTo] = useState(2026);
  const [topN, setTopN] = useState(15);
  const [includePdf, setIncludePdf] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors] = useState<{
    yearFrom?: string;
    yearTo?: string;
    topN?: string;
  }>({});

  // 年份/上限联动校验：起始 ≤ 截止，均在合理区间
  const validate = (
    field: "yearFrom" | "yearTo" | "topN",
    value: number,
  ): string | undefined => {
    if (field === "topN") {
      if (!Number.isFinite(value) || value < 5 || value > 30)
        return "请输入 5–30 之间的整数";
      return undefined;
    }
    if (!Number.isFinite(value) || value < 2000 || value > 2030)
      return "请输入 2000–2030 之间的年份";
    const other = field === "yearFrom" ? yearTo : yearFrom;
    if (Number.isFinite(other) && other >= 2000 && other <= 2030) {
      if (field === "yearFrom" && value > other) return "起始年份不能晚于截止年份";
      if (field === "yearTo" && value < other) return "截止年份不能早于起始年份";
    }
    return undefined;
  };

  const setField = (field: "yearFrom" | "yearTo" | "topN", raw: string) => {
    const value = Number(raw);
    if (field === "yearFrom") setYearFrom(value);
    if (field === "yearTo") setYearTo(value);
    if (field === "topN") setTopN(value);
    // 两个年份字段联动重算，保证双向约束即时反馈
    setErrors((prev) => {
      const next = { ...prev, [field]: validate(field, value) };
      if (field !== "topN") {
        const other = field === "yearFrom" ? "yearTo" : "yearFrom";
        next[other] = validate(other, field === "yearFrom" ? yearTo : yearFrom);
      }
      return next;
    });
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!topic.trim() || submitting) return;
    const next = {
      yearFrom: validate("yearFrom", yearFrom),
      yearTo: validate("yearTo", yearTo),
      topN: validate("topN", topN),
    };
    setErrors(next);
    if (next.yearFrom || next.yearTo || next.topN) return;
    setSubmitting(true);
    await newSession(topic.trim(), yearFrom, yearTo, topN, includePdf);
    setSubmitting(false);
  };

  const inputCls = (err?: string) =>
    `h-11 w-full rounded-xl border bg-card px-4 text-foreground transition-colors focus:outline-2 focus:outline-ring/30 ${
      err
        ? "border-destructive focus:border-destructive"
        : "border-border focus:border-ring"
    }`;

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-2xl flex-col px-6 pb-16 pt-14">
      <div className="mb-9">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="mb-3 flex items-center gap-2 text-accent">
              <LibraryBig size={20} />
              <span className="text-xs font-bold uppercase tracking-[0.25em]">
                Literature Research Agent
              </span>
            </div>
            <h1 className="font-serif text-4xl font-semibold leading-tight text-foreground">
              文献调研智能体
            </h1>
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            <button
              onClick={() => setHistoryOpen(true)}
              title="查看历史调研记录"
              className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-2 text-xs font-bold text-muted-foreground transition-colors hover:border-accent/60 hover:text-foreground"
            >
              <History size={14} />
              历史调研
            </button>
            <span className="hidden text-xs font-bold text-muted-foreground sm:inline">
              {authUser}
            </span>
            <button
              onClick={logout}
              title="退出登录"
              className="flex h-8 w-8 cursor-pointer items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              <LogOut size={14} />
            </button>
          </div>
        </div>
        <p className="mt-3 max-w-lg leading-relaxed text-muted-foreground">
          给定研究主题，多智能体自动完成检索、筛选、综述、引用核验与 BibTeX
          生成，生成后支持逐轮人工审核与定向补检。
        </p>
      </div>

      <form onSubmit={submit} className="flex flex-col gap-6">
        <div>
          <label
            htmlFor="topic"
            className="mb-2 block text-sm font-bold text-foreground"
          >
            研究主题
          </label>
          <textarea
            id="topic"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            rows={2}
            required
            placeholder="例如：大语言模型智能体在软件工程中的应用"
            className="w-full resize-none rounded-xl border border-border bg-card px-4 py-3 leading-relaxed text-foreground transition-colors placeholder:text-muted-foreground/75 focus:border-ring focus:outline-2 focus:outline-ring/30"
          />
          {/* 快速开始：点击直接填入示例主题 */}
          <div className="mt-2.5 flex flex-wrap items-center gap-2">
            <span className="text-xs text-muted-foreground">快速开始</span>
            {EXAMPLES.map((ex) => (
              <button
                key={ex}
                type="button"
                onClick={() => setTopic(ex)}
                className="cursor-pointer rounded-full border border-border bg-card px-3 py-1 text-xs text-muted-foreground transition-colors hover:border-accent/60 hover:bg-accent/10 hover:text-foreground"
              >
                {ex}
              </button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div>
            <label
              htmlFor="yearFrom"
              className="mb-2 block text-sm font-bold text-foreground"
            >
              起始年份
            </label>
            <input
              id="yearFrom"
              type="number"
              min={2000}
              max={2030}
              value={yearFrom}
              onChange={(e) => setField("yearFrom", e.target.value)}
              aria-invalid={!!errors.yearFrom}
              className={inputCls(errors.yearFrom)}
            />
            {errors.yearFrom && (
              <p className="mt-1.5 text-xs text-destructive">{errors.yearFrom}</p>
            )}
          </div>
          <div>
            <label
              htmlFor="yearTo"
              className="mb-2 block text-sm font-bold text-foreground"
            >
              截止年份
            </label>
            <input
              id="yearTo"
              type="number"
              min={2000}
              max={2030}
              value={yearTo}
              onChange={(e) => setField("yearTo", e.target.value)}
              aria-invalid={!!errors.yearTo}
              className={inputCls(errors.yearTo)}
            />
            {errors.yearTo && (
              <p className="mt-1.5 text-xs text-destructive">{errors.yearTo}</p>
            )}
          </div>
          <div>
            <label
              htmlFor="topN"
              className="mb-2 flex items-center gap-1.5 text-sm font-bold text-foreground"
            >
              入选文献上限（篇）
              <InfoHint text="最终入选综述引用的文献数量上限；生成后仍可在审核阶段人工增删。" />
            </label>
            <input
              id="topN"
              type="number"
              min={5}
              max={30}
              value={topN}
              onChange={(e) => setField("topN", e.target.value)}
              aria-invalid={!!errors.topN}
              className={inputCls(errors.topN)}
            />
            {errors.topN && (
              <p className="mt-1.5 text-xs text-destructive">{errors.topN}</p>
            )}
          </div>
        </div>

        <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-border bg-card px-4 py-3.5 transition-colors hover:border-ring/50">
          <input
            type="checkbox"
            checked={includePdf}
            onChange={(e) => setIncludePdf(e.target.checked)}
            className="mt-1 h-4 w-4 cursor-pointer accent-[var(--primary)]"
          />
          <span className="flex items-center gap-1.5 text-sm font-bold leading-snug">
            下载 PDF 全文并向量化入库
            <InfoHint text="仅支持 arXiv 来源；首次启用需下载嵌入模型（约 2GB），耗时较长。" />
          </span>
        </label>

        {/* 主按钮：品牌琥珀金 + hover 抬升微光 */}
        <button
          type="submit"
          disabled={!topic.trim() || submitting}
          className="flex cursor-pointer items-center justify-center gap-2.5 rounded-xl bg-accent px-8 py-4 text-base font-bold text-accent-foreground shadow-lg shadow-accent/25 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-xl hover:shadow-accent/35 focus-visible:outline-2 focus-visible:outline-ring active:translate-y-0 disabled:cursor-not-allowed disabled:opacity-40 disabled:shadow-none disabled:hover:translate-y-0"
        >
          {submitting ? (
            <>
              <Loader2 size={19} className="animate-spin" />
              正在创建会话…
            </>
          ) : (
            <>
              <Sparkles size={19} />
              开始调研
            </>
          )}
        </button>
      </form>

      {/* 数据源信任信号：品牌色徽标 */}
      <div className="mt-8 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-muted-foreground">
        <span className="inline-flex items-center gap-1.5">
          <BookOpen size={13} />
          数据源
        </span>
        {SOURCES.map((s) => (
          <span key={s.name} className="inline-flex items-center gap-1.5">
            <span
              className="inline-block h-2 w-2 rounded-full"
              style={{ backgroundColor: s.color }}
            />
            {s.name}
          </span>
        ))}
        <span>· CrossRef 引用核验</span>
      </div>

      {/* 输出预览：让用户提前知道会得到什么 */}
      <div className="mt-5 rounded-2xl border border-border bg-card p-5">
        <div className="mb-4 text-xs font-bold uppercase tracking-wider text-muted-foreground">
          你将得到
        </div>
        <div className="flex flex-col gap-5 sm:flex-row">
          <div className="flex min-w-0 flex-1 flex-col gap-2.5">
            {PREVIEW_PAPERS.map((p) => (
              <div
                key={p.title}
                className="rounded-xl border border-dashed border-border px-3.5 py-2.5"
              >
                <div className="truncate font-serif text-[13px] font-semibold text-foreground">
                  {p.title}
                </div>
                <div className="mt-0.5 text-xs text-muted-foreground">
                  {p.year} · 打分排序 · 逐条 DOI 核验
                </div>
              </div>
            ))}
            <div className="text-xs text-muted-foreground">
              …以及一份带引用编号的综述草稿
            </div>
          </div>
          <ul className="flex shrink-0 flex-col gap-2.5 text-sm text-foreground sm:w-52">
            {[
              { icon: <FileText size={15} />, text: "Markdown 综述报告" },
              { icon: <FileSpreadsheet size={15} />, text: "Excel 文献矩阵" },
              { icon: <Check size={15} />, text: "BibTeX 引用条目" },
              {
                icon: <UploadCloud size={15} />,
                text: "一键推送 Zotero 文献库",
                highlight: true,
              },
            ].map((x) => (
              <li
                key={x.text}
                className={`flex items-center gap-2 ${
                  x.highlight ? "font-bold text-accent" : ""
                }`}
              >
                {x.icon}
                {x.text}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
