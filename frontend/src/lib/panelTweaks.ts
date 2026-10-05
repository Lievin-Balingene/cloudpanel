import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";
import { useAuthStore } from "@/stores/auth";

export type PanelTweaks = {
  panel_locale: "fr" | "en";
  show_ai_assistant: boolean;
  compact_home_buttons: boolean;
  session_idle_minutes: number;
  enable_2fa_prompt: boolean;
  require_strong_passwords: boolean;
  min_password_length: number;
  allow_ini_edit: boolean;
};

const DEFAULTS: PanelTweaks = {
  panel_locale: "fr",
  show_ai_assistant: true,
  compact_home_buttons: true,
  session_idle_minutes: 60,
  enable_2fa_prompt: true,
  require_strong_passwords: true,
  min_password_length: 10,
  allow_ini_edit: true,
};

type PublicPayload = { values: Partial<PanelTweaks> };

export function usePanelTweaks() {
  const token = useAuthStore((s) => s.accessToken);
  const { data, ...rest } = useQuery({
    queryKey: ["tweak-settings-public"],
    queryFn: () => apiRequest<PublicPayload>("/server-setup/tweak-settings/public/"),
    enabled: Boolean(token),
    staleTime: 30_000,
  });
  const tweaks: PanelTweaks = {
    ...DEFAULTS,
    ...(data?.values || {}),
    panel_locale: data?.values?.panel_locale === "en" ? "en" : "fr",
    show_ai_assistant: data?.values?.show_ai_assistant !== false,
    compact_home_buttons: data?.values?.compact_home_buttons !== false,
    session_idle_minutes: Math.max(
      5,
      Number(data?.values?.session_idle_minutes ?? DEFAULTS.session_idle_minutes) || 60,
    ),
    allow_ini_edit: data?.values?.allow_ini_edit !== false,
  };
  return { tweaks, ...rest };
}

const UI: Record<"fr" | "en", Record<string, string>> = {
  fr: {
    logout: "Déconnexion",
    theme: "Thème",
    search: "Rechercher…",
    welcome: "Accueil",
    aiHidden: "Assistant IA masqué (Tweak Settings)",
    sessionExpired: "Session expirée pour inactivité",
    homeSubtitle:
      "Comptes, packages, DNS, services et sécurité — panneau d'administration V-zone.",
    panelGreeting: "Bonjour",
    toolsSearch: "Rechercher un outil…",
  },
  en: {
    logout: "Logout",
    theme: "Theme",
    search: "Search…",
    welcome: "Home",
    aiHidden: "AI assistant hidden (Tweak Settings)",
    sessionExpired: "Session expired due to inactivity",
    homeSubtitle: "Accounts, packages, DNS, services and security — V-zone admin panel.",
    panelGreeting: "Hello",
    toolsSearch: "Search for a tool…",
  },
};

export function usePanelI18n() {
  const { tweaks } = usePanelTweaks();
  const locale = tweaks.panel_locale;
  return (key: string) => UI[locale][key] ?? UI.fr[key] ?? key;
}

/** Applique lang HTML + déconnexion après inactivité. */
export function usePanelSessionEffects() {
  const { tweaks } = usePanelTweaks();
  const logout = useAuthStore((s) => s.logout);
  const token = useAuthStore((s) => s.accessToken);

  useEffect(() => {
    document.documentElement.lang = tweaks.panel_locale;
  }, [tweaks.panel_locale]);

  useEffect(() => {
    if (!token) return;
    const idleMs = tweaks.session_idle_minutes * 60_000;
    let last = Date.now();
    let timer: number | undefined;

    const bump = () => {
      last = Date.now();
    };
    const tick = () => {
      if (Date.now() - last >= idleMs) {
        void logout();
        return;
      }
      timer = window.setTimeout(tick, 15_000);
    };

    const evts = ["mousemove", "mousedown", "keydown", "touchstart", "scroll"] as const;
    for (const e of evts) window.addEventListener(e, bump, { passive: true });
    timer = window.setTimeout(tick, 15_000);
    return () => {
      for (const e of evts) window.removeEventListener(e, bump);
      if (timer) window.clearTimeout(timer);
    };
  }, [token, tweaks.session_idle_minutes, logout]);
}
