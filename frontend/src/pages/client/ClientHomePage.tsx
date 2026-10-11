import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import type { LucideIcon } from "lucide-react";
import {
  Globe,
  Package,
  Mail,
  Database,
  Folder,
  Shield,
  AppWindow,
  Upload,
  Code2,
  Terminal,
  FileCode2,
  LayoutTemplate,
  GitBranch,
  Box,
  HardDrive,
  KeyRound,
  Search,
  Server,
  Clock,
  ArrowRight,
  PieChart,
  FileLock2,
  BarChart3,
  Lock,
  Ban,
  Settings,
  Gauge,
} from "lucide-react";
import { useMemo, useState } from "react";
import { apiRequest } from "@/lib/api";
import { formatBytes } from "@/lib/format";
import { usePanelI18n, usePanelTweaks } from "@/lib/panelTweaks";
import { whmPortalUrl } from "@/lib/portal";
import { useAuthStore } from "@/stores/auth";
import type { DashboardOverview } from "@/types";

type Tool = { to: string; label: string; icon: LucideIcon };
type Section = { title: string; tools: Tool[] };

const sections: Section[] = [
  {
    title: "Fichiers",
    tools: [
      { to: "/panel/files", label: "Gestionnaire de fichiers", icon: Folder },
      { to: "/panel/disk-usage", label: "Utilisation disque", icon: PieChart },
      { to: "/panel/directory-privacy", label: "Confidentialité dossiers", icon: FileLock2 },
      { to: "/panel/ftp", label: "Comptes FTP", icon: Upload },
      { to: "/panel/backups", label: "Sauvegardes", icon: HardDrive },
    ],
  },
  {
    title: "Bases de données",
    tools: [{ to: "/panel/databases", label: "MySQL / PostgreSQL", icon: Database }],
  },
  {
    title: "Domaines",
    tools: [
      { to: "/panel/domains", label: "Domaines", icon: AppWindow },
      { to: "/panel/dns", label: "Éditeur de zone DNS", icon: Globe },
    ],
  },
  {
    title: "E-mail",
    tools: [{ to: "/panel/email", label: "Comptes e-mail", icon: Mail }],
  },
  {
    title: "Statistiques",
    tools: [
      { to: "/panel/metrics", label: "Visiteurs & erreurs", icon: BarChart3 },
      { to: "/panel/package", label: "Ressources & quotas", icon: Gauge },
    ],
  },
  {
    title: "Sécurité",
    tools: [
      { to: "/panel/security", label: "Mot de passe & 2FA", icon: KeyRound },
      { to: "/panel/ssh-keys", label: "Clés SSH", icon: Lock },
      { to: "/panel/ip-blocker", label: "Bloqueur d’IP", icon: Ban },
      { to: "/panel/domains", label: "SSL / TLS", icon: Shield },
    ],
  },
  {
    title: "Logiciels",
    tools: [
      { to: "/panel/php", label: "MultiPHP Manager", icon: FileCode2 },
      { to: "/panel/wordpress", label: "WordPress", icon: LayoutTemplate },
      { to: "/panel/python", label: "Application Python", icon: Code2 },
      { to: "/panel/node", label: "Application Node.js", icon: Terminal },
      { to: "/panel/git", label: "Contrôle de version Git", icon: GitBranch },
      { to: "/panel/docker", label: "Docker", icon: Box },
    ],
  },
  {
    title: "Avancé",
    tools: [
      { to: "/panel/cron", label: "Tâches Cron", icon: Clock },
      { to: "/panel/terminal", label: "Terminal", icon: Terminal },
    ],
  },
  {
    title: "Préférences",
    tools: [
      { to: "/panel/preferences", label: "Préférences du compte", icon: Settings },
      { to: "/panel/package", label: "Mon forfait", icon: Package },
    ],
  },
];

