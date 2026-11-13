import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { apiRequest } from "@/lib/api";
import { useAuthStore } from "@/stores/auth";
import type { User } from "@/types";

/** Lit le handoff depuis le fragment (#handoff=) — jamais envoyé au serveur HTTP. */
function readHandoffFromHash(): string {
  const raw = (window.location.hash || "").replace(/^#/, "");
  if (!raw) return "";
  const params = new URLSearchParams(raw.includes("=") ? raw : `handoff=${raw}`);
  return (params.get("handoff") || params.get("token") || "").trim();
}

function clearHash() {
  try {
    const url = `${window.location.pathname}${window.location.search}`;
    window.history.replaceState(null, "", url);
  } catch {
    /* ignore */
  }
}

/** Échange one-shot WHM Login as → session panneau client. */
export function SsoHandoffPage() {
  const navigate = useNavigate();
  const setSession = useAuthStore((s) => s.setSession);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Compat query string (anciens liens) puis fragment
    const qs = new URLSearchParams(window.location.search);
    const fromQuery = (qs.get("handoff") || qs.get("token") || "").trim();
    const handoff = readHandoffFromHash() || fromQuery;
    clearHash();
    if (fromQuery) {
      try {
        const clean = new URL(window.location.href);
        clean.searchParams.delete("handoff");
        clean.searchParams.delete("token");
        clean.searchParams.delete("_");
        window.history.replaceState(null, "", clean.pathname + clean.search + clean.hash);
      } catch {
        /* ignore */
      }
    }
    if (!handoff) {
      setError("Lien de connexion invalide.");
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const data = await apiRequest<{
          tokens: { access: string; refresh: string };
          user: User;
        }>("/auth/sso/exchange/", {
          method: "POST",
          body: JSON.stringify({ handoff }),
          retry: false,
        });
        if (cancelled) return;
        setSession(data.tokens.access, data.tokens.refresh, data.user);
        navigate("/panel", { replace: true });
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Connexion SSO impossible.");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [setSession, navigate]);

  return (
    <div className="flex min-h-[100dvh] items-center justify-center bg-[#e8eef4] p-6 dark:bg-surface-dark">
      <div className="w-full max-w-sm rounded-xl border border-cp-border bg-white p-6 text-center shadow-panel dark:border-ink-700 dark:bg-ink-950">
        {error ? (
          <>
            <p className="text-sm font-semibold text-cp-danger">Échec de la connexion</p>
            <p className="mt-2 text-sm text-cp-muted">{error}</p>
            <a href="/whm/accounts" className="mt-4 inline-block text-sm text-cp-link hover:underline">
              Retour à List Accounts
            </a>
          </>
        ) : (
          <>
            <Loader2 className="mx-auto h-8 w-8 animate-spin text-cp-orange" />
            <p className="mt-3 text-sm font-medium text-cp-text">Connexion au panneau client…</p>
            <p className="mt-1 text-xs text-cp-muted">Session sécurisée one-shot (style cPanel Login as)</p>
          </>
        )}
      </div>
    </div>
  );
}
