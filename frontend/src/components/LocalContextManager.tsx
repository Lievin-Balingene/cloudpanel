import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, MessageCircle, PlugZap, Smartphone, Wifi } from "lucide-react";
import { useState } from "react";
import { apiRequest, apiRequestPaginated } from "@/lib/api";
import { type LocalOverview, type LocalProfile, useLocalProfile } from "@/lib/localContext";
import { PageHeader } from "@/components/ui/PageChrome";
import { FormPageSkeleton, PanelSkeleton } from "@/components/ui/Skeleton";
import type { User } from "@/types";

type Tab = "lieu" | "coupure" | "messages";

export function LocalContextManager() {
  const qc = useQueryClient();
  const { data: profile, isLoading } = useLocalProfile();
  const [tab, setTab] = useState<Tab>("lieu");
  const [error, setError] = useState<string | null>(null);

  const overview = useQuery({
    queryKey: ["local-context-overview"],
    queryFn: () => apiRequest<LocalOverview>("/local-context/overview/"),
  });

  if (isLoading || !profile) {
    return (
      <div className="space-y-4">
        <FormPageSkeleton />
        <PanelSkeleton lines={5} />
      </div>
    );
  }

  return (
    <div className="space-y-4 animate-fade-up">
      <PageHeader
        title="Contexte local"
        subtitle="Le panneau s’adapte au lien lent, aux coupures et au téléphone — ce n’est pas un logiciel de facturation."
        stats={[
          { label: "Fuseau", value: profile.timezone.replace("Africa/", "") },
          { label: "Économie data", value: profile.data_saver ? "oui" : "non" },
          { label: "Services arrêtés", value: overview.data?.services_down ?? "—" },
        ]}
      />
      {error && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-cp-danger">{error}</p>
      )}
      <div className="flex gap-1 rounded-lg border border-cp-border bg-white p-1 dark:border-ink-800 dark:bg-ink-950">
        {(
          [
            ["lieu", "Lien et fuseau"],
            ["coupure", "Après une coupure"],
            ["messages", "Prévenir le client"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            className={`flex-1 rounded-md px-3 py-2 text-sm font-medium ${
              tab === id ? "bg-cp-navy text-white" : "text-cp-muted hover:bg-cp-canvas"
            }`}
          >
            {label}
          </button>
        ))}
      </div>
      {tab === "lieu" && (
        <PlaceForm
          profile={profile}
          onError={setError}
          onSaved={() => {
            setError(null);
            void qc.invalidateQueries({ queryKey: ["local-context-profile"] });
            void qc.invalidateQueries({ queryKey: ["local-context-overview"] });
          }}
        />
      )}
      {tab === "coupure" && <OutagePanel overview={overview.data} onError={setError} />}
      {tab === "messages" && <NoticeForm onError={setError} />}
    </div>
  );
}

