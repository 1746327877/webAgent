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
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
