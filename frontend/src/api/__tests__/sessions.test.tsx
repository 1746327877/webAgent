import { renderHook } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { expect, test, vi } from "vitest";
import type { ReactNode } from "react";

const mocks = vi.hoisted(() => ({ apiJson: vi.fn() }));

vi.mock("@/lib/api", () => ({
  apiJson: mocks.apiJson,
  apiFetch: vi.fn(),
}));

import { BULK_DELETE_CHUNK, useBulkDeleteSessions } from "@/api/sessions";

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

test("超过单请求上限时分批删除并汇总删除条数", async () => {
  const { result } = renderHook(() => useBulkDeleteSessions(), { wrapper });
  const ids = Array.from({ length: BULK_DELETE_CHUNK + 5 }, (_, i) => `id-${i}`);
  mocks.apiJson
    .mockResolvedValueOnce({ deleted: BULK_DELETE_CHUNK })
    .mockResolvedValueOnce({ deleted: 5 });

  const res = await result.current.mutateAsync(ids);

  expect(mocks.apiJson).toHaveBeenCalledTimes(2);
  expect(res).toEqual({ deleted: BULK_DELETE_CHUNK + 5 });
  const firstBody = JSON.parse(mocks.apiJson.mock.calls[0][1].body);
  const secondBody = JSON.parse(mocks.apiJson.mock.calls[1][1].body);
  expect(firstBody.ids).toHaveLength(BULK_DELETE_CHUNK);
  expect(secondBody.ids).toHaveLength(5);
});

test("未超过上限时只发一次请求", async () => {
  mocks.apiJson.mockReset();
  mocks.apiJson.mockResolvedValueOnce({ deleted: 2 });
  const { result } = renderHook(() => useBulkDeleteSessions(), { wrapper });

  const res = await result.current.mutateAsync(["a", "b"]);

  expect(mocks.apiJson).toHaveBeenCalledTimes(1);
  expect(res).toEqual({ deleted: 2 });
});
