"use client";

import { create } from "zustand";

import type {
  NodeStatus,
  Paper,
  RunStatus,
  SSEEvent,
  Tab,
  VerifyItem,
} from "./types";
import { NODE_ORDER } from "./types";

const SESSION_KEY = "litagent_session";

export interface Toast {
  id: number;
  kind: "info" | "error" | "success";
  msg: string;
}

function deriveNodesFromState(state: Record<string, unknown>): Record<string, NodeStatus> {
  const done = new Set<string>();
  const subQueries = (state.sub_queries as string[] | undefined) ?? [];
  const rawPapers = (state.papers as Paper[] | undefined) ?? [];
  const screened = (state.screened as Paper[] | undefined) ?? [];
  if (subQueries.length > 0) done.add("planner");
  if (rawPapers.length > 0) done.add("retriever");
  if (screened.length > 0) done.add("screening");
  if (state.survey_draft) done.add("writer");
  if (((state.verify_report as VerifyItem[] | undefined) ?? []).length > 0)
    done.add("verifier");
  if (((state.bib_entries as string[] | undefined) ?? []).length > 0)
    done.add("bib_generator");
  if (state.pdf_ingested !== undefined) done.add("pdf_ingest");

  const result: Record<string, NodeStatus> = {};
  for (const n of NODE_ORDER) result[n] = done.has(n) ? "done" : "pending";
  return result;
}

interface WorkbenchState {
  sessionId: string | null;
  topic: string;
  runStatus: RunStatus;
  // 认证状态
  authUser: string | null;   // null=未登录；loading 中由 authChecking 区分
  authChecking: boolean;
  errorMsg: string | null;
  nodeStatus: Record<string, NodeStatus>;
  nodeMeta: Record<string, string>;
  nodeLogs: Record<string, string[]>;
  nodeDuration: Record<string, number>; // 各节点耗时（秒）
  nodeStartAt: Record<string, number>;
  subQueries: string[];
  rawCount: number;
  papers: Paper[];
  surveyDraft: string;
  verifyReport: VerifyItem[];
  bibEntries: string[];
  pdfIngested: number | null;
  retryCount: number;
  activeTab: Tab;
  selectedRef: number | null;
  sseOpen: boolean;
  startSent: boolean;
  historyOpen: boolean;
  toasts: Toast[];

  newSession: (
    topic: string,
    yearFrom: number,
    yearTo: number,
    topN: number,
    includePdf: boolean,
  ) => Promise<void>;
  initAuth: () => Promise<void>;
  login: (username: string, password: string) => Promise<string | null>;
  register: (username: string, password: string) => Promise<string | null>;
  logout: () => Promise<void>;
  restoreSession: (id: string) => void;
  reset: () => void;
  ensureStart: () => void;
  handleEvent: (ev: SSEEvent) => void;
  setSseOpen: (open: boolean) => void;
  setTab: (t: Tab) => void;
  selectRef: (n: number | null) => void;
  setHistoryOpen: (v: boolean) => void;
  sendFeedback: (
    action: "approved" | "rewrite" | "refetch" | "drop",
    opts?: { comment?: string; drop?: number[] },
  ) => Promise<void>;
  pushToast: (msg: string, kind?: Toast["kind"]) => void;
  dismissToast: (id: number) => void;
}

let toastSeq = 0;

const initialData = {
  topic: "",
  errorMsg: null,
  nodeStatus: Object.fromEntries(NODE_ORDER.map((n) => [n, "pending"])) as Record<string, NodeStatus>,
  nodeMeta: {} as Record<string, string>,
  nodeLogs: {} as Record<string, string[]>,
  nodeDuration: {} as Record<string, number>,
  nodeStartAt: {} as Record<string, number>,
  subQueries: [] as string[],
  rawCount: 0,
  papers: [] as Paper[],
  surveyDraft: "",
  verifyReport: [] as VerifyItem[],
  bibEntries: [] as string[],
  pdfIngested: null as number | null,
  retryCount: 0,
  startSent: false,
};