function PlaceForm({
  profile,
  onSaved,
  onError,
}: {
  profile: LocalProfile;
  onSaved: () => void;
  onError: (m: string | null) => void;
}) {
  const [form, setForm] = useState({
    country: profile.country,
    timezone: profile.timezone,
    data_saver: profile.data_saver,
    lite_panel: profile.lite_panel,
    require_phone: profile.require_phone,
    phone_prefix: profile.phone_prefix,
    notify_channel: profile.notify_channel,
    backup_window_start: profile.backup_window_start,
    backup_window_end: profile.backup_window_end,
    defer_heavy_jobs: profile.defer_heavy_jobs,
    apply_country_defaults: true,
  });

  const save = useMutation({
    mutationFn: () =>
      apiRequest("/local-context/profile/", {
        method: "PATCH",
        body: JSON.stringify(form),
      }),
    onSuccess: onSaved,
    onError: (e: Error) => onError(e.message),
  });

  return (
    <form
      className="vz-panel space-y-4 p-4"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate();
      }}
    >
      <p className="text-sm leading-relaxed text-cp-muted">
        Un panneau classique suppose la fibre et un serveur toujours allumé. Ici : moins de data
        mobile, un VPS petit, des sauvegardes la nuit, un numéro WhatsApp pour prévenir le client
        que son <em>site</em> est prêt — pas pour encaisser.
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block space-y-1 text-sm">
          <span className="text-xs font-medium text-cp-muted">Pays (indicatif + heure)</span>
          <select
            className="vz-input w-full"
            value={form.country}
            onChange={(e) => {
              const code = e.target.value;
              const row = profile.catalog.countries.find((c) => c.code === code);
              setForm((f) => ({
                ...f,
                country: code,
                timezone: form.apply_country_defaults && row?.tz ? row.tz : f.timezone,
                phone_prefix: form.apply_country_defaults && row?.prefix ? row.prefix : f.phone_prefix,
              }));
            }}
          >
            {profile.catalog.countries.map((c) => (
              <option key={c.code} value={c.code}>
                {c.label}
              </option>
            ))}
          </select>
        </label>
        <label className="block space-y-1 text-sm">
          <span className="text-xs font-medium text-cp-muted">Fuseau</span>
          <select
            className="vz-input w-full"
            value={form.timezone}
            onChange={(e) => setForm({ ...form, timezone: e.target.value })}
          >
            {profile.catalog.timezones.map((tz) => (
              <option key={tz} value={tz}>
                {tz}
              </option>
            ))}
          </select>
        </label>
        <label className="block space-y-1 text-sm">
          <span className="text-xs font-medium text-cp-muted">Indicatif téléphone</span>
          <input
            className="vz-input w-full"
            value={form.phone_prefix}
            onChange={(e) => setForm({ ...form, phone_prefix: e.target.value })}
          />
        </label>
      </div>
      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          className="mt-1"
          checked={form.data_saver}
          onChange={(e) => setForm({ ...form, data_saver: e.target.checked })}
        />
        <span>
          <strong className="inline-flex items-center gap-1">
            <Wifi className="h-3.5 w-3.5" /> Économie de données
          </strong>
          <span className="block text-cp-muted">
            Moins de rafraîchissements. Utile en 3G, partage de connexion, Go cher.
          </span>
        </span>
      </label>
      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          className="mt-1"
          checked={form.lite_panel}
          onChange={(e) => setForm({ ...form, lite_panel: e.target.checked })}
        />
        <span>
          <strong>Panneau allégé (petit VPS)</strong>
          <span className="block text-cp-muted">
            Masque Docker et Kubernetes. Garde sites, mail, fichiers, PHP — ce qu’on vend vraiment
            sur 2–4 Go.
          </span>
        </span>
      </label>
      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          className="mt-1"
          checked={form.require_phone}
          onChange={(e) => setForm({ ...form, require_phone: e.target.checked })}
        />
        <span>
          <strong className="inline-flex items-center gap-1">
            <Smartphone className="h-3.5 w-3.5" /> Numéro à la création du compte
          </strong>
          <span className="block text-cp-muted">
            Pour prévenir que le site est en ligne, qu’un certificat expire, que le disque est
            plein. Pas pour facturer.
          </span>
        </span>
      </label>
      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          className="mt-1"
          checked={form.defer_heavy_jobs}
          onChange={(e) => setForm({ ...form, defer_heavy_jobs: e.target.checked })}
        />
        <span>
          Sauvegardes seulement la nuit ({form.backup_window_start}h–{form.backup_window_end}h heure
          locale). Le lien reste libre le jour.
        </span>
      </label>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block space-y-1 text-sm">
          <span className="text-xs font-medium text-cp-muted">Début fenêtre nuit</span>
          <input
            className="vz-input w-full"
            type="number"
            min={0}
            max={23}
            value={form.backup_window_start}
            onChange={(e) => setForm({ ...form, backup_window_start: Number(e.target.value) })}
          />
        </label>
        <label className="block space-y-1 text-sm">
          <span className="text-xs font-medium text-cp-muted">Fin</span>
          <input
            className="vz-input w-full"
            type="number"
            min={0}
            max={23}
            value={form.backup_window_end}
            onChange={(e) => setForm({ ...form, backup_window_end: Number(e.target.value) })}
          />
        </label>
      </div>
      <button type="submit" className="vz-btn-primary" disabled={save.isPending}>
        Enregistrer
      </button>
    </form>
  );
}

