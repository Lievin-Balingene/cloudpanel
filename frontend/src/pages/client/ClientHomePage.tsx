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

type Section = { title: string; tools: Tool[] };

const sections: Section[] = [
  {
    title: "FILES",
    tools: [
      { to: "/panel/files", label: "File Manager", desc: "Manage your files", icon: Folder },
      { to: "/panel/ftp", label: "FTP Accounts", desc: "Add FTP accounts", icon: Upload },
      { to: "/panel/backups", label: "Backup", desc: "Backup & restore", icon: HardDrive },
    ],
  },
  {
    title: "DATABASES",
    tools: [
      {
        to: "/panel/databases",
        label: "MySQL® Databases",
        desc: "Create and manage databases",
        icon: Database,
      },
    ],
  },
  {
    title: "DOMAINS",
    tools: [
      { to: "/panel/domains", label: "Domains", desc: "Create and manage domains", icon: AppWindow },
      { to: "/panel/dns", label: "Zone Editor", desc: "Manage DNS records", icon: Globe },
      { to: "/panel/domains", label: "SSL/TLS Status", desc: "View certificate status", icon: Shield },
    ],
  },
  {
    title: "EMAIL",
    tools: [
      { to: "/panel/email", label: "Email Accounts", desc: "Create email accounts", icon: Mail },
    ],
  },
  {
    title: "METRICS",
    tools: [
      {
        to: "/panel/package",
        label: "Resource Usage",
        desc: "View package quotas",
        icon: Activity,
      },
    ],
  },
  {
    title: "SECURITY",
    tools: [
      { to: "/panel/security", label: "Security", desc: "2FA & password policy", icon: KeyRound },
      { to: "/panel/domains", label: "SSL/TLS", desc: "Manage certificates", icon: Shield },
    ],
  },
  {
    title: "SOFTWARE",
    tools: [
      { to: "/panel/php", label: "Select PHP Version", desc: "MultiPHP Manager", icon: FileCode2 },
      { to: "/panel/python", label: "Setup Python App", desc: "WSGI / ASGI apps", icon: Code2 },
      { to: "/panel/node", label: "Setup Node.js App", desc: "npm & process", icon: Terminal },
      { to: "/panel/git", label: "Git Version Control", desc: "Clone & deploy", icon: GitBranch },
      { to: "/panel/docker", label: "Docker Containers", desc: "Images & logs", icon: Box },
    ],
  },
  {
    title: "ADVANCED",
    tools: [
      { to: "/panel/cron", label: "Cron Jobs", desc: "Coming soon", icon: Activity, disabled: true },
    ],
  },
  {
    title: "PREFERENCES",
    tools: [
      { to: "/panel/package", label: "Package", desc: "Your hosting plan", icon: Package },
      { to: "/panel/security", label: "Password & Security", desc: "Account security", icon: KeyRound },
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
    <div className="space-y-4 animate-fade-up">
      <div className="vz-panel p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold text-cp-text">Home</h1>
            <p className="text-sm text-cp-muted">
              Package : <strong>{data?.my_package ?? "non assigné"}</strong>
              {" · "}
              Domaines : <strong>{data?.domains_total ?? 0}</strong>
              {" · "}
              Zones DNS : <strong>{data?.dns_zones ?? 0}</strong>
            </p>
          </div>
          <label className="relative block w-full max-w-xs">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-cp-muted" />
            <input
              className="vz-input pl-9"
              placeholder="Search Tools"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </label>
        </div>
      </div>

      {filtered.map((section) => (
        <section key={section.title} className="vz-panel overflow-hidden">
          <div className="border-b border-cp-border bg-[#f7f9fb] px-4 py-2 dark:border-ink-800 dark:bg-ink-900">
            <h2 className="text-xs font-bold uppercase tracking-[0.08em] text-cp-muted">
              {section.title}
            </h2>
          </div>
          <div className="grid gap-2 p-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {section.tools.map((tool) => {
              const body = (
                <div
                  className={`flex items-start gap-3 rounded border border-transparent p-3 transition ${
                    tool.disabled
                      ? "cursor-not-allowed opacity-45"
                      : "hover:border-cp-border hover:bg-cp-canvas"
                  }`}
                >
                  <tool.icon className="mt-0.5 h-8 w-8 shrink-0 text-cp-orange" />
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-cp-text">{tool.label}</p>
                    <p className="text-xs text-cp-muted">{tool.desc}</p>
                  </div>
                </div>
              );
              if (tool.disabled) {
                return (
                  <div key={`${section.title}-${tool.label}`} aria-disabled>
                    {body}
                  </div>
                );
              }
              return (
                <Link key={`${section.title}-${tool.label}`} to={tool.to}>
                  {body}
                </Link>
              );
            })}
          </div>
        </section>
      ))}
    </div>
  );
}
