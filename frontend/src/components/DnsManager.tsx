import { FormEvent, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FilePlus2, Globe2, Plus, ShieldCheck, ShieldOff, Trash2 } from "lucide-react";
import { apiRequest } from "@/lib/api";
import type { DnsRecord, DnsZone } from "@/types";
import { IconAction } from "@/components/ui/IconAction";
import { Modal } from "@/components/ui/Modal";
import { EmptyState, PageHeader, StatusDot } from "@/components/ui/PageChrome";

export function DnsManager({ title }: { title: string }) {
  const qc = useQueryClient();
  const { data: zones = [], isLoading } = useQuery({
    queryKey: ["dns-zones"],
    queryFn: () => apiRequest<DnsZone[]>("/dns/zones/"),
  });
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [zoneName, setZoneName] = useState("");
  const [createKind, setCreateKind] = useState<"zone" | "record" | null>(null);
  const [record, setRecord] = useState({
    record_type: "A",
    name: "www",
    content: "",
    ttl: 14400,
    priority: 10,
  });

  const selected = useMemo(
    () => zones.find((z) => z.id === selectedId) ?? zones[0] ?? null,
    [zones, selectedId],
  );

  const createZone = useMutation({
    mutationFn: () =>
      apiRequest("/dns/zones/", {
        method: "POST",
        body: JSON.stringify({ name: zoneName }),
      }),
    onSuccess: () => {
      setZoneName("");
      setCreateKind(null);
      void qc.invalidateQueries({ queryKey: ["dns-zones"] });
    },
  });

  const createRecord = useMutation({
    mutationFn: () => {
      if (!selected) throw new Error("Aucune zone");
      const payload: Record<string, unknown> = {
        record_type: record.record_type,
        name: record.name,
        content: record.content,
        ttl: record.ttl,
      };
      if (record.record_type === "MX" || record.record_type === "SRV") {
        payload.priority = record.priority;
      }
      return apiRequest(`/dns/zones/${selected.id}/records/`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },
    onSuccess: () => {
      setCreateKind(null);
      void qc.invalidateQueries({ queryKey: ["dns-zones"] });
    },
  });

  const toggleDnssec = useMutation({
    mutationFn: (enabled: boolean) => {
      if (!selected) throw new Error("Aucune zone");
      return apiRequest(`/dns/zones/${selected.id}/dnssec/`, {
        method: "POST",
        body: JSON.stringify({ enabled }),
      });
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["dns-zones"] }),
  });

  const deleteRecord = useMutation({
    mutationFn: (rec: DnsRecord) =>
      apiRequest(`/dns/zones/${rec.zone}/records/${rec.id}/`, { method: "DELETE" }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["dns-zones"] }),
  });

  function onCreateZone(e: FormEvent) {
    e.preventDefault();
    createZone.mutate();
  }

  function onCreateRecord(e: FormEvent) {
    e.preventDefault();
    createRecord.mutate();
  }

  return (
    <div className="space-y-4 animate-fade-up">
      <PageHeader
        title={title}
        subtitle="Zones DNS, enregistrements, DNSSEC et numéros de série SOA automatiques."
        stats={[
          { label: "Zones", value: zones.length },
          { label: "Enregistrements", value: zones.reduce((total, zone) => total + zone.record_count, 0) },
          { label: "DNSSEC actif", value: zones.filter((zone) => zone.dnssec_enabled).length },
        ]}
        actions={<button type="button" className="vz-btn-primary" onClick={() => setCreateKind("zone")}><Plus className="h-4 w-4" />Créer une zone</button>}
      />

      <div className="grid gap-4 lg:grid-cols-[minmax(0,13rem)_minmax(0,1fr)]">
        <div className="vz-panel min-w-0 overflow-hidden">
          <div className="border-b border-cp-border bg-cp-canvas px-3 py-2 text-[10px] font-semibold uppercase tracking-wide text-cp-muted dark:border-ink-800 dark:bg-ink-900">
            Zones
          </div>
          {isLoading && <p className="p-3 text-xs text-cp-muted">Chargement…</p>}
          <ul className="max-h-[min(70vh,32rem)] overflow-y-auto">
            {zones.map((z) => (
              <li key={z.id} className="min-w-0">
                <button
                  type="button"
                  title={z.name}
                  className={`block w-full min-w-0 overflow-hidden border-b border-cp-border px-2.5 py-2 text-left dark:border-ink-800 ${
                    selected?.id === z.id
                      ? "bg-cp-orange-soft font-semibold text-cp-orange-dark"
                      : "hover:bg-cp-canvas dark:hover:bg-ink-900"
                  }`}
                  onClick={() => setSelectedId(z.id)}
                >
                  <span className="block truncate text-xs leading-snug">{z.name}</span>
                  <span className="mt-0.5 block truncate text-[10px] font-normal leading-tight text-cp-muted">
                    {z.record_count} rec. · s{z.soa_serial}
                  </span>
                </button>
              </li>
            ))}
          </ul>
          {!isLoading && zones.length === 0 && (
            <EmptyState
              icon={<Globe2 className="h-8 w-8" />}
              message="Aucune zone DNS."
              action={
                <button type="button" className="vz-btn-primary" onClick={() => setCreateKind("zone")}>
                  <Plus className="h-4 w-4" />
                  Créer une zone
                </button>
              }
            />
          )}
        </div>

        <div className="min-w-0 space-y-3">
          {selected ? (
            <>
              <div className="vz-panel flex min-w-0 flex-wrap items-center justify-between gap-2 overflow-hidden p-3 sm:p-4">
                <div className="min-w-0 flex-1 overflow-hidden">
                  <p className="truncate text-sm font-semibold" title={selected.name}>
                    {selected.name}
                  </p>
                  <div className="mt-1 flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-cp-muted">
                    <span className="truncate">Propriétaire {selected.owner_username}</span>
                    <StatusDot
                      status={selected.dnssec_enabled ? "active" : "inactive"}
                      label={`DNSSEC ${selected.dnssec_enabled ? "actif" : "inactif"}`}
                    />
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <button type="button" className="vz-btn-primary" onClick={() => setCreateKind("record")}>
                    <FilePlus2 className="h-4 w-4" />
                    Ajouter
                  </button>
                  <IconAction
                    label={selected.dnssec_enabled ? "Désactiver DNSSEC" : "Activer DNSSEC"}
                    onClick={() => toggleDnssec.mutate(!selected.dnssec_enabled)}
                  >
                    {selected.dnssec_enabled ? (
                      <ShieldOff className="h-4 w-4" />
                    ) : (
                      <ShieldCheck className="h-4 w-4" />
                    )}
                  </IconAction>
                </div>
              </div>

              <div className="vz-panel min-w-0 overflow-x-auto">
                <table className="w-full min-w-[36rem] table-fixed text-left text-xs">
                  <thead className="bg-cp-canvas text-[10px] uppercase text-cp-muted dark:bg-ink-900">
                    <tr>
                      <th className="w-14 px-2 py-2">Type</th>
                      <th className="w-28 px-2 py-2">Nom</th>
                      <th className="px-2 py-2">Contenu</th>
                      <th className="w-16 px-2 py-2">TTL</th>
                      <th className="w-12 px-2 py-2">Prio</th>
                      <th className="w-10 px-2 py-2" />
                    </tr>
                  </thead>
                  <tbody>
                    {selected.records.length === 0 && (
                      <tr>
                        <td colSpan={6}>
                          <EmptyState
                            icon={<FilePlus2 className="h-8 w-8" />}
                            message="Aucun enregistrement dans cette zone."
                            action={
                              <button
                                type="button"
                                className="vz-btn-primary"
                                onClick={() => setCreateKind("record")}
                              >
                                <Plus className="h-4 w-4" />
                                Ajouter un enregistrement
                              </button>
                            }
                          />
                        </td>
                      </tr>
                    )}
                    {selected.records.map((rec) => (
                      <tr key={rec.id} className="border-t border-cp-border dark:border-ink-800">
                        <td className="px-2 py-1.5 font-mono text-[11px]">{rec.record_type}</td>
                        <td className="max-w-0 truncate px-2 py-1.5 text-[11px]" title={rec.name}>
                          {rec.name}
                        </td>
                        <td
                          className="max-w-0 truncate px-2 py-1.5 font-mono text-[10px] leading-snug"
                          title={rec.content}
                        >
                          {rec.content}
                        </td>
                        <td className="px-2 py-1.5 text-[11px] tabular-nums">{rec.ttl ?? "—"}</td>
                        <td className="px-2 py-1.5 text-[11px] tabular-nums">{rec.priority ?? "—"}</td>
                        <td className="px-2 py-1.5 text-right">
                          <IconAction
                            label="Supprimer l’enregistrement"
                            danger
                            onClick={() => deleteRecord.mutate(rec)}
                          >
                            <Trash2 className="h-4 w-4" />
                          </IconAction>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <div className="vz-panel">
              <EmptyState
                icon={<Globe2 className="h-8 w-8" />}
                message="Sélectionnez ou créez une zone DNS."
                action={
                  <button type="button" className="vz-btn-primary" onClick={() => setCreateKind("zone")}>
                    <Plus className="h-4 w-4" />
                    Créer une zone
                  </button>
                }
              />
            </div>
          )}
        </div>
      </div>
      {createKind === "zone" && <Modal title="Nouvelle zone DNS" subtitle="La zone et son SOA seront créés automatiquement." onClose={() => setCreateKind(null)}><form className="space-y-3" onSubmit={onCreateZone}><div><label className="mb-1 block text-xs font-medium text-cp-muted">Nom de domaine</label><input className="vz-input" placeholder="exemple.com" required autoFocus value={zoneName} onChange={(e) => setZoneName(e.target.value)} /></div><div className="flex justify-end gap-2"><button type="button" className="vz-btn-ghost" onClick={() => setCreateKind(null)}>Annuler</button><button className="vz-btn-primary" type="submit" disabled={createZone.isPending}>{createZone.isPending ? "Création…" : "Créer"}</button></div></form></Modal>}
      {createKind === "record" && selected && <Modal title="Nouvel enregistrement" subtitle={selected.name} onClose={() => setCreateKind(null)} wide><form className="grid gap-3 sm:grid-cols-2" onSubmit={onCreateRecord}><div><label className="mb-1 block text-xs font-medium text-cp-muted">Type</label><select className="vz-input" value={record.record_type} onChange={(e) => setRecord({ ...record, record_type: e.target.value })}>{["A", "AAAA", "CNAME", "TXT", "MX", "SRV", "CAA", "NS"].map((type) => <option key={type} value={type}>{type}</option>)}</select></div><div><label className="mb-1 block text-xs font-medium text-cp-muted">Nom</label><input className="vz-input" value={record.name} onChange={(e) => setRecord({ ...record, name: e.target.value })} placeholder="www" /></div><div className="sm:col-span-2"><label className="mb-1 block text-xs font-medium text-cp-muted">Contenu</label><input className="vz-input" required value={record.content} onChange={(e) => setRecord({ ...record, content: e.target.value })} /></div><div><label className="mb-1 block text-xs font-medium text-cp-muted">TTL</label><input className="vz-input" type="number" value={record.ttl} onChange={(e) => setRecord({ ...record, ttl: Number(e.target.value) })} /></div>{(record.record_type === "MX" || record.record_type === "SRV") && <div><label className="mb-1 block text-xs font-medium text-cp-muted">Priorité</label><input className="vz-input" type="number" value={record.priority} onChange={(e) => setRecord({ ...record, priority: Number(e.target.value) })} /></div>}<div className="flex justify-end gap-2 sm:col-span-2"><button type="button" className="vz-btn-ghost" onClick={() => setCreateKind(null)}>Annuler</button><button className="vz-btn-primary" type="submit" disabled={createRecord.isPending}>{createRecord.isPending ? "Ajout…" : "Ajouter"}</button></div></form></Modal>}
    </div>
  );
}
