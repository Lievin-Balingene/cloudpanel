import { FormEvent, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";
import type { DnsRecord, DnsZone } from "@/types";

export function DnsManager({ title }: { title: string }) {
  const qc = useQueryClient();
  const { data: zones = [], isLoading } = useQuery({
    queryKey: ["dns-zones"],
    queryFn: () => apiRequest<DnsZone[]>("/dns/zones/"),
  });
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [zoneName, setZoneName] = useState("");
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
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["dns-zones"] }),
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
      <div className="vz-panel p-4">
        <h1 className="text-xl font-semibold">{title}</h1>
        <p className="text-sm text-cp-muted">
          A, AAAA, CNAME, TXT, MX, SRV, CAA, NS · DNSSEC · serial SOA auto.
        </p>
      </div>

      <form className="vz-panel flex flex-wrap gap-2 p-4" onSubmit={onCreateZone}>
        <input
          className="vz-input max-w-sm flex-1"
          placeholder="exemple.com"
          required
          value={zoneName}
          onChange={(e) => setZoneName(e.target.value)}
        />
        <button className="vz-btn-primary" type="submit">
          Créer la zone
        </button>
      </form>

      <div className="grid gap-4 lg:grid-cols-[240px_1fr]">
        <div className="vz-panel overflow-hidden">
          <div className="border-b border-cp-border bg-cp-canvas px-3 py-2 text-xs font-semibold uppercase text-cp-muted dark:border-ink-800 dark:bg-ink-900">
            Zones
          </div>
          {isLoading && <p className="p-3 text-sm">Chargement…</p>}
          <ul>
            {zones.map((z) => (
              <li key={z.id}>
                <button
                  type="button"
                  className={`block w-full border-b border-cp-border px-3 py-2 text-left text-sm dark:border-ink-800 ${
                    selected?.id === z.id ? "bg-cp-orange-soft font-semibold text-cp-orange-dark" : ""
                  }`}
                  onClick={() => setSelectedId(z.id)}
                >
                  {z.name}
                  <span className="mt-0.5 block text-[11px] font-normal text-cp-muted">
                    {z.record_count} records · serial {z.soa_serial}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>

        <div className="space-y-3">
          {selected ? (
            <>
              <div className="vz-panel flex flex-wrap items-center justify-between gap-2 p-4">
                <div>
                  <p className="font-semibold">{selected.name}</p>
                  <p className="text-xs text-cp-muted">
                    Propriétaire {selected.owner_username} · DNSSEC{" "}
                    {selected.dnssec_enabled ? "ON" : "OFF"}
                  </p>
                </div>
                <button
                  type="button"
                  className="vz-btn-ghost"
                  onClick={() => toggleDnssec.mutate(!selected.dnssec_enabled)}
                >
                  {selected.dnssec_enabled ? "Désactiver DNSSEC" : "Activer DNSSEC"}
                </button>
              </div>

              <form className="vz-panel grid gap-2 p-4 md:grid-cols-6" onSubmit={onCreateRecord}>
                <select
                  className="vz-input"
                  value={record.record_type}
                  onChange={(e) => setRecord({ ...record, record_type: e.target.value })}
                >
                  {["A", "AAAA", "CNAME", "TXT", "MX", "SRV", "CAA", "NS"].map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
                <input
                  className="vz-input"
                  value={record.name}
                  onChange={(e) => setRecord({ ...record, name: e.target.value })}
                  placeholder="nom"
                />
                <input
                  className="vz-input md:col-span-2"
                  value={record.content}
                  onChange={(e) => setRecord({ ...record, content: e.target.value })}
                  placeholder="contenu"
                  required
                />
                <input
                  className="vz-input"
                  type="number"
                  value={record.ttl}
                  onChange={(e) => setRecord({ ...record, ttl: Number(e.target.value) })}
                />
                <button className="vz-btn-primary" type="submit">
                  Ajouter
                </button>
              </form>

              <div className="vz-panel overflow-x-auto">
                <table className="min-w-full text-left text-sm">
                  <thead className="bg-cp-canvas text-xs uppercase text-cp-muted dark:bg-ink-900">
                    <tr>
                      <th className="px-3 py-2">Type</th>
                      <th className="px-3 py-2">Nom</th>
                      <th className="px-3 py-2">Contenu</th>
                      <th className="px-3 py-2">TTL</th>
                      <th className="px-3 py-2">Prio</th>
                      <th className="px-3 py-2" />
                    </tr>
                  </thead>
                  <tbody>
                    {selected.records.map((rec) => (
                      <tr key={rec.id} className="border-t border-cp-border dark:border-ink-800">
                        <td className="px-3 py-2 font-mono text-xs">{rec.record_type}</td>
                        <td className="px-3 py-2">{rec.name}</td>
                        <td className="px-3 py-2 font-mono text-xs">{rec.content}</td>
                        <td className="px-3 py-2">{rec.ttl ?? "—"}</td>
                        <td className="px-3 py-2">{rec.priority ?? "—"}</td>
                        <td className="px-3 py-2 text-right">
                          <button
                            type="button"
                            className="text-cp-danger hover:underline"
                            onClick={() => deleteRecord.mutate(rec)}
                          >
                            Supprimer
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <div className="vz-panel p-6 text-sm text-cp-muted">Aucune zone sélectionnée.</div>
          )}
        </div>
      </div>
    </div>
  );
}