function StatTile({
  label,
  value,
  to,
  icon: Icon,
  percent,
}: {
  label: string;
  value: string;
  to?: string;
  icon: LucideIcon;
  percent?: number;
}) {
  const pct =
    typeof percent === "number" ? Math.max(0, Math.min(100, percent)) : null;
  const inner = (
    <div className="vz-stat-tile">
      <div className="relative z-[1] flex items-start justify-between gap-2">
        <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-cp-muted">
          {label}
        </p>
        <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-cp-orange/10 text-cp-orange">
          <Icon className="h-3.5 w-3.5" />
        </span>
      </div>
      <p className="relative z-[1] mt-2 text-[15px] font-bold leading-tight tabular-nums text-cp-text sm:text-base">
        {value}
      </p>
      {pct != null ? (
        <div className="relative z-[1] mt-2.5 h-1.5 overflow-hidden rounded-full bg-[#e8eef4] dark:bg-ink-800">
          <div
            className={`h-full rounded-full transition-all ${
              pct >= 90 ? "bg-cp-danger" : pct >= 70 ? "bg-amber-500" : "bg-cp-orange"
            }`}
            style={{ width: `${pct}%` }}
          />
        </div>
      ) : null}
    </div>
  );
  if (!to) return inner;
  return (
    <Link to={to} className="block focus:outline-none focus-visible:ring-2 focus-visible:ring-cp-orange/40">
      {inner}
    </Link>
  );
}

