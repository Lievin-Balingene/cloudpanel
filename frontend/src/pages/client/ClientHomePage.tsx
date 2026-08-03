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
  GitBranch,
  Box,
  HardDrive,
  KeyRound,
  Activity,
  Search,
  Layers,
  Lock,
  Gauge,
} from "lucide-react";
import { useMemo, useState } from "react";
import { apiRequest } from "@/lib/api";
import type { DashboardOverview } from "@/types";

type Tool = {
  to: string;
  label: string;
  desc: string;
  icon: LucideIcon;
  disabled?: boolean;
};

type SectionTheme = {
  accent: string;
  soft: string;
  border: string;
  icon: LucideIcon;
};

type Section = {
  id: string;
  title: string;
  subtitle: string;
  theme: SectionTheme;
  tools: Tool[];
};

const sections: Section[] = [
  {
    id: "files",
    title: "Files",
    subtitle: "Fichiers, FTP et sauvegardes",
    theme: {
      accent: "#1a5fb4",
      soft: "#e8f0fa",
      border: "#c5d8ef",
      icon: Folder,
    },
    tools: [
      { to: "/panel/files", label: "File Manager", desc: "Parcourir et éditer vos fichiers", icon: Folder },
      { to: "/panel/ftp", label: "FTP Accounts", desc: "Comptes FTP et quotas", icon: Upload },
      { to: "/panel/backups", label: "Backup", desc: "Sauvegarder et restaurer", icon: HardDrive },
    ],
  },
  {
    id: "databases",
    title: "Databases",
    subtitle: "MySQL / MariaDB / PostgreSQL",
    theme: {
      accent: "#0f766e",
      soft: "#e6f5f3",
      border: "#b7e0da",
      icon: Database,
    },
    tools: [
      {
        to: "/panel/databases",
        label: "Databases",
        desc: "Bases, users, privilèges, phpMyAdmin",
        icon: Database,
      },
    ],
  },
  {
    id: "domains",
    title: "Domains",
    subtitle: "Domaines, DNS et certificats",
    theme: {
      accent: "#1e4d8c",
      soft: "#e9eef8",
      border: "#c2d0e8",
      icon: Globe,
    },
    tools: [
      { to: "/panel/domains", label: "Domains", desc: "Principal, addon, sous-domaines", icon: AppWindow },
      { to: "/panel/dns", label: "Zone Editor", desc: "Enregistrements DNS", icon: Globe },
      { to: "/panel/domains", label: "SSL / TLS", desc: "Statut des certificats", icon: Shield },
    ],
  },
  {
    id: "email",
    title: "Email",
    subtitle: "Boîtes et webmail Roundcube",
    theme: {
      accent: "#b45309",
      soft: "#fef3e6",
      border: "#f0d4a8",
      icon: Mail,
    },
    tools: [
      { to: "/panel/email", label: "Email Accounts", desc: "Créer et gérer les boîtes", icon: Mail },
    ],
  },
  {
    id: "metrics",
    title: "Metrics",
    subtitle: "Quotas et consommation",
    theme: {
      accent: "#475569",
      soft: "#eef2f6",
      border: "#d0d7e0",
      icon: Gauge,
    },
    tools: [
      {
        to: "/panel/package",
        label: "Resource Usage",
        desc: "Disque, mails, apps — limites package",
        icon: Activity,
      },
    ],
  },
  {
    id: "security",
    title: "Security",
    subtitle: "Compte et chiffrement",
    theme: {
      accent: "#9f1239",
      soft: "#fce8ee",
      border: "#efc2cf",
      icon: Lock,
    },
    tools: [
      { to: "/panel/security", label: "Security", desc: "2FA et mot de passe", icon: KeyRound },
      { to: "/panel/domains", label: "SSL Status", desc: "Certificats HTTPS", icon: Shield },
    ],
  },
  {
    id: "software",
    title: "Software",
    subtitle: "Runtimes, Git et conteneurs",
    theme: {
      accent: "#0e7490",
      soft: "#e5f6fa",
      border: "#b5dde8",
      icon: Layers,
    },
    tools: [
      { to: "/panel/php", label: "PHP Version", desc: "Sélecteur MultiPHP", icon: FileCode2 },
      { to: "/panel/python", label: "Python App", desc: "WSGI / ASGI", icon: Code2 },
      { to: "/panel/node", label: "Node.js App", desc: "npm et process", icon: Terminal },
      { to: "/panel/git", label: "Git", desc: "Clone, pull, deploy", icon: GitBranch },
      { to: "/panel/docker", label: "Docker", desc: "Images, ports, logs", icon: Box },
    ],
  },
  {
    id: "preferences",
    title: "Preferences",
    subtitle: "Compte et plan d'hébergement",
    theme: {
      accent: "#152536",
      soft: "#e8eef4",
      border: "#c5ced8",
      icon: Package,
    },
    tools: [
      { to: "/panel/package", label: "Package", desc: "Votre plan d'hébergement", icon: Package },
      { to: "/panel/security", label: "Password & Security", desc: "Sécurité du compte", icon: KeyRound },
    ],
  },
];

