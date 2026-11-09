"use client";

import {
  CheckCircle2,
  ChevronDown,
  Ellipsis,
  RefreshCw,
  SearchCheck,
} from "lucide-react";
import { useRef, useState } from "react";

import { useWorkbench } from "@/lib/store";

// 快捷审核意见：点选即填
const QUICK_COMMENTS = [
  "补充近三年顶会/顶刊文献",
  "方法对比部分太薄",
  "近三年文献占比太低",
];

function fmtDur(sec?: number): string {
  if (sec === undefined) return "";
  if (sec < 60) return `${sec}s`;
  return `${Math.floor(sec / 60)}m${String(sec % 60).padStart(2, "0")}s`;
}

export default function ReviewBar() {
  const sendFeedback = useWorkbench((s) => s.sendFeedback);
  const papers = useWorkbench((s) => s.papers);
  const surveyDraft = useWorkbench((s) => s.surveyDraft);
  const verifyReport = useWorkbench((s) => s.verifyReport);
  const retryCount = useWorkbench((s) => s.retryCount);
  const nodeDuration = useWorkbench((s) => s.nodeDuration);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const [confirmPass, setConfirmPass] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const pass = verifyReport.filter((v) => v.ok).length;
  const failCount = verifyReport.length - pass;

  const act = async (
    action: "approved" | "rewrite" | "refetch",
    withComment = false,
  ) => {
    if (busy) return;
    setBusy(true);
    setMoreOpen(false);
    setConfirmPass(false);
    await sendFeedback(action, { comment: withComment ? comment : "" });
    setComment("");
    setBusy(false);
  };

  const tryApprove = () => {
    // 拦截：存在未核验文献时先确认，不静默放行
    if (failCount > 0) {
      setConfirmPass(true);
      return;
    }
    act("approved");
  };

  const addQuick = (text: string) => {
    setComment((prev) => (prev ? `${prev}；${text}` : text));
    textareaRef.current?.focus();
  };

  // 元信息行：字数 / 撰写耗时 / 轮次（学术可追溯性）
  const writerDur = nodeDuration.writer;
  const metaLine = [
    `综述 ${surveyDraft.length} 字`,
    writerDur !== undefined ? `撰写 ${fmtDur(writerDur)}` : null,
    retryCount > 0 ? `第 ${retryCount + 1} 轮修订` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <div className="border-t border-accent/40 bg-card px-6 py-4">
      <div className="mx-auto flex max-w-5xl flex-col gap-3">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <div className="flex items-center gap-2 text-sm font-bold text-foreground">
            <span className="dot-blink inline-block h-2 w-2 rounded-full bg-accent" />
            综述草稿已生成（{papers.length} 篇文献），等待你的审核
          </div>
          {metaLine && (
            <div className="text-xs text-muted-foreground">{metaLine}</div>
          )}
        </div>

        {/* 快捷意见 chips：点选即填，降低输入成本 */}
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-muted-foreground">快捷意见</span>
          {QUICK_COMMENTS.map((q) => (
            <button
              key={q}
              type="button"
              onClick={() => addQuick(q)}
              className="cursor-pointer rounded-full border border-border bg-background px-3 py-1 text-xs text-muted-foreground transition-colors hover:border-accent/60 hover:bg-accent/10 hover:text-foreground"
            >
              {q}
            </button>
          ))}
        </div>

        <textarea
          ref={textareaRef}
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          rows={2}
          placeholder="审核意见（选填）：如「补充 agent 评测基准的对比实验」…"
          className="w-full resize-none rounded-xl border border-border bg-background px-4 py-3 text-sm leading-relaxed text-foreground placeholder:text-muted-foreground/75 focus:border-ring focus:outline-2 focus:outline-ring/30"
        />

        <div className="flex flex-wrap items-center gap-2.5">
          {/* 主操作：提交意见重写（用户最高频需求） */}
          <button
            onClick={() => act("rewrite", true)}
            disabled={busy}
            className="inline-flex cursor-pointer items-center gap-2 rounded-lg bg-primary px-5 py-2.5 text-sm font-bold text-primary-foreground shadow-sm transition-all hover:-translate-y-px hover:shadow-md disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:translate-y-0"
          >
            <RefreshCw size={15} />
            提交意见重写
          </button>
          {/* 次操作：通过并导出（存在未核验文献时弹确认） */}
          <button
            onClick={tryApprove}
            disabled={busy}
            className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-success/60 px-4 py-2.5 text-sm font-bold text-success transition-colors hover:bg-success/10 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <CheckCircle2 size={15} />
            通过并导出
          </button>
          {/* 低频操作收纳：定向补检 */}
          <div className="relative">
            <button
              onClick={() => setMoreOpen((v) => !v)}
              disabled={busy}
              className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-border px-3 py-2.5 text-sm font-bold text-muted-foreground transition-colors hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Ellipsis size={15} />
              更多
              <ChevronDown
                size={13}
                className={`transition-transform ${moreOpen ? "rotate-180" : ""}`}
              />
            </button>
            {moreOpen && (
              <>
                <div
                  className="fixed inset-0 z-40"
                  onClick={() => setMoreOpen(false)}
                />
                <div className="absolute bottom-11 left-0 z-50 w-48 overflow-hidden rounded-xl border border-border bg-card shadow-xl">
                  <button
                    onClick={() => act("refetch", true)}
                    className="flex w-full cursor-pointer items-center gap-2.5 px-3.5 py-2.5 text-sm font-bold text-foreground transition-colors hover:bg-muted"
                  >
                    <SearchCheck size={15} className="text-accent" />
                    请求定向补检
                  </button>
                  <div className="border-t border-border px-3.5 py-2 text-[10px] leading-relaxed text-muted-foreground">
                    按审核意见补充检索一轮新文献后重写
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      {/* 未核验拦截确认 */}
      {confirmPass && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-6">
          <div className="w-full max-w-md rounded-2xl border border-border bg-card p-6 shadow-2xl">
            <div className="mb-2 flex items-center gap-2 font-serif text-lg font-semibold text-foreground">
              <CheckCircle2 size={18} className="text-warning" />
              确认通过并导出？
            </div>
            <p className="text-sm leading-relaxed text-muted-foreground">
              仍有 <b className="text-warning">{failCount}</b> 篇文献未通过
              CrossRef
              核验（共 {verifyReport.length} 篇，通过 {pass}{" "}
              篇）。正文中的未核验引用已标黄，导出后请人工复核这些条目。
            </p>
            <div className="mt-5 flex justify-end gap-2.5">
              <button
                onClick={() => setConfirmPass(false)}
                className="cursor-pointer rounded-lg border border-border px-4 py-2 text-sm font-bold text-muted-foreground transition-colors hover:text-foreground"
              >
                返回查看核验报告
              </button>
              <button
                onClick={() => act("approved")}
                disabled={busy}
                className="cursor-pointer rounded-lg bg-success px-4 py-2 text-sm font-bold text-white transition-opacity hover:opacity-90 disabled:opacity-40"
              >
                仍要通过并导出
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
