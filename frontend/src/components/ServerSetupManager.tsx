import { FormEvent, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Server, Globe2, Save } from "lucide-react";
import { apiRequest } from "@/lib/api";
import { runWithProgress } from "@/stores/operations";

interface ServerSetupData {
  hostname: string;
  os_hostname: string;
  nameserver1: string;
  nameserver2: string;
  nameserver3: string;
  nameserver4: string;
  resolver1: string | null;
  resolver2: string | null;
  contact_email: string;
  apply_hostname_to_mail: boolean;
  public_ip: string;
  hostname_applied_at: string | null;
  last_hostname_error: string;
  updated_at: string | null;
  hostname_apply?: { ok?: boolean; hostname?: string; error?: string } | null;
}

export function ServerSetupManager({ title }: { title: string }) {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["server-setup"],
    queryFn: () => apiRequest<ServerSetupData>("/server-setup/"),
  });
  const [form, setForm] = useState({
    hostname: "",
    nameserver1: "",
    nameserver2: "",
    nameserver3: "",
    nameserver4: "",
    contact_email: "",
    apply_hostname_to_mail: true,
  });
  const [error, setError] = useState<string | null>(null);
  const [okMsg, setOkMsg] = useState<string | null>(null);

  useEffect(() => {
    if (!data) return;
    setForm({
      hostname: data.hostname || data.os_hostname || "",
      nameserver1: (data.nameserver1 || "").replace(/\.$/, ""),
      nameserver2: (data.nameserver2 || "").replace(/\.$/, ""),
      nameserver3: (data.nameserver3 || "").replace(/\.$/, ""),
      nameserver4: (data.nameserver4 || "").replace(/\.$/, ""),
      contact_email: data.contact_email || "",
      apply_hostname_to_mail: data.apply_hostname_to_mail,
    });
  }, [data]);

  const save = useMutation({
    mutationFn: () =>
      runWithProgress("Enregistrement configuration serveur", () =>
        apiRequest<ServerSetupData>("/server-setup/", {
          method: "PUT",
          body: JSON.stringify({
            ...form,
            apply_hostname: true,
          }),
        }),
      ),
    onSuccess: (payload) => {
      setError(null);
      setOkMsg(
        payload.hostname_apply?.ok
          ? `Hostname appliqué: ${payload.hostname_apply.hostname || payload.hostname}`
          : "Configuration enregistrée (nameservers + hostname).",
      );
      void qc.invalidateQueries({ queryKey: ["server-setup"] });
    },
    onError: (err: Error) => {
      setOkMsg(null);
      setError(err.message);
    },
  });

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    save.mutate();
  }

  return (
    <div className="space-y-4 animate-fade-up">
      <div className="vz-panel overflow-hidden">
        <div className="border-b border-cp-border bg-cp-header px-4 py-2 text-white">
          <h1 className="text-sm font-semibold uppercase tracking-wide">{title}</h1>
          <p className="text-[11px] text-white/80">
            Hostname système + nameservers par défaut pour les nouveaux comptes / zones DNS.
          </p>
        </div>
        <div className="grid gap-3 p-4 sm:grid-cols-2">
          <div className="rounded border border-cp-border bg-cp-canvas p-3 text-sm">
            <p className="text-xs font-semibold uppercase text-cp-muted">Hostname OS actuel</p>
            <p className="mt-1 font-mono text-cp-text">{data?.os_hostname || "—"}</p>
          </div>
          <div className="rounded border border-cp-border bg-cp-canvas p-3 text-sm">
            <p className="text-xs font-semibold uppercase text-cp-muted">IP publique</p>
            <p className="mt-1 font-mono text-cp-text">{data?.public_ip || "—"}</p>
          </div>
        </div>
      </div>

      {isLoading && <p className="text-sm text-cp-muted">Chargement…</p>}
      {error && (
        <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-cp-danger">{error}</p>
      )}
      {okMsg && (
        <p className="rounded border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
          {okMsg}
        </p>
      )}
      {data?.last_hostname_error && (
        <p className="rounded border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800">
          Dernière erreur hostname: {data.last_hostname_error}
        </p>
      )}

      <form className="vz-panel space-y-5 p-4" onSubmit={onSubmit}>
        <section className="space-y-3">
          <div className="flex items-center gap-2 text-sm font-semibold">
            <Server className="h-4 w-4 text-cp-orange" />
            Hostname du serveur
          </div>
          <label className="block space-y-1">
            <span className="text-xs font-medium text-cp-muted">FQDN (ex: vmi3182722.vzonecloud.co.uk)</span>
            <input
              className="vz-input font-mono"
              value={form.hostname}
              onChange={(e) => setForm({ ...form, hostname: e.target.value })}
              required
              placeholder="server.example.com"
            />
          </label>
          <label className="flex items-center gap-2 text-sm text-cp-text">
            <input
              type="checkbox"
              checked={form.apply_hostname_to_mail}
              onChange={(e) => setForm({ ...form, apply_hostname_to_mail: e.target.checked })}
            />
            Appliquer aussi à Postfix (myhostname)
          </label>
          <p className="text-xs text-cp-muted">
            Applique `hostnamectl`, met à jour `/etc/hosts`, `VZONE_PANEL_HOSTNAMES`, `ALLOWED_HOSTS` et
            régénère Nginx.
          </p>
        </section>

        <section className="space-y-3 border-t border-cp-border pt-4">
          <div className="flex items-center gap-2 text-sm font-semibold">
            <Globe2 className="h-4 w-4 text-cp-orange" />
            Nameservers par défaut
          </div>
          <p className="text-xs text-cp-muted">
            Utilisés automatiquement pour chaque nouvelle zone DNS / nouveau compte.
          </p>
          <div className="grid gap-3 md:grid-cols-2">
            <label className="space-y-1">
              <span className="text-xs font-medium text-cp-muted">Nameserver 1 *</span>
              <input
                className="vz-input font-mono"
                required
                value={form.nameserver1}
                onChange={(e) => setForm({ ...form, nameserver1: e.target.value })}
                placeholder="ns1.example.com"
              />
            </label>
            <label className="space-y-1">
              <span className="text-xs font-medium text-cp-muted">Nameserver 2 *</span>
              <input
                className="vz-input font-mono"
                required
                value={form.nameserver2}
                onChange={(e) => setForm({ ...form, nameserver2: e.target.value })}
                placeholder="ns2.example.com"
              />
            </label>
            <label className="space-y-1">
              <span className="text-xs font-medium text-cp-muted">Nameserver 3</span>
              <input
                className="vz-input font-mono"
                value={form.nameserver3}
                onChange={(e) => setForm({ ...form, nameserver3: e.target.value })}
                placeholder="ns3.example.com"
              />
            </label>
            <label className="space-y-1">
              <span className="text-xs font-medium text-cp-muted">Nameserver 4</span>
              <input
                className="vz-input font-mono"
                value={form.nameserver4}
                onChange={(e) => setForm({ ...form, nameserver4: e.target.value })}
                placeholder="ns4.example.com"
              />
            </label>
          </div>
          <label className="block space-y-1">
            <span className="text-xs font-medium text-cp-muted">Email contact (SOA / admin)</span>
            <input
              className="vz-input"
              type="email"
              value={form.contact_email}
              onChange={(e) => setForm({ ...form, contact_email: e.target.value })}
              placeholder="admin@example.com"
            />
          </label>
        </section>

        <div className="flex justify-end border-t border-cp-border pt-3">
          <button className="vz-btn-primary" type="submit" disabled={save.isPending}>
            <Save className="h-4 w-4" />
            {save.isPending ? "Application…" : "Save Changes"}
          </button>
        </div>
      </form>
    </div>
  );
}
