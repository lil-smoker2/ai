/** Route map - matches the spec navigation. Unbuilt modules resolve to an
 * honest placeholder rather than fabricated functionality. */
import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./layouts/AppShell";
import { Protected, PublicOnly } from "./routes/Protected";
import { useAuth } from "./features/auth/AuthProvider";
import { Welcome } from "./pages/Welcome";
import { Login } from "./pages/Login";
import { Register } from "./pages/Register";
import { Onboarding } from "./pages/Onboarding";
import { Dashboard } from "./pages/Dashboard";
import { InventoryPage } from "./pages/InventoryPage";
import { ImagesPage } from "./pages/ImagesPage";
import { NetWorthPage } from "./pages/NetWorthPage";
import { MoneyPage } from "./pages/MoneyPage";
import { GoalsPage } from "./pages/GoalsPage";
import { ShoppingPage } from "./pages/ShoppingPage";
import { EarningsPage } from "./pages/EarningsPage";
import { TasksPage } from "./pages/TasksPage";
import { StudentPage } from "./pages/StudentPage";
import { NotificationsPage } from "./pages/NotificationsPage";
import { AssistantPage } from "./pages/AssistantPage";
import { ReportsPage } from "./pages/ReportsPage";
import { UnderConstruction } from "./pages/UnderConstruction";

/** Entry route. In local single-user mode the app auto-signs-in, so wait for
 * that and then go straight to the dashboard; only fall back to the Welcome /
 * login screen when there is genuinely no session (hosted deployments). */
function Root() {
  const { user, loading } = useAuth();
  if (loading) return <div className="page-loading">Loading…</div>;
  if (user) return <Navigate to="/app" replace />;
  return <Welcome />;
}

export function App() {
  return (
    <Routes>
      <Route path="/" element={<Root />} />
      <Route path="/login" element={<PublicOnly><Login /></PublicOnly>} />
      <Route path="/register" element={<PublicOnly><Register /></PublicOnly>} />

      <Route path="/app" element={<Protected />}>
        <Route element={<AppShell />}>
          <Route index element={<Dashboard />} />
          <Route path="onboarding" element={<Onboarding />} />
          <Route path="inventory" element={<InventoryPage />} />
          <Route path="images" element={<ImagesPage />} />
          <Route path="networth" element={<NetWorthPage />} />
          <Route path="money" element={<MoneyPage />} />
          <Route path="goals" element={<GoalsPage />} />
          <Route path="shopping" element={<ShoppingPage />} />
          <Route path="earnings-savings" element={<EarningsPage />} />
          <Route path="reports" element={<ReportsPage />} />
          <Route path="tasks" element={<TasksPage />} />
          <Route path="student" element={<StudentPage />} />
          <Route
            path="notifications"
            element={<NotificationsPage />}
          />
          <Route path="assistant" element={<AssistantPage />} />
          <Route
            path="settings"
            element={
              <UnderConstruction
                title="Settings"
                milestone={6}
                detail="Profile editing, currency/timezone preferences, export and account management arrive in Milestone 6."
              />
            }
          />
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/app" replace />} />
    </Routes>
  );
}