export function ClientHomePage() {
  const [q, setQ] = useState("");
  const { data } = useQuery({
    queryKey: ["dashboard-overview"],
    queryFn: () => apiRequest<DashboardOverview>("/dashboard/overview/"),
  });

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return sections;
    return sections
      .map((section) => ({
        ...section,
        tools: section.tools.filter(
          (t) =>
            t.label.toLowerCase().includes(needle) ||
            t.desc.toLowerCase().includes(needle) ||
            section.title.toLowerCase().includes(needle),
        ),
      }))
      .filter((s) => s.tools.length > 0);
  }, [q]);

  return (
    <div className="space-y-5 animate-fade-up">
      <div className="vz-panel overflow-hidden">
        <div className="border-b border-cp-border bg-gradient-to-r from-[#152536] to-[#1e4d8c] px-4 py-4 text-white">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h1 className="font-display text-xl font-semibold tracking-tight">Tableau de bord</h1>
              <p className="mt-1 text-sm text-white/75">
                Package : <span className="font-semibold text-white">{data?.my_package ?? "non assigné"}</span>
                {" · "}
                Domaines : <span className="font-semibold text-white">{data?.domains_total ?? 0}</span>
                {" · "}
                Zones DNS : <span className="font-semibold text-white">{data?.dns_zones ?? 0}</span>
              </p>
            </div>
            <label className="relative block w-full max-w-xs">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-white/50" />
              <input
                className="w-full rounded-lg border border-white/20 bg-white/10 py-2 pl-9 pr-3 text-sm text-white placeholder:text-white/45 outline-none backdrop-blur focus:border-white/40 focus:ring-2 focus:ring-white/20"
                placeholder="Rechercher un outil…"
                value={q}
                onChange={(e) => setQ(e.target.value)}
              />
            </label>
          </div>
        </div>
      </div>

      {filtered.map((section) => {
        const SectionIcon = section.theme.icon;
        return (
          <section
            key={section.id}
            className="vz-panel overflow-hidden"
            style={{ borderColor: section.theme.border }}
          >
            <div
              className="flex items-center gap-3 border-b px-4 py-3"
              style={{
                background: `linear-gradient(90deg, ${section.theme.soft} 0%, transparent 70%)`,
                borderColor: section.theme.border,
              }}
            >
              <span
                className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-white shadow-sm"
                style={{ backgroundColor: section.theme.accent }}
              >
                <SectionIcon className="h-4.5 w-4.5 h-4 w-4" />
              </span>
              <div className="min-w-0">
                <h2
                  className="text-sm font-bold uppercase tracking-[0.06em]"
                  style={{ color: section.theme.accent }}
                >
                  {section.title}
                </h2>
                <p className="text-xs text-cp-muted">{section.subtitle}</p>
              </div>
            </div>

            <div className="grid gap-3 p-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {section.tools.map((tool) => {
                const ToolIcon = tool.icon;
                const body = (
                  <div
                    className={`cp-tool-tile ${
                      tool.disabled ? "cursor-not-allowed opacity-45" : ""
                    }`}
                    style={{ borderColor: section.theme.border }}
                  >
                    <span
                      className="absolute inset-y-0 left-0 w-1 rounded-l-xl"
                      style={{ backgroundColor: section.theme.accent }}
                      aria-hidden
                    />
                    <span
                      className="ml-1 inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg"
                      style={{
                        backgroundColor: section.theme.soft,
                        color: section.theme.accent,
                      }}
                    >
                      <ToolIcon className="h-5 w-5" />
                    </span>
                    <div className="min-w-0 pt-0.5">
                      <p className="text-sm font-semibold text-cp-text">{tool.label}</p>
                      <p className="mt-0.5 text-xs leading-snug text-cp-muted">{tool.desc}</p>
                    </div>
                  </div>
                );

                if (tool.disabled) {
                  return (
                    <div key={`${section.id}-${tool.label}`} aria-disabled>
                      {body}
                    </div>
                  );
                }
                return (
                  <Link
                    key={`${section.id}-${tool.label}`}
                    to={tool.to}
                    className="group block focus:outline-none focus-visible:ring-2 focus-visible:ring-cp-link/40 rounded-xl"
                  >
                    {body}
                  </Link>
                );
              })}
            </div>
          </section>
        );
      })}

      {filtered.length === 0 && (
        <div className="vz-panel p-8 text-center text-sm text-cp-muted">
          Aucun outil ne correspond à « {q} ».
        </div>
      )}
    </div>
  );
}