function OutagePanel({
  overview,
  onError,
}: {
  overview?: LocalOverview;
  onError: (m: string | null) => void;
}) {
  const qc = useQueryClient();
  const recover = useMutation({
    mutationFn: () => apiRequest("/local-context/recover/", { method: "POST", body: "{}" }),
    onSuccess: () => {
      onError(null);
      void qc.invalidateQueries({ queryKey: ["local-context-overview"] });
    },
    onError: (e: Error) => onError(e.message),
  });

  return (
    <div className="space-y-4">
      <div className="vz-panel p-4">
        <p className="flex items-start gap-2 text-sm text-cp-muted">
          <PlugZap className="mt-0.5 h-4 w-4 shrink-0 text-cp-orange" />
          Après une coupure ou un générateur qui redémarre, nginx et le panneau peuvent rester
          arrêtés. Un clic relance la pile (sites, mail, API).
        </p>
        <button
          type="button"
          className="vz-btn-primary mt-3"
          disabled={recover.isPending}
          onClick={() => recover.mutate()}
        >
          Relancer les services
        </button>
      </div>
      <div className="vz-panel overflow-hidden">
        <ul className="divide-y divide-cp-border dark:divide-ink-800">
          {(overview?.services || []).map((s) => (
            <li key={s.id} className="flex items-center justify-between px-4 py-3 text-sm">
              <span>{s.label}</span>
              <span
                className={
                  s.state === "active" ? "text-emerald-600" : "text-amber-700 dark:text-amber-300"
                }
              >
                {s.state === "active"
                  ? "en marche"
                  : s.state === "unknown"
                    ? "non vérifié (Windows / mock)"
                    : s.state}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function NoticeForm({ onError }: { onError: (m: string | null) => void }) {
  const { data: users = [] } = useQuery({
    queryKey: ["users", "local-notice"],
    queryFn: async () => {
      const res = await apiRequestPaginated<User>("/auth/users/?role=client&page_size=200");
      return res.results;
    },
  });
  const [userId, setUserId] = useState("");
  const [kind, setKind] = useState("welcome");
  const notice = useQuery({
    queryKey: ["local-notice", userId, kind],
    queryFn: () =>
      apiRequest<{ body: string; whatsapp_url: string; sms_url: string }>(
        `/local-context/notice/?user_id=${userId}&kind=${kind}`,
      ),
    enabled: Boolean(userId),
  });

  const copy = async () => {
    if (!notice.data?.body) return;
    try {
      await navigator.clipboard.writeText(notice.data.body);
    } catch (e) {
      onError(e instanceof Error ? e.message : "Copie impossible");
    }
  };

  return (
    <div className="vz-panel space-y-3 p-4">
      <p className="flex items-start gap-2 text-sm text-cp-muted">
        <MessageCircle className="mt-0.5 h-4 w-4 shrink-0 text-cp-orange" />
        Texte à envoyer depuis votre téléphone : site prêt, disque plein, SSL, reprise après
        coupure. Aucun montant, aucun moyen de paiement.
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        <select className="vz-input" value={userId} onChange={(e) => setUserId(e.target.value)}>
          <option value="">Compte…</option>
          {users.map((u) => (
            <option key={u.id} value={u.id}>
              {u.username}
              {u.phone ? ` · ${u.phone}` : " · pas de numéro"}
            </option>
          ))}
        </select>
        <select className="vz-input" value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="welcome">Compte / site prêt</option>
          <option value="disk">Disque presque plein</option>
          <option value="ssl">Certificat HTTPS à renouveler</option>
          <option value="outage">Reprise après coupure</option>
        </select>
      </div>
      {notice.data?.body && (
        <>
          <textarea className="vz-input min-h-[120px] w-full" readOnly value={notice.data.body} />
          <div className="flex flex-wrap gap-2">
            <button type="button" className="vz-btn-ghost inline-flex items-center gap-1 text-sm" onClick={() => void copy()}>
              <Copy className="h-4 w-4" /> Copier
            </button>
            {notice.data.whatsapp_url && (
              <a
                className="vz-btn-primary inline-flex items-center gap-1 text-sm"
                href={notice.data.whatsapp_url}
                target="_blank"
                rel="noreferrer"
              >
                Ouvrir WhatsApp
              </a>
            )}
            {notice.data.sms_url && (
              <a className="vz-btn-ghost text-sm" href={notice.data.sms_url}>
                SMS
              </a>
            )}
          </div>
        </>
      )}
    </div>
  );
}
