import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { Drawer } from "../src/components/overlay/drawer";

const nativeBack = vi.hoisted(() => ({
  callback: null as null | (() => void),
  remove: vi.fn(async () => undefined),
  emit: (() => undefined) as () => void,
}));

vi.mock("../src/platform", () => ({ isNativePlatform: () => true }));
vi.mock("@capacitor/app", () => ({
  App: {
    addListener: vi.fn(async (_event: string, callback: () => void) => {
      nativeBack.callback = callback;
      nativeBack.emit = () => nativeBack.callback?.();
      return { remove: nativeBack.remove };
    }),
  },
}));

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

  it("closes the topmost drawer on native Android Back and removes its listener", async () => {
    nativeBack.callback = null;
    nativeBack.remove.mockClear();
    const user = userEvent.setup();
    render(<DrawerHarness />);
    await user.click(screen.getByRole("button", { name: "打开任务编辑" }));
    await waitFor(() => expect(nativeBack.callback).toBeTypeOf("function"));

    nativeBack.emit();

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(nativeBack.remove).toHaveBeenCalledOnce();
  });
});
