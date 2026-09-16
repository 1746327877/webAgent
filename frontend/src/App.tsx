import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import LoginPage from "@/pages/LoginPage";
import RegisterPage from "@/pages/RegisterPage";
import ChatPage from "@/pages/ChatPage";
import AgentsPage from "@/pages/AgentsPage";
import AgentEditorPage from "@/pages/AgentEditorPage";
import KbPage from "@/pages/KbPage";
import KbDetailPage from "@/pages/KbDetailPage";
import KeysPage from "@/pages/KeysPage";
import CapabilitiesPage from "@/pages/CapabilitiesPage";
import RequireAuth from "@/components/RequireAuth";
import Toaster from "@/components/ui/toaster";
import ChatView from "@/components/chat/ChatView";
import AdminTracePage from "@/pages/AdminTracePage";

// echarts 体积大，仪表盘按路由懒加载，避免进入首屏 entry chunk
const AdminPage = lazy(() => import("@/pages/AdminPage"));

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
          <Route path="keys" element={<KeysPage />} />
          <Route path="capabilities" element={<CapabilitiesPage />} />
          <Route
            path="admin"
            element={
              <Suspense
                fallback={<div className="flex-1 p-6 text-sm text-muted-foreground">加载中…</div>}
              >
                <AdminPage />
              </Suspense>
            }
          />
          <Route path="admin/sessions/:sessionId" element={<AdminTracePage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <Toaster />
    </BrowserRouter>
  );
}
