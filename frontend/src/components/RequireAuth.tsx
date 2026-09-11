import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { bootstrapAuth } from "@/lib/api";
import { useAuthStore } from "@/stores/auth";

export default function RequireAuth({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.accessToken);
  const [checking, setChecking] = useState(!token);

  useEffect(() => {
    if (!token) bootstrapAuth().finally(() => setChecking(false));
  }, [token]);

  if (checking) return <div className="p-8 text-muted-foreground">加载中…</div>;
  if (!token) return <Navigate to="/login" replace />;
  return <>{children}</>;
}
