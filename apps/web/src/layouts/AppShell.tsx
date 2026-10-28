/** Application shell: desktop sidebar, mobile bottom nav + More sheet. */
import { useState, type CSSProperties } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  BarChart3,
  Bot,
  Gem,
  GraduationCap,
  Home,
  Images,
  ListChecks,
  LogOut,
  Bell,
  Package,
  PiggyBank,
  Settings,
  ShoppingBag,
  Target,
  User,
  Wallet,
  Menu,
  X,
} from "lucide-react";
import { useAuth } from "../features/auth/AuthProvider";
import { backgroundForPath } from "../lib/backgrounds";
import { api } from "../services/api";
import type { AlertsResponse } from "../types/api";

const NAV_ITEMS = [
  { to: "/app", label: "Home", icon: Home, end: true },
  { to: "/app/inventory", label: "Inventory", icon: Package },
  { to: "/app/images", label: "Images", icon: Images },
  { to: "/app/shopping", label: "Shopping", icon: ShoppingBag },
  { to: "/app/money", label: "Money", icon: Wallet },
  { to: "/app/networth", label: "Net worth", icon: Gem },
  { to: "/app/earnings-savings", label: "Savings & Earnings", icon: PiggyBank },
  { to: "/app/goals", label: "Goals & Priorities", icon: Target },
  { to: "/app/tasks", label: "Tasks & Reminders", icon: ListChecks },
  { to: "/app/student", label: "Student Life", icon: GraduationCap },
  { to: "/app/assistant", label: "AI Assistant", icon: Bot },
  { to: "/app/reports", label: "Reports", icon: BarChart3 },
  { to: "/app/notifications", label: "Notifications", icon: Bell },
  { to: "/app/settings", label: "Settings", icon: Settings },
];

// Mobile primary bar per spec; everything else goes in More. Resolved by path
// so inserting a nav item cannot silently move the tabs.
const MOBILE_PRIMARY_PATHS = ["/app", "/app/goals", "/app/shopping", "/app/money"];
const MOBILE_PRIMARY = MOBILE_PRIMARY_PATHS.map(
  (to) => NAV_ITEMS.find((item) => item.to === to) ?? NAV_ITEMS[0],
);
const MOBILE_MORE = NAV_ITEMS.filter((item) => !MOBILE_PRIMARY.includes(item));

// The one nav item that carries a count. Compared by path, not label, so
// renaming the label cannot silently move the badge.
const ALERTS_PATH = "/app/notifications";

export function AppShell() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [moreOpen, setMoreOpen] = useState(false);

  // The picture changes with the section; --page-bg is read by .shell in
  // styles.css, which layers a wash over it.
  const shellStyle = { "--page-bg": `url(${backgroundForPath(pathname)})` } as CSSProperties;

  // How many things the app's own records say need attention right now. Quiet
  // hours hide the number, not the list: nothing here interrupts the user, so
  // the only honest thing quiet hours can do is stop badging the sidebar.
  const alerts = useQuery({
    queryKey: ["notification-alerts"],
    queryFn: () => api<AlertsResponse>("/api/notifications/alerts"),
    staleTime: 60_000,
  });
  const alertCount =
    alerts.data && !alerts.data.in_quiet_hours && alerts.data.count > 0 ? alerts.data.count : null;

  const badgeFor = (to: string) =>
    to === ALERTS_PATH && alertCount !== null ? (
      <span className="nav-badge">{alertCount}</span>
    ) : null;

  const signOut = () => {
    logout();
    navigate("/login");
  };

  return (
    <div className="shell" style={shellStyle}>
      <aside className="sidebar">
        <div className="brand">LifeSmart</div>
        <nav aria-label="Main navigation">
          {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
            >
              <Icon size={18} aria-hidden />
              <span>{label}</span>
              {badgeFor(to)}
            </NavLink>
          ))}
        </nav>
        <button className="nav-link sign-out" onClick={signOut}>
          <LogOut size={18} aria-hidden />
          <span>Sign out</span>
        </button>
      </aside>

      <div className="main-area">
        <header className="topbar">
          <span className="topbar-user" title={user?.email}>
            <User size={16} aria-hidden /> {user?.full_name ?? "…"}
          </span>
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>

      <nav className="bottom-nav" aria-label="Mobile navigation">
        {MOBILE_PRIMARY.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) => (isActive ? "tab active" : "tab")}
          >
            <Icon size={20} aria-hidden />
            <span>{label}</span>
          </NavLink>
        ))}
        <button className="tab" onClick={() => setMoreOpen(true)} aria-label="More">
          <Menu size={20} aria-hidden />
          <span>More</span>
        </button>
      </nav>

      {moreOpen && (
        <div className="more-sheet-backdrop" onClick={() => setMoreOpen(false)}>
          <div
            className="more-sheet"
            role="dialog"
            aria-label="More navigation"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="more-sheet-header">
              <strong>More</strong>
              <button aria-label="Close menu" onClick={() => setMoreOpen(false)}>
                <X size={20} />
              </button>
            </div>
            {MOBILE_MORE.map(({ to, label, icon: Icon }) => (
              <NavLink key={to} to={to} className="nav-link" onClick={() => setMoreOpen(false)}>
                <Icon size={18} aria-hidden />
                <span>{label}</span>
                {badgeFor(to)}
              </NavLink>
            ))}
            <button className="nav-link sign-out" onClick={signOut}>
              <LogOut size={18} aria-hidden />
              <span>Sign out</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
