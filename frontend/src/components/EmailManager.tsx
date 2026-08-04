import { FormEvent, useMemo, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ExternalLink,
  Forward,
  Globe,
  KeyRound,
  Mail,
  PauseCircle,
  PlayCircle,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Trash2,
  X,
} from "lucide-react";
import { apiRequest } from "@/lib/api";

interface MailOverview {
  domains: number;
  mailboxes: number;
  active_mailboxes: number;
  forwarders: number;
  webmail_url: string;
}

interface MailDomain {
  id: number;
  name: string;
  max_quota_mb: number;
  dkim_enabled: boolean;
  dkim_selector: string;
  spf_record: string;
  dmarc_policy: string;
  mailbox_count: number;
  is_active: boolean;
}

interface Mailbox {
  id: number;
  mail_domain: number;
  domain_name: string;
  local_part: string;
  address: string;
  quota_mb: number;
  used_mb: number;
  status: string;
  is_suspended: boolean;
}

interface MailForwarder {
  id: number;
  mail_domain: number;
  local_part: string;
  address: string;
  destinations: string[];
  keep_copy: boolean;
}

type TabId = "boxes" | "domains" | "forwards";
type CreateKind = "box" | "domain" | "forward" | null;

function IconAction({
  label,
  onClick,
  disabled,
  danger,
  children,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  danger?: boolean;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      disabled={disabled}
      onClick={onClick}
      className={`inline-flex h-8 w-8 items-center justify-center rounded-md border border-transparent transition
        hover:border-cp-border hover:bg-cp-canvas disabled:cursor-not-allowed disabled:opacity-40
        dark:hover:border-ink-600 dark:hover:bg-ink-900
        ${danger ? "text-cp-danger hover:bg-red-50 dark:hover:bg-red-950/40" : "text-cp-muted hover:text-cp-navy dark:hover:text-ink-100"}`}
    >
      {children}
    </button>
  );
}

