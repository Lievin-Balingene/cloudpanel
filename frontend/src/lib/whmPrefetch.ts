import type { QueryClient } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";

type Prefetch = { key: readonly unknown[]; path: string };

const PREFETCH: Record<string, Prefetch[]> = {
  "/whm": [{ key: ["dashboard-overview"], path: "/dashboard/overview/" }],
  "/whm/tweak-settings": [{ key: ["tweak-settings"], path: "/server-setup/tweak-settings/" }],
  "/whm/server-setup": [{ key: ["server-setup"], path: "/server-setup/" }],
  "/whm/ip-functions": [{ key: ["ip-functions"], path: "/server-setup/ip-functions/" }],
  "/whm/panel-update": [{ key: ["panel-update-overview"], path: "/server-setup/panel-update/" }],
  "/whm/accounts": [{ key: ["packages", "client"], path: "/packages/?type=client" }],
  "/whm/packages": [{ key: ["packages"], path: "/packages/" }],
  "/whm/domains": [{ key: ["domains"], path: "/domains/" }],
  "/whm/dns": [{ key: ["dns-zones"], path: "/dns/zones/" }],
  "/whm/ftp": [{ key: ["ftp-accounts"], path: "/ftp/accounts/" }],
  "/whm/cron": [{ key: ["cron-jobs"], path: "/cron/jobs/" }],
  "/whm/email": [{ key: ["email-overview"], path: "/email/overview/" }],
  "/whm/databases": [{ key: ["databases"], path: "/databases/" }],
  "/whm/python": [{ key: ["python-apps"], path: "/python/apps/" }],
  "/whm/node": [{ key: ["node-apps"], path: "/node/apps/" }],
  "/whm/php": [{ key: ["php-overview"], path: "/php/overview/" }],
  "/whm/git": [{ key: ["git-repos"], path: "/git/repos/" }],
  "/whm/docker": [{ key: ["docker-overview"], path: "/docker/overview/" }],
  "/whm/backups": [{ key: ["backup-overview"], path: "/backups/overview/" }],
  "/whm/monitoring": [{ key: ["monitoring-overview"], path: "/monitoring/overview/" }],
  "/whm/firewall": [{ key: ["firewall-overview"], path: "/firewall/overview/" }],
  "/whm/security": [{ key: ["security-overview"], path: "/security/overview/" }],
  "/whm/smtp-restrictions": [
    { key: ["smtp-restrictions"], path: "/security/smtp-restrictions/" },
  ],
  "/whm/wordpress": [{ key: ["wordpress-sites"], path: "/wordpress/sites/" }],
  "/whm/kubernetes": [{ key: ["k8s-overview"], path: "/kubernetes/overview/" }],
  "/whm/resources": [{ key: ["dashboard-server"], path: "/dashboard/server/" }],
  "/whm/pulse": [{ key: ["pulse-overview"], path: "/packages/pulse/" }],
  "/whm/local": [
    { key: ["local-context-profile"], path: "/local-context/profile/" },
    { key: ["local-context-overview"], path: "/local-context/overview/" },
  ],
  "/whm/ai-ops": [{ key: ["ai-pending-actions"], path: "/ai/actions/pending/" }],
  "/whm/ols": [{ key: ["ols-overview"], path: "/server-setup/ols/" }],
  "/whm/repairs": [{ key: ["repairs-overview"], path: "/server-setup/repairs/" }],
  "/whm/transfer": [{ key: ["transfer-jobs"], path: "/transfer/jobs/" }],
  "/whm/api": [{ key: ["api-tokens"], path: "/api-tokens/" }],
};

const warmed = new Set<string>();

export function prefetchWhmRoute(qc: QueryClient, to: string) {
  const entries = PREFETCH[to];
  if (!entries || warmed.has(to)) return;
  warmed.add(to);
  for (const item of entries) {
    void qc.prefetchQuery({
      queryKey: [...item.key],
      queryFn: () => apiRequest(item.path),
      staleTime: 45_000,
    });
  }
}
