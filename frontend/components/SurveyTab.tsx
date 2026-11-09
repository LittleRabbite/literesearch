"use client";

import { useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { useWorkbench } from "@/lib/store";

function linkifyRefs(md: string): string {
  return md.replace(/\[(\d{1,2})\]/g, (_m, n) => `[${n}](#ref-${n})`);
}

export default function SurveyTab() {
  const surveyDraft = useWorkbench((s) => s.surveyDraft);
  const running = useWorkbench((s) => s.runStatus === "running");
  const selectedRef = useWorkbench((s) => s.selectedRef);
  const selectRef = useWorkbench((s) => s.selectRef);
  const setTab = useWorkbench((s) => s.setTab);
  const verifyReport = useWorkbench((s) => s.verifyReport);

  // 未通过核验的引用编号集合：正文上标显示琥珀警示态
  const failedRefs = new Set(
    verifyReport.filter((v) => !v.ok).map((v) => v.ref),
  );

  useEffect(() => {
    if (selectedRef === null) return;
    const el = document.querySelector(`[data-ref="${selectedRef}"]`);
    el?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [selectedRef]);

  return (
    <div className="mx-auto max-w-[720px] px-6 py-6">
      {surveyDraft ? (
        <div className={`survey-md ${running ? "stream-cursor" : ""}`}>
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              a: ({ href, children }) => {
                const m = href?.match(/^#ref-(\d+)$/);
                if (!m) return <a href={href}>{children}</a>;
                const n = Number(m[1]);
                const failed = failedRefs.has(n);
                return (
                  <span
                    data-ref={n}
                    className={`refchip ${failed ? "refchip-fail" : ""} ${
                      selectedRef === n ? "refchip-active" : ""
                    }`}
                    onClick={() => {
                      selectRef(n);
                      setTab("papers");
                    }}
                    title={
                      failed
                        ? "该文献 DOI 未核验通过，建议替换或补检"
                        : "定位到文献卡片"
                    }
                  >
                    {n}
                  </span>
                );
              },
            }}
          >
            {linkifyRefs(surveyDraft)}
          </ReactMarkdown>
        </div>
      ) : (
        <div className="py-24 text-center text-muted-foreground">
          {running ? "综述撰写中，内容将实时流式呈现…" : "综述尚未生成"}
        </div>
      )}
    </div>
  );
}
