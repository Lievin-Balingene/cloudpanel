import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";
import { runWithProgress } from "@/stores/operations";

interface K8sOverview {
  provision_mode: string;
  kubectl_available: boolean;
  kubectl_bin?: string;
  namespaces: number;
  pods: number;
  workloads: number;
  pods_running: number;
  pods_non_running: number;
}

interface K8sRes {
  namespaces: { name: string; status?: string }[];
  pods: { name: string; namespace: string; status: string; node?: string }[];
  workloads: { name: string; namespace: string; kind: string; ready: string }[];
}

export function KubernetesManager({ title }: { title: string }) {
  const qc = useQueryClient();
  const { data: overview } = useQuery({
    queryKey: ["k8s-overview"],
    queryFn: () => apiRequest<K8sOverview>("/kubernetes/overview/"),
  });
  const { data: resources } = useQuery({
    queryKey: ["k8s-resources"],
    queryFn: () => apiRequest<K8sRes>("/kubernetes/resources/"),
  });
  const [manifest, setManifest] = useState("");
  const [namespace, setNamespace] = useState("");
  const [output, setOutput] = useState("");
  const [error, setError] = useState<string | null>(null);

  const apply = useMutation({
    mutationFn: () =>
      runWithProgress("Kubernetes apply", () =>
        apiRequest<{ ok: boolean; output: string }>("/kubernetes/apply/", {
          method: "POST",
          body: JSON.stringify({ manifest, namespace }),
        }),
      ),
    onSuccess: (data) => {
      setError(null);
      setOutput(data.output || "Applied.");
      void qc.invalidateQueries({ queryKey: ["k8s-overview"] });
      void qc.invalidateQueries({ queryKey: ["k8s-resources"] });
    },
    onError: (err: Error) => setError(err.message),
  });

  const remove = useMutation({
    mutationFn: () =>
      runWithProgress("Kubernetes delete", () =>
        apiRequest<{ ok: boolean; output: string }>("/kubernetes/delete/", {
          method: "POST",
          body: JSON.stringify({ manifest, namespace }),
        }),
      ),
    onSuccess: (data) => {
      setError(null);
      setOutput(data.output || "Deleted.");
      void qc.invalidateQueries({ queryKey: ["k8s-overview"] });
      void qc.invalidateQueries({ queryKey: ["k8s-resources"] });
    },
    onError: (err: Error) => setError(err.message),
  });

  function onApply(e: FormEvent) {
    e.preventDefault();
    apply.mutate();
  }

  return (
    <div className="space-y-4 animate-fade-up">
      <div className="vz-panel p-4">
        <h1 className="text-xl font-semibold">{title}</h1>
        <p className="text-sm text-cp-muted">
          Kubernetes : aperçu cluster, pods/workloads, apply/delete manifest YAML.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[
          { label: "Namespaces", value: overview?.namespaces ?? "—" },
          { label: "Pods", value: overview?.pods ?? "—" },
          { label: "Workloads", value: overview?.workloads ?? "—" },
          { label: "Pods Running", value: overview?.pods_running ?? "—" },
        ].map((card) => (
          <div key={card.label} className="vz-panel p-4">
            <p className="text-xs font-semibold uppercase text-cp-muted">{card.label}</p>
            <p className="mt-1 text-2xl font-semibold text-cp-orange">{card.value}</p>
          </div>
        ))}
      </div>

      {!overview?.kubectl_available && (
        <div className="rounded border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 space-y-1">
          <p className="font-medium">kubectl introuvable sur le serveur.</p>
          <p>
            Sur le serveur (SSH), exécutez :
          </p>
          <pre className="overflow-x-auto rounded bg-white/80 px-2 py-1 text-xs text-ink-900">
            sudo bash /opt/vzone-src/scripts/install-kubernetes.sh
          </pre>
          <p className="text-xs text-amber-800">
            Puis rechargez cette page. Sans cluster, seuls les outils client sont installés ;
            pour un cluster local : <code className="text-xs">VZONE_INSTALL_K3S=1 sudo -E bash …/install-kubernetes.sh</code>
          </p>
        </div>
      )}
      {overview?.kubectl_available && overview.kubectl_bin && (
        <p className="text-xs text-cp-muted">kubectl : {overview.kubectl_bin} · mode {overview.provision_mode}</p>
      )}
      {error && <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-cp-danger">{error}</p>}

      <form className="vz-panel space-y-2 p-4" onSubmit={onApply}>
        <div className="grid gap-2 md:grid-cols-4">
          <input
            className="vz-input md:col-span-1"
            placeholder="namespace (optionnel)"
            value={namespace}
            onChange={(e) => setNamespace(e.target.value)}
          />
          <button className="vz-btn-primary" type="submit" disabled={apply.isPending}>
            Apply YAML
          </button>
          <button
            className="vz-btn-secondary"
            type="button"
            disabled={remove.isPending}
            onClick={() => remove.mutate()}
          >
            Delete YAML
          </button>
        </div>
        <textarea
          className="vz-input min-h-56 font-mono text-xs"
          placeholder={"apiVersion: v1\nkind: Namespace\nmetadata:\n  name: demo"}
          value={manifest}
          onChange={(e) => setManifest(e.target.value)}
        />
      </form>

      {output && (
        <div className="vz-panel p-4">
          <h2 className="mb-2 text-xs font-semibold uppercase text-cp-muted">Sortie kubectl</h2>
          <pre className="max-h-64 overflow-auto rounded bg-cp-canvas p-3 text-xs dark:bg-ink-900">{output}</pre>
        </div>
      )}

      <div className="grid gap-3 xl:grid-cols-3">
        <div className="vz-panel overflow-x-auto">
          <div className="border-b border-cp-border px-3 py-2 text-xs font-semibold uppercase text-cp-muted">Namespaces</div>
          <table className="min-w-full text-left text-xs">
            <tbody>
              {(resources?.namespaces || []).map((n) => (
                <tr key={n.name} className="border-t border-cp-border">
                  <td className="px-3 py-2 font-mono">{n.name}</td>
                  <td className="px-3 py-2 text-cp-muted">{n.status || "Active"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="vz-panel overflow-x-auto xl:col-span-2">
          <div className="border-b border-cp-border px-3 py-2 text-xs font-semibold uppercase text-cp-muted">Pods</div>
          <table className="min-w-full text-left text-xs">
            <thead>
              <tr className="text-cp-muted">
                <th className="px-3 py-2">Namespace</th>
                <th className="px-3 py-2">Pod</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Node</th>
              </tr>
            </thead>
            <tbody>
              {(resources?.pods || []).slice(0, 80).map((p) => (
                <tr key={`${p.namespace}/${p.name}`} className="border-t border-cp-border">
                  <td className="px-3 py-2">{p.namespace}</td>
                  <td className="px-3 py-2 font-mono">{p.name}</td>
                  <td className="px-3 py-2">{p.status}</td>
                  <td className="px-3 py-2 text-cp-muted">{p.node || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