function QuotaBar({ used, total }: { used: number; total: number }) {
  const pct = total > 0 ? Math.min(100, Math.round((used / total) * 100)) : 0;
  return (
    <div className="min-w-[7rem]">
      <div className="mb-0.5 flex justify-between text-[11px] text-cp-muted">
        <span>
          {used}/{total} Mo
        </span>
        <span>{pct}%</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-cp-canvas dark:bg-ink-800">
        <div
          className={`h-full rounded-full transition-all ${
            pct >= 90 ? "bg-cp-danger" : pct >= 70 ? "bg-cp-orange" : "bg-cp-link"
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function StatusDot({ status }: { status: string }) {
  const color =
    status === "active"
      ? "bg-cp-success"
      : status === "suspended"
        ? "bg-cp-danger"
        : "bg-cp-muted";
  const label =
    status === "active" ? "Active" : status === "suspended" ? "Suspendue" : status;
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-cp-muted">
      <span className={`h-1.5 w-1.5 rounded-full ${color}`} />
      {label}
    </span>
  );
}

function Modal({
  title,
  subtitle,
  onClose,
  children,
}: {
  title: string;
  subtitle?: string;
  onClose: () => void;
  children: ReactNode;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div
        className="w-full max-w-md rounded-[10px] border border-cp-border bg-white p-4 shadow-xl dark:border-ink-700 dark:bg-ink-950"
        role="dialog"
        aria-modal="true"
      >
        <div className="mb-3 flex items-start justify-between gap-3">
          <div>
            <p className="font-semibold text-cp-text">{title}</p>
            {subtitle && <p className="mt-0.5 text-xs text-cp-muted">{subtitle}</p>}
          </div>
          <button
            type="button"
            className="rounded-md p-1 text-cp-muted hover:bg-cp-canvas hover:text-cp-text"
            onClick={onClose}
            aria-label="Fermer"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function EmailManager({ title }: { title: string }) {
  const qc = useQueryClient();
  const { data: overview } = useQuery({
    queryKey: ["email-overview"],
    queryFn: () => apiRequest<MailOverview>("/email/overview/"),
  });
  const { data: domains = [] } = useQuery({
    queryKey: ["email-domains"],
    queryFn: () => apiRequest<MailDomain[]>("/email/domains/"),
  });
  const { data: mailboxes = [], isLoading } = useQuery({
    queryKey: ["email-mailboxes"],
    queryFn: () => apiRequest<Mailbox[]>("/email/mailboxes/"),
  });
  const { data: forwarders = [] } = useQuery({
    queryKey: ["email-forwarders"],
    queryFn: () => apiRequest<MailForwarder[]>("/email/forwarders/"),
  });

  const [tab, setTab] = useState<TabId>("boxes");
  const [createKind, setCreateKind] = useState<CreateKind>(null);
  const [search, setSearch] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [resetPwd, setResetPwd] = useState<{
    id: number;
    address: string;
    password: string;
  } | null>(null);

  const [domainForm, setDomainForm] = useState({ name: "", max_quota_mb: 1024 });
  const [boxForm, setBoxForm] = useState({
    mail_domain_id: 0,
    local_part: "",
    password: "",
    quota_mb: 250,
  });
  const [fwdForm, setFwdForm] = useState({
    mail_domain_id: 0,
    local_part: "",
    destinations: "",
    keep_copy: false,
  });

  const invalidateAll = () => {
    void qc.invalidateQueries({ queryKey: ["email-overview"] });
    void qc.invalidateQueries({ queryKey: ["email-domains"] });
    void qc.invalidateQueries({ queryKey: ["email-mailboxes"] });
    void qc.invalidateQueries({ queryKey: ["email-forwarders"] });
  };

  const createDomain = useMutation({
    mutationFn: () =>
      apiRequest("/email/domains/", {
        method: "POST",
        body: JSON.stringify({ ...domainForm, enable_dns: true }),
      }),
    onSuccess: () => {
      setDomainForm({ name: "", max_quota_mb: 1024 });
      setCreateKind(null);
      setError(null);
      setTab("domains");
      invalidateAll();
    },
    onError: (err: Error) => setError(err.message),
  });

  const createBox = useMutation({
    mutationFn: (payload: typeof boxForm) =>
      apiRequest("/email/mailboxes/", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      setBoxForm((f) => ({ ...f, local_part: "", password: "" }));
      setCreateKind(null);
      setError(null);
      setTab("boxes");
      invalidateAll();
    },
    onError: (err: Error) => setError(err.message),
  });

  const createFwd = useMutation({
    mutationFn: (payload: {
      mail_domain_id: number;
      local_part: string;
      destinations: string[];
      keep_copy: boolean;
    }) =>
      apiRequest("/email/forwarders/", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      setFwdForm((f) => ({ ...f, local_part: "", destinations: "" }));
      setCreateKind(null);
      setError(null);
      setTab("forwards");
      invalidateAll();
    },
    onError: (err: Error) => setError(err.message),
  });

  const suspend = useMutation({
    mutationFn: ({ id, suspended }: { id: number; suspended: boolean }) =>
      apiRequest(`/email/mailboxes/${id}/suspend/`, {
        method: "POST",
        body: JSON.stringify({ suspended }),
      }),
    onSuccess: invalidateAll,
  });

  const removeBox = useMutation({
    mutationFn: (id: number) => apiRequest(`/email/mailboxes/${id}/`, { method: "DELETE" }),
    onSuccess: invalidateAll,
  });

  const removeFwd = useMutation({
    mutationFn: (id: number) => apiRequest(`/email/forwarders/${id}/`, { method: "DELETE" }),
    onSuccess: invalidateAll,
  });

  const enableDkim = useMutation({
    mutationFn: (id: number) =>
      apiRequest(`/email/domains/${id}/dkim/`, {
        method: "POST",
        body: JSON.stringify({ selector: "default" }),
      }),
    onSuccess: invalidateAll,
    onError: (err: Error) => setError(err.message),
  });

  const syncDns = useMutation({
    mutationFn: (id: number) =>
      apiRequest(`/email/domains/${id}/dns-sync/`, { method: "POST", body: "{}" }),
    onSuccess: invalidateAll,
    onError: (err: Error) => setError(err.message),
  });

  const openWebmail = useMutation({
    mutationFn: (mailboxId: number) =>
      apiRequest<{ url: string; address: string }>("/email/webmail/sso/", {
        method: "POST",
        body: JSON.stringify({ mailbox_id: mailboxId }),
      }),
    onSuccess: (data) => {
      setError(null);
      const raw = data.url || "";
      const url = raw.startsWith("http")
        ? raw
        : `${window.location.origin}${raw.startsWith("/") ? "" : "/"}${raw}`;
      const popup = window.open(url, "_blank", "noopener,noreferrer");
      if (!popup) window.location.assign(url);
    },
    onError: (err: Error) => setError(err.message),
  });

  const changePassword = useMutation({
    mutationFn: ({ id, password }: { id: number; password: string }) =>
      apiRequest(`/email/mailboxes/${id}/`, {
        method: "PATCH",
        body: JSON.stringify({ password }),
      }),
    onSuccess: () => {
      setResetPwd(null);
      setError(null);
      invalidateAll();
    },
    onError: (err: Error) => setError(err.message),
  });

  const selectedDomainId = boxForm.mail_domain_id || domains[0]?.id || 0;
  const selectedFwdDomainId = fwdForm.mail_domain_id || domains[0]?.id || 0;

  const filteredBoxes = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return mailboxes;
    return mailboxes.filter(
      (b) =>
        b.address.toLowerCase().includes(q) ||
        b.domain_name.toLowerCase().includes(q) ||
        b.local_part.toLowerCase().includes(q),
    );
  }, [mailboxes, search]);

  const tabs: { id: TabId; label: string; count: number; icon: ReactNode }[] = [
    {
      id: "boxes",
      label: "Boîtes",
      count: overview?.mailboxes ?? mailboxes.length,
      icon: <Mail className="h-3.5 w-3.5" />,
    },
    {
      id: "domains",
      label: "Domaines",
      count: overview?.domains ?? domains.length,
      icon: <Globe className="h-3.5 w-3.5" />,
    },
    {
      id: "forwards",
      label: "Redirections",
      count: overview?.forwarders ?? forwarders.length,
      icon: <Forward className="h-3.5 w-3.5" />,
    },
  ];

  function openCreate(kind: CreateKind) {
    setError(null);
    if (kind === "box" || kind === "forward") {
      if (!domains.length) {
        setError("Ajoutez d’abord un domaine mail.");
        setCreateKind("domain");
        return;
      }
    }
    setCreateKind(kind);
  }

  function onCreateDomain(e: FormEvent) {
    e.preventDefault();
    createDomain.mutate();
  }

  function onCreateBox(e: FormEvent) {
    e.preventDefault();
    if (!selectedDomainId) {
      setError("Créez d'abord un domaine mail.");
      return;
    }
    const payload = { ...boxForm, mail_domain_id: selectedDomainId };
    setBoxForm(payload);
    createBox.mutate(payload);
  }

  function onCreateFwd(e: FormEvent) {
    e.preventDefault();
    if (!selectedFwdDomainId) {
      setError("Créez d'abord un domaine mail.");
      return;
    }
    createFwd.mutate({
      mail_domain_id: selectedFwdDomainId,
      local_part: fwdForm.local_part,
      destinations: fwdForm.destinations
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
      keep_copy: fwdForm.keep_copy,
    });
  }

  return (
    <div className="space-y-4 animate-fade-up">
      <div className="vz-panel p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold">{title}</h1>
            <p className="mt-0.5 text-sm text-cp-muted">
              Créez des boîtes, ouvrez le webmail, gérez domaines et redirections.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {overview?.webmail_url && (
              <a
                className="vz-btn-ghost !px-2.5"
                href={overview.webmail_url}
                target="_blank"
                rel="noreferrer"
                title="Ouvrir Roundcube"
              >
                <ExternalLink className="h-4 w-4" />
                <span className="hidden sm:inline">Roundcube</span>
              </a>
            )}
            <button
              type="button"
              className="vz-btn-primary"
              onClick={() =>
                openCreate(tab === "domains" ? "domain" : tab === "forwards" ? "forward" : "box")
              }
            >
              <Plus className="h-4 w-4" />
              {tab === "domains" ? "Domaine" : tab === "forwards" ? "Redirection" : "Boîte"}
            </button>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap gap-4 text-sm">
          {[
            { label: "Boîtes", value: overview?.mailboxes ?? "—" },
            { label: "Actives", value: overview?.active_mailboxes ?? "—" },
            { label: "Domaines", value: overview?.domains ?? "—" },
            { label: "Redirections", value: overview?.forwarders ?? "—" },
          ].map((s) => (
            <div key={s.label} className="min-w-[4.5rem]">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-cp-muted">
                {s.label}
              </p>
              <p className="text-lg font-semibold text-cp-text">{s.value}</p>
            </div>
          ))}
        </div>
      </div>

      {error && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-cp-danger dark:border-red-900 dark:bg-red-950/30">
          {error}
        </p>
      )}

      <div className="vz-panel overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-cp-border px-2 dark:border-ink-800">
          <div className="flex gap-0.5 p-1">
            {tabs.map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => setTab(t.id)}
                className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition ${
                  tab === t.id
                    ? "bg-cp-link-soft text-cp-navy dark:bg-ink-800 dark:text-ink-50"
                    : "text-cp-muted hover:bg-cp-canvas hover:text-cp-text dark:hover:bg-ink-900"
                }`}
              >
                {t.icon}
                {t.label}
                <span className="rounded-full bg-cp-canvas px-1.5 text-[10px] tabular-nums text-cp-muted dark:bg-ink-900">
                  {t.count}
                </span>
              </button>
            ))}
          </div>
          {tab === "boxes" && (
            <div className="relative m-2 min-w-[12rem] flex-1 sm:max-w-xs sm:flex-none">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-cp-muted" />
              <input
                className="vz-input !py-1.5 pl-8 text-sm"
                placeholder="Rechercher une boîte…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
          )}
        </div>

        {tab === "boxes" && (
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="bg-cp-canvas/80 text-[11px] uppercase tracking-wide text-cp-muted dark:bg-ink-900/80">
                <tr>
                  <th className="px-4 py-2.5 font-semibold">Adresse</th>
                  <th className="px-4 py-2.5 font-semibold">Quota</th>
                  <th className="px-4 py-2.5 font-semibold">État</th>
                  <th className="px-4 py-2.5 text-right font-semibold">Actions</th>
                </tr>
              </thead>
              <tbody>
                {isLoading && (
                  <tr>
                    <td className="px-4 py-8 text-cp-muted" colSpan={4}>
                      Chargement…
                    </td>
                  </tr>
                )}
                {!isLoading && filteredBoxes.length === 0 && (
                  <tr>
                    <td className="px-4 py-10 text-center text-cp-muted" colSpan={4}>
                      <Mail className="mx-auto mb-2 h-8 w-8 opacity-40" />
                      <p>Aucune boîte mail.</p>
                      <button
                        type="button"
                        className="mt-3 vz-btn-primary"
                        onClick={() => openCreate("box")}
                      >
                        <Plus className="h-4 w-4" />
                        Créer une boîte
                      </button>
                    </td>
                  </tr>
                )}
                {filteredBoxes.map((box) => (
                  <tr
                    key={box.id}
                    className="border-t border-cp-border/80 transition hover:bg-cp-canvas/50 dark:border-ink-800 dark:hover:bg-ink-900/40"
                  >
                    <td className="px-4 py-3">
                      <p className="font-medium text-cp-text">{box.address}</p>
                      <p className="text-[11px] text-cp-muted">{box.domain_name}</p>
                    </td>
                    <td className="px-4 py-3">
                      <QuotaBar used={box.used_mb} total={box.quota_mb} />
                    </td>
                    <td className="px-4 py-3">
                      <StatusDot status={box.status} />
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-0.5">
                        <IconAction
                          label="Ouvrir le webmail"
                          disabled={box.status !== "active" || openWebmail.isPending}
                          onClick={() => openWebmail.mutate(box.id)}
                        >
                          <Mail className="h-4 w-4" />
                        </IconAction>
                        <IconAction
                          label="Changer le mot de passe"
                          onClick={() =>
                            setResetPwd({ id: box.id, address: box.address, password: "" })
                          }
                        >
                          <KeyRound className="h-4 w-4" />
                        </IconAction>
                        <IconAction
                          label={box.is_suspended ? "Réactiver" : "Suspendre"}
                          onClick={() =>
                            suspend.mutate({ id: box.id, suspended: !box.is_suspended })
                          }
                        >
                          {box.is_suspended ? (
                            <PlayCircle className="h-4 w-4" />
                          ) : (
                            <PauseCircle className="h-4 w-4" />
                          )}
                        </IconAction>
                        <IconAction
                          label="Supprimer"
                          danger
                          onClick={() => {
                            if (window.confirm(`Supprimer ${box.address} ?`)) {
                              removeBox.mutate(box.id);
                            }
                          }}
                        >
                          <Trash2 className="h-4 w-4" />
                        </IconAction>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {tab === "domains" && (
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="bg-cp-canvas/80 text-[11px] uppercase tracking-wide text-cp-muted dark:bg-ink-900/80">
                <tr>
                  <th className="px-4 py-2.5 font-semibold">Domaine</th>
                  <th className="px-4 py-2.5 font-semibold">Boîtes</th>
                  <th className="px-4 py-2.5 font-semibold">DKIM</th>
                  <th className="px-4 py-2.5 text-right font-semibold">Actions</th>
                </tr>
              </thead>
              <tbody>
                {domains.length === 0 && (
                  <tr>
                    <td className="px-4 py-10 text-center text-cp-muted" colSpan={4}>
                      <Globe className="mx-auto mb-2 h-8 w-8 opacity-40" />
                      <p>Aucun domaine mail.</p>
                      <button
                        type="button"
                        className="mt-3 vz-btn-primary"
                        onClick={() => openCreate("domain")}
                      >
                        <Plus className="h-4 w-4" />
                        Ajouter un domaine
                      </button>
                    </td>
                  </tr>
                )}
                {domains.map((d) => (
                  <tr
                    key={d.id}
                    className="border-t border-cp-border/80 transition hover:bg-cp-canvas/50 dark:border-ink-800 dark:hover:bg-ink-900/40"
                  >
                    <td className="px-4 py-3 font-medium">{d.name}</td>
                    <td className="px-4 py-3 tabular-nums text-cp-muted">{d.mailbox_count}</td>
                    <td className="px-4 py-3">
                      {d.dkim_enabled ? (
                        <span className="inline-flex items-center gap-1 text-xs text-cp-success">
                          <ShieldCheck className="h-3.5 w-3.5" />
                          Actif
                        </span>
                      ) : (
                        <span className="text-xs text-cp-muted">Inactif</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-0.5">
                        {!d.dkim_enabled && (
                          <IconAction
                            label="Activer DKIM"
                            onClick={() => enableDkim.mutate(d.id)}
                          >
                            <ShieldCheck className="h-4 w-4" />
                          </IconAction>
                        )}
                        <IconAction
                          label="Synchroniser DNS (SPF / DKIM / DMARC)"
                          onClick={() => syncDns.mutate(d.id)}
                        >
                          <RefreshCw className="h-4 w-4" />
                        </IconAction>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {tab === "forwards" && (
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="bg-cp-canvas/80 text-[11px] uppercase tracking-wide text-cp-muted dark:bg-ink-900/80">
                <tr>
                  <th className="px-4 py-2.5 font-semibold">Adresse</th>
                  <th className="px-4 py-2.5 font-semibold">Vers</th>
                  <th className="px-4 py-2.5 text-right font-semibold">Actions</th>
                </tr>
              </thead>
              <tbody>
                {forwarders.length === 0 && (
                  <tr>
                    <td className="px-4 py-10 text-center text-cp-muted" colSpan={3}>
                      <Forward className="mx-auto mb-2 h-8 w-8 opacity-40" />
                      <p>Aucune redirection.</p>
                      <button
                        type="button"
                        className="mt-3 vz-btn-primary"
                        onClick={() => openCreate("forward")}
                      >
                        <Plus className="h-4 w-4" />
                        Créer une redirection
                      </button>
                    </td>
                  </tr>
                )}
                {forwarders.map((fwd) => (
                  <tr
                    key={fwd.id}
                    className="border-t border-cp-border/80 transition hover:bg-cp-canvas/50 dark:border-ink-800 dark:hover:bg-ink-900/40"
                  >
                    <td className="px-4 py-3 font-medium">{fwd.address}</td>
                    <td className="px-4 py-3 text-xs text-cp-muted">
                      {fwd.destinations.join(", ")}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex justify-end">
                        <IconAction
                          label="Supprimer"
                          danger
                          onClick={() => {
                            if (window.confirm(`Supprimer ${fwd.address} ?`)) {
                              removeFwd.mutate(fwd.id);
                            }
                          }}
                        >
                          <Trash2 className="h-4 w-4" />
                        </IconAction>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {createKind === "domain" && (
        <Modal
          title="Nouveau domaine mail"
          subtitle="SPF / DKIM / DMARC seront publiés automatiquement."
          onClose={() => setCreateKind(null)}
        >
          <form className="space-y-3" onSubmit={onCreateDomain}>
            <div>
              <label className="mb-1 block text-xs font-medium text-cp-muted">Domaine</label>
              <input
                className="vz-input"
                placeholder="exemple.com"
                required
                autoFocus
                value={domainForm.name}
                onChange={(e) => setDomainForm({ ...domainForm, name: e.target.value })}
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-cp-muted">
                Quota max (Mo)
              </label>
              <input
                className="vz-input"
                type="number"
                min={1}
                value={domainForm.max_quota_mb}
                onChange={(e) =>
                  setDomainForm({ ...domainForm, max_quota_mb: Number(e.target.value) })
                }
              />
            </div>
            <div className="flex justify-end gap-2 pt-1">
              <button type="button" className="vz-btn-ghost" onClick={() => setCreateKind(null)}>
                Annuler
              </button>
              <button className="vz-btn-primary" type="submit" disabled={createDomain.isPending}>
                {createDomain.isPending ? "…" : "Ajouter"}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {createKind === "box" && (
        <Modal title="Nouvelle boîte mail" onClose={() => setCreateKind(null)}>
          <form className="space-y-3" onSubmit={onCreateBox}>
            <div>
              <label className="mb-1 block text-xs font-medium text-cp-muted">Domaine</label>
              <select
                className="vz-input"
                value={selectedDomainId}
                onChange={(e) =>
                  setBoxForm({ ...boxForm, mail_domain_id: Number(e.target.value) })
                }
              >
                {domains.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-cp-muted">
                Adresse (partie locale)
              </label>
              <div className="flex items-center gap-2">
                <input
                  className="vz-input"
                  placeholder="info"
                  required
                  autoFocus
                  value={boxForm.local_part}
                  onChange={(e) => setBoxForm({ ...boxForm, local_part: e.target.value })}
                />
                <span className="shrink-0 text-sm text-cp-muted">
                  @
                  {domains.find((d) => d.id === selectedDomainId)?.name || "domaine"}
                </span>
              </div>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-cp-muted">Mot de passe</label>
              <input
                className="vz-input"
                type="password"
                placeholder="min. 8 caractères"
                required
                minLength={8}
                value={boxForm.password}
                onChange={(e) => setBoxForm({ ...boxForm, password: e.target.value })}
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-cp-muted">Quota (Mo)</label>
              <input
                className="vz-input"
                type="number"
                min={1}
                value={boxForm.quota_mb}
                onChange={(e) => setBoxForm({ ...boxForm, quota_mb: Number(e.target.value) })}
              />
            </div>
            <div className="flex justify-end gap-2 pt-1">
              <button type="button" className="vz-btn-ghost" onClick={() => setCreateKind(null)}>
                Annuler
              </button>
              <button className="vz-btn-primary" type="submit" disabled={createBox.isPending}>
                {createBox.isPending ? "…" : "Créer"}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {createKind === "forward" && (
        <Modal title="Nouvelle redirection" onClose={() => setCreateKind(null)}>
          <form className="space-y-3" onSubmit={onCreateFwd}>
            <div>
              <label className="mb-1 block text-xs font-medium text-cp-muted">Domaine</label>
              <select
                className="vz-input"
                value={selectedFwdDomainId}
                onChange={(e) =>
                  setFwdForm({ ...fwdForm, mail_domain_id: Number(e.target.value) })
                }
              >
                {domains.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-cp-muted">Alias</label>
              <div className="flex items-center gap-2">
                <input
                  className="vz-input"
                  placeholder="contact"
                  required
                  autoFocus
                  value={fwdForm.local_part}
                  onChange={(e) => setFwdForm({ ...fwdForm, local_part: e.target.value })}
                />
                <span className="shrink-0 text-sm text-cp-muted">
                  @
                  {domains.find((d) => d.id === selectedFwdDomainId)?.name || "domaine"}
                </span>
              </div>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-cp-muted">
                Destinations (séparées par virgule)
              </label>
              <input
                className="vz-input"
                placeholder="info@exemple.com"
                required
                value={fwdForm.destinations}
                onChange={(e) => setFwdForm({ ...fwdForm, destinations: e.target.value })}
              />
            </div>
            <label className="flex items-center gap-2 text-sm text-cp-text">
              <input
                type="checkbox"
                checked={fwdForm.keep_copy}
                onChange={(e) => setFwdForm({ ...fwdForm, keep_copy: e.target.checked })}
              />
              Conserver une copie locale
            </label>
            <div className="flex justify-end gap-2 pt-1">
              <button type="button" className="vz-btn-ghost" onClick={() => setCreateKind(null)}>
                Annuler
              </button>
              <button className="vz-btn-primary" type="submit" disabled={createFwd.isPending}>
                {createFwd.isPending ? "…" : "Créer"}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {resetPwd && (
        <Modal
          title="Nouveau mot de passe"
          subtitle={resetPwd.address}
          onClose={() => setResetPwd(null)}
        >
          <div className="space-y-3">
            <input
              className="vz-input"
              type="password"
              minLength={8}
              placeholder="min. 8 caractères"
              value={resetPwd.password}
              onChange={(e) => setResetPwd({ ...resetPwd, password: e.target.value })}
              autoFocus
            />
            <div className="flex justify-end gap-2">
              <button type="button" className="vz-btn-ghost" onClick={() => setResetPwd(null)}>
                Annuler
              </button>
              <button
                type="button"
                className="vz-btn-primary"
                disabled={resetPwd.password.length < 8 || changePassword.isPending}
                onClick={() =>
                  changePassword.mutate({ id: resetPwd.id, password: resetPwd.password })
                }
              >
                Enregistrer
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
