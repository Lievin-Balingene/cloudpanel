export type UserRole = "administrator" | "reseller" | "client";

export interface ResourceQuota {
  disk_mb: number | null;
  cpu_millicores: number | null;
  ram_mb: number | null;
  emails: number;
  databases: number;
  domains: number;
  ftp_accounts: number;
  python_apps: number;
  node_apps: number;
  docker_containers: number;
  unlimited_disk?: boolean;
  unlimited_cpu?: boolean;
  unlimited_ram?: boolean;
}

export interface User {
  id: number;
  email: string;
  username: string;
  first_name: string;
  last_name: string;
  role: UserRole;
  is_active: boolean;
  is_suspended: boolean;
  must_change_password: boolean;
  two_factor_enabled: boolean;
  module_permissions: string[];
  system_username?: string;
  home_directory?: string;
  primary_domain?: string;
  quota?: ResourceQuota;
}

export interface ApiSuccess<T> {
  success: true;
  data: T;
}

export interface ApiError {
  success: false;
  error: {
    code: string;
    message: string;
    details?: unknown;
    extra?: Record<string, unknown>;
  };
}

export interface SystemMetrics {
  cpu: { percent: number; count: number };
  memory: { total: number; available: number; percent: number; used: number };
  disk: { total: number; used: number; free: number; percent: number };
  load_average: number[] | null;
  temperatures: Record<string, number>;
  collected_at: string;
}

export interface HostingPackage {
  id: number;
  name: string;
  slug: string;
  description: string;
  package_type: "client" | "reseller";
  is_active: boolean;
  is_default: boolean;
  disk_mb: number;
  bandwidth_mb: number;
  unlimited_disk: boolean;
  unlimited_bandwidth: boolean;
  cpu_millicores: number;
  ram_mb: number;
  domains: number;
  subdomains: number;
  emails: number;
  databases: number;
  ftp_accounts: number;
  python_apps: number;
  node_apps: number;
  docker_containers: number;
  max_accounts: number;
  can_create_packages: boolean;
  allow_dns: boolean;
  allow_ssl: boolean;
  allow_backup?: boolean;
  allow_git?: boolean;
  allow_ssh?: boolean;
  assigned_count?: number;
}

export interface DnsRecord {
  id: number;
  zone: number;
  record_type: string;
  name: string;
  content: string;
  ttl: number | null;
  priority: number | null;
  weight: number | null;
  port: number | null;
  flags: number | null;
  tag: string;
  is_active: boolean;
}

export interface DnsZone {
  id: number;
  name: string;
  owner: number;
  owner_username: string;
  ttl_default: number;
  soa_serial: number;
  dnssec_enabled: boolean;
  is_active: boolean;
  records: DnsRecord[];
  record_count: number;
}

export interface DashboardOverview {
  users_total: number;
  clients: number;
  resellers: number;
  dns_zones: number;
  domains_total?: number;
  packages_active: number;
  sessions_active: number;
  my_package: string | null;
  disk: {
    total: number;
    used: number;
    free: number;
    percent: number;
    unlimited?: boolean;
    home_directory?: string;
    quota_mb?: number | null;
    used_mb?: number;
    breakdown_mb?: Record<string, number>;
  };
  usage?: {
    domains: number;
    dns_zones: number;
    emails: number;
    databases: number;
    ftp_accounts: number;
  } | null;
  account?: {
    username: string;
    email: string;
    home_directory: string;
    primary_domain: string;
    last_login_ip: string;
    last_login: string | null;
  } | null;
  services: { name: string; active: boolean }[];
  metrics: SystemMetrics | null;
}

export interface HistoryPoint {
  collected_at: string;
  cpu_percent: number;
  ram_percent: number;
  disk_percent: number;
  load_1: number | null;
  net_bytes_sent: number;
  net_bytes_recv: number;
}

export interface SslInfo {
  id: number;
  provider: string;
  status: string;
  common_name: string;
  auto_renew: boolean;
  issued_at: string | null;
  expires_at: string | null;
  last_error: string;
  is_expiring_soon: boolean;
  has_private_key: boolean;
}

export interface DomainRedirect {
  id: number;
  source_path: string;
  destination_url: string;
  redirect_type: string;
  wildcard: boolean;
  is_active: boolean;
}

export interface Domain {
  id: number;
  name: string;
  owner: number;
  owner_username: string;
  domain_type: string;
  parent: number | null;
  parent_name: string | null;
  document_root: string;
  is_active: boolean;
  is_suspended: boolean;
  dns_zone: number | null;
  dns_zone_name: string | null;
  ipv4_address: string | null;
  ipv6_address: string | null;
  ssl: SslInfo | null;
  redirects: DomainRedirect[];
}
