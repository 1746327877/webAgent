import { render, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import type { MessageItemData } from "@/api/sessions";

const mocks = vi.hoisted(() => ({ scrollToIndex: vi.fn() }));

vi.mock("react-virtuoso", async () => {
  const React = await import("react");
  const Virtuoso = React.forwardRef((props: any, ref: any) => {
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
});

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
