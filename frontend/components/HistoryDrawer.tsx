"use client";

import { History, Loader2, RotateCcw, Search, Trash2, X } from "lucide-react";
import { useEffect, useState } from "react";

import { useWorkbench } from "@/lib/store";
import type { RunStatus } from "@/lib/types";

interface SessionMeta {
  id: string;
  topic: string;
  status: RunStatus;
  error: string | null;
  created_at: string;
  updated_at: string;
  raw_count: number;
  screened_count: number;
  verify_pass: number;
  verify_total: number;
  retry_count: number;
}

const STATUS_CLS: Record<string, { label: string; cls: string }> = {
  created: { label: "待启动", cls: "bg-muted text-muted-foreground" },
  running: { label: "运行中", cls: "bg-primary-soft text-primary" },
  paused: { label: "待审核", cls: "bg-accent/15 text-accent" },
  finished: { label: "已完成", cls: "bg-success/10 text-success" },
  error: { label: "出错", cls: "bg-destructive/10 text-destructive" },
  idle: { label: "空闲", cls: "bg-muted text-muted-foreground" },
};

function relTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const min = Math.floor(diff / 60000);
  if (min < 1) return "刚刚";
  if (min < 60) return `${min} 分钟前`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr} 小时前`;
  const day = Math.floor(hr / 24);
  if (day < 7) return `${day} 天前`;
  return new Date(iso).toLocaleDateString("zh-CN", { month: "numeric", day: "numeric" });
}

export default function HistoryDrawer() {
  const historyOpen = useWorkbench((s) => s.historyOpen);
  const setHistoryOpen = useWorkbench((s) => s.setHistoryOpen);
  const restoreSession = useWorkbench((s) => s.restoreSession);
  const sessionId = useWorkbench((s) => s.sessionId);
  const authUser = useWorkbench((s) => s.authUser);
  const pushToast = useWorkbench((s) => s.pushToast);

  const [items, setItems] = useState<SessionMeta[] | null>(null);
  const [query, setQuery] = useState("");
  const [confirmDel, setConfirmDel] = useState<string | null>(null);

  useEffect(() => {
    if (!historyOpen) return;
    setConfirmDel(null);
    setItems(null); // 每次打开先回到加载态，避免残留上一用户的列表
    const timer = setTimeout(async () => {
      try {
        const resp = await fetch(
          `/api/sessions${query.trim() ? `?q=${encodeURIComponent(query.trim())}` : ""}`,
        );
        if (!resp.ok) throw new Error(`加载失败（${resp.status}）`);
        setItems((await resp.json()) as SessionMeta[]);
      } catch (e) {
        pushToast(e instanceof Error ? e.message : String(e), "error");
        setItems([]);
      }
    }, 220);
    return () => clearTimeout(timer);
  }, [historyOpen, query, authUser, pushToast]);

  const restore = (id: string) => {
    if (id === sessionId) {
      setHistoryOpen(false); // 当前会话仅关闭抽屉
      return;
    }
    restoreSession(id);
    setHistoryOpen(false);
    pushToast("已恢复历史会话", "success");
  };

  const remove = async (id: string) => {
    if (confirmDel !== id) {
      setConfirmDel(id); // 行内二次确认
      return;
    }
    try {
      const resp = await fetch(`/api/sessions/${id}`, { method: "DELETE" });
      if (!resp.ok) throw new Error(`删除失败（${resp.status}）`);
      setItems((prev) => prev?.filter((x) => x.id !== id) ?? []);
      pushToast("已删除该调研记录", "success");
    } catch (e) {
      pushToast(e instanceof Error ? e.message : String(e), "error");
    }
    setConfirmDel(null);
  };

  return (
    <>
      {historyOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/30"
          onClick={() => setHistoryOpen(false)}
        />
      )}
      <aside
        className={`fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col border-l border-border bg-card shadow-2xl transition-transform duration-300 ${
          historyOpen ? "translate-x-0" : "translate-x-full"
        }`}
        aria-hidden={!historyOpen}
      >
        <div className="flex h-14 shrink-0 items-center gap-2.5 border-b border-border px-5">
          <History size={17} className="text-accent" />
          <span className="font-serif text-base font-semibold">历史调研</span>
          <button
            onClick={() => setHistoryOpen(false)}
            aria-label="关闭历史列表"
            className="ml-auto flex h-8 w-8 cursor-pointer items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <X size={16} />
          </button>
        </div>

        <div className="border-b border-border px-5 py-3">
          <div className="relative">
            <Search
              size={14}
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
            />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="按主题搜索…"
              className="h-9 w-full rounded-lg border border-border bg-background pl-8 pr-3 text-sm text-foreground placeholder:text-muted-foreground/75 focus:border-ring focus:outline-2 focus:outline-ring/30"
            />
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-3">
          {items === null ? (
            <div className="flex items-center justify-center gap-2 py-16 text-sm text-muted-foreground">
              <Loader2 size={15} className="animate-spin" />
              加载中…
            </div>
          ) : items.length === 0 ? (
            <div className="py-16 text-center text-sm text-muted-foreground">
              {query ? "没有匹配的调研记录" : "还没有历史调研记录"}
            </div>
          ) : (
            <ul className="flex flex-col gap-2">
              {items.map((it) => {
                const st = STATUS_CLS[it.status] ?? STATUS_CLS.idle;
                const current = it.id === sessionId;
                return (
                  <li key={it.id}>
                    <div
                      role="button"
                      tabIndex={0}
                      onClick={() => restore(it.id)}
                      onKeyDown={(e) => e.key === "Enter" && restore(it.id)}
                      className={`group cursor-pointer rounded-xl border px-4 py-3 transition-colors ${
                        current
                          ? "border-accent/60 bg-accent/5"
                          : "border-border bg-background hover:border-ring/50 hover:bg-muted/50"
                      }`}
                    >
                      <div className="flex items-start gap-2">
                        <span
                          className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold ${st.cls}`}
                        >
                          {st.label}
                        </span>
                        <span className="min-w-0 flex-1 truncate text-sm font-bold text-foreground">
                          {it.topic}
                        </span>
                      </div>
                      <div className="mt-1.5 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-xs text-muted-foreground">
                        <span title={new Date(it.created_at).toLocaleString("zh-CN")}>
                          {relTime(it.created_at)}
                        </span>
                        {it.screened_count > 0 && (
                          <>
                            <span>·</span>
                            <span className="tabular-nums">
                              原始 {it.raw_count} → 入选 {it.screened_count}
                            </span>
                            {it.verify_total > 0 && (
                              <>
                                <span>·</span>
                                <span
                                  className={`tabular-nums ${
                                    it.verify_pass < it.verify_total
                                      ? "font-bold text-warning"
                                      : "text-success"
                                  }`}
                                >
                                  核验 {it.verify_pass}/{it.verify_total}
                                </span>
                              </>
                            )}
                          </>
                        )}
                        {current && (
                          <span className="text-accent">· 当前会话</span>
                        )}
                      </div>
                      <div className="mt-2 flex items-center gap-2 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
                        <span className="inline-flex items-center gap-1 text-xs font-bold text-primary">
                          <RotateCcw size={12} />
                          {current ? "查看" : "恢复会话"}
                        </span>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            remove(it.id);
                          }}
                          className={`ml-auto inline-flex cursor-pointer items-center gap-1 rounded px-1.5 py-0.5 text-xs font-bold transition-colors ${
                            confirmDel === it.id
                              ? "bg-destructive/10 text-destructive"
                              : "text-muted-foreground hover:text-destructive"
                          }`}
                        >
                          <Trash2 size={12} />
                          {confirmDel === it.id ? "确认删除？" : "删除"}
                        </button>
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </aside>
    </>
  );
}
