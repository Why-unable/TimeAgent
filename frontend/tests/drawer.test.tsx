import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { Drawer } from "../src/components/overlay/drawer";

function DrawerHarness() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>打开任务编辑</button>
      {open && (
        <Drawer title="编辑任务" onClose={() => setOpen(false)}>
          <label>
            任务标题
            <input />
          </label>
          <button type="button">保存</button>
        </Drawer>
      )}
    </>
  );
}

describe("Drawer", () => {
  it("enters and contains keyboard focus, closes on Escape, and restores focus", async () => {
    const user = userEvent.setup();
    render(<DrawerHarness />);
    const trigger = screen.getByRole("button", { name: "打开任务编辑" });
    await user.click(trigger);

    const dialog = screen.getByRole("dialog", { name: "编辑任务" });
    expect(dialog).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("button", { name: "关闭" })).toHaveFocus();
    await user.tab({ shift: true });
    expect(screen.getByRole("button", { name: "保存" })).toHaveFocus();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });
});
