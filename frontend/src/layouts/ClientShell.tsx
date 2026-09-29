import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Home,
  Globe,
  Package,
  LogOut,
  Moon,
  Sun,
  AppWindow,
  FolderOpen,
  Upload,
  Mail,
  Database,
  Code2,
  Terminal,
  FileCode2,
  LayoutTemplate,
  GitBranch,
  Box,
  HardDrive,
  KeyRound,
  Shield,
  ChevronDown,
  Clock,
  Menu,
  X,
  Server,
  PieChart,
  Lock,
  Ban,
  Settings,
  BarChart3,
  FileLock2,
  Gauge,
  Zap,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { apiRequest } from "@/lib/api";
import { formatBytes } from "@/lib/format";
import { whmPortalUrl } from "@/lib/portal";
import { useAuthStore } from "@/stores/auth";
import { useThemeStore } from "@/stores/theme";
import { OperationProgressHost } from "@/components/OperationProgressHost";
import { AiDeploymentAssistant } from "@/components/AiDeploymentAssistant";
import type { DashboardOverview } from "@/types";

type NavItem = { to: string; label: string; icon: typeof Home; end?: boolean };

type NavSection = { id: string; label: string; items: NavItem[] };

/** Sections alignées sur cPanel (ordre & regroupement familiers). */
const sections: NavSection[] = [
  {
    id: "files",
    label: "Fichiers",
    items: [
      { to: "/panel/files", label: "Gestionnaire de fichiers", icon: FolderOpen },
      { to: "/panel/disk-usage", label: "Utilisation disque", icon: PieChart },
      { to: "/panel/directory-privacy", label: "Confidentialité dossiers", icon: FileLock2 },
      { to: "/panel/ftp", label: "Comptes FTP", icon: Upload },
      { to: "/panel/backups", label: "Sauvegardes", icon: HardDrive },
    ],
  },
  {
    id: "databases",
    label: "Bases de données",
    items: [{ to: "/panel/databases", label: "MySQL / PostgreSQL", icon: Database }],
  },
  {
    id: "domains",
    label: "Domaines",
    items: [
      { to: "/panel/domains", label: "Domaines", icon: AppWindow },
      { to: "/panel/dns", label: "Éditeur de zone DNS", icon: Globe },
    ],
  },
  {
    id: "email",
    label: "E-mail",
    items: [{ to: "/panel/email", label: "Comptes e-mail", icon: Mail }],
  },
  {
    id: "metrics",
    label: "Statistiques",
    items: [
      { to: "/panel/metrics", label: "Visiteurs & erreurs", icon: BarChart3 },
      { to: "/panel/package", label: "Ressources & quotas", icon: Gauge },
      { to: "/panel/pulse", label: "V-zone Pulse", icon: Zap },
    ],
  },
  {
    id: "security",
    label: "Sécurité",
    items: [
      { to: "/panel/security", label: "Mot de passe & 2FA", icon: KeyRound },
      { to: "/panel/ssh-keys", label: "Clés SSH", icon: Lock },
      { to: "/panel/ip-blocker", label: "Bloqueur d’IP", icon: Ban },
      { to: "/panel/domains", label: "SSL / TLS", icon: Shield },
    ],
  },
  {
    id: "software",
    label: "Logiciels",
    items: [
      { to: "/panel/php", label: "MultiPHP Manager", icon: FileCode2 },
      { to: "/panel/wordpress", label: "WordPress", icon: LayoutTemplate },
      { to: "/panel/python", label: "Application Python", icon: Code2 },
      { to: "/panel/node", label: "Application Node.js", icon: Terminal },
      { to: "/panel/git", label: "Contrôle de version Git", icon: GitBranch },
      { to: "/panel/docker", label: "Docker", icon: Box },
    ],
  },
  {
    id: "advanced",
    label: "Avancé",
    items: [
      { to: "/panel/cron", label: "Tâches Cron", icon: Clock },
      { to: "/panel/terminal", label: "Terminal", icon: Terminal },
    ],
  },
  {
    id: "preferences",
    label: "Préférences",
    items: [
      { to: "/panel/preferences", label: "Préférences du compte", icon: Settings },
      { to: "/panel/package", label: "Mon forfait", icon: Package },
    ],
  },
];

