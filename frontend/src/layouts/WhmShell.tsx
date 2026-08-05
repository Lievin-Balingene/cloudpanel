import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
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
  Clock,
  Rocket,
  Search,
  X,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { useAuthStore } from "@/stores/auth";
import { useThemeStore } from "@/stores/theme";
import { OperationProgressHost } from "@/components/OperationProgressHost";

type NavItem = {
  to: string;
  label: string;
  icon: LucideIcon;
  end?: boolean;
  keywords?: string[];
};

type NavSection = {
  title: string;
  items: NavItem[];
};

const navSections: NavSection[] = [
  {
    title: "Favorites",
    items: [
      { to: "/whm", end: true, label: "Home", icon: LayoutDashboard, keywords: ["accueil", "dashboard"] },
      {
        to: "/whm/accounts/create",
        label: "Create a New Account",
        icon: UserPlus,
        keywords: ["créer", "compte", "account"],
      },
      { to: "/whm/accounts", label: "List Accounts", icon: Users, keywords: ["comptes", "users"] },
      {
        to: "/whm/server-setup",
        label: "Basic WebHost Manager Setup",
        icon: Server,
        keywords: ["hostname", "nameserver", "setup"],
      },
    ],
  },
  {
    title: "Account Functions",
    items: [
      { to: "/whm/transfer", label: "Transfer Tool", icon: ArrowRightLeft, keywords: ["migration"] },
      { to: "/whm/packages", label: "Packages", icon: Package, keywords: ["quota", "plan"] },
      { to: "/whm/domains", label: "Domains", icon: AppWindow, keywords: ["domaine", "ssl"] },
      { to: "/whm/dns", label: "DNS Functions", icon: Globe, keywords: ["zone", "record"] },
    ],
  },
  {
    title: "Service Configuration",
    items: [
      { to: "/whm/email", label: "Email", icon: Mail, keywords: ["mail", "roundcube"] },
      { to: "/whm/databases", label: "Databases", icon: Database, keywords: ["mysql", "postgres"] },
      { to: "/whm/ftp", label: "FTP", icon: Upload },
      { to: "/whm/cron", label: "Cron Jobs", icon: Clock, keywords: ["planification"] },
      { to: "/whm/files", label: "File Manager", icon: FolderOpen, keywords: ["fichiers"] },
    ],
  },
  {
    title: "Software",
    items: [
      { to: "/whm/python", label: "Setup Python App", icon: Code2, keywords: ["django", "flask"] },
      { to: "/whm/node", label: "Setup Node.js App", icon: Terminal, keywords: ["express", "npm"] },
      { to: "/whm/php", label: "MultiPHP Manager", icon: FileCode2 },
      { to: "/whm/wordpress", label: "WordPress", icon: LayoutTemplate, keywords: ["wp"] },
      { to: "/whm/git", label: "Git Version Control", icon: GitBranch },
    ],
  },
  {
    title: "Server",
    items: [
      { to: "/whm/terminal", label: "Terminal", icon: Terminal, keywords: ["ssh", "shell"] },
      { to: "/whm/docker", label: "Docker", icon: Box },
      { to: "/whm/kubernetes", label: "Kubernetes", icon: Network, keywords: ["k8s"] },
      { to: "/whm/backups", label: "Backup", icon: HardDrive, keywords: ["sauvegarde"] },
      { to: "/whm/monitoring", label: "Service Status", icon: Bell, keywords: ["alerte"] },
      { to: "/whm/resources", label: "Server Information", icon: Activity, keywords: ["cpu", "ram"] },
      { to: "/whm/panel-update", label: "Panel Update", icon: Rocket, keywords: ["mise à jour", "update", "git"] },
      { to: "/whm/ols", label: "OpenLiteSpeed", icon: Zap, keywords: ["ols", "litespeed", "lsphp", "php"] },
      { to: "/whm/firewall", label: "Firewall", icon: Shield, keywords: ["fail2ban"] },
      { to: "/whm/security", label: "Security Center", icon: KeyRound },
      { to: "/whm/account-security", label: "Two-Factor Auth", icon: KeyRound, keywords: ["2fa"] },
    ],
  },
];

