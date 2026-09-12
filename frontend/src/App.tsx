import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import LoginPage from "@/pages/LoginPage";
import RegisterPage from "@/pages/RegisterPage";
import ChatPage from "@/pages/ChatPage";
import AgentsPage from "@/pages/AgentsPage";
import AgentEditorPage from "@/pages/AgentEditorPage";
import KbPage from "@/pages/KbPage";
import KbDetailPage from "@/pages/KbDetailPage";
import RequireAuth from "@/components/RequireAuth";
import ChatView from "@/components/chat/ChatView";
import AdminTracePage from "@/pages/AdminTracePage";

// echarts 体积大，仪表盘按路由懒加载，避免进入首屏 entry chunk
const AdminDashboardPage = lazy(() => import("@/pages/AdminDashboardPage"));

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route
          path="/"
          element={
            <RequireAuth>
              <ChatPage />
            </RequireAuth>
          }
        >
          <Route index element={<ChatView />} />
          <Route path="sessions/:sessionId" element={<ChatView />} />
          <Route path="agents" element={<AgentsPage />} />
          <Route path="agents/new" element={<AgentEditorPage />} />
          <Route path="agents/:agentId" element={<AgentEditorPage />} />
          <Route path="kb" element={<KbPage />} />
          <Route path="kb/:kbId" element={<KbDetailPage />} />
          <Route
            path="admin"
            element={
              <Suspense
                fallback={<div className="flex-1 p-6 text-sm text-muted-foreground">加载中…</div>}
              >
                <AdminDashboardPage />
              </Suspense>
            }
          />
          <Route path="admin/sessions/:sessionId" element={<AdminTracePage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
