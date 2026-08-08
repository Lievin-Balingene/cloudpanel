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
  Network,
  GitBranch,
  Box,
  HardDrive,
  KeyRound,
  Shield,
  ChevronDown,
  Activity,
  Clock,
} from "lucide-react";
import { useMemo, useState } from "react";
import { apiRequest } from "@/lib/api";
import { formatBytes } from "@/lib/format";
import { useAuthStore } from "@/stores/auth";
import { useThemeStore } from "@/stores/theme";
import { OperationProgressHost } from "@/components/OperationProgressHost";
import { AiDeploymentAssistant } from "@/components/AiDeploymentAssistant";
import type { DashboardOverview } from "@/types";

type NavItem = { to: string; label: string; icon: typeof Home; end?: boolean };

type NavSection = { id: string; label: string; items: NavItem[] };

const sections: NavSection[] = [
  {
    id: "files",
    label: "Files",
    items: [
      { to: "/panel/files", label: "File Manager", icon: FolderOpen },
      { to: "/panel/ftp", label: "FTP Accounts", icon: Upload },
      { to: "/panel/backups", label: "Backup", icon: HardDrive },
    ],
  },
  {
    id: "databases",
    label: "Databases",
    items: [{ to: "/panel/databases", label: "MySQL® / PostgreSQL", icon: Database }],
  },
  {
    id: "domains",
    label: "Domains",
    items: [
      { to: "/panel/domains", label: "Domains", icon: AppWindow },
      { to: "/panel/dns", label: "Zone Editor", icon: Globe },
    ],
  },
  {
    id: "email",
    label: "Email",
    items: [{ to: "/panel/email", label: "Email Accounts", icon: Mail }],
  },
  {
    id: "advanced",
    label: "Advanced",
    items: [{ to: "/panel/cron", label: "Cron Jobs", icon: Clock }],
  },
  {
    id: "metrics",
    label: "Metrics",
    items: [{ to: "/panel/package", label: "Resource Usage", icon: Activity }],
  },
  {
    id: "security",
    label: "Security",
    items: [
      { to: "/panel/security", label: "Security / 2FA", icon: KeyRound },
      { to: "/panel/domains", label: "SSL/TLS Status", icon: Shield },
    ],
  },
  {
    id: "software",
    label: "Software",
    items: [
      { to: "/panel/php", label: "Select PHP Version", icon: FileCode2 },
      { to: "/panel/wordpress", label: "WordPress", icon: LayoutTemplate },
      { to: "/panel/kubernetes", label: "Kubernetes", icon: Network },
      { to: "/panel/terminal", label: "Terminal SSH", icon: Terminal },
      { to: "/panel/python", label: "Setup Python App", icon: Code2 },
      { to: "/panel/node", label: "Setup Node.js App", icon: Terminal },
      { to: "/panel/git", label: "Git Version Control", icon: GitBranch },
      { to: "/panel/docker", label: "Docker Containers", icon: Box },
    ],
  },
  {
    id: "preferences",
    label: "Preferences",
    items: [
      { to: "/panel", label: "Home", icon: Home, end: true },
      { to: "/panel/package", label: "Mon package", icon: Package },
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
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span className="font-medium text-cp-text">{label}</span>
        <span className="text-cp-muted">{usedLabel}</span>
      </div>
      <div className="h-2 overflow-hidden rounded bg-[#e2e8f0] dark:bg-ink-800">
        <div
          className={`h-full rounded ${pct >= 90 ? "bg-cp-danger" : pct >= 70 ? "bg-amber-500" : "bg-cp-orange"}`}
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
  // Préférer used_mb (explicite) — évite toute confusion d'unités avec le disque serveur
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
          <div className="border-b border-cp-border bg-cp-header px-3 py-2 text-xs font-semibold uppercase tracking-wide text-white">
            General Information
          </div>
          <dl className="space-y-2 p-3 text-sm">
            <div className="flex justify-between gap-2">
              <dt className="text-cp-muted">Current User</dt>
              <dd className="font-medium text-cp-text">{account?.username ?? user?.username ?? "—"}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-cp-muted">Primary Domain</dt>
              <dd className="truncate font-medium text-cp-text" title={account?.primary_domain || undefined}>
                {account?.primary_domain || "—"}
              </dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-cp-muted">Home Directory</dt>
              <dd className="truncate font-medium text-cp-text" title={account?.home_directory || undefined}>
                {account?.home_directory || `/home/${user?.username ?? "…"}`}
              </dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-cp-muted">Last Login IP</dt>
              <dd className="font-medium text-cp-text">{account?.last_login_ip || "—"}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-cp-muted">Theme</dt>
              <dd className="font-medium text-cp-text">V-zone</dd>
            </div>
          </dl>
        </div>

        <div className="vz-panel overflow-hidden">
          <div className="border-b border-cp-border bg-cp-header px-3 py-2 text-xs font-semibold uppercase tracking-wide text-white">
            Statistics
          </div>
          <div className="space-y-3 p-3">
            <UsageBar label="Disk Usage" usedLabel={diskLabel} percent={diskPct} />
            {data?.disk?.breakdown_mb && Object.keys(data.disk.breakdown_mb).length > 0 && diskUsedMb >= 1 && (
              <p className="text-[10px] leading-relaxed text-cp-muted">
                {Object.entries(data.disk.breakdown_mb)
                  .filter(([, mb]) => mb >= 0.1)
                  .slice(0, 4)
                  .map(([name, mb]) => `${name}: ${formatUsedMb(mb)} Mo`)
                  .join(" · ") || "Home quasi vide"}
              </p>
            )}
            <UsageBar
              label="Bandwidth"
              usedLabel={
                pkg?.unlimited_bandwidth
                  ? "∞"
                  : pkg
                    ? `0 / ${pkg.bandwidth_mb} Mo`
                    : "—"
              }
              percent={0}
            />
            <InfoRow label="Package" value={data?.my_package ?? pkg?.name ?? "Aucun"} />
            <InfoRow label="Domains" value={fmtQuota(usage?.domains ?? data?.domains_total, pkg?.domains)} />
            <InfoRow label="Email Accounts" value={fmtQuota(usage?.emails, pkg?.emails)} />
            <InfoRow label="Databases" value={fmtQuota(usage?.databases, pkg?.databases)} />
            <InfoRow label="FTP Accounts" value={fmtQuota(usage?.ftp_accounts, pkg?.ftp_accounts)} />
            <InfoRow label="DNS Zones" value={String(usage?.dns_zones ?? data?.dns_zones ?? 0)} />
          </div>
        </div>
      </div>
    </aside>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between border-t border-cp-border pt-2 text-xs first:border-0 first:pt-0">
      <span className="text-cp-muted">{label}</span>
      <span className="font-semibold text-cp-text">{value}</span>
    </div>
  );
}

function AsideMenu() {
  const location = useLocation();
  const initiallyOpen = useMemo(() => {
    const open = new Set<string>(["files", "domains", "email", "software"]);
    for (const section of sections) {
      if (section.items.some((i) => location.pathname === i.to || (i.to !== "/panel" && location.pathname.startsWith(i.to)))) {
        open.add(section.id);
      }
    }
    return open;
  }, [location.pathname]);
  const [openIds, setOpenIds] = useState<Set<string>>(initiallyOpen);

  function toggle(id: string) {
    setOpenIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <aside className="hidden w-56 shrink-0 md:block">
      <div className="vz-panel sticky top-4 overflow-hidden">
        <div className="border-b border-cp-border bg-cp-header px-3 py-2 text-xs font-semibold uppercase tracking-wide text-white">
          Tools
        </div>
        <nav className="max-h-[calc(100vh-8rem)] overflow-y-auto py-1">
          <NavLink
            to="/panel"
            end
            className={({ isActive }) =>
              `flex items-center gap-2 px-3 py-2 text-sm ${
                isActive ? "bg-cp-orange-soft font-semibold text-cp-orange-dark" : "text-cp-text hover:bg-cp-canvas"
              }`
            }
          >
            <Home className="h-4 w-4 text-cp-orange" />
            Home
          </NavLink>
          {sections.map((section) => {
            const open = openIds.has(section.id);
            return (
              <div key={section.id} className="border-t border-cp-border/70">
                <button
                  type="button"
                  className="flex w-full items-center justify-between px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-cp-muted hover:bg-cp-canvas"
                  onClick={() => toggle(section.id)}
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
                        className={({ isActive }) =>
                          `flex items-center gap-2 px-3 py-1.5 pl-4 text-sm ${
                            isActive
                              ? "bg-cp-orange-soft font-medium text-cp-orange-dark"
                              : "text-cp-text hover:bg-cp-canvas"
                          }`
                        }
                      >
                        <item.icon className="h-3.5 w-3.5 text-cp-orange" />
                        {item.label}
                      </NavLink>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </nav>
      </div>
    </aside>
  );
}

export function ClientShell() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const theme = useThemeStore((s) => s.theme);
  const toggle = useThemeStore((s) => s.toggle);

  return (
    <div className="vz-client-canvas min-h-screen dark:bg-surface-dark">
      <header className="sticky top-0 z-20 border-b border-black/20 bg-cp-header text-white shadow-md">
        <div className="flex items-center justify-between px-4 py-2.5">
          <div className="flex items-center gap-2.5">
            <img
              src="/vzone-mark.svg"
              alt="V-zone"
              className="h-8 w-8 rounded-lg shadow-sm"
              width={32}
              height={32}
            />
            <div>
              <p className="text-sm font-semibold tracking-wide">V-zone</p>
              <p className="text-[11px] text-white/85">Panneau client</p>
            </div>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <span className="hidden rounded-full bg-white/15 px-2.5 py-1 sm:inline">{user?.username}</span>
            <button type="button" className="rounded-lg px-2 py-1.5 transition hover:bg-white/15" onClick={toggle}>
              {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </button>
            <button
              type="button"
              className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 transition hover:bg-white/15"
              onClick={() => void logout()}
            >
              <LogOut className="h-4 w-4" />
              Logout
            </button>
          </div>
        </div>
      </header>

      <div className="mx-auto flex max-w-[1400px] gap-5 p-4 md:gap-6 md:p-6">
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
