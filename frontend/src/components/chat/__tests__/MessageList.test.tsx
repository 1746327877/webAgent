import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import type { MessageItemData } from "@/api/sessions";

const mocks = vi.hoisted(() => ({
  scrollToIndex: vi.fn(),
  captured: vi.fn(),
}));

vi.mock("react-virtuoso", async () => {
  const React = await import("react");
  const Virtuoso = React.forwardRef((props: any, ref: any) => {
    mocks.captured(props);
    React.useImperativeHandle(ref, () => ({ scrollToIndex: mocks.scrollToIndex }));
    return (
      <div>
        {props.data.map((item: MessageItemData, index: number) => (
          <div key={item.id}>{props.itemContent(index, item)}</div>
        ))}
      </div>
    );
  });
  Virtuoso.displayName = "VirtuosoMock";
  return { Virtuoso };
});

import MessageList from "@/components/chat/MessageList";

function makeMessage(id: string, content: string): MessageItemData {
  return {
    id,
    role: "user",
    blocks: [{ type: "text", content }],
    status: "done",
    rating: null,
    error: null,
    created_at: "2026-09-16T10:00:00Z",
  };
}

function renderList(items: MessageItemData[], sessionKey = "s1") {
  return render(
    <MessageList items={items} sessionKey={sessionKey} renderActions={() => null} />,
  );
}

beforeEach(() => {
  mocks.scrollToIndex.mockClear();
  mocks.captured.mockClear();
});

/** 最近一次渲染传给 Virtuoso 的 props */
function lastVirtuosoProps(): Record<string, unknown> {
  const calls = mocks.captured.mock.calls;
  return (calls[calls.length - 1]?.[0] ?? {}) as Record<string, unknown>;
}

test("进入会话（有历史消息）后自动跳到最底部", async () => {
  const items = [makeMessage("m1", "一"), makeMessage("m2", "二"), makeMessage("m3", "三")];
  renderList(items);

  await waitFor(() =>
    expect(mocks.scrollToIndex).toHaveBeenCalledWith({ index: "LAST", align: "end" }),
  );
  expect(mocks.scrollToIndex).toHaveBeenCalledTimes(1);
});

test("空会话不触发置底；流式追加消息也不重复置底", async () => {
  const { rerender } = renderList([]);
  expect(mocks.scrollToIndex).not.toHaveBeenCalled();

  rerender(
    <MessageList
      items={[makeMessage("m1", "一")]}
      sessionKey="s1"
      renderActions={() => null}
    />,
  );
  await waitFor(() => expect(mocks.scrollToIndex).toHaveBeenCalledTimes(1));

  // 同一会话内流式追加：不再重复跳（交给 followOutput）
  rerender(
    <MessageList
      items={[makeMessage("m1", "一"), makeMessage("m2", "二")]}
      sessionKey="s1"
      renderActions={() => null}
    />,
  );
  await waitFor(() => expect(mocks.scrollToIndex).toHaveBeenCalledTimes(1));
});

test("流式跟随用即时滚动（非 smooth），且短内容贴底", () => {
  renderList([makeMessage("m1", "一")]);
  const props = lastVirtuosoProps();
  expect(props.followOutput).toBe("auto");
  expect(props.alignToBottom).toBe(true);
});

test("切换会话后重新置底", async () => {
  const { rerender } = renderList([makeMessage("m1", "一")], "s1");
  await waitFor(() => expect(mocks.scrollToIndex).toHaveBeenCalledTimes(1));

  rerender(
    <MessageList
      items={[makeMessage("m2", "二")]}
      sessionKey="s2"
      renderActions={() => null}
    />,
  );
  await waitFor(() => expect(mocks.scrollToIndex).toHaveBeenCalledTimes(2));
});

test("离开底部时出现「跳到最新」，点击平滑滚到底；回到底部后隐藏", async () => {
  renderList([makeMessage("m1", "一"), makeMessage("m2", "二")]);

  // 初始按"在底部"处理：不该闪出按钮
  expect(screen.queryByRole("button", { name: "跳到最新" })).not.toBeInTheDocument();

  // 模拟 Virtuoso 上报"已离开底部"
  act(() => {
    (lastVirtuosoProps().atBottomStateChange as (value: boolean) => void)(false);
  });
  const button = screen.getByRole("button", { name: "跳到最新" });

  mocks.scrollToIndex.mockClear();
  fireEvent.click(button);
  expect(mocks.scrollToIndex).toHaveBeenCalledWith({
    index: "LAST",
    align: "end",
    behavior: "smooth",
  });

  // 回到底部后按钮消失
  act(() => {
    (lastVirtuosoProps().atBottomStateChange as (value: boolean) => void)(true);
  });
  expect(screen.queryByRole("button", { name: "跳到最新" })).not.toBeInTheDocument();
});

test("空会话不显示「跳到最新」", () => {
  renderList([]);
  act(() => {
    (lastVirtuosoProps().atBottomStateChange as (value: boolean) => void)(false);
  });
  expect(screen.queryByRole("button", { name: "跳到最新" })).not.toBeInTheDocument();
});

test("消息列与输入框同宽（不再额外居中收窄），纵向更紧凑", () => {
  renderList([makeMessage("m1", "一")]);
  const wrapper = screen.getByText("一").closest("div.px-4");
  expect(wrapper).not.toBeNull();
  expect(wrapper).toHaveClass("py-1.5");
  // 不要 mx-auto + max-w-* 那种"居中收窄"，否则宽屏下会明显窄于输入框
  expect(wrapper).not.toHaveClass("mx-auto");
  expect(wrapper?.className).not.toMatch(/max-w-/);
});
