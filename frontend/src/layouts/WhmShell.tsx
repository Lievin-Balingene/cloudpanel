import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
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
  Wrench,
  Bot,
  SlidersHorizontal,
  ChevronRight,
  ChevronDown,
  ChevronsDown,
  ChevronsUp,
  User,
  Menu,
  type LucideIcon,
} from "lucide-react";
import { useAuthStore } from "@/stores/auth";
import { useThemeStore } from "@/stores/theme";
import { OperationProgressHost } from "@/components/OperationProgressHost";
import { AiDeploymentAssistant } from "@/components/AiDeploymentAssistant";
import { apiRequest } from "@/lib/api";
import { canAccessWhmRoute } from "@/lib/resellerAcl";
import { cpanelPortalUrl } from "@/lib/portal";
import type { DashboardOverview } from "@/types";

type NavItem = {
  to: string;
  label: string;
  icon: LucideIcon;
  end?: boolean;
  keywords?: string[];
};

type NavSection = {
  id: string;
  title: string;
  items: NavItem[];
};

const navSections: NavSection[] = [
  {
    id: "favorites",
    title: "Home",
    items: [
      { to: "/whm", end: true, label: "Home", icon: LayoutDashboard, keywords: ["accueil", "dashboard"] },
      {
        to: "/whm/accounts/create",
        label: "Create a New Account",
        icon: UserPlus,
        keywords: ["créer", "compte", "account"],
      },
      { to: "/whm/accounts", end: true, label: "List Accounts", icon: Users, keywords: ["comptes", "users"] },
      {
        to: "/whm/server-setup",
        label: "Basic WebHost Manager Setup",
        icon: Server,
        keywords: ["hostname", "nameserver", "setup"],
      },
    ],
  },
  {
    id: "server-config",
    title: "Server Configuration",
    items: [
      {
        to: "/whm/server-setup",
        label: "Basic Setup / Hostname",
        icon: Server,
        keywords: ["hostname", "nameserver", "contact"],
      },
      {
        to: "/whm/tweak-settings",
        label: "Tweak Settings",
        icon: SlidersHorizontal,
        keywords: ["tweak", "features", "php", "security", "limits"],
      },
      {
        to: "/whm/panel-update",
        label: "Update Preferences",
        icon: Rocket,
        keywords: ["mise à jour", "update", "git"],
      },
      {
        to: "/whm/cron",
        label: "Configure Cron Jobs",
        icon: Clock,
        keywords: ["planification", "cron"],
      },
      {
        to: "/whm/repairs",
        label: "Réparations système",
        icon: Wrench,
        keywords: ["repair", "smtp", "dkim", "nginx"],
      },
    ],
  },
  {
    id: "ip-functions",
    title: "IP Functions",
    items: [
      {
        to: "/whm/ip-functions",
        label: "IP Address Usage / Deny / Change Site IP",
        icon: Network,
        keywords: ["ip", "deny", "migration", "shared"],
      },
    ],
  },
  {
    id: "ai-ops",
    title: "AI Operations",
    items: [
      {
        to: "/whm/ai-ops",
        label: "AI Assistant / Command Approval",
        icon: Bot,
        keywords: ["ia", "diagnostic", "approuver", "commande"],
      },
    ],
  },
  {
    id: "account-info",
    title: "Account Information",
    items: [
      { to: "/whm/accounts", end: true, label: "List Accounts", icon: Users, keywords: ["comptes", "list"] },
      { to: "/whm/domains", label: "List Domains", icon: AppWindow, keywords: ["domaine", "parked", "subdomain"] },
      { to: "/whm/resources", label: "View Bandwidth / Resources", icon: Activity, keywords: ["cpu", "ram", "bandwidth"] },
    ],
  },
  {
    id: "account-functions",
    title: "Account Functions",
    items: [
      {
        to: "/whm/accounts/create",
        label: "Create a New Account",
        icon: UserPlus,
        keywords: ["créer", "compte"],
      },
      { to: "/whm/accounts", end: true, label: "Modify / Suspend / Terminate", icon: Users, keywords: ["modify", "suspend"] },
      {
        to: "/whm/resellers",
        label: "Edit Reseller Privileges",
        icon: Shield,
        keywords: ["revendeur", "acl", "privileges"],
      },
      { to: "/whm/transfer", label: "Transfer Tool", icon: ArrowRightLeft, keywords: ["migration", "cpmove"] },
    ],
  },
  {
    id: "packages",
    title: "Packages",
    items: [
      {
        to: "/whm/packages/create",
        label: "Add a Package",
        icon: Package,
        keywords: ["créer", "quota", "plan", "feature", "pulse", "cpu", "ram"],
      },
      {
        to: "/whm/packages",
        end: true,
        label: "List Packages",
        icon: Package,
        keywords: ["edit", "quota", "plan"],
      },
      {
        to: "/whm/pulse",
        label: "V-zone Pulse",
        icon: Zap,
        keywords: ["cgroups", "lve", "cpu", "ram", "resource", "governor"],
      },
    ],
  },
  {
    id: "dns",
    title: "DNS Functions",
    items: [
      { to: "/whm/dns", label: "DNS Zone Manager", icon: Globe, keywords: ["zone", "record", "a", "mx", "txt"] },
    ],
  },
  {
    id: "transfers",
    title: "Transfers",
    items: [
      { to: "/whm/transfer", label: "Transfer Tool", icon: ArrowRightLeft, keywords: ["migration"] },
    ],
  },
  {
    id: "backup",
    title: "Backup",
    items: [
      { to: "/whm/backups", label: "Backup Configuration / Restore", icon: HardDrive, keywords: ["sauvegarde"] },
    ],
  },
  {
    id: "system-health",
    title: "System Health",
    items: [
      { to: "/whm/resources", label: "System Information", icon: Activity, keywords: ["cpu", "ram", "disk"] },
      { to: "/whm/monitoring", label: "Process / Service Health", icon: Bell, keywords: ["alerte", "monitoring"] },
      { to: "/whm/terminal", label: "Process Manager (Terminal)", icon: Terminal, keywords: ["ssh", "shell"] },
    ],
  },
  {
    id: "server-status",
    title: "Server Status",
    items: [
      { to: "/whm/monitoring", label: "Service Status", icon: Bell, keywords: ["services"] },
      { to: "/whm/resources", label: "Server Monitoring", icon: Activity, keywords: ["load"] },
    ],
  },
  {
    id: "services",
    title: "Service Configuration",
    items: [
      { to: "/whm/email", label: "Mailserver / Email", icon: Mail, keywords: ["roundcube", "exim"] },
      { to: "/whm/databases", label: "Database Services", icon: Database, keywords: ["mysql", "postgres"] },
      { to: "/whm/ftp", label: "FTP Configuration", icon: Upload },
      { to: "/whm/files", label: "File Manager", icon: FolderOpen, keywords: ["fichiers"] },
      { to: "/whm/ols", label: "OpenLiteSpeed / Web", icon: Zap, keywords: ["ols", "litespeed", "nginx"] },
    ],
  },
  {
    id: "software",
    title: "Software",
    items: [
      { to: "/whm/php", label: "MultiPHP Manager", icon: FileCode2, keywords: ["php"] },
      { to: "/whm/wordpress", label: "WordPress", icon: LayoutTemplate, keywords: ["wp"] },
      { to: "/whm/python", label: "Setup Python App", icon: Code2, keywords: ["django", "flask"] },
      { to: "/whm/node", label: "Setup Node.js App", icon: Terminal, keywords: ["express", "npm"] },
      { to: "/whm/git", label: "Git Version Control", icon: GitBranch },
      { to: "/whm/docker", label: "Docker", icon: Box },
      { to: "/whm/kubernetes", label: "Kubernetes", icon: Network, keywords: ["k8s"] },
      { to: "/whm/panel-update", label: "Panel / System Update", icon: Rocket, keywords: ["update"] },
    ],
  },
  {
    id: "security",
    title: "Security Center",
    items: [
      { to: "/whm/security", label: "Security Advisor / Policy", icon: KeyRound, keywords: ["password", "policy"] },
      {
        to: "/whm/smtp-restrictions",
        label: "SMTP Restrictions",
        icon: Mail,
        keywords: ["smtp", "spam", "mail", "mta", "port 25"],
      },
      { to: "/whm/firewall", label: "Firewall & Fail2Ban", icon: Shield, keywords: ["fail2ban", "cphulk"] },
      { to: "/whm/account-security", label: "Two-Factor Authentication", icon: KeyRound, keywords: ["2fa"] },
      { to: "/whm/domains", label: "SSL/TLS & AutoSSL", icon: AppWindow, keywords: ["ssl", "letsencrypt"] },
    ],
  },
  {
    id: "email-db",
    title: "Email & Databases",
    items: [
      { to: "/whm/email", label: "Email Accounts", icon: Mail },
      { to: "/whm/databases", label: "MySQL / PostgreSQL", icon: Database },
    ],
  },
  {
    id: "cpanel-dev",
    title: "cPanel & Development",
    items: [
      { to: "/whm/files", label: "Browse Account Files", icon: FolderOpen },
      { to: "/whm/terminal", label: "Terminal / API Ops", icon: Terminal },
      { to: "/whm/docker", label: "Containers", icon: Box },
    ],
  },
];

