import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { apiRequest } from "@/lib/api";
import { IconAction } from "@/components/ui/IconAction";
import { Modal } from "@/components/ui/Modal";
import { EmptyState, PageHeader, StatusDot } from "@/components/ui/PageChrome";

interface PhpOverview {
  versions: number;
  default_version: string | null;
  selectors: number;
  active_selectors: number;
  provision_mode: string;
}

interface PhpVersion {
  id: number;
  version: string;
  is_available: boolean;
  is_default: boolean;
  binary_path: string;
}

interface PhpSelector {
  id: number;
  php_version: number;
  php_version_string: string;
  relative_path: string;
  domain_name: string;
  handler: string;
  ini_settings: Record<string, string>;
  extensions: string[];
  is_active: boolean;
}

type IniForm = {
  memory_limit: string;
  upload_max_filesize: string;
  post_max_size: string;
  max_execution_time: string;
  max_input_time: string;
  display_errors: string;
};

const defaultIni: IniForm = {
  memory_limit: "256M",
  upload_max_filesize: "64M",
  post_max_size: "64M",
  max_execution_time: "60",
  max_input_time: "60",
  display_errors: "Off",
};

function iniFromSelector(sel: PhpSelector): IniForm {
  const s = sel.ini_settings || {};
  return {
    memory_limit: s.memory_limit || "256M",
    upload_max_filesize: s.upload_max_filesize || "64M",
    post_max_size: s.post_max_size || "64M",
    max_execution_time: s.max_execution_time || "60",
    max_input_time: s.max_input_time || "60",
    display_errors: s.display_errors || "Off",
  };
}

function IniFields({
  value,
  onChange,
}: {
  value: IniForm;
  onChange: (next: IniForm) => void;
}) {
  const fields: { key: keyof IniForm; label: string }[] = [
    { key: "memory_limit", label: "memory_limit" },
    { key: "upload_max_filesize", label: "upload_max_filesize" },
    { key: "post_max_size", label: "post_max_size" },
    { key: "max_execution_time", label: "max_execution_time" },
    { key: "max_input_time", label: "max_input_time" },
  ];
  return (
    <div className="grid gap-3 sm:grid-cols-2 sm:col-span-2">
      {fields.map((f) => (
        <label key={f.key} className="block text-sm">
          <span className="mb-1 block font-medium text-cp-muted">{f.label}</span>
          <input
            className="vz-input w-full font-mono text-xs"
            value={value[f.key]}
            onChange={(e) => onChange({ ...value, [f.key]: e.target.value })}
          />
        </label>
      ))}
      <label className="block text-sm">
        <span className="mb-1 block font-medium text-cp-muted">display_errors</span>
        <select
          className="vz-input w-full"
          value={value.display_errors}
          onChange={(e) => onChange({ ...value, display_errors: e.target.value })}
        >
          <option value="Off">Off</option>
          <option value="On">On</option>
        </select>
      </label>
    </div>
  );
}

