import { useEffect, useState } from "react";
import { WifiOff } from "lucide-react";

/** Bandeau visible dès que le réseau lâche — cas fréquent (3G, coupure, générateur). */
export function ConnectivityBanner() {
  const [online, setOnline] = useState(
    typeof navigator === "undefined" ? true : navigator.onLine,
  );

  useEffect(() => {
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    return () => {
      window.removeEventListener("online", on);
      window.removeEventListener("offline", off);
    };
  }, []);

  if (online) return null;
  return (
    <div className="flex items-start gap-2 border-b border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-950 dark:border-amber-900/50 dark:bg-amber-950/50 dark:text-amber-100">
      <WifiOff className="mt-0.5 h-4 w-4 shrink-0" />
      <p>
        Pas de réseau pour le moment. Vous pouvez continuer à lire cette page. Dès que le signal
        revient, cliquez sur Actualiser — rien n’est perdu sur le serveur.
      </p>
    </div>
  );
}
