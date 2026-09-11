import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, test, vi } from "vitest";
import LoginPage from "@/pages/LoginPage";
import { useAuthStore } from "@/stores/auth";

beforeEach(() => {
  useAuthStore.getState().clear();
});

test("登录成功后写入 access token", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ access_token: "tk_123", token_type: "bearer" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    ),
  );
  render(
    <MemoryRouter>
      <LoginPage />
    </MemoryRouter>,
  );
  await userEvent.type(screen.getByLabelText("用户名"), "alice");
  await userEvent.type(screen.getByLabelText("密码"), "Passw0rd!");
  await userEvent.click(screen.getByRole("button", { name: "登录" }));
  expect(useAuthStore.getState().accessToken).toBe("tk_123");
  vi.unstubAllGlobals();
});
