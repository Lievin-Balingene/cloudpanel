import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";
import { useDataSaver } from "@/lib/localContext";

export interface LiveHostMetrics {
  collected_at: string;
  cpu: { percent: number; count: number; per_cpu: number[] };
  memory: {
    total: number;
    available: number;
    used: number;
    free: number;
    percent: number;
    cached: number;
    buffers: number;
  };
  swap: { total: number; used: number; percent: number };
  load_average: number[] | null;
}

export function useLiveHostMetrics(enabled = true) {
  const dataSaver = useDataSaver();
  return useQuery({
    queryKey: ["dashboard-live"],
    queryFn: () => apiRequest<LiveHostMetrics | null>("/dashboard/live/"),
    enabled,
    refetchInterval: dataSaver ? 30_000 : 2000,
    staleTime: dataSaver ? 20_000 : 0,
    refetchOnWindowFocus: !dataSaver,
  });
}
