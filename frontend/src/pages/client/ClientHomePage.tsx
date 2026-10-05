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

function StatChip({
  label,
  value,
  to,
}: {
  label: string;
  value: string;
  to?: string;
}) {
  const inner = (
    <div className="rounded-xl border border-cp-border/70 bg-white/80 px-3 py-2.5 dark:border-ink-700 dark:bg-ink-900/70">
      <p className="text-[11px] font-medium uppercase tracking-wide text-cp-muted">{label}</p>
      <p className="mt-0.5 text-base font-semibold text-cp-text">{value}</p>
    </div>
  );
  if (!to) return inner;
  return (
    <Link to={to} className="block transition hover:-translate-y-0.5 hover:shadow-sm">
      {inner}
    </Link>
  );
}

export function ClientHomePage() {
  const user = useAuthStore((s) => s.user);
  const isReseller = user?.role === "reseller";
  const [q, setQ] = useState("");
  const { data } = useQuery({
    queryKey: ["dashboard-overview"],
    queryFn: () => apiRequest<DashboardOverview>("/dashboard/overview/"),
  });

  const greetName = user?.first_name?.trim() || user?.username || "bienvenue";
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

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return sections;
    return sections
      .map((section) => ({
        ...section,
        tools: section.tools.filter(
          (t) =>
            t.label.toLowerCase().includes(needle) ||
            section.title.toLowerCase().includes(needle),
        ),
      }))
      .filter((s) => s.tools.length > 0);
  }, [q]);

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
        <div className="bg-gradient-to-br from-[#1e3a5f] via-[#243d5c] to-[#2a4a6b] px-4 py-5 text-white sm:px-5 sm:py-6">
          <p className="text-xs font-medium uppercase tracking-wider text-white/70">
            Informations générales
          </p>
          <h1 className="mt-1 text-xl font-semibold tracking-tight sm:text-2xl">
            Bonjour, {greetName}
          </h1>
          <p className="mt-1 max-w-xl text-sm text-white/80">
            {data?.account?.primary_domain
              ? `Domaine principal : ${data.account.primary_domain}.`
              : "Gérez vos sites, e-mails et fichiers."}
            {data?.my_package ? (
              <>
                {" "}
                Forfait <strong className="text-white">{data.my_package}</strong>.
              </>
            ) : null}
          </p>
          <label className="relative mt-4 block max-w-md">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-white/50" />
            <input
              className="w-full rounded-xl border border-white/20 bg-white/10 py-2.5 pl-9 pr-3 text-sm text-white placeholder:text-white/50 outline-none backdrop-blur-sm transition focus:border-white/40 focus:bg-white/15"
              placeholder="Rechercher un outil…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              aria-label="Rechercher un outil"
            />
          </label>
        </div>

        <div className="grid grid-cols-2 gap-2 p-3 sm:grid-cols-4 sm:gap-3 sm:p-4 xl:hidden">
          <StatChip label="Disque" value={`${diskUsed} / ${diskQuota}`} to="/panel/disk-usage" />
          <StatChip
            label="Domaines"
            value={String(data?.domains_total ?? data?.usage?.domains ?? 0)}
            to="/panel/domains"
          />
          <StatChip
            label="E-mails"
            value={String(data?.usage?.emails ?? 0)}
            to="/panel/email"
          />
          <StatChip
            label="Bases"
            value={String(data?.usage?.databases ?? 0)}
            to="/panel/databases"
          />
        </div>

        <div className="flex flex-wrap gap-2 border-t border-cp-border px-3 py-3 sm:px-4 dark:border-ink-800">
          {[
            { to: "/panel/files", label: "Fichiers" },
            { to: "/panel/email", label: "E-mail" },
            { to: "/panel/wordpress", label: "WordPress" },
            { to: "/panel/domains", label: "Domaines" },
            { to: "/panel/backups", label: "Sauvegarde" },
          ].map((a) => (
            <Link
              key={a.to + a.label}
              to={a.to}
              className="inline-flex min-h-9 items-center rounded-full border border-cp-border bg-cp-canvas px-3 text-xs font-medium text-cp-text transition hover:border-cp-orange/50 hover:bg-white dark:border-ink-700 dark:bg-ink-900 dark:hover:bg-ink-800"
            >
              {a.label}
            </Link>
          ))}
        </div>
      </div>

      {filtered.map((section) => (
        <section key={section.title} className="vz-panel overflow-hidden">
          <div className="border-b border-cp-border bg-[#f0f4f8] px-3 py-2.5 sm:px-4 dark:border-ink-700 dark:bg-ink-900">
            <h2 className="text-sm font-semibold text-cp-text">{section.title}</h2>
          </div>
          <div className="grid grid-cols-2 gap-2 p-3 sm:grid-cols-3 sm:p-4 lg:grid-cols-4">
            {section.tools.map((tool) => (
              <Link
                key={`${section.title}-${tool.label}`}
                to={tool.to}
                className="group flex items-center gap-2.5 rounded-lg border border-cp-border/70 bg-[#f7f9fc] px-2.5 py-2 transition hover:border-cp-orange/45 hover:bg-white hover:shadow-sm dark:border-ink-700 dark:bg-ink-900/70 dark:hover:bg-ink-900"
              >
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white text-cp-orange shadow-sm ring-1 ring-cp-border/60 transition group-hover:ring-cp-orange/30 dark:bg-ink-950 dark:ring-ink-700">
                  <tool.icon className="h-4 w-4" />
                </span>
                <span className="min-w-0 truncate text-sm font-medium text-cp-text">
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
