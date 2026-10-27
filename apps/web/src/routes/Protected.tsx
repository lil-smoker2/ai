/** Route guard: requires authentication; preserves the intended destination. */
import { Navigate, Outlet, useLocation } from "react-router-dom";
import type { ReactElement } from "react";
import { getToken } from "../services/api";
import { useAuth } from "../features/auth/AuthProvider";

export function Protected() {
  const location = useLocation();
  const { loading } = useAuth();

  if (!getToken()) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }
  if (loading) return <div className="page-loading">Loading…</div>;
  return <Outlet />;
}

export function PublicOnly({ children }: { children: ReactElement }) {
  if (getToken()) return <Navigate to="/app" replace />;
  return children;
}