export function ClientHomePage() {
  const user = useAuthStore((s) => s.user);
  const isReseller = user?.role === "reseller";
  const [q, setQ] = useState("");
  const { tweaks } = usePanelTweaks();
  const t = usePanelI18n();
  const compact = tweaks.compact_home_buttons;
  const { data } = useQuery({
    queryKey: ["dashboard-overview"],
    queryFn: () => apiRequest<DashboardOverview>("/dashboard/overview/"),
  });

  const greetName = user?.first_name?.trim() || user?.username || "bienvenue";
  const diskUsedMb =
    typeof data?.disk?.used_mb === "number"
      ? data.disk.used_mb
      : data?.disk
        ? data.disk.used / (1024 * 1024)
        : 0;
  const diskUsed =
    typeof data?.disk?.used_mb === "number"
      ? data.disk.used_mb < 10
        ? `${data.disk.used_mb.toFixed(1)} Mo`
        : `${Math.round(data.disk.used_mb)} Mo`
      : data?.disk
        ? formatBytes(data.disk.used)
        : "—";
  const diskQuota = data?.disk?.unlimited
    ? "∞"
    : data?.disk?.quota_mb
      ? `${data.disk.quota_mb} Mo`
      : data?.disk
        ? formatBytes(data.disk.total)
        : "—";
  const diskPct = data?.disk?.unlimited
    ? 0
    : data?.disk?.percent ??
      (data?.disk?.quota_mb && data.disk.quota_mb > 0
        ? Math.min(100, (diskUsedMb / data.disk.quota_mb) * 100)
        : undefined);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return sections;
    return sections
      .map((section) => ({
        ...section,
        tools: section.tools.filter(
          (tool) =>
            tool.label.toLowerCase().includes(needle) ||
            section.title.toLowerCase().includes(needle),
        ),
      }))
      .filter((s) => s.tools.length > 0);
  }, [q]);

  const quickLinks = [
    { to: "/panel/files", label: "Fichiers", icon: Folder },
    { to: "/panel/email", label: "E-mail", icon: Mail },
    { to: "/panel/wordpress", label: "WordPress", icon: LayoutTemplate },
    { to: "/panel/domains", label: "Domaines", icon: AppWindow },
    { to: "/panel/backups", label: "Sauvegarde", icon: HardDrive },
  ];

  return (
    <div className="space-y-4 animate-fade-up">
      {isReseller && (
        <a
          href={whmPortalUrl("/whm")}
          className="vz-panel flex items-center gap-3 border-cp-orange/40 bg-gradient-to-r from-cp-orange-soft to-white p-3.5 transition hover:shadow-md sm:gap-4 sm:p-4 dark:from-ink-900 dark:to-ink-950"
        >
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-cp-orange text-white shadow sm:h-12 sm:w-12">
            <Server className="h-5 w-5 sm:h-6 sm:w-6" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-bold text-cp-orange-dark">Espace revendeur (V-zone Admin)</p>
            <p className="text-xs text-cp-muted sm:text-sm">
              Créer et gérer les comptes de vos clients.
            </p>
          </div>
          <ArrowRight className="hidden h-4 w-4 shrink-0 text-cp-orange sm:block" />
        </a>
      )}

      <div className="vz-panel overflow-hidden">
        <div className="relative overflow-hidden bg-gradient-to-br from-[#152a45] via-[#1e3a55] to-[#2a5080] px-4 pb-5 pt-5 text-white sm:px-6 sm:pb-6 sm:pt-6">
          <div
            className="pointer-events-none absolute inset-0 opacity-[0.07]"
            style={{
              backgroundImage:
                "radial-gradient(circle at 1px 1px, #fff 1px, transparent 0)",
              backgroundSize: "22px 22px",
            }}
            aria-hidden
          />
          <div
            className="pointer-events-none absolute -right-10 -top-14 h-48 w-48 rounded-full bg-cp-orange/25 blur-3xl"
            aria-hidden
          />
          <div
            className="pointer-events-none absolute -bottom-16 left-1/4 h-40 w-40 rounded-full bg-sky-400/15 blur-3xl"
            aria-hidden
          />

          <div className="relative flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between sm:gap-6">
            <div className="min-w-0 flex-1">
              <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-white/55">
                Informations générales
              </p>
              <h1 className="mt-2 text-[1.5rem] font-semibold tracking-tight sm:text-[1.75rem]">
                {t("panelGreeting")},{" "}
                <span className="bg-gradient-to-r from-white to-orange-100 bg-clip-text text-transparent">
                  {greetName}
                </span>
              </h1>
              <div className="mt-2.5 flex flex-wrap items-center gap-2 text-[13px] sm:text-sm">
                {data?.account?.primary_domain ? (
                  <span className="inline-flex max-w-full items-center gap-1.5 rounded-lg bg-white/10 px-2.5 py-1 ring-1 ring-white/15">
                    <Globe className="h-3.5 w-3.5 shrink-0 text-sky-200" />
                    <span className="truncate text-white/90">
                      {data.account.primary_domain}
                    </span>
                  </span>
                ) : (
                  <span className="text-white/75">
                    {tweaks.panel_locale === "en"
                      ? "Manage your sites, email and files."
                      : "Gérez vos sites, e-mails et fichiers."}
                  </span>
                )}
                {data?.my_package ? (
                  <span className="inline-flex items-center gap-1.5 rounded-lg bg-cp-orange/20 px-2.5 py-1 font-medium text-orange-100 ring-1 ring-cp-orange/35">
                    <Package className="h-3.5 w-3.5 shrink-0" />
                    {data.my_package}
                  </span>
                ) : null}
              </div>
            </div>

            <label className="relative block w-full max-w-md shrink-0 sm:w-[min(100%,22rem)]">
              <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-[#7a8fa3]" />
              <input
                className="vz-hero-search w-full rounded-xl border border-white/25 bg-white py-3 pl-10 pr-3.5 text-sm font-medium text-[#1a2b3c] shadow-[0_8px_24px_rgba(0,0,0,0.18)] outline-none transition placeholder:font-normal placeholder:text-[#8a9bb0] focus:border-cp-orange focus:ring-2 focus:ring-cp-orange/35"
                placeholder={t("toolsSearch")}
                value={q}
                onChange={(e) => setQ(e.target.value)}
                aria-label={t("toolsSearch")}
                autoComplete="off"
                spellCheck={false}
              />
            </label>
          </div>

          <div className="vz-chip-scroll relative mt-4 sm:hidden">
            {quickLinks.map((a) => (
              <Link key={a.to} to={a.to} className="vz-quick-chip">
                <a.icon className="h-3.5 w-3.5 opacity-90" />
                {a.label}
              </Link>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2.5 p-3 sm:grid-cols-4 sm:gap-3 sm:p-4 xl:hidden">
          <StatTile
            label="Disque"
            value={`${diskUsed} / ${diskQuota}`}
            to="/panel/disk-usage"
            icon={HardDrive}
            percent={diskPct}
          />
          <StatTile
            label="Domaines"
            value={String(data?.domains_total ?? data?.usage?.domains ?? 0)}
            to="/panel/domains"
            icon={Globe}
          />
          <StatTile
            label="E-mails"
            value={String(data?.usage?.emails ?? 0)}
            to="/panel/email"
            icon={Mail}
          />
          <StatTile
            label="Bases"
            value={String(data?.usage?.databases ?? 0)}
            to="/panel/databases"
            icon={Database}
          />
        </div>

        <div className="hidden flex-wrap gap-2 border-t border-cp-border bg-[#f7f9fc]/80 px-4 py-3 sm:flex dark:border-ink-800 dark:bg-ink-900/40">
          {quickLinks.map((a) => (
            <Link
              key={a.to + a.label}
              to={a.to}
              className="inline-flex min-h-9 items-center gap-1.5 rounded-full border border-cp-border bg-white px-3.5 text-xs font-semibold text-cp-text shadow-sm transition hover:border-cp-orange/45 hover:text-cp-orange dark:border-ink-700 dark:bg-ink-900 dark:hover:bg-ink-800"
            >
              <a.icon className="h-3.5 w-3.5 text-cp-orange" />
              {a.label}
            </Link>
          ))}
        </div>
      </div>

      {filtered.map((section) => (
        <section key={section.title} className="vz-panel overflow-hidden">
          <div className="flex items-center justify-between border-b border-cp-border bg-gradient-to-r from-[#eef3f8] to-[#f7f9fc] px-3 py-2.5 sm:px-4 dark:border-ink-700 dark:from-ink-900 dark:to-ink-950">
            <h2 className="text-sm font-semibold text-cp-text">{section.title}</h2>
            <span className="rounded-full bg-white/80 px-2 py-0.5 text-[10px] font-semibold tabular-nums text-cp-muted dark:bg-ink-800">
              {section.tools.length}
            </span>
          </div>
          {/* Mobile : tuiles verticales ; desktop : rangées horizontales */}
          <div
            className={`grid p-3 sm:p-4 ${
              compact
                ? "grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4"
                : "grid-cols-2 gap-2.5 sm:grid-cols-3 sm:gap-3 lg:grid-cols-4"
            }`}
          >
            {section.tools.map((tool) => (
              <Link
                key={`${section.title}-${tool.label}`}
                to={tool.to}
                className="vz-tool-tile group sm:flex-row sm:items-center"
              >
                <span
                  className={`flex shrink-0 items-center justify-center rounded-xl bg-white text-cp-orange shadow-sm ring-1 ring-cp-border/50 transition group-hover:ring-cp-orange/35 dark:bg-ink-950 dark:ring-ink-700 ${
                    compact ? "h-9 w-9" : "h-11 w-11"
                  }`}
                >
                  <tool.icon className={compact ? "h-4 w-4" : "h-5 w-5"} />
                </span>
                <span
                  className={`min-w-0 font-medium leading-snug text-cp-text ${
                    compact ? "text-[13px]" : "text-sm sm:text-base"
                  }`}
                >
                  {tool.label}
                </span>
              </Link>
            ))}
          </div>
        </section>
      ))}

      {filtered.length === 0 && (
        <div className="vz-panel p-8 text-center text-sm text-cp-muted">
          Aucun outil ne correspond à « {q} ».
        </div>
      )}
    </div>
  );
}