function UsageBar({
  label,
  usedLabel,
  percent,
}: {
  label: string;
  usedLabel: string;
  percent: number;
}) {
  const pct = Math.max(0, Math.min(100, percent));
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-2 text-xs">
        <span className="font-medium text-cp-text">{label}</span>
        <span className="tabular-nums text-cp-muted">{usedLabel}</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-[#e2e8f0] dark:bg-ink-800">
        <div
          className={`h-full rounded-full transition-all ${
            pct >= 90 ? "bg-cp-danger" : pct >= 70 ? "bg-amber-500" : "bg-cp-orange"
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function HostUsagePanel() {
  const user = useAuthStore((s) => s.user);
  const { data } = useQuery({
    queryKey: ["dashboard-overview"],
    queryFn: () => apiRequest<DashboardOverview>("/dashboard/overview/"),
    refetchInterval: 30000,
  });
  const { data: assignment } = useQuery({
    queryKey: ["package-mine"],
    queryFn: () =>
      apiRequest<{
        package: {
          name: string;
          disk_mb: number;
          bandwidth_mb: number;
          domains: number;
          emails: number;
          databases: number;
          ftp_accounts: number;
          unlimited_disk: boolean;
          unlimited_bandwidth: boolean;
        };
      } | null>("/packages/mine/"),
  });

  const pkg = assignment?.package;
  const account = data?.account;
  const usage = data?.usage;
  const unlimitedDisk = Boolean(data?.disk?.unlimited || pkg?.unlimited_disk);
  const diskLimitMb =
    !unlimitedDisk && (data?.disk?.quota_mb ?? (pkg ? pkg.disk_mb : null))
      ? Number(data?.disk?.quota_mb ?? pkg?.disk_mb)
      : null;
  const diskUsedMb =
    typeof data?.disk?.used_mb === "number"
      ? data.disk.used_mb
      : data?.disk
        ? data.disk.used / (1024 * 1024)
        : 0;
  const diskPct =
    diskLimitMb && diskLimitMb > 0
      ? Math.min(100, (diskUsedMb / diskLimitMb) * 100)
      : data?.disk?.percent ?? 0;
  const formatUsedMb = (mb: number) =>
    mb < 0.1 ? "0" : mb < 10 ? mb.toFixed(1) : mb < 100 ? mb.toFixed(1) : mb.toFixed(0);
  const diskLabel = unlimitedDisk
    ? `${formatUsedMb(diskUsedMb)} Mo / ∞`
    : diskLimitMb
      ? `${formatUsedMb(diskUsedMb)} / ${diskLimitMb} Mo`
      : data?.disk
        ? `${formatBytes(data.disk.used)} / ${formatBytes(data.disk.total)}`
        : "—";

  const fmtQuota = (used: number | undefined, limit: number | undefined) => {
    const u = used ?? 0;
    if (limit == null) return String(u);
    return `${u} / ${limit}`;
  };

  return (
    <aside className="hidden w-72 shrink-0 xl:block">
      <div className="sticky top-4 space-y-3">
        <div className="vz-panel overflow-hidden">
          <div className="border-b border-cp-border bg-cp-header px-3 py-2.5 text-xs font-semibold tracking-wide text-white">
            Votre compte
          </div>
          <dl className="space-y-2.5 p-3.5 text-sm">
            <div className="flex justify-between gap-2">
              <dt className="text-cp-muted">Identifiant</dt>
              <dd className="font-medium text-cp-text">{account?.username ?? user?.username ?? "—"}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-cp-muted">Domaine principal</dt>
              <dd className="truncate font-medium text-cp-text" title={account?.primary_domain || undefined}>
                {account?.primary_domain || "—"}
              </dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-cp-muted">Forfait</dt>
              <dd className="font-medium text-cp-text">{data?.my_package ?? pkg?.name ?? "—"}</dd>
            </div>
          </dl>
        </div>

        <div className="vz-panel overflow-hidden">
          <div className="border-b border-cp-border bg-cp-header px-3 py-2.5 text-xs font-semibold tracking-wide text-white">
            Utilisation
          </div>
          <div className="space-y-3.5 p-3.5">
            <UsageBar label="Espace disque" usedLabel={diskLabel} percent={diskPct} />
            <UsageBar
              label="Bande passante"
              usedLabel={
                pkg?.unlimited_bandwidth
                  ? "Illimitée"
                  : pkg
                    ? `0 / ${pkg.bandwidth_mb} Mo`
                    : "—"
              }
              percent={0}
            />
            <InfoRow label="Domaines" value={fmtQuota(usage?.domains ?? data?.domains_total, pkg?.domains)} />
            <InfoRow label="Boîtes mail" value={fmtQuota(usage?.emails, pkg?.emails)} />
            <InfoRow label="Bases de données" value={fmtQuota(usage?.databases, pkg?.databases)} />
            <InfoRow label="Comptes FTP" value={fmtQuota(usage?.ftp_accounts, pkg?.ftp_accounts)} />
          </div>
        </div>
      </div>
    </aside>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between border-t border-cp-border pt-2.5 text-xs first:border-0 first:pt-0">
      <span className="text-cp-muted">{label}</span>
      <span className="font-semibold tabular-nums text-cp-text">{value}</span>
    </div>
  );
}

function ToolsNav({ onNavigate }: { onNavigate?: () => void }) {
  const location = useLocation();
  const initiallyOpen = useMemo(() => {
    const open = new Set<string>(["files", "domains", "email"]);
    for (const section of sections) {
      if (
        section.items.some(
          (i) =>
            location.pathname === i.to ||
            (i.to !== "/panel" && location.pathname.startsWith(i.to)),
        )
      ) {
        open.add(section.id);
      }
    }
    return open;
  }, [location.pathname]);
  const [openIds, setOpenIds] = useState<Set<string>>(initiallyOpen);

  useEffect(() => {
    setOpenIds((prev) => {
      const next = new Set(prev);
      for (const section of sections) {
        if (
          section.items.some(
            (i) =>
              location.pathname === i.to ||
              (i.to !== "/panel" && location.pathname.startsWith(i.to)),
          )
        ) {
          next.add(section.id);
        }
      }
      return next;
    });
  }, [location.pathname]);

  function toggle(id: string) {
    setOpenIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <nav className="max-h-[calc(100dvh-8rem)] overflow-y-auto overscroll-contain py-1">
      <NavLink
        to="/panel"
        end
        onClick={onNavigate}
        className={({ isActive }) =>
          `flex min-h-11 items-center gap-2.5 px-3 py-2.5 text-sm sm:min-h-0 sm:py-2 ${
            isActive ? "bg-cp-orange-soft font-semibold text-cp-orange-dark" : "text-cp-text hover:bg-cp-canvas"
          }`
        }
      >
        <Home className="h-4 w-4 text-cp-orange" />
        Accueil
      </NavLink>
      {sections.map((section) => {
        const open = openIds.has(section.id);
        return (
          <div key={section.id} className="border-t border-cp-border/70">
            <button
              type="button"
              className="flex min-h-11 w-full items-center justify-between px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-cp-muted hover:bg-cp-canvas sm:min-h-0 sm:py-2"
              onClick={() => toggle(section.id)}
              aria-expanded={open}
            >
              {section.label}
              <ChevronDown className={`h-3.5 w-3.5 transition ${open ? "rotate-180" : ""}`} />
            </button>
            {open && (
              <div className="pb-1">
                {section.items.map((item) => (
                  <NavLink
                    key={`${section.id}-${item.to}-${item.label}`}
                    to={item.to}
                    end={item.end}
                    onClick={onNavigate}
                    className={({ isActive }) =>
                      `flex min-h-10 items-center gap-2.5 px-3 py-2 pl-4 text-sm sm:min-h-0 sm:py-1.5 ${
                        isActive
                          ? "bg-cp-orange-soft font-medium text-cp-orange-dark"
                          : "text-cp-text hover:bg-cp-canvas"
                      }`
                    }
                  >
                    <item.icon className="h-3.5 w-3.5 shrink-0 text-cp-orange" />
                    <span className="truncate">{item.label}</span>
                  </NavLink>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </nav>
  );
}

function AsideMenu() {
  return (
    <aside className="hidden w-56 shrink-0 lg:block">
      <div className="vz-panel sticky top-4 overflow-hidden">
        <div className="border-b border-cp-border bg-cp-header px-3 py-2.5 text-xs font-semibold tracking-wide text-white">
          Menu
        </div>
        <ToolsNav />
      </div>
    </aside>
  );
}

export function ClientShell() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const theme = useThemeStore((s) => s.theme);
  const toggle = useThemeStore((s) => s.toggle);
  const location = useLocation();
  const [navOpen, setNavOpen] = useState(false);

  useEffect(() => {
    setNavOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    document.title = "Panneau client · V-zone";
  }, []);

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

  return (
    <div className="vz-client-canvas min-h-screen dark:bg-surface-dark">
      <header className="sticky top-0 z-20 border-b border-black/20 bg-cp-header text-white shadow-md">
        <div className="flex items-center justify-between gap-2 px-3 py-2.5 sm:px-4">
          <div className="flex min-w-0 items-center gap-2">
            <button
              type="button"
              className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg hover:bg-white/15 lg:hidden"
              aria-label="Ouvrir le menu"
              aria-expanded={navOpen}
              onClick={() => setNavOpen(true)}
            >
              <Menu className="h-5 w-5" />
            </button>
            <NavLink to="/panel" className="flex min-w-0 items-center gap-2">
              <img
                src="/vzone-mark.svg"
                alt=""
                className="h-8 w-8 shrink-0 rounded-lg shadow-sm"
                width={32}
                height={32}
              />
              <div className="min-w-0">
                <p className="text-sm font-semibold tracking-wide">V-zone</p>
                <p className="truncate text-[11px] text-white/85">
                  {user?.role === "reseller"
                    ? "cPanel · Espace client (revendeur)"
                    : "cPanel · Espace client"}
                </p>
              </div>
            </NavLink>
          </div>
          <div className="flex shrink-0 items-center gap-1 text-sm sm:gap-2">
            {user?.role === "reseller" && (
              <a
                href={whmPortalUrl("/whm")}
                className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-cp-orange px-2.5 text-xs font-bold uppercase tracking-wide text-white shadow hover:brightness-110 sm:px-3"
                title="Ouvrir WHM (gestion des comptes)"
              >
                <Server className="h-3.5 w-3.5" />
                <span className="hidden xs:inline sm:inline">WHM</span>
              </a>
            )}
            <span className="hidden max-w-[8rem] truncate rounded-full bg-white/15 px-2.5 py-1 text-xs sm:inline">
              {user?.username}
            </span>
            <button
              type="button"
              className="inline-flex h-10 w-10 items-center justify-center rounded-lg transition hover:bg-white/15"
              onClick={toggle}
              aria-label={theme === "dark" ? "Passer en mode clair" : "Passer en mode sombre"}
            >
              {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </button>
            <button
              type="button"
              className="inline-flex h-10 items-center gap-1.5 rounded-lg px-2 transition hover:bg-white/15 sm:px-2.5"
              onClick={() => void logout()}
              aria-label="Se déconnecter"
            >
              <LogOut className="h-4 w-4" />
              <span className="hidden sm:inline">Déconnexion</span>
            </button>
          </div>
        </div>
      </header>

      {navOpen ? (
        <>
          <button
            type="button"
            className="fixed inset-0 z-40 bg-black/45 backdrop-blur-[1px] lg:hidden"
            aria-label="Fermer le menu"
            onClick={() => setNavOpen(false)}
          />
          <div className="fixed inset-y-0 left-0 z-50 flex w-[min(19rem,90vw)] flex-col bg-cp-canvas p-3 shadow-2xl dark:bg-ink-950 lg:hidden">
            <div className="mb-2 flex items-center justify-between gap-2 px-1">
              <div>
                <p className="text-sm font-semibold text-cp-text">Menu</p>
                {user?.username ? (
                  <p className="text-xs text-cp-muted">Connecté · {user.username}</p>
                ) : null}
              </div>
              <button
                type="button"
                className="inline-flex h-10 w-10 items-center justify-center rounded-lg text-cp-muted hover:bg-white hover:text-cp-text dark:hover:bg-ink-900"
                aria-label="Fermer"
                onClick={() => setNavOpen(false)}
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="vz-panel min-h-0 flex-1 overflow-hidden">
              <ToolsNav onNavigate={() => setNavOpen(false)} />
            </div>
          </div>
        </>
      ) : null}

      <div className="mx-auto flex max-w-[1400px] gap-3 p-3 pb-[max(1rem,env(safe-area-inset-bottom))] sm:gap-4 sm:p-4 md:gap-5 md:p-5 lg:gap-6">
        <AsideMenu />
        <main className="min-w-0 flex-1 space-y-4 animate-fade-up">
          <Outlet />
        </main>
        <HostUsagePanel />
      </div>
      <OperationProgressHost />
      <AiDeploymentAssistant />
    </div>
  );
}
