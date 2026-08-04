import { NavLink, Outlet } from "react-router-dom";
import {
  LayoutDashboard,
  Users,
  Package,
  Globe,
  Activity,
  LogOut,
  Moon,
  Sun,
  Server,
  AppWindow,
  FolderOpen,
  Upload,
  Mail,
  Database,
  Code2,
  Terminal,
  FileCode2,
  LayoutTemplate,
  Network,
  GitBranch,
  Box,
  HardDrive,
  Bell,
  Shield,
  KeyRound,
  ArrowRightLeft,
  UserPlus,
} from "lucide-react";
import { useAuthStore } from "@/stores/auth";
import { useThemeStore } from "@/stores/theme";
import { OperationProgressHost } from "@/components/OperationProgressHost";

const navSections = [
  {
    title: "Favorites",
    items: [
      { to: "/whm", end: true, label: "Home", icon: LayoutDashboard },
      { to: "/whm/accounts/create", label: "Create a New Account", icon: UserPlus },
      { to: "/whm/accounts", label: "List Accounts", icon: Users },
      { to: "/whm/server-setup", label: "Basic WebHost Manager Setup", icon: Server },
    ],
  },
  {
    title: "Account Functions",
    items: [
      { to: "/whm/transfer", label: "Transfer Tool", icon: ArrowRightLeft },
      { to: "/whm/packages", label: "Packages", icon: Package },
      { to: "/whm/domains", label: "Domains", icon: AppWindow },
      { to: "/whm/dns", label: "DNS Functions", icon: Globe },
    ],
  },
  {
    title: "Service Configuration",
    items: [
      { to: "/whm/email", label: "Email", icon: Mail },
      { to: "/whm/databases", label: "Databases", icon: Database },
      { to: "/whm/ftp", label: "FTP", icon: Upload },
      { to: "/whm/files", label: "File Manager", icon: FolderOpen },
    ],
  },
  {
    title: "Software",
    items: [
      { to: "/whm/python", label: "Setup Python App", icon: Code2 },
      { to: "/whm/node", label: "Setup Node.js App", icon: Terminal },
      { to: "/whm/php", label: "MultiPHP Manager", icon: FileCode2 },
      { to: "/whm/wordpress", label: "WordPress", icon: LayoutTemplate },
      { to: "/whm/git", label: "Git Version Control", icon: GitBranch },
    ],
  },
  {
    title: "Server",
    items: [
      { to: "/whm/terminal", label: "Terminal", icon: Terminal },
      { to: "/whm/docker", label: "Docker", icon: Box },
      { to: "/whm/kubernetes", label: "Kubernetes", icon: Network },
      { to: "/whm/backups", label: "Backup", icon: HardDrive },
      { to: "/whm/monitoring", label: "Service Status", icon: Bell },
      { to: "/whm/resources", label: "Server Information", icon: Activity },
      { to: "/whm/firewall", label: "Firewall", icon: Shield },
      { to: "/whm/security", label: "Security Center", icon: KeyRound },
      { to: "/whm/account-security", label: "Two-Factor Auth", icon: KeyRound },
    ],
  },
];

export function WhmShell() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const theme = useThemeStore((s) => s.theme);
  const toggle = useThemeStore((s) => s.toggle);

  return (
    <div className="flex min-h-screen bg-cp-canvas dark:bg-surface-dark">
      <aside className="flex w-[260px] shrink-0 flex-col bg-cp-sidebar text-white shadow-[4px_0_24px_rgba(0,0,0,0.18)]">
        <div className="flex items-center gap-3 border-b border-white/10 bg-cp-header px-4 py-3.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-md bg-cp-orange text-sm font-bold text-white shadow">
            VZ
          </div>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold tracking-wide">V-zone WHM</p>
            <p className="text-[10px] uppercase tracking-wider text-white/50">Web Host Manager</p>
          </div>
        </div>
        <nav className="flex-1 overflow-y-auto pb-4">
          {navSections.map((section) => (
            <div key={section.title}>
              <p className="whm-section-title">{section.title}</p>
              {section.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) =>
                    `whm-nav-item ${isActive ? "whm-nav-item-active" : ""}`
                  }
                >
                  <item.icon className="h-4 w-4 shrink-0 opacity-90" />
                  <span className="truncate">{item.label}</span>
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="border-t border-white/10 bg-cp-header/80 p-3 text-xs text-white/70">
          <p className="truncate font-medium text-white">{user?.username}</p>
          <p className="capitalize text-white/50">{user?.role}</p>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-black/20 bg-cp-header px-4 py-2.5 text-white shadow">
          <div className="flex items-center gap-3">
            <span className="rounded bg-cp-orange px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide">
              WHM
            </span>
            <p className="text-sm text-white/90">
              Hostname tools · <span className="font-semibold text-white">V-zone Panel</span>
            </p>
          </div>
          <div className="flex items-center gap-1">
            <button
              type="button"
              className="rounded-md px-2.5 py-1.5 text-white/80 hover:bg-white/10 hover:text-white"
              onClick={toggle}
              title="Theme"
            >
              {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </button>
            <button
              type="button"
              className="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-sm text-white/90 hover:bg-white/10"
              onClick={() => void logout()}
            >
              <LogOut className="h-4 w-4" />
              Logout
            </button>
          </div>
        </header>
        <main className="flex-1 p-4 md:p-6">
          <Outlet />
        </main>
      </div>
      <OperationProgressHost />
    </div>
  );
}
