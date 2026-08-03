import { NavLink, Outlet } from "react-router-dom";
import {
  Home,
  Globe,
  Package,
  LogOut,
  Moon,
  Sun,
  LayoutGrid,
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
  KeyRound,
} from "lucide-react";
import { useAuthStore } from "@/stores/auth";
import { useThemeStore } from "@/stores/theme";

const nav = [
  { to: "/panel", end: true, label: "Accueil", icon: Home },
  { to: "/panel/domains", label: "Domains", icon: AppWindow },
  { to: "/panel/files", label: "File Manager", icon: FolderOpen },
  { to: "/panel/ftp", label: "FTP", icon: Upload },
  { to: "/panel/email", label: "Email", icon: Mail },
  { to: "/panel/databases", label: "Databases", icon: Database },
  { to: "/panel/python", label: "Python", icon: Code2 },
  { to: "/panel/node", label: "Node.js", icon: Terminal },
  { to: "/panel/php", label: "PHP", icon: FileCode2 },
  { to: "/panel/git", label: "Git", icon: GitBranch },
  { to: "/panel/docker", label: "Docker", icon: Box },
  { to: "/panel/backups", label: "Backups", icon: HardDrive },
  { to: "/panel/security", label: "Sécurité", icon: KeyRound },
  { to: "/panel/dns", label: "Zone Editor", icon: Globe },
  { to: "/panel/package", label: "Mon package", icon: Package },
];

export function ClientShell() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const theme = useThemeStore((s) => s.theme);
  const toggle = useThemeStore((s) => s.toggle);

  return (
    <div className="min-h-screen bg-cp-canvas dark:bg-surface-dark">
      <header className="border-b border-cp-border bg-white dark:border-ink-800 dark:bg-ink-950">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
          <div className="flex items-center gap-2">
            <div className="flex h-9 w-9 items-center justify-center rounded bg-cp-orange text-white">
              <LayoutGrid className="h-5 w-5" />
            </div>
            <div>
              <p className="text-sm font-semibold text-cp-text dark:text-ink-50">V-zone Panel</p>
              <p className="text-xs text-cp-muted">Espace client · {user?.username}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button type="button" className="vz-btn-ghost" onClick={toggle}>
              {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </button>
            <button type="button" className="vz-btn-ghost" onClick={() => void logout()}>
              <LogOut className="h-4 w-4" />
              Quitter
            </button>
          </div>
        </div>
        <nav className="border-t border-cp-border bg-cp-orange-soft dark:border-ink-800 dark:bg-ink-900">
          <div className="mx-auto flex max-w-6xl gap-1 overflow-x-auto px-2">
            {nav.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `inline-flex shrink-0 items-center gap-1.5 px-3 py-2.5 text-sm ${
                    isActive
                      ? "border-b-2 border-cp-orange font-semibold text-cp-orange-dark"
                      : "text-cp-text hover:text-cp-orange dark:text-ink-200"
                  }`
                }
              >
                <item.icon className="h-4 w-4" />
                {item.label}
              </NavLink>
            ))}
          </div>
        </nav>
      </header>
      <main className="mx-auto max-w-6xl p-4 md:p-6">
        <Outlet />
      </main>
    </div>
  );
}
