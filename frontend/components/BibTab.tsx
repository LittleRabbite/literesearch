"use client";

import { Check, Copy, Download } from "lucide-react";
import { useState } from "react";

import { useWorkbench } from "@/lib/store";

export default function BibTab() {
  const bibEntries = useWorkbench((s) => s.bibEntries);
  const sessionId = useWorkbench((s) => s.sessionId);
  const pushToast = useWorkbench((s) => s.pushToast);
  const [copied, setCopied] = useState(false);

  if (bibEntries.length === 0) {
    return (
      <div className="py-24 text-center text-muted-foreground">
        BibTeX 生成完成后在此展示
      </div>
    );
  }

  const text = bibEntries.filter(Boolean).join("\n\n");

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      pushToast("复制失败，请手动选择复制", "error");
    }
  };

  return (
    <div className="mx-auto max-w-3xl px-6 py-6">
      <div className="mb-3 flex items-center justify-between">
        <span className="text-xs text-muted-foreground">
          共 {bibEntries.filter(Boolean).length} 条 · 优先来自 arXiv/DOI
          官方源，LLM 兜底条目建议人工核对
        </span>
        <div className="flex items-center gap-2">
          <button
            onClick={copy}
            className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-1.5 text-xs font-bold text-foreground transition-colors hover:bg-muted"
          >
            {copied ? <Check size={13} /> : <Copy size={13} />}
            {copied ? "已复制" : "复制全部"}
          </button>
          <a
            href={`/api/sessions/${sessionId}/export?format=bib`}
            download
            className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-1.5 text-xs font-bold text-foreground transition-colors hover:bg-muted"
          >
            <Download size={13} />
            下载 .bib
          </a>
        </div>
      </div>
      <pre className="overflow-x-auto rounded-xl border border-border bg-card p-4 font-mono text-xs leading-relaxed text-card-foreground">
        {text}
      </pre>
    </div>
  );
}
