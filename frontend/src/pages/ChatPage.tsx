import { Outlet } from "react-router-dom";
import SessionSidebar from "@/components/sidebar/SessionSidebar";

export default function ChatPage() {
  return (
    <div className="flex h-screen">
      <SessionSidebar />
      <main className="flex min-w-0 flex-1 flex-col">
        <Outlet />
      </main>
    </div>
  );
}
