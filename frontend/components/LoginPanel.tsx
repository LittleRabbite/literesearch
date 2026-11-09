"use client";

import { LibraryBig, Loader2, LogIn, UserPlus } from "lucide-react";
import { useState } from "react";

import { useWorkbench } from "@/lib/store";

export default function LoginPanel() {
  const login = useWorkbench((s) => s.login);
  const register = useWorkbench((s) => s.register);
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setError(null);
    setBusy(true);
    const err =
      mode === "login"
        ? await login(username.trim(), password)
        : await register(username.trim(), password);
    if (err) setError(err);
    setBusy(false);
  };

  const inputCls =
    "h-11 w-full rounded-xl border border-border bg-card px-4 text-foreground transition-colors placeholder:text-muted-foreground/75 focus:border-ring focus:outline-2 focus:outline-ring/30";

  return (
    <div className="flex min-h-screen items-center justify-center px-6">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <div className="mb-3 flex items-center justify-center gap-2 text-accent">
            <LibraryBig size={20} />
            <span className="text-xs font-bold uppercase tracking-[0.25em]">
              Literature Research Agent
            </span>
          </div>
          <h1 className="font-serif text-3xl font-semibold text-foreground">
            文献调研智能体
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">
            {mode === "login" ? "登录后开始你的调研" : "创建账号，独立管理你的调研记录"}
          </p>
        </div>

        <div className="mb-5 grid grid-cols-2 rounded-xl border border-border bg-card p-1">
          {(["login", "register"] as const).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => {
                setMode(m);
                setError(null);
              }}
              className={`cursor-pointer rounded-lg py-2 text-sm font-bold transition-colors ${
                mode === m
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {m === "login" ? "登录" : "注册"}
            </button>
          ))}
        </div>

        <form onSubmit={submit} className="flex flex-col gap-4">
          <div>
            <label htmlFor="username" className="mb-1.5 block text-sm font-bold text-foreground">
              用户名
            </label>
            <input
              id="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoComplete="username"
              placeholder="2–32 个字符"
              className={inputCls}
            />
          </div>
          <div>
            <label htmlFor="password" className="mb-1.5 block text-sm font-bold text-foreground">
              密码
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              placeholder={mode === "register" ? "至少 6 位" : ""}
              className={inputCls}
            />
          </div>
          {error && (
            <p className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </p>
          )}
          <button
            type="submit"
            disabled={busy}
            className="flex cursor-pointer items-center justify-center gap-2 rounded-xl bg-accent px-6 py-3.5 text-base font-bold text-accent-foreground shadow-lg shadow-accent/25 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-xl hover:shadow-accent/35 active:translate-y-0 disabled:cursor-not-allowed disabled:opacity-40 disabled:shadow-none"
          >
            {busy ? (
              <Loader2 size={18} className="animate-spin" />
            ) : mode === "login" ? (
              <LogIn size={18} />
            ) : (
              <UserPlus size={18} />
            )}
            {mode === "login" ? "登录" : "注册并登录"}
          </button>
          {mode === "register" && (
            <p className="text-center text-xs leading-relaxed text-muted-foreground">
              首位注册的用户将自动继承本系统升级前的历史调研记录
            </p>
          )}
        </form>
      </div>
    </div>
  );
}
