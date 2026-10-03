import { useMemo } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, BookOpenText, Sun } from "lucide-react";

import { useBriefingRuns, useLaunchBriefing } from "../../features/briefings/hooks";

export function MorningBrief({ targetDate }: { targetDate: string }) {
  const runs = useBriefingRuns();
  const launch = useLaunchBriefing();
  const navigate = useNavigate();
  const todayRun = useMemo(
    () => (Array.isArray(runs.data) ? runs.data.find((run) => run.target_date === targetDate) : null) ?? null,
    [runs.data, targetDate],
  );
  const preview = todayRun?.rendered_markdown
    .split("\n")
    .map((line) => line.trim().replace(/^#{1,6}\s+/, "").replace(/^[-*]\s+/, ""))
    .filter(Boolean)
    .slice(0, 2)
    .join(" ")
    .slice(0, 320);

  const launchBriefing = () => {
    launch.mutate({ definitionId: null, targetDate }, {
      onSuccess: ({ conversation }) => navigate(`/chat/${conversation.id}`),
    });
  };

  return (
    <section aria-label="晨间简报" className="mt-5 flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-orange-200/20 bg-gradient-to-r from-orange-200/[0.08] via-slate-900 to-amber-100/[0.04] p-4">
      <div className="flex min-w-0 items-start gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-orange-200/10 text-orange-100">
          <Sun size={19} aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <h2 className="text-sm font-semibold text-orange-50">晨间简报</h2>
          {todayRun ? (
            <p className="mt-1 text-sm text-slate-300">
              {todayRun.status === "completed" ? "今日日程简报已准备好。" :
                todayRun.status === "partial" ? "今日日程简报已部分完成，可查看可用内容。" :
                  todayRun.status === "failed" ? "今日日程简报生成失败，可以重新查看或稍后再试。" :
                    "今日日程简报正在准备中。"}
            </p>
          ) : (
            <p className="mt-1 text-sm text-slate-400">按需汇总今天的日程、任务和已启用的简报内容。</p>
          )}
          {preview && <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-200">{preview}</p>}
          {runs.isError && <p role="status" className="mt-1 text-xs text-slate-500">暂时无法读取简报状态。</p>}
          {launch.isError && <p role="alert" className="mt-1 text-xs text-rose-200">简报没有启动，请稍后重试。</p>}
        </div>
      </div>
      {todayRun ? (
        <Link to={todayRun.conversation_id ? `/chat/${todayRun.conversation_id}` : "/briefings"} className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-orange-100/20 px-4 text-sm font-medium text-orange-50 hover:bg-orange-100/5">
          <BookOpenText size={16} /> 查看简报 <ArrowRight size={15} />
        </Link>
      ) : (
        <button type="button" onClick={launchBriefing} disabled={launch.isPending} className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-orange-100 px-4 text-sm font-semibold text-slate-950 hover:bg-white disabled:opacity-60">
          <BookOpenText size={16} /> {launch.isPending ? "正在准备…" : "生成今日日程简报"}
        </button>
      )}
    </section>
  );
}