/** Outils aplatis pour ACL / navigation. */
const allTools = navSections.flatMap((s) =>
  s.items.map((item) => ({ ...item, section: s.title, sectionId: s.id })),
);

function matchesQuery(item: NavItem, q: string) {
  if (!q) return true;
  const hay = [item.label, item.to, ...(item.keywords || [])].join(" ").toLowerCase();
  return hay.includes(q);
}

function sectionContainsPath(section: NavSection, pathname: string) {
  return section.items.some((item) =>
    item.end ? pathname === item.to : pathname === item.to || pathname.startsWith(`${item.to}/`),
  );
}

function WhmSearchField({
  value,
  onChange,
  onSubmitFirst,
  placeholder,
  variant = "header",
  results,
  onPick,
  showResults,
}: {
  value: string;
  onChange: (v: string) => void;
  onSubmitFirst?: () => void;
  placeholder: string;
  variant?: "header" | "aside";
  results?: typeof allTools;
  onPick?: (to: string) => void;
  showResults?: boolean;
}) {
  const listRef = useRef<HTMLDivElement>(null);
  const isAside = variant === "aside";

  return (
    <div className={`relative ${isAside ? "w-full" : "w-full max-w-md flex-1"}`} ref={listRef}>
      <Search
        className={`pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 ${
          isAside ? "text-[#5a6f85]" : "text-[#8a9bb0]"
        }`}
      />
      <input
        type="search"
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
            ? "w-full rounded border-0 bg-[#e8eef4] py-1.5 pl-8 pr-8 text-[12px] text-[#2c3e50] placeholder:text-[#7a8fa3] outline-none ring-1 ring-[#c5d0dc] focus:ring-2 focus:ring-[#4a90c8]"
            : "w-full rounded border border-[#c5d0dc] bg-white py-1.5 pl-8 pr-8 text-sm text-[#2c3e50] placeholder:text-[#8a9bb0] outline-none focus:border-[#4a90c8] focus:ring-1 focus:ring-[#4a90c8]/40"
        }
        aria-label={placeholder}
      />
      {value && (
        <button
          type="button"
          className={`absolute right-2 top-1/2 -translate-y-1/2 rounded p-0.5 ${
            isAside ? "text-[#5a6f85] hover:bg-black/5" : "text-[#8a9bb0] hover:bg-black/5"
          }`}
          onClick={() => onChange("")}
          aria-label="Effacer"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      )}
      {showResults && value.trim() && results && results.length > 0 && onPick && (
        <div className="absolute left-0 right-0 top-[calc(100%+4px)] z-50 max-h-72 overflow-auto rounded border border-[#c5d0dc] bg-white shadow-xl">
          {results.slice(0, 12).map((item) => (
            <button
              key={`${item.sectionId}-${item.to}-${item.label}`}
              type="button"
              className="flex w-full items-center gap-2 border-b border-[#e8eef4] px-3 py-2 text-left text-sm text-[#2c3e50] last:border-0 hover:bg-[#f0f4f8]"
              onClick={() => onPick(item.to)}
            >
              <item.icon className="h-3.5 w-3.5 shrink-0 text-cp-orange" />
              <span className="min-w-0 flex-1 truncate font-medium">{item.label}</span>
              <span className="shrink-0 text-[10px] uppercase tracking-wide text-[#8a9bb0]">
                {item.section}
              </span>
            </button>
          ))}
        </div>
      )}
      {showResults && value.trim() && results && results.length === 0 && (
        <div className="absolute left-0 right-0 top-[calc(100%+4px)] z-50 rounded border border-[#c5d0dc] bg-white px-3 py-2 text-xs text-[#8a9bb0] shadow-xl">
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
  const location = useLocation();

  const visibleSections = useMemo(() => {
    const role = user?.role;
    const privs = user?.reseller_privileges;
    return navSections
      .map((section) => ({
        ...section,
        items: section.items.filter((item) => canAccessWhmRoute(role, privs, item.to)),
      }))
      .filter((section) => section.items.length > 0);
  }, [user?.role, user?.reseller_privileges]);

  const visibleTools = useMemo(
    () =>
      visibleSections.flatMap((s) =>
        s.items.map((item) => ({ ...item, section: s.title, sectionId: s.id })),
      ),
    [visibleSections],
  );

  const [headerQuery, setHeaderQuery] = useState("");
  const [asideQuery, setAsideQuery] = useState("");
  const [headerOpen, setHeaderOpen] = useState(false);
  const [navOpen, setNavOpen] = useState(false);
  const [openSections, setOpenSections] = useState<Set<string>>(() => new Set(["favorites"]));
  const headerSearchWrap = useRef<HTMLDivElement>(null);

  const { data: overview } = useQuery({
    queryKey: ["dashboard-overview"],
    queryFn: () => apiRequest<DashboardOverview>("/dashboard/overview/"),
    staleTime: 30_000,
    refetchInterval: 60_000,
  });

  const { data: setup } = useQuery({
    queryKey: ["server-setup-shell"],
    queryFn: () =>
      apiRequest<{ hostname?: string; nameserver1?: string }>("/server-setup/").catch(() => ({
        hostname: "",
      })),
    staleTime: 60_000,
  });

  const { data: panelInfo } = useQuery({
    queryKey: ["panel-version-shell"],
    queryFn: () => apiRequest<{ version: string }>("/server-setup/panel-update/"),
    staleTime: 120_000,
  });

  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (!headerSearchWrap.current?.contains(e.target as Node)) {
        setHeaderOpen(false);
      }
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  // Ouvre la section active selon la route + ferme le drawer mobile
  useEffect(() => {
    setNavOpen(false);
    const active = visibleSections.find((s) => sectionContainsPath(s, location.pathname));
    if (active) {
      setOpenSections((prev) => {
        if (prev.has(active.id)) return prev;
        const next = new Set(prev);
        next.add(active.id);
        return next;
      });
    }
  }, [location.pathname, visibleSections]);

  useEffect(() => {
    if (!navOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setNavOpen(false);
    };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [navOpen]);

  const headerResults = useMemo(() => {
    const q = headerQuery.trim().toLowerCase();
    if (!q) return [];
    const seen = new Set<string>();
    const out: typeof visibleTools = [];
    for (const item of visibleTools) {
      if (!matchesQuery(item, q)) continue;
      const k = `${item.to}|${item.label}`;
      if (seen.has(k)) continue;
      seen.add(k);
      out.push(item);
    }
    return out;
  }, [headerQuery, visibleTools]);

  const filteredSections = useMemo(() => {
    const q = asideQuery.trim().toLowerCase();
    if (!q) return visibleSections;
    return visibleSections
      .map((section) => ({
        ...section,
        items: section.items.filter((item) => matchesQuery(item, q)),
      }))
      .filter((section) => section.items.length > 0);
  }, [asideQuery, visibleSections]);

  // Pendant une recherche sidebar : tout ouvrir
  useEffect(() => {
    if (asideQuery.trim()) {
      setOpenSections(new Set(filteredSections.map((s) => s.id)));
    }
  }, [asideQuery, filteredSections]);

  function toggleSection(id: string) {
    setOpenSections((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function expandAll() {
    setOpenSections(new Set(visibleSections.map((s) => s.id)));
  }

  function collapseAll() {
    setOpenSections(new Set());
  }

  function goTo(to: string) {
    navigate(to);
    setHeaderQuery("");
    setHeaderOpen(false);
    setAsideQuery("");
    setNavOpen(false);
  }

  function onHeaderSubmit() {
    if (headerResults[0]) goTo(headerResults[0].to);
  }

  function onAsideSubmit(e?: FormEvent) {
    e?.preventDefault();
    const q = asideQuery.trim().toLowerCase();
    if (!q) return;
    const first = visibleTools.find((item) => matchesQuery(item, q));
    if (first) goTo(first.to);
  }

  const load = overview?.metrics?.load_average;
  const loadLabel =
    load && load.length >= 3
      ? load.map((n) => (typeof n === "number" ? n.toFixed(2) : "—")).join(" ")
      : "—";
  const hostname = setup?.hostname || window.location.hostname || "—";
  const version = panelInfo?.version || "";

  return (
    <div className="flex h-[100dvh] overflow-hidden bg-[#d8e0ea] dark:bg-surface-dark">
      {navOpen ? (
        <button
          type="button"
          className="fixed inset-0 z-40 bg-black/45 md:hidden"
          aria-label="Fermer le menu"
          onClick={() => setNavOpen(false)}
        />
      ) : null}

      {/* Sidebar V-zone Admin — drawer mobile, fixe desktop */}
      <aside
        className={`fixed inset-y-0 left-0 z-50 flex h-full w-[min(248px,88vw)] shrink-0 flex-col bg-[#2a4a6b] text-white shadow-[2px_0_8px_rgba(0,0,0,0.25)] transition-transform duration-200 ease-out md:static md:z-auto md:w-[248px] md:translate-x-0 ${
          navOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="shrink-0 px-3 pb-2 pt-3">
          <div className="flex items-center gap-2.5">
            <img
              src="/vzone-mark.svg"
              alt="V-zone"
              className="h-9 w-9 shrink-0 rounded-[9px] shadow-sm"
              width={36}
              height={36}
            />
            <div className="min-w-0 flex-1">
              <p className="select-none font-sans text-[20px] font-bold leading-none tracking-tight text-white">
                WHM
              </p>
              <p className="mt-0.5 truncate text-[10px] font-medium uppercase tracking-[0.12em] text-white/55">
                V-zone Admin
              </p>
            </div>
            <button
              type="button"
              className="inline-flex h-9 w-9 items-center justify-center rounded-md text-white/80 hover:bg-white/10 md:hidden"
              aria-label="Fermer le menu"
              onClick={() => setNavOpen(false)}
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          <div className="mt-3 grid grid-cols-2 gap-1.5">
            <button
              type="button"
              onClick={expandAll}
              className="inline-flex items-center justify-center gap-1 rounded border border-white/35 bg-transparent px-2 py-1 text-[11px] font-medium text-white hover:bg-white/10"
            >
              Expand <ChevronsDown className="h-3 w-3" />
            </button>
            <button
              type="button"
              onClick={collapseAll}
              className="inline-flex items-center justify-center gap-1 rounded border border-white/35 bg-transparent px-2 py-1 text-[11px] font-medium text-white hover:bg-white/10"
            >
              Collapse <ChevronsUp className="h-3 w-3" />
            </button>
          </div>

          <form className="mt-2.5" onSubmit={onAsideSubmit}>
            <WhmSearchField
              variant="aside"
              value={asideQuery}
              onChange={setAsideQuery}
              onSubmitFirst={() => onAsideSubmit()}
              placeholder="Search Tools (Ctrl /)"
            />
          </form>
        </div>

        <nav className="min-h-0 flex-1 overflow-y-auto overscroll-contain pb-2">
          {filteredSections.length === 0 ? (
            <p className="px-4 py-6 text-center text-xs text-white/50">Aucun résultat</p>
          ) : (
            filteredSections.map((section) => {
              const open = openSections.has(section.id) || Boolean(asideQuery.trim());
              return (
                <div key={section.id} className="border-b border-white/10">
                  <button
                    type="button"
                    onClick={() => toggleSection(section.id)}
                    className="flex w-full items-center gap-2 px-3 py-2.5 text-left text-[13px] font-medium text-white hover:bg-white/10"
                  >
                    {open ? (
                      <ChevronDown className="h-3.5 w-3.5 shrink-0 opacity-80" />
                    ) : (
                      <ChevronRight className="h-3.5 w-3.5 shrink-0 opacity-80" />
                    )}
                    <span className="truncate">{section.title}</span>
                  </button>
                  {open && (
                    <div className="bg-[#23405c] pb-1">
                      {section.items.map((item) => (
                        <NavLink
                          key={`${section.id}-${item.to}-${item.label}`}
                          to={item.to}
                          end={item.end}
                          className={({ isActive }) =>
                            `flex items-center gap-2 border-l-2 py-1.5 pl-8 pr-3 text-[12.5px] transition ${
                              isActive
                                ? "border-cp-orange bg-white/10 font-semibold text-white"
                                : "border-transparent text-white/85 hover:bg-white/10 hover:text-white"
                            }`
                          }
                          onClick={() => {
                            setAsideQuery("");
                            setNavOpen(false);
                          }}
                        >
                          <item.icon className="h-3.5 w-3.5 shrink-0 opacity-80" />
                          <span className="truncate">{item.label}</span>
                        </NavLink>
                      ))}
                    </div>
                  )}
                </div>
              );
            })
          )}
        </nav>

        <div className="shrink-0 border-t border-white/15 px-3 py-2 text-[11px] text-white/65">
          <p className="truncate font-medium text-white">{user?.username}</p>
          <p className="capitalize text-white/45">{user?.role}</p>
        </div>
      </aside>

      {/* Colonne droite : topbar */}
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <header className="z-30 shrink-0 border-b border-[#c5d0dc] bg-white shadow-sm dark:border-ink-700 dark:bg-ink-950">
          <div className="hidden flex-wrap items-center gap-x-4 gap-y-2 px-3 py-1.5 text-[11px] text-[#5a6f85] dark:text-ink-300 sm:flex sm:px-4">
            <span>
              <span className="text-[#8a9bb0]">Username:</span>{" "}
              <span className="font-medium text-[#2c3e50] dark:text-ink-100">{user?.username || "—"}</span>
            </span>
            <span className="hidden sm:inline">
              <span className="text-[#8a9bb0]">Hostname:</span>{" "}
              <span className="font-medium text-[#2c3e50] dark:text-ink-100">{hostname}</span>
            </span>
            {version && (
              <span className="hidden md:inline">
                <span className="text-[#8a9bb0]">V-zone:</span>{" "}
                <span className="font-medium text-[#2c3e50] dark:text-ink-100">{version}</span>
              </span>
            )}
            <span className="ml-auto hidden lg:inline">
              <span className="text-[#8a9bb0]">Load Averages:</span>{" "}
              <span className="font-mono font-medium text-[#2c3e50] dark:text-ink-100">{loadLabel}</span>
            </span>
            <span className="hidden items-center gap-1 rounded-full bg-[#eef2f6] px-2 py-0.5 text-[10px] font-medium text-[#5a6f85] dark:bg-ink-800 lg:inline-flex">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
              No alerts
            </span>
          </div>

          <div className="flex items-center gap-2 border-t border-[#e8eef4] px-2 py-2 dark:border-ink-800 sm:px-4">
            <button
              type="button"
              className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-[#c5d0dc] text-[#2c3e50] hover:bg-[#f0f4f8] dark:border-ink-600 dark:text-ink-100 dark:hover:bg-ink-800 md:hidden"
              aria-label="Ouvrir le menu"
              aria-expanded={navOpen}
              onClick={() => setNavOpen(true)}
            >
              <Menu className="h-5 w-5" />
            </button>
            <div className="relative min-w-0 flex-1" ref={headerSearchWrap}>
              <WhmSearchField
                variant="header"
                value={headerQuery}
                onChange={(v) => {
                  setHeaderQuery(v);
                  setHeaderOpen(true);
                }}
                onSubmitFirst={onHeaderSubmit}
                placeholder="Search Tools…"
                results={headerResults}
                onPick={goTo}
                showResults={headerOpen}
              />
            </div>

            <div className="flex shrink-0 items-center gap-1">
              {user?.role === "reseller" && (
                <a
                  href={cpanelPortalUrl("/panel")}
                  className="inline-flex h-9 items-center gap-1.5 rounded-full border border-cp-orange/40 bg-cp-orange-soft px-2.5 text-xs font-semibold text-cp-orange-dark hover:brightness-105"
                  title="Ouvrir mon cPanel"
                >
                  <AppWindow className="h-3.5 w-3.5" />
                  <span className="hidden sm:inline">cPanel</span>
                </a>
              )}
              <button
                type="button"
                className="flex h-9 w-9 items-center justify-center rounded-full border border-[#c5d0dc] text-[#5a6f85] hover:bg-[#f0f4f8] dark:border-ink-600 dark:text-ink-300 dark:hover:bg-ink-800"
                onClick={toggle}
                title="Theme"
              >
                {theme === "dark" ? <Sun className="h-3.5 w-3.5" /> : <Moon className="h-3.5 w-3.5" />}
              </button>
              <button
                type="button"
                className="hidden h-9 w-9 items-center justify-center rounded-full border border-[#c5d0dc] text-[#5a6f85] hover:bg-[#f0f4f8] dark:border-ink-600 dark:text-ink-300 sm:flex"
                title={user?.username}
              >
                <User className="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                className="inline-flex h-9 items-center gap-1.5 rounded-full border border-[#c5d0dc] px-2.5 text-xs font-medium text-[#2c3e50] hover:bg-[#f0f4f8] dark:border-ink-600 dark:text-ink-100 dark:hover:bg-ink-800"
                onClick={() => void logout()}
              >
                <LogOut className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">Logout</span>
              </button>
            </div>
          </div>
        </header>

        <main className="min-h-0 flex-1 overflow-y-auto overscroll-contain bg-[#eef2f6] p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] dark:bg-surface-dark sm:p-4 md:p-6">
          <Outlet />
        </main>
      </div>
      <OperationProgressHost />
      <AiDeploymentAssistant />
    </div>
  );
}
