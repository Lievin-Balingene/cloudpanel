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
        <div className="relative overflow-hidden bg-gradient-to-br from-[#1a3354] via-[#243d5c] to-[#2f5680] px-4 pb-4 pt-5 text-white sm:px-5 sm:pb-5 sm:pt-6">
          <div
            className="pointer-events-none absolute -right-8 -top-10 h-40 w-40 rounded-full bg-white/10 blur-2xl"
            aria-hidden
          />
          <div
            className="pointer-events-none absolute -bottom-12 left-1/3 h-32 w-32 rounded-full bg-cp-orange/20 blur-3xl"
            aria-hidden
          />
          <p className="relative text-[10px] font-semibold uppercase tracking-[0.16em] text-white/65">
            Informations générales
          </p>
          <h1 className="relative mt-1.5 text-[1.35rem] font-semibold tracking-tight sm:text-2xl">
            {t("panelGreeting")},{" "}
            <span className="text-white">{greetName}</span>
          </h1>
          <p className="relative mt-1.5 max-w-xl text-[13px] leading-relaxed text-white/80 sm:text-sm">
            {data?.account?.primary_domain
              ? tweaks.panel_locale === "en"
                ? `Primary domain: ${data.account.primary_domain}.`
                : `Domaine principal : ${data.account.primary_domain}.`
              : tweaks.panel_locale === "en"
                ? "Manage your sites, email and files."
                : "Gérez vos sites, e-mails et fichiers."}
            {data?.my_package ? (
              <>
                {" "}
                {tweaks.panel_locale === "en" ? "Plan" : "Forfait"}{" "}
                <strong className="font-semibold text-white">{data.my_package}</strong>.
              </>
            ) : null}
          </p>

          <label className="relative mt-4 block max-w-md">
            <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-white/55" />
            <input
              className="w-full rounded-2xl border border-white/20 bg-white/12 py-3 pl-10 pr-3 text-sm text-white placeholder:text-white/50 outline-none shadow-inner backdrop-blur-md transition focus:border-white/45 focus:bg-white/18"
              placeholder={t("toolsSearch")}
              value={q}
              onChange={(e) => setQ(e.target.value)}
              aria-label={t("toolsSearch")}
            />
          </label>

          <div className="vz-chip-scroll relative mt-3.5 sm:hidden">
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

        <div className="hidden flex-wrap gap-2 border-t border-cp-border px-3 py-3 sm:flex sm:px-4 dark:border-ink-800">
          {quickLinks.map((a) => (
            <Link
              key={a.to + a.label}
              to={a.to}
              className="inline-flex min-h-9 items-center gap-1.5 rounded-full border border-cp-border bg-cp-canvas px-3 text-xs font-medium text-cp-text transition hover:border-cp-orange/50 hover:bg-white dark:border-ink-700 dark:bg-ink-900 dark:hover:bg-ink-800"
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
