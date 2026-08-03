import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  CartesianGrid,
  Legend,
} from "recharts";
import { apiRequest } from "@/lib/api";
import type { HistoryPoint } from "@/types";

export function WhmResourcesPage() {
  const qc = useQueryClient();
  const { data: history = [], isLoading } = useQuery({
    queryKey: ["dashboard-history"],
    queryFn: () => apiRequest<HistoryPoint[]>("/dashboard/history/?hours=24"),
    refetchInterval: 15000,
  });

  const capture = useMutation({
    mutationFn: () => apiRequest("/dashboard/capture/", { method: "POST", body: "{}" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["dashboard-history"] });
      void qc.invalidateQueries({ queryKey: ["dashboard-overview"] });
    },
  });

  const chartData = history.map((h) => ({
    ...h,
    time: new Date(h.collected_at).toLocaleTimeString("fr-FR", {
      hour: "2-digit",
      minute: "2-digit",
    }),
  }));

  return (
    <div className="space-y-4 animate-fade-up">
      <div className="vz-panel flex flex-wrap items-center justify-between gap-3 p-4">
        <div>
          <h1 className="text-xl font-semibold">Server Resources</h1>
          <p className="text-sm text-cp-muted">
            Historique CPU / RAM / Disque (rétention 72 h, capture Celery ou manuelle).
          </p>
        </div>
        <button className="vz-btn-primary" type="button" onClick={() => capture.mutate()}>
          Capturer maintenant
        </button>
      </div>

      <div className="vz-panel h-80 p-4">
        {isLoading && <p className="text-sm text-cp-muted">Chargement…</p>}
        {!isLoading && chartData.length === 0 && (
          <p className="text-sm text-cp-muted">
            Aucun historique. Cliquez sur « Capturer maintenant » pour démarrer.
          </p>
        )}
        {chartData.length > 0 && (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#d5dde5" />
              <XAxis dataKey="time" tick={{ fontSize: 11 }} />
              <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="cpu_percent" name="CPU %" stroke="#1a5fb4" dot={false} />
              <Line type="monotone" dataKey="ram_percent" name="RAM %" stroke="#1a5fb4" dot={false} />
              <Line
                type="monotone"
                dataKey="disk_percent"
                name="Disque %"
                stroke="#2e7d32"
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
