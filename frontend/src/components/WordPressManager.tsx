import { FormEvent, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, Plus, Trash2 } from "lucide-react";
import { apiRequest } from "@/lib/api";
import { runWithProgress } from "@/stores/operations";
import { IconAction } from "@/components/ui/IconAction";
import { Modal } from "@/components/ui/Modal";
import { EmptyState, PageHeader, StatusDot } from "@/components/ui/PageChrome";

interface WpOverview {
  sites: number;
  active: number;
  error: number;
  provisioning: number;
  wp_cli: boolean;
  provision_mode: string;
}

interface DomainRow {
  id: number;
  name: string;
  domain_type: string;
  document_root: string;
}

interface WordPressSite {
  id: number;
  domain: number;
  domain_name: string;
  title: string;
  admin_user: string;
  admin_email: string;
  site_url: string;
  admin_url: string;
  database_name: string;
  db_username: string;
  php_version: string;
  status: string;
  last_error: string;
  admin_password?: string;
}

export function WordPressManager({ title }: { title: string }) {
  const qc = useQueryClient();
  const { data: overview } = useQuery({
    queryKey: ["wordpress-overview"],
    queryFn: () => apiRequest<WpOverview>("/wordpress/overview/"),
  });
  const { data: sites = [], isLoading } = useQuery({
    queryKey: ["wordpress-sites"],
    queryFn: () => apiRequest<WordPressSite[]>("/wordpress/sites/"),
  });
  const { data: domains = [] } = useQuery({
    queryKey: ["domains"],
    queryFn: () => apiRequest<DomainRow[]>("/domains/"),
  });

  const usedDomainIds = useMemo(() => new Set(sites.map((s) => s.domain)), [sites]);
  const availableDomains = useMemo(
    () =>
      domains.filter(
        (d) =>
          !usedDomainIds.has(d.id) &&
          ["primary", "addon", "subdomain"].includes(d.domain_type),
      ),
    [domains, usedDomainIds],
  );

  const [form, setForm] = useState({
    domain_id: "",
    title: "Mon site",
    admin_user: "admin",
    admin_email: "",
    admin_password: "",
    locale: "fr_FR",
  });
  const [error, setError] = useState<string | null>(null);
  const [credentials, setCredentials] = useState<{
    url: string;
    user: string;
    password: string;
  } | null>(null);
  const [installOpen, setInstallOpen] = useState(false);

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["wordpress-overview"] });
    void qc.invalidateQueries({ queryKey: ["wordpress-sites"] });
    void qc.invalidateQueries({ queryKey: ["domains"] });
    void qc.invalidateQueries({ queryKey: ["databases"] });
  };

  const install = useMutation({
    mutationFn: () =>
      runWithProgress(
        `WordPress · ${availableDomains.find((d) => String(d.id) === form.domain_id)?.name || "install"}`,
        () =>
          apiRequest<WordPressSite>("/wordpress/sites/", {
            method: "POST",
            body: JSON.stringify({
              domain_id: Number(form.domain_id),
              title: form.title,
              admin_user: form.admin_user,
              admin_email: form.admin_email,
              admin_password: form.admin_password || undefined,
              locale: form.locale,
            }),
          }),
        {
          tickDetail: (ms) =>
            ms < 5000
              ? "Téléchargement WordPress…"
              : ms < 20000
                ? "Base MySQL + configuration…"
                : "Finalisation de l’installation…",
        },
      ),
    onSuccess: (data) => {
      setError(null);
      if (data.admin_password) {
        setCredentials({
          url: data.admin_url || `${data.site_url}/wp-admin/`,
          user: data.admin_user,
          password: data.admin_password,
        });
      }
      setForm({
        domain_id: "",
        title: "Mon site",
        admin_user: "admin",
        admin_email: "",
        admin_password: "",
        locale: "fr_FR",
      });
      invalidate();
      setInstallOpen(false);
    },
    onError: (err: Error) => setError(err.message),
  });

  const remove = useMutation({
    mutationFn: (id: number) =>
      runWithProgress(`Suppression WordPress #${id}`, () =>
        apiRequest(`/wordpress/sites/${id}/?remove_files=true&remove_database=true`, {
          method: "DELETE",
        }),
      ),
    onSuccess: () => {
      setCredentials(null);
      invalidate();
    },
    onError: (err: Error) => setError(err.message),
  });

  function onInstall(e: FormEvent) {
    e.preventDefault();
    if (!form.domain_id) {
      setError("Sélectionnez un domaine.");
      return;
    }
    install.mutate();
  }

  return (
    <div className="space-y-4 animate-fade-up">
      <PageHeader title={title} subtitle="Installez WordPress avec MySQL, PHP-FPM et WP-CLI." stats={[{ label: "Sites", value: overview?.sites ?? "—" }, { label: "Actifs", value: overview?.active ?? "—" }, { label: "Erreurs", value: overview?.error ?? "—" }, { label: "WP-CLI", value: overview?.wp_cli ? "OK" : "—" }]} actions={<button type="button" className="vz-btn-primary" onClick={() => setInstallOpen(true)} disabled={!availableDomains.length}><Plus className="h-4 w-4" /> Installer WordPress</button>} />
      {overview && !overview.wp_cli && overview.provision_mode !== "mock" && (
          <p className="mt-2 text-sm text-amber-700">
            WP-CLI n’est pas détecté sur le serveur. Exécutez{" "}
            <code className="rounded bg-black/5 px-1">sudo bash /opt/vzone-src/scripts/install-wp-cli.sh</code>
          </p>
        )}

      {error && (
        <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-cp-danger">{error}</p>
      )}

      {credentials && (
        <div className="vz-panel border border-emerald-200 bg-emerald-50/80 p-4 text-sm">
          <p className="font-semibold text-emerald-900">Installation réussie — conservez ces identifiants</p>
          <p className="mt-1">
            Admin :{" "}
            <a className="text-cp-orange underline" href={credentials.url} target="_blank" rel="noreferrer">
              {credentials.url}
            </a>
          </p>
          <p>
            Utilisateur : <code>{credentials.user}</code>
          </p>
          <p>
            Mot de passe : <code className="select-all">{credentials.password}</code>
          </p>
          <button type="button" className="mt-2 text-xs text-cp-muted underline" onClick={() => setCredentials(null)}>
            Masquer
          </button>
        </div>
      )}

      {installOpen && <Modal title="Installer WordPress" subtitle="Un domaine, une base et un compte administrateur seront configurés." onClose={() => setInstallOpen(false)} wide><form className="grid gap-3 sm:grid-cols-2" onSubmit={onInstall}>
        <select
          className="vz-input sm:col-span-2"
          required
          value={form.domain_id}
          onChange={(e) => setForm({ ...form, domain_id: e.target.value })}
        >
          <option value="">Domaine…</option>
          {availableDomains.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </select>
        <input
          className="vz-input"
          placeholder="Titre du site"
          value={form.title}
          onChange={(e) => setForm({ ...form, title: e.target.value })}
        />
        <input
          className="vz-input"
          placeholder="Admin user"
          value={form.admin_user}
          onChange={(e) => setForm({ ...form, admin_user: e.target.value })}
        />
        <input
          className="vz-input"
          type="email"
          placeholder="Admin email"
          value={form.admin_email}
          onChange={(e) => setForm({ ...form, admin_email: e.target.value })}
        />
        <input
          className="vz-input"
          type="password"
          placeholder="Mot de passe admin (auto si vide)"
          value={form.admin_password}
          onChange={(e) => setForm({ ...form, admin_password: e.target.value })}
        />
        <select
          className="vz-input"
          value={form.locale}
          onChange={(e) => setForm({ ...form, locale: e.target.value })}
        >
          <option value="fr_FR">Français</option>
          <option value="en_US">English</option>
        </select>
        {!availableDomains.length && (
          <p className="sm:col-span-2 text-sm text-cp-muted">
            Aucun domaine libre — créez un domaine ou désinstallez un site WordPress existant.
          </p>
        )}
        <div className="flex justify-end gap-2 sm:col-span-2"><button type="button" className="vz-btn-ghost" onClick={() => setInstallOpen(false)}>Annuler</button><button className="vz-btn-primary" type="submit" disabled={install.isPending || !availableDomains.length}>Installer</button></div>
      </form></Modal>}

      <div className="vz-panel overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-cp-canvas text-xs uppercase text-cp-muted dark:bg-ink-900">
            <tr>
              <th className="px-3 py-2">Site</th>
              <th className="px-3 py-2">PHP / DB</th>
              <th className="px-3 py-2">État</th>
              <th className="px-3 py-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td className="px-3 py-4 text-cp-muted" colSpan={4}>
                  Chargement…
                </td>
              </tr>
            )}
            {!isLoading && sites.length === 0 && (
              <tr>
                <td className="px-3 py-4 text-cp-muted" colSpan={4}>
                  Aucun site WordPress.
                </td>
              </tr>
            )}
            {sites.map((site) => (
              <tr key={site.id} className="border-t border-cp-border/60">
                <td className="px-3 py-3">
                  <p className="font-medium">{site.title}</p>
                  <p className="text-xs text-cp-muted">{site.domain_name}</p>
                  {site.last_error && (
                    <p className="mt-1 max-w-md text-xs text-cp-danger">{site.last_error}</p>
                  )}
                </td>
                <td className="px-3 py-3 text-xs text-cp-muted">
                  <p>PHP {site.php_version || "—"}</p>
                  <p>
                    {site.database_name || "—"} / {site.db_username || "—"}
                  </p>
                </td>
                <td className="px-3 py-3"><StatusDot status={site.status} label={site.status} /></td>
                <td className="px-3 py-3">
                  <div className="flex flex-wrap gap-2">
                    {site.admin_url && <a href={site.admin_url} target="_blank" rel="noreferrer" className="inline-flex h-8 w-8 items-center justify-center text-cp-muted" title="Ouvrir wp-admin" aria-label="Ouvrir wp-admin"><ExternalLink className="h-4 w-4" /></a>}
                    {site.site_url && <a href={site.site_url} target="_blank" rel="noreferrer" className="inline-flex h-8 w-8 items-center justify-center text-cp-muted" title="Visiter le site" aria-label="Visiter le site"><ExternalLink className="h-4 w-4" /></a>}
                    <IconAction label={`Supprimer WordPress sur ${site.domain_name}`} danger
                      disabled={remove.isPending}
                      onClick={() => {
                        if (
                          window.confirm(
                            `Supprimer WordPress sur ${site.domain_name} (fichiers + base) ?`,
                          )
                        ) {
                          remove.mutate(site.id);
                        }
                      }}
                    ><Trash2 className="h-4 w-4" /></IconAction>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!isLoading && sites.length === 0 && <div className="vz-panel"><EmptyState icon={<Plus className="h-5 w-5" />} message="Aucun site WordPress installé." action={<button className="vz-btn-primary" onClick={() => setInstallOpen(true)} disabled={!availableDomains.length}>Installer WordPress</button>} /></div>}
    </div>
  );
}