const allTools = navSections.flatMap((s) =>
  s.items.map((item) => ({ ...item, section: s.title })),
);

function matchesQuery(item: NavItem, q: string) {
  if (!q) return true;
  const hay = [item.label, item.to, ...(item.keywords || [])].join(" ").toLowerCase();
  return hay.includes(q);
}

function WhmSearchField({
  value,
  onChange,
  onSubmitFirst,
  placeholder,
  variant = "header",
  autoFocus,
  results,
  onPick,
  showResults,
}: {
  value: string;
  onChange: (v: string) => void;
  onSubmitFirst?: () => void;
  placeholder: string;
  variant?: "header" | "aside";
  autoFocus?: boolean;
  results?: typeof allTools;
  onPick?: (to: string) => void;
  showResults?: boolean;
}) {
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (!listRef.current?.contains(e.target as Node)) {
        /* parent controls closing via blur/empty */
      }
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const isAside = variant === "aside";

  return (
    <div className={`relative ${isAside ? "w-full" : "w-full max-w-xl flex-1"}`} ref={listRef}>
      <Search
        className={`pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 ${
          isAside ? "text-white/45" : "text-white/55"
        }`}
      />
      <input
        type="search"
        autoFocus={autoFocus}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            onSubmitFirst?.();
          }
          if (e.key === "Escape") onChange("");
        }}
        placeholder={placeholder}
        className={
          isAside
            ? "w-full rounded-md border border-white/15 bg-black/25 py-1.5 pl-8 pr-8 text-[12px] text-white placeholder:text-white/40 outline-none focus:border-cp-orange/60 focus:ring-1 focus:ring-cp-orange/40"
            : "w-full rounded-md border border-white/20 bg-white/10 py-1.5 pl-8 pr-8 text-sm text-white placeholder:text-white/50 outline-none focus:border-white/40 focus:bg-white/15 focus:ring-1 focus:ring-white/30"
        }
        aria-label={placeholder}
      />
      {value && (
        <button
          type="button"
          className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-0.5 text-white/50 hover:bg-white/10 hover:text-white"
          onClick={() => onChange("")}
          aria-label="Effacer"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      )}
      {showResults && value.trim() && results && results.length > 0 && onPick && (
        <div className="absolute left-0 right-0 top-[calc(100%+4px)] z-50 max-h-72 overflow-auto rounded-md border border-black/20 bg-white shadow-xl dark:border-ink-700 dark:bg-ink-950">
          {results.slice(0, 12).map((item) => (
            <button
              key={item.to}
              type="button"
              className="flex w-full items-center gap-2 border-b border-cp-border/60 px-3 py-2 text-left text-sm text-cp-text last:border-0 hover:bg-cp-canvas dark:border-ink-800 dark:text-ink-100 dark:hover:bg-ink-900"
              onClick={() => onPick(item.to)}
            >
              <item.icon className="h-3.5 w-3.5 shrink-0 text-cp-orange" />
              <span className="min-w-0 flex-1 truncate font-medium">{item.label}</span>
              <span className="shrink-0 text-[10px] uppercase tracking-wide text-cp-muted">
                {item.section}
              </span>
            </button>
          ))}
        </div>
      )}
      {showResults && value.trim() && results && results.length === 0 && (
        <div className="absolute left-0 right-0 top-[calc(100%+4px)] z-50 rounded-md border border-black/20 bg-white px-3 py-2 text-xs text-cp-muted shadow-xl dark:border-ink-700 dark:bg-ink-950">
          Aucun outil trouvé
        </div>
      )}
    </div>
  );
}

