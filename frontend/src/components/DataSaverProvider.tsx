import { useQueryClient } from "@tanstack/react-query";
import { useEffect, type ReactNode } from "react";
import { useDataSaver } from "@/lib/localContext";

/** Allonge le cache et coupe les rafraîchissements agressifs (Go de data chers). */
export function DataSaverProvider({ children }: { children: ReactNode }) {
  const dataSaver = useDataSaver();
  const qc = useQueryClient();

  useEffect(() => {
    qc.setDefaultOptions({
      queries: {
        staleTime: dataSaver ? 180_000 : 30_000,
        retry: 1,
        refetchOnWindowFocus: !dataSaver,
      },
    });
  }, [dataSaver, qc]);

  return <>{children}</>;
}
