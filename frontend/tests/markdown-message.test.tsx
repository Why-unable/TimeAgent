import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MarkdownMessage } from "../src/components/chat/markdown-message";

describe("MarkdownMessage", () => {
  it("renders GitHub-flavored tables and inline formatting", () => {
    render(
      <MarkdownMessage
        content={[
          "已为你设置好提醒 ✅",
          "",
          "| 项目 | 内容 |",
          "| --- | --- |",
          "| **提醒内容** | 吃早餐 |",
          "| **状态** | 已就绪 |",
        ].join("\n")}
      />,
    );

    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "项目" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "提醒内容" }).querySelector("strong")).not.toBeNull();
    expect(screen.getByText("已为你设置好提醒 ✅")).toBeInTheDocument();
  });

  it("does not render raw HTML from model output", () => {
    const { container } = render(
      <MarkdownMessage content={'<img src="x" onerror="alert(1)">安全文本'} />,
    );

    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
  });
});
