import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { SchedulePlan } from "../src/api/planning";
import { PlanDiffReview } from "../src/components/planning/plan-diff-review";

function plan(version: number, paperStart: string): SchedulePlan {
  return {
    id: "plan-1",
    version,
    status: "draft",
    items: [
      { task_id: "paper", state: "placed", start_at: paperStart, end_at: paperStart.replace("09:00", "10:00") },
      { task_id: "redis", state: "placed", start_at: "2026-10-05T11:00:00Z", end_at: "2026-10-05T12:00:00Z" },
    ],
  } as SchedulePlan;
}

describe("PlanDiffReview", () => {
  it("shows only changed tasks and says when other arrangements stayed the same", () => {
    render(
      <PlanDiffReview
        previous={plan(1, "2026-10-05T09:00:00Z")}
        current={plan(2, "2026-10-05T10:00:00Z")}
        timezone="UTC"
        taskTitles={new Map([["paper", "论文"], ["redis", "Redis"]])}
      />,
    );

    expect(screen.getByText("本次调整 · 1 项")).toBeInTheDocument();
    expect(screen.getByText("论文")).toBeInTheDocument();
    expect(screen.queryByText("Redis")).not.toBeInTheDocument();
    expect(screen.getByText(/其余 1 项安排保持不变/)).toBeInTheDocument();
  });
});
