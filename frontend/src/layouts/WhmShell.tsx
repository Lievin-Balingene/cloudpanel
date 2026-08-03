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
  GitBranch,
  Box,
  HardDrive,
  Bell,
  Shield,
  KeyRound,
} from "lucide-react";
import { useAuthStore } from "@/stores/auth";
import { useThemeStore } from "@/stores/theme";
import { OperationProgressHost } from "@/components/OperationProgressHost";

const nav = [
  { to: "/whm", end: true, label: "Accueil WHM", icon: LayoutDashboard },
  { to: "/whm/accounts", label: "Comptes", icon: Users },
  { to: "/whm/packages", label: "Packages", icon: Package },
  { to: "/whm/domains", label: "Domaines", icon: AppWindow },
  { to: "/whm/files", label: "File Manager", icon: FolderOpen },
  { to: "/whm/ftp", label: "FTP", icon: Upload },
  { to: "/whm/email", label: "Email", icon: Mail },
  { to: "/whm/databases", label: "Bases", icon: Database },
  { to: "/whm/python", label: "Python", icon: Code2 },
  { to: "/whm/node", label: "Node.js", icon: Terminal },
  { to: "/whm/php", label: "PHP", icon: FileCode2 },
  { to: "/whm/git", label: "Git", icon: GitBranch },
  { to: "/whm/docker", label: "Docker", icon: Box },
  { to: "/whm/backups", label: "Backups", icon: HardDrive },
  { to: "/whm/monitoring", label: "Monitoring", icon: Bell },
  { to: "/whm/firewall", label: "Firewall", icon: Shield },
  { to: "/whm/security", label: "Sécurité", icon: KeyRound },
  { to: "/whm/account-security", label: "Mon 2FA", icon: KeyRound },
  { to: "/whm/dns", label: "Fonctions DNS", icon: Globe },
  { to: "/whm/resources", label: "Ressources serveur", icon: Activity },
];

export function WhmShell() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const theme = useThemeStore((s) => s.theme);
  const toggle = useThemeStore((s) => s.toggle);

  return (
    <div className="flex min-h-screen bg-cp-canvas dark:bg-surface-dark">
      <aside className="flex w-64 shrink-0 flex-col bg-cp-sidebar text-white">
        <div className="flex items-center gap-2 border-b border-white/10 bg-cp-header px-4 py-3">
          <Server className="h-5 w-5 text-white/80" />
          <div>
            <p className="text-sm font-semibold tracking-wide">V-zone WHM</p>
            <p className="text-[11px] text-white/60">Web Host Manager</p>
          </div>
        </div>
        <div className="border-b border-white/10 px-4 py-2 text-[11px] uppercase tracking-wider text-white/50">
          Navigation serveur
        </div>
        <nav className="flex-1 overflow-y-auto">
          {nav.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `whm-nav-item flex items-center gap-2 ${isActive ? "whm-nav-item-active" : ""}`
              }
            >
              <item.icon className="h-4 w-4 opacity-90" />
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-white/10 p-3 text-xs text-white/70">
          <p className="truncate font-medium text-white">{user?.username}</p>
          <p className="capitalize">{user?.role}</p>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-cp-border bg-cp-header px-4 py-2 text-white">
          <p className="text-sm">
            Serveur · <span className="font-semibold text-white">V-zone Panel</span>
          </p>
          <div className="flex items-center gap-2">
            <button type="button" className="rounded px-2 py-1 hover:bg-white/10" onClick={toggle}>
              {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </button>
            <button
              type="button"
              className="inline-flex items-center gap-1 rounded px-2 py-1 text-sm hover:bg-white/10"
              onClick={() => void logout()}
            >
              <LogOut className="h-4 w-4" />
              Quitter
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