export function PhpManager({ title }: { title: string }) {
  const qc = useQueryClient();
  const { data: overview } = useQuery({
    queryKey: ["php-overview"],
    queryFn: () => apiRequest<PhpOverview>("/php/overview/"),
  });
  const { data: versions = [] } = useQuery({
    queryKey: ["php-versions"],
    queryFn: () => apiRequest<PhpVersion[]>("/php/versions/"),
  });
  const { data: selectors = [], isLoading } = useQuery({
    queryKey: ["php-selectors"],
    queryFn: () => apiRequest<PhpSelector[]>("/php/selectors/"),
  });

  const [form, setForm] = useState({
    php_version_id: 0,
    relative_path: "public_html",
    domain_name: "",
    handler: "fpm",
    ini: { ...defaultIni },
  });
  const [editSel, setEditSel] = useState<PhpSelector | null>(null);
  const [editIni, setEditIni] = useState<IniForm>(defaultIni);
  const [error, setError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["php-overview"] });
    void qc.invalidateQueries({ queryKey: ["php-versions"] });
    void qc.invalidateQueries({ queryKey: ["php-selectors"] });
  };

  const defaultVersionId =
    form.php_version_id ||
    versions.find((v) => v.is_default)?.id ||
    versions[0]?.id ||
    0;

  const create = useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      apiRequest("/php/selectors/", { method: "POST", body: JSON.stringify(payload) }),
    onSuccess: () => {
      setForm({
        php_version_id: 0,
        relative_path: "public_html",
        domain_name: "",
        handler: "fpm",
        ini: { ...defaultIni },
      });
      setError(null);
      invalidate();
      setCreateOpen(false);
    },
    onError: (err: Error) => setError(err.message),
  });

  const changeVersion = useMutation({
    mutationFn: ({ id, php_version_id }: { id: number; php_version_id: number }) =>
      apiRequest(`/php/selectors/${id}/`, {
        method: "PATCH",
        body: JSON.stringify({ php_version_id }),
      }),
    onSuccess: invalidate,
    onError: (err: Error) => setError(err.message),
  });

  const saveIni = useMutation({
    mutationFn: ({ id, ini_settings }: { id: number; ini_settings: Record<string, string> }) =>
      apiRequest(`/php/selectors/${id}/`, {
        method: "PATCH",
        body: JSON.stringify({ ini_settings }),
      }),
    onSuccess: () => {
      setEditSel(null);
      invalidate();
    },
    onError: (err: Error) => setError(err.message),
  });

  const remove = useMutation({
    mutationFn: (id: number) => apiRequest(`/php/selectors/${id}/`, { method: "DELETE" }),
    onSuccess: invalidate,
  });

  function onCreate(e: FormEvent) {
    e.preventDefault();
    if (!defaultVersionId) {
      setError("Aucune version PHP disponible.");
      return;
    }
    create.mutate({
      php_version_id: defaultVersionId,
      relative_path: form.relative_path,
      domain_name: form.domain_name,
      handler: form.handler,
      ini_settings: { ...form.ini },
    });
  }

  return (
    <div className="space-y-4 animate-fade-up">
      <PageHeader
        title={title}
        subtitle="Choisissez la version PHP et les directives php.ini de votre site (MultiPHP + éditeur INI)."
        stats={[
          { label: "Versions", value: overview?.versions ?? "—" },
          { label: "Défaut", value: overview?.default_version ?? "—" },
          { label: "Sélecteurs actifs", value: overview?.active_selectors ?? "—" },
        ]}
        actions={
          <button className="vz-btn-primary" type="button" onClick={() => setCreateOpen(true)}>
            <Plus className="h-4 w-4" /> Créer un sélecteur
          </button>
        }
      />

      {error && (
        <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-cp-danger">
          {error}
        </p>
      )}

      <div className="vz-panel overflow-x-auto">
        <div className="border-b border-cp-border bg-cp-canvas px-3 py-2 text-xs font-semibold uppercase text-cp-muted dark:border-ink-800 dark:bg-ink-900">
          Versions disponibles
        </div>
        <table className="min-w-full text-left text-sm">
          <thead>
            <tr className="text-xs uppercase text-cp-muted">
              <th className="px-3 py-2">Version</th>
              <th className="px-3 py-2">Binaire</th>
              <th className="px-3 py-2">État</th>
            </tr>
          </thead>
          <tbody>
            {versions.map((v) => (
              <tr key={v.id} className="border-t border-cp-border dark:border-ink-800">
                <td className="px-3 py-2 font-mono text-xs">
                  PHP {v.version}
                  {v.is_default ? " (défaut)" : ""}
                </td>
                <td className="px-3 py-2 font-mono text-xs text-cp-muted">
                  {v.binary_path || "—"}
                </td>
                <td className="px-3 py-2">
                  <StatusDot
                    status={v.is_available ? "active" : "inactive"}
                    label={v.is_available ? "Disponible" : "Indisponible"}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {createOpen && (
        <Modal title="Créer un sélecteur PHP" onClose={() => setCreateOpen(false)} wide>
          <form className="grid gap-3 sm:grid-cols-2" onSubmit={onCreate}>
            <select
              className="vz-input"
              value={defaultVersionId}
              onChange={(e) => setForm({ ...form, php_version_id: Number(e.target.value) })}
            >
              <option value={0}>Version…</option>
              {versions.map((v) => (
                <option key={v.id} value={v.id}>
                  PHP {v.version}
                </option>
              ))}
            </select>
            <input
              className="vz-input"
              placeholder="chemin (ex. public_html)"
              required
              value={form.relative_path}
              onChange={(e) => setForm({ ...form, relative_path: e.target.value })}
            />
            <input
              className="vz-input"
              placeholder="domaine (opt.)"
              value={form.domain_name}
              onChange={(e) => setForm({ ...form, domain_name: e.target.value })}
            />
            <select
              className="vz-input"
              value={form.handler}
              onChange={(e) => setForm({ ...form, handler: e.target.value })}
            >
              <option value="fpm">FPM</option>
              <option value="cgi">CGI</option>
              <option value="lsapi">LSAPI</option>
            </select>
            <IniFields value={form.ini} onChange={(ini) => setForm({ ...form, ini })} />
            <div className="flex justify-end gap-2 sm:col-span-2">
              <button type="button" className="vz-btn-ghost" onClick={() => setCreateOpen(false)}>
                Annuler
              </button>
              <button className="vz-btn-primary" type="submit" disabled={create.isPending}>
                Créer
              </button>
            </div>
          </form>
        </Modal>
      )}

      {editSel && (
        <Modal
          title={`Éditeur INI · ${editSel.relative_path}`}
          onClose={() => setEditSel(null)}
          wide
        >
          <form
            className="grid gap-3 sm:grid-cols-2"
            onSubmit={(e) => {
              e.preventDefault();
              saveIni.mutate({ id: editSel.id, ini_settings: { ...editIni } });
            }}
          >
            <IniFields value={editIni} onChange={setEditIni} />
            <div className="flex justify-end gap-2 sm:col-span-2">
              <button type="button" className="vz-btn-ghost" onClick={() => setEditSel(null)}>
                Annuler
              </button>
              <button className="vz-btn-primary" type="submit" disabled={saveIni.isPending}>
                Enregistrer
              </button>
            </div>
          </form>
        </Modal>
      )}

      <div className="vz-panel overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-cp-canvas text-xs uppercase text-cp-muted dark:bg-ink-900">
            <tr>
              <th className="px-3 py-2">Chemin</th>
              <th className="px-3 py-2">Version</th>
              <th className="px-3 py-2">Handler</th>
              <th className="px-3 py-2">INI</th>
              <th className="px-3 py-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td className="px-3 py-4" colSpan={5}>
                  Chargement…
                </td>
              </tr>
            )}
            {selectors.map((sel) => (
              <tr key={sel.id} className="border-t border-cp-border dark:border-ink-800">
                <td className="px-3 py-2">
                  <div className="font-mono text-xs">{sel.relative_path}</div>
                  <div className="text-[11px] text-cp-muted">{sel.domain_name || "—"}</div>
                </td>
                <td className="px-3 py-2">
                  <select
                    className="vz-input"
                    value={sel.php_version}
                    onChange={(e) =>
                      changeVersion.mutate({
                        id: sel.id,
                        php_version_id: Number(e.target.value),
                      })
                    }
                  >
                    {versions.map((v) => (
                      <option key={v.id} value={v.id}>
                        PHP {v.version}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="px-3 py-2">{sel.handler}</td>
                <td className="px-3 py-2 font-mono text-[11px] text-cp-muted">
                  {sel.ini_settings?.memory_limit || "—"}
                </td>
                <td className="px-3 py-2">
                  <div className="flex gap-1">
                    <IconAction
                      label={`Éditer php.ini ${sel.relative_path}`}
                      onClick={() => {
                        setEditSel(sel);
                        setEditIni(iniFromSelector(sel));
                      }}
                    >
                      <Pencil className="h-4 w-4" />
                    </IconAction>
                    <IconAction
                      label={`Supprimer le sélecteur ${sel.relative_path}`}
                      danger
                      onClick={() => {
                        if (window.confirm(`Supprimer le sélecteur ${sel.relative_path} ?`)) {
                          remove.mutate(sel.id);
                        }
                      }}
                    >
                      <Trash2 className="h-4 w-4" />
                    </IconAction>
                  </div>
                </td>
              </tr>
            ))}
            {!isLoading && selectors.length === 0 && (
              <tr>
                <td colSpan={5}>
                  <EmptyState icon={<Plus className="h-5 w-5" />} message="Aucun sélecteur PHP." />
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
