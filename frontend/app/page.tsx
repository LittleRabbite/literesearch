"use client";

import { useEffect, useRef } from "react";

import HistoryDrawer from "@/components/HistoryDrawer";
import LoginPanel from "@/components/LoginPanel";
import NewTaskForm from "@/components/NewTaskForm";
import Toasts from "@/components/Toasts";
import Workbench from "@/components/Workbench";
import { useWorkbench } from "@/lib/store";

export default function Home() {
  const authUser = useWorkbench((s) => s.authUser);
  const authChecking = useWorkbench((s) => s.authChecking);
  const initAuth = useWorkbench((s) => s.initAuth);
  const sessionId = useWorkbench((s) => s.sessionId);
  const restoreSession = useWorkbench((s) => s.restoreSession);
  const handleEvent = useWorkbench((s) => s.handleEvent);
  const setSseOpen = useWorkbench((s) => s.setSseOpen);
  const esRef = useRef<EventSource | null>(null);

  // 启动时校验登录态（HttpOnly Cookie）
  useEffect(() => {
    initAuth();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 刷新恢复：从 localStorage 找回会话（仅登录后执行）
  useEffect(() => {
    if (!authUser) return;
    const saved = localStorage.getItem("litagent_session");
    if (saved && !useWorkbench.getState().sessionId) {
      restoreSession(saved);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authUser]);

  // SSE 订阅：仅依赖 sessionId，避免严格模式下「开→关→重开」循环
  useEffect(() => {
    if (!authUser || !sessionId || esRef.current) return;
    const es = new EventSource(`/api/sessions/${sessionId}/events`);
    esRef.current = es;
    es.onopen = () => {
      useWorkbench.getState().setSseOpen(true);
      // 连接建立即尝试启动，不依赖快照解析（ensureStart 内部幂等）
      useWorkbench.getState().ensureStart();
    };
    es.onmessage = (e) => {
      try {
        useWorkbench.getState().handleEvent(JSON.parse(e.data));
      } catch (err) {
        // 心跳注释行不会进入 onmessage，走到这里说明解析或处理真出错
        console.error("SSE 事件处理失败:", err, e.data?.slice(0, 200));
      }
    };
    es.onerror = () => {
      // 浏览器会自动重连；后端重启后快照会重新同步状态
    };
    return () => {
      es.close();
      esRef.current = null;
      useWorkbench.getState().setSseOpen(false);
    };
  }, [sessionId, authUser]);

  if (authChecking) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">
        正在校验登录状态…
      </div>
    );
  }

  return (
    <>
      {authUser ? (
        sessionId ? <Workbench /> : <NewTaskForm />
      ) : (
        <LoginPanel />
      )}
      <HistoryDrawer />
      <Toasts />
    </>
  );
}