export function WhmShell() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const theme = useThemeStore((s) => s.theme);
  const toggle = useThemeStore((s) => s.toggle);
  const navigate = useNavigate();

  const [headerQuery, setHeaderQuery] = useState("");
  const [asideQuery, setAsideQuery] = useState("");
  const [headerOpen, setHeaderOpen] = useState(false);
  const headerSearchWrap = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (!headerSearchWrap.current?.contains(e.target as Node)) {
        setHeaderOpen(false);
      }
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const headerResults = useMemo(() => {
    const q = headerQuery.trim().toLowerCase();
    if (!q) return [];
    return allTools.filter((item) => matchesQuery(item, q));
  }, [headerQuery]);

  const filteredSections = useMemo(() => {
    const q = asideQuery.trim().toLowerCase();
    if (!q) return navSections;
    return navSections
      .map((section) => ({
        ...section,
        items: section.items.filter((item) => matchesQuery(item, q)),
      }))
      .filter((section) => section.items.length > 0);
  }, [asideQuery]);

  function goTo(to: string) {
    navigate(to);
    setHeaderQuery("");
    setHeaderOpen(false);
    setAsideQuery("");
  }

  function onHeaderSubmit() {
    if (headerResults[0]) goTo(headerResults[0].to);
  }

  function onAsideSubmit(e?: FormEvent) {
    e?.preventDefault();
    const q = asideQuery.trim().toLowerCase();
    if (!q) return;
    const first = allTools.find((item) => matchesQuery(item, q));
    if (first) goTo(first.to);
  }

  return (
    <div className="flex h-screen overflow-hidden bg-cp-canvas dark:bg-surface-dark">
      {/* Sidebar : hauteur viewport, scroll uniquement sur la nav */}
      <aside className="flex h-full w-[270px] shrink-0 flex-col bg-cp-sidebar text-white shadow-[4px_0_24px_rgba(0,0,0,0.18)]">
        <div className="shrink-0 border-b border-white/10 bg-cp-header px-3 py-3">
          <div className="mb-2.5 flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded bg-cp-orange text-xs font-bold text-white shadow">
              VZ
            </div>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold tracking-wide">V-zone WHM</p>
              <p className="text-[10px] uppercase tracking-wider text-white/45">Web Host Manager</p>
            </div>
          </div>
          <form onSubmit={onAsideSubmit}>
            <WhmSearchField
              variant="aside"
              value={asideQuery}
              onChange={setAsideQuery}
              onSubmitFirst={() => onAsideSubmit()}
              placeholder="Find tools…"
            />
          </form>
        </div>

        <nav className="min-h-0 flex-1 overflow-y-auto overscroll-contain pb-3">
          {filteredSections.length === 0 ? (
            <p className="px-4 py-6 text-center text-xs text-white/45">Aucun résultat</p>
          ) : (
            filteredSections.map((section) => (
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
                    onClick={() => setAsideQuery("")}
                  >
                    <item.icon className="h-4 w-4 shrink-0 opacity-90" />
                    <span className="truncate">{item.label}</span>
                  </NavLink>
                ))}
              </div>
            ))
          )}
        </nav>

        <div className="shrink-0 border-t border-white/10 bg-cp-header/90 px-3 py-2.5 text-xs text-white/70">
          <p className="truncate font-medium text-white">{user?.username}</p>
          <p className="capitalize text-white/45">{user?.role}</p>
        </div>
      </aside>

      {/* Colonne droite : header sticky + contenu scrollable */}
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <header className="z-30 flex shrink-0 flex-wrap items-center gap-3 border-b border-black/25 bg-cp-header px-3 py-2 text-white shadow-md sm:px-4">
          <div className="flex shrink-0 items-center gap-2">
            <span className="rounded bg-cp-orange px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide">
              WHM
            </span>
            <p className="hidden text-sm text-white/85 md:block">
              <span className="font-semibold text-white">V-zone Panel</span>
            </p>
          </div>

          <div className="relative w-full max-w-xl flex-1" ref={headerSearchWrap}>
            <WhmSearchField
              variant="header"
              value={headerQuery}
              onChange={(v) => {
                setHeaderQuery(v);
                setHeaderOpen(true);
              }}
              onSubmitFirst={onHeaderSubmit}
              placeholder="Search for features and tools…"
              results={headerResults}
              onPick={goTo}
              showResults={headerOpen}
            />
          </div>

          <div className="ml-auto flex shrink-0 items-center gap-0.5">
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
              <span className="hidden sm:inline">Logout</span>
            </button>
          </div>
        </header>

        <main className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-4 md:p-6">
          <Outlet />
        </main>
      </div>
      <OperationProgressHost />
    </div>
  );
}
