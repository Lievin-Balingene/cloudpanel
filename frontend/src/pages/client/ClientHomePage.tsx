import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Globe, Package, Mail, Database, Folder, Shield, AppWindow, Upload, Code2, Terminal, FileCode2, GitBranch, Box, HardDrive, KeyRound } from "lucide-react";
import { apiRequest } from "@/lib/api";
import type { DashboardOverview } from "@/types";

const tools = [
  { to: "/panel/domains", label: "Domains", desc: "Domaines & SSL", icon: AppWindow },
  { to: "/panel/files", label: "File Manager", desc: "Fichiers & éditeur", icon: Folder },
  { to: "/panel/ftp", label: "FTP Accounts", desc: "Comptes & journaux", icon: Upload },
  { to: "/panel/email", label: "Email Accounts", desc: "Boîtes & forwarders", icon: Mail },
  { to: "/panel/databases", label: "Databases", desc: "MySQL & PostgreSQL", icon: Database },
  { to: "/panel/python", label: "Setup Python App", desc: "WSGI / ASGI", icon: Code2 },
  { to: "/panel/node", label: "Setup Node.js App", desc: "npm & démarrage", icon: Terminal },
  { to: "/panel/php", label: "Select PHP Version", desc: "MultiPHP", icon: FileCode2 },
  { to: "/panel/git", label: "Git Version Control", desc: "Clone & deploy", icon: GitBranch },
  { to: "/panel/docker", label: "Docker Containers", desc: "Images & logs", icon: Box },
  { to: "/panel/backups", label: "Backup", desc: "Créer & restaurer", icon: HardDrive },
  { to: "/panel/security", label: "Sécurité", desc: "2FA & mot de passe", icon: KeyRound },
  { to: "/panel/dns", label: "Zone Editor", desc: "Gérer les DNS", icon: Globe },
  { to: "/panel/package", label: "Mon package", desc: "Quotas & limites", icon: Package },
  { to: "#", label: "SSL/TLS Status", desc: "Via Domains", icon: Shield, disabled: true },
];

export function ClientHomePage() {
  const { data } = useQuery({
    queryKey: ["dashboard-overview"],
    queryFn: () => apiRequest<DashboardOverview>("/dashboard/overview/"),
  });

  return (
    <div className="space-y-4 animate-fade-up">
      <div className="vz-panel p-4">
        <h1 className="text-xl font-semibold">Accueil du panneau</h1>
        <p className="text-sm text-cp-muted">
          Package : <strong>{data?.my_package ?? "non assigné"}</strong> · Zones DNS :{" "}
          <strong>{data?.dns_zones ?? 0}</strong>
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {tools.map((tool) => {
          const content = (
            <div className={`cp-tool ${tool.disabled ? "opacity-50" : ""}`}>
              <tool.icon className="h-8 w-8 text-cp-orange" />
              <p className="font-semibold">{tool.label}</p>
              <p className="text-xs text-cp-muted">{tool.desc}</p>
            </div>
          );
          if (tool.disabled) {
            return (
              <div key={tool.label} aria-disabled>
                {content}
              </div>
            );
          }
          return (
            <Link key={tool.label} to={tool.to}>
              {content}
            </Link>
          );
        })}
      </div>
    </div>
  );
}
