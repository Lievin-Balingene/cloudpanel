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
  Network,
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
  desc?: string;
  icon: LucideIcon;
  disabled?: boolean;
};

type Section = { title: string; tools: Tool[] };

const sections: Section[] = [
  {
    title: "Files",
    tools: [
      { to: "/panel/files", label: "File Manager", icon: Folder },
      { to: "/panel/ftp", label: "FTP Accounts", icon: Upload },
      { to: "/panel/backups", label: "Backup", icon: HardDrive },
    ],
  },
  {
    title: "Databases",
    tools: [
      {
        to: "/panel/databases",
        label: "MySQL® Databases",
        icon: Database,
      },
    ],
  },
  {
    title: "Domains",
    tools: [
      { to: "/panel/domains", label: "Domains", icon: AppWindow },
      { to: "/panel/dns", label: "Zone Editor", icon: Globe },
      { to: "/panel/domains", label: "SSL/TLS Status", icon: Shield },
    ],
  },
  {
    title: "Email",
    tools: [
      { to: "/panel/email", label: "Email Accounts", icon: Mail },
    ],
  },
  {
    title: "Metrics",
    tools: [
      {
        to: "/panel/package",
        label: "Resource Usage",
        icon: Activity,
      },
    ],
  },
  {
    title: "Security",
    tools: [
      { to: "/panel/security", label: "Security", icon: KeyRound },
      { to: "/panel/domains", label: "SSL/TLS", icon: Shield },
    ],
  },
  {
    title: "Software",
    tools: [
      { to: "/panel/php", label: "Select PHP Version", icon: FileCode2 },
      { to: "/panel/wordpress", label: "WordPress", icon: LayoutTemplate },
      { to: "/panel/kubernetes", label: "Kubernetes", icon: Network },
      { to: "/panel/python", label: "Setup Python App", icon: Code2 },
      { to: "/panel/node", label: "Setup Node.js App", icon: Terminal },
      { to: "/panel/git", label: "Git Version Control", icon: GitBranch },
      { to: "/panel/docker", label: "Docker Containers", icon: Box },
    ],
  },
  {
    title: "Advanced",
    tools: [
      { to: "/panel/cron", label: "Cron Jobs", icon: Activity },
    ],
  },
  {
    title: "Preferences",
    tools: [
      { to: "/panel/package", label: "Package", icon: Package },
      { to: "/panel/security", label: "Password & Security", icon: KeyRound },
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
            (t.desc ?? "").toLowerCase().includes(needle) ||
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
            <h1 className="text-lg font-semibold text-cp-text">Home</h1>
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
          <div className="border-b border-cp-border bg-[#f0f4f8] px-3 py-2.5 dark:border-ink-700 dark:bg-ink-900">
            <h2 className="text-[11px] font-semibold uppercase tracking-wide text-cp-muted">
              {section.title}
            </h2>
          </div>
          <div className="grid gap-2 p-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {section.tools.map((tool) => {
              const body = (
                <div
                  className={`flex items-center gap-2.5 rounded-lg border px-2.5 py-2.5 transition ${
                    tool.disabled
                      ? "cursor-not-allowed border-transparent opacity-45"
                      : "border-cp-border/60 bg-[#f7f9fc] hover:border-cp-orange/40 hover:bg-white hover:shadow-sm dark:border-ink-700 dark:bg-ink-900/80 dark:hover:bg-ink-900"
                  }`}
                >
                  <tool.icon className="h-4 w-4 shrink-0 text-cp-orange" />
                  <div className="min-w-0">
                    <p className="text-[13px] font-medium leading-5 text-cp-text">{tool.label}</p>
                    {tool.desc ? <p className="text-xs text-cp-muted">{tool.desc}</p> : null}
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

      {filtered.length === 0 && (
        <div className="vz-panel p-8 text-center text-sm text-cp-muted">
          No tools match “{q}”.
        </div>
      )}
    </div>
  );
}
