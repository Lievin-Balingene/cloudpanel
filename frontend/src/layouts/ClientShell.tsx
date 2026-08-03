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
    <div className="min-h-screen bg-[#071018] text-white">
      <header className="border-b border-white/10 bg-[#0b1622]/95 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-400/15 text-emerald-300">
              <LayoutGrid className="h-5 w-5" />
            </div>
            <div>
              <p className="font-display text-sm font-semibold">V-zone</p>
              <p className="text-xs text-white/45">Espace client · {user?.username}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              className="rounded-lg px-2 py-1.5 text-white/70 hover:bg-white/10 hover:text-white"
              onClick={toggle}
            >
              {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </button>
            <button
              type="button"
              className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-sm text-white/70 hover:bg-white/10 hover:text-white"
              onClick={() => void logout()}
            >
              <LogOut className="h-4 w-4" />
              Quitter
            </button>
          </div>
        </div>
        <nav className="border-t border-white/10">
          <div className="mx-auto flex max-w-6xl gap-1 overflow-x-auto px-2">
            {nav.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `inline-flex shrink-0 items-center gap-1.5 px-3 py-2.5 text-sm transition ${
                    isActive
                      ? "border-b-2 border-emerald-400 font-semibold text-white"
                      : "text-white/55 hover:text-white"
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