export const useWorkbench = create<WorkbenchState>((set, get) => ({
  sessionId: null,
  runStatus: "idle",
  activeTab: "survey",
  selectedRef: null,
  sseOpen: false,
  historyOpen: false,
  authUser: null,
  authChecking: true,
  toasts: [],
  ...initialData,

  // ---- 认证 ----
  initAuth: async () => {
    try {
      const resp = await fetch("/api/auth/me");
      set({ authUser: resp.ok ? (await resp.json()).username : null });
    } catch {
      set({ authUser: null });
    } finally {
      set({ authChecking: false });
    }
  },

  login: async (username, password) => {
    const resp = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    if (!resp.ok) {
      const detail = await resp.json().catch(() => ({}));
      return detail.detail ?? "登录失败";
    }
    set({ authUser: (await resp.json()).username });
    return null;
  },

  register: async (username, password) => {
    const resp = await fetch("/api/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    if (!resp.ok) {
      const detail = await resp.json().catch(() => ({}));
      return detail.detail ?? "注册失败";
    }
    set({ authUser: (await resp.json()).username });
    return null;
  },

  logout: async () => {
    await fetch("/api/auth/logout", { method: "POST" }).catch(() => {});
    // 登出同时清掉本浏览器的会话记忆，避免下次恢复到他人会话
    localStorage.removeItem(SESSION_KEY);
    set({
      authUser: null,
      sessionId: null,
      runStatus: "idle",
      activeTab: "survey",
      sseOpen: false,
      ...initialData, // 含 startSent:false，清空全部调研数据
    });
  },

  pushToast: (msg, kind = "info") => {
    const id = ++toastSeq;
    set((s) => ({ toasts: [...s.toasts, { id, kind, msg }] }));
    setTimeout(() => get().dismissToast(id), 4200);
  },
  dismissToast: (id) =>
    set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),

  newSession: async (topic, yearFrom, yearTo, topN, includePdf) => {
    try {
      const resp = await fetch("/api/sessions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          topic,
          year_from: yearFrom,
          year_to: yearTo,
          top_n: topN,
          include_pdf: includePdf,
        }),
      });
      if (!resp.ok) throw new Error(`创建失败（${resp.status}）`);
      const { session_id } = (await resp.json()) as { session_id: string };
      localStorage.setItem(SESSION_KEY, session_id);
      set({ ...initialData, sessionId: session_id, topic, runStatus: "created" });
    } catch (e) {
      get().pushToast(e instanceof Error ? e.message : String(e), "error");
    }
  },

  restoreSession: (id) => {
    set({ sessionId: id, runStatus: "created", ...initialData });
  },

  reset: () => {
    localStorage.removeItem(SESSION_KEY);
    set({ sessionId: null, runStatus: "idle", activeTab: "survey", selectedRef: null, sseOpen: false, ...initialData });
  },

  // 启动图执行：连接建立（onopen）或快照到达时调用，幂等
  ensureStart: () => {
    const s = get();
    if (!s.sessionId || s.startSent || s.runStatus !== "created") return;
    set({ startSent: true });
    fetch(`/api/sessions/${s.sessionId}/start`, { method: "POST" })
      .then((r) => {
        if (r.status === 409) return; // 会话已在执行（刷新恢复场景），后端守卫拒绝
        if (!r.ok) throw new Error(`启动失败（${r.status}）`);
      })
      .catch(() => {
        set({ startSent: false }); // 允许 SSE 自动重连后重试
        get().pushToast("任务启动失败，请重试", "error");
      });
  },

  setSseOpen: (open) => set({ sseOpen: open }),

  setTab: (t) => set({ activeTab: t }),
  selectRef: (n) => set({ selectedRef: n }),
  setHistoryOpen: (v) => set({ historyOpen: v }),

  handleEvent: (ev) => {
    const s = get();
    switch (ev.type) {
      case "snapshot": {
        const state = ev.state ?? {};
        const status = (ev.status as RunStatus) ?? "created";
        set({
          topic: (ev.topic as string) || s.topic,
          runStatus: status,
          subQueries: (state.sub_queries as string[] | undefined) ?? [],
          papers: (state.screened as Paper[] | undefined) ?? [],
          rawCount: ((state.papers as Paper[] | undefined) ?? []).length,
          surveyDraft: (state.survey_draft as string | undefined) ?? "",
          verifyReport: (state.verify_report as VerifyItem[] | undefined) ?? [],
          bibEntries: (state.bib_entries as string[] | undefined) ?? [],
          pdfIngested: (state.pdf_ingested as number | undefined) ?? null,
          retryCount: (state.retry_count as number | undefined) ?? 0,
          nodeStatus: deriveNodesFromState(state),
        });
        // 新建会话：连接/快照任一就绪即启动（ensureStart 幂等，见 onopen 兜底）
        if (status === "created") get().ensureStart();
        break;
      }
      case "node_start":
        if (ev.node) {
          const ns = { ...get().nodeStatus, [ev.node]: "running" as NodeStatus };
          set({
            nodeStatus: ns,
            runStatus: "running",
            nodeStartAt: { ...get().nodeStartAt, [ev.node]: Date.now() },
          });
        }
        break;
      case "node_end":
        if (ev.node) {
          const ns = { ...get().nodeStatus, [ev.node]: "done" as NodeStatus };
          const startAt = get().nodeStartAt[ev.node];
          const nd = { ...get().nodeDuration };
          if (startAt) nd[ev.node] = Math.round((Date.now() - startAt) / 1000);
          set({ nodeStatus: ns, nodeDuration: nd });
        }
        break;
      case "progress":
        if (ev.node && ev.message) {
          set((st) => {
            const logs = st.nodeLogs[ev.node!] ?? [];
            // 相同消息去重，避免轮询类进度刷屏
            if (logs[logs.length - 1] === ev.message) return {};
            return {
              nodeMeta: { ...st.nodeMeta, [ev.node!]: ev.message! },
              nodeLogs: { ...st.nodeLogs, [ev.node!]: [...logs, ev.message!] },
            };
          });
        }
        break;
      case "artifact": {
        const d = ev.data ?? {};
        switch (ev.node) {
          case "planner":
            set({ subQueries: (d.sub_queries as string[] | undefined) ?? [] });
            break;
          case "retriever":
            set((st) => ({
              rawCount: st.rawCount + ((d.papers as Paper[] | undefined) ?? []).length,
              retryCount: (d.retry_count as number | undefined) ?? st.retryCount,
            }));
            break;
          case "screening":
            set({ papers: (d.screened as Paper[] | undefined) ?? [] });
            break;
          case "writer":
            set({ surveyDraft: (d.survey_draft as string | undefined) ?? "" });
            break;
          case "verifier":
            set({ verifyReport: (d.verify_report as VerifyItem[] | undefined) ?? [] });
            break;
          case "bib_generator":
            set({ bibEntries: (d.bib_entries as string[] | undefined) ?? [] });
            break;
          case "pdf_ingest":
            set({ pdfIngested: (d.pdf_ingested as number | undefined) ?? 0 });
            break;
        }
        break;
      }
      case "token":
        if (ev.content) set({ surveyDraft: get().surveyDraft + ev.content });
        break;
      case "interrupt":
        set({
          runStatus: "paused",
          nodeStatus: { ...get().nodeStatus, human_review: "waiting" },
          activeTab: "survey",
        });
        break;
      case "status":
        if (ev.status) set({ runStatus: ev.status as RunStatus });
        break;
      case "error":
        set({ runStatus: "error", errorMsg: ev.message ?? "未知错误" });
        get().pushToast(ev.message ?? "执行出错", "error");
        break;
      case "done":
        break;
    }
  },

  sendFeedback: async (action, opts) => {
    const id = get().sessionId;
    if (!id) return;
    try {
      const resp = await fetch(`/api/sessions/${id}/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action,
          comment: opts?.comment ?? "",
          drop: opts?.drop ?? [],
        }),
      });
      if (!resp.ok) {
        const detail = await resp.json().catch(() => ({}));
        throw new Error(
          (detail as { detail?: string }).detail ?? `提交失败（${resp.status}）`,
        );
      }
      set({
        runStatus: "running",
        nodeStatus: { ...get().nodeStatus, human_review: "done" },
      });
    } catch (e) {
      get().pushToast(e instanceof Error ? e.message : String(e), "error");
    }
  },
}));
