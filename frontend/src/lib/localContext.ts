import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";
import { useAuthStore } from "@/stores/auth";

export type LocalCatalogItem = { code: string; label: string };

export type LocalProfile = {
  country: string;
  timezone: string;
  data_saver: boolean;
  lite_panel: boolean;
  require_phone: boolean;
  phone_prefix: string;
  notify_channel: string;
  backup_window_start: number;
  backup_window_end: number;
  defer_heavy_jobs: boolean;
  in_backup_window: boolean;
  catalog: {
    countries: Array<LocalCatalogItem & { prefix?: string; tz?: string }>;
    timezones: string[];
    notify_channels: LocalCatalogItem[];
  };
};

export type LocalOverview = {
  data_saver: boolean;
  lite_panel: boolean;
  in_backup_window: boolean;
  timezone: string;
  services_down: number;
  services: { id: string; label: string; unit: string; state: string }[];
};

export function useLocalProfile() {
  const token = useAuthStore((s) => s.accessToken);
  return useQuery({
    queryKey: ["local-context-profile"],
    queryFn: () => apiRequest<LocalProfile>("/local-context/profile/"),
    enabled: Boolean(token),
    staleTime: 60_000,
  });
}

export function useDataSaver(): boolean {
  const { data } = useLocalProfile();
  return Boolean(data?.data_saver);
}

export function useLitePanel(): boolean {
  const { data } = useLocalProfile();
  return Boolean(data?.lite_panel);
}
