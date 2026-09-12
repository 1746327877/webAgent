import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  keys: [] as unknown[],
  created: null as unknown,
  createArgs: [] as string[],
  revokeArgs: [] as string[],
  createError: null as unknown,
  revokeError: null as unknown,
  revokePending: false,
}));

vi.mock("@/api/keys", () => ({
  useApiKeys: () => ({ data: mocks.keys, isLoading: false, error: null }),
  useCreateApiKey: () => ({
    mutateAsync: async (name: string) => {
      mocks.createArgs.push(name);
      if (mocks.createError) throw mocks.createError;
      return mocks.created;
    },
    isPending: false,
  }),
  useRevokeApiKey: () => ({
    mutateAsync: async (id: string) => {
      mocks.revokeArgs.push(id);
      if (mocks.revokeError) throw mocks.revokeError;
    },
    isPending: mocks.revokePending,
  }),
}));

import KeysPage from "@/pages/KeysPage";

beforeEach(() => {
  mocks.keys = [];
  mocks.created = null;
  mocks.createArgs = [];
  mocks.revokeArgs = [];
  mocks.createError = null;
  mocks.revokeError = null;
  mocks.revokePending = false;
});

test("展示已有密钥的前缀与吊销状态", () => {
  mocks.keys = [
    {
      id: "k1",
      name: "脚本",
      key_prefix: "sk-AbCd1234",
      last_used_at: null,
      revoked: false,
      created_at: null,
    },
  ];
  render(<KeysPage />);
  expect(screen.getByText("脚本")).toBeInTheDocument();
  expect(screen.getByText("sk-AbCd1234…")).toBeInTheDocument();
});

test("创建后明文一次性展示", async () => {
  mocks.created = {
    id: "k2",
    name: "新密钥",
    key_prefix: "sk-New",
    last_used_at: null,
    revoked: false,
    created_at: null,
    key: "sk-plaintext-secret",
  };
  render(<KeysPage />);
  await userEvent.type(screen.getByLabelText("密钥名称"), "新密钥");
  await userEvent.click(screen.getByRole("button", { name: "创建" }));
  expect(await screen.findByText("sk-plaintext-secret")).toBeInTheDocument();
  expect(mocks.createArgs).toEqual(["新密钥"]);
});

test("吊销按钮确认后调用撤销", async () => {
  mocks.keys = [
    {
      id: "k1",
      name: "脚本",
      key_prefix: "sk-AbCd1234",
      last_used_at: null,
      revoked: false,
      created_at: null,
    },
  ];
  vi.spyOn(window, "confirm").mockReturnValue(true);
  render(<KeysPage />);
  await userEvent.click(screen.getByRole("button", { name: "吊销" }));
  await waitFor(() => expect(mocks.revokeArgs).toEqual(["k1"]));
});

test("创建失败时展示错误且不展示明文", async () => {
  mocks.createError = new Error("HTTP 500");
  render(<KeysPage />);
  await userEvent.type(screen.getByLabelText("密钥名称"), "新密钥");
  await userEvent.click(screen.getByRole("button", { name: "创建" }));
  expect(await screen.findByText("HTTP 500")).toBeInTheDocument();
  expect(screen.queryByText("明文仅此一次展示，请立即复制保存。")).not.toBeInTheDocument();
  expect(mocks.createArgs).toEqual(["新密钥"]);
});

test("吊销失败时展示错误", async () => {
  mocks.keys = [
    {
      id: "k1",
      name: "脚本",
      key_prefix: "sk-AbCd1234",
      last_used_at: null,
      revoked: false,
      created_at: null,
    },
  ];
  mocks.revokeError = new Error("HTTP 500");
  vi.spyOn(window, "confirm").mockReturnValue(true);
  render(<KeysPage />);
  await userEvent.click(screen.getByRole("button", { name: "吊销" }));
  expect(await screen.findByText("HTTP 500")).toBeInTheDocument();
  await waitFor(() => expect(mocks.revokeArgs).toEqual(["k1"]));
});

test("吊销进行中按钮禁用，避免重复请求", () => {
  mocks.keys = [
    {
      id: "k1",
      name: "脚本",
      key_prefix: "sk-AbCd1234",
      last_used_at: null,
      revoked: false,
      created_at: null,
    },
  ];
  mocks.revokePending = true;
  render(<KeysPage />);
  expect(screen.getByRole("button", { name: "吊销" })).toBeDisabled();
});
