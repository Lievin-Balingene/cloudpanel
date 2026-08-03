import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";

interface Assignment {
  package: {
    name: string;
    disk_mb: number;
    bandwidth_mb: number;
    domains: number;
    emails: number;
    databases: number;
    ftp_accounts: number;
    python_apps: number;
    node_apps: number;
    docker_containers: number;
    allow_backup: boolean;
    unlimited_disk: boolean;
    unlimited_bandwidth: boolean;
  };
}

export function ClientPackagePage() {
  const { data, isLoading } = useQuery({
    queryKey: ["package-mine"],
    queryFn: () => apiRequest<Assignment | null>("/packages/mine/"),
  });

  if (isLoading) {
    return <div className="vz-panel p-4">Chargement…</div>;
  }

  if (!data) {
    return (
      <div className="vz-panel p-6">
        <h1 className="text-xl font-semibold">Mon package</h1>
        <p className="mt-2 text-sm text-cp-muted">Aucun package assigné pour le moment.</p>
      </div>
    );
  }

  const pkg = data.package;
  const rows = [
    ["Package", pkg.name],
    ["Disque", pkg.unlimited_disk ? "Illimité" : `${pkg.disk_mb} Mo`],
    ["Bande passante", pkg.unlimited_bandwidth ? "Illimitée" : `${pkg.bandwidth_mb} Mo`],
    ["Domaines", String(pkg.domains)],
    ["Comptes e-mail", String(pkg.emails)],
    ["Bases de données", String(pkg.databases)],
    ["Comptes FTP", String(pkg.ftp_accounts)],
    ["Apps Python", String(pkg.python_apps)],
    ["Apps Node.js", String(pkg.node_apps)],
    ["Conteneurs Docker", String(pkg.docker_containers)],
    ["Backups", pkg.allow_backup ? "Autorisés" : "Désactivés"],
  ];

  return (
    <div className="vz-panel overflow-hidden animate-fade-up">
      <div className="border-b border-cp-border bg-cp-orange-soft px-4 py-3 dark:border-ink-800 dark:bg-ink-900">
        <h1 className="text-lg font-semibold">Resource Usage / Package</h1>
      </div>
      <table className="min-w-full text-sm">
        <tbody>
          {rows.map(([k, v]) => (
            <tr key={k} className="border-t border-cp-border dark:border-ink-800">
              <td className="w-1/3 bg-cp-canvas px-4 py-2 font-medium dark:bg-ink-900">{k}</td>
              <td className="px-4 py-2">{v}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
