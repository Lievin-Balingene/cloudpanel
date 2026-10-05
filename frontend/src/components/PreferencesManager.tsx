import { FormEvent, useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Languages, Mail, Moon, ShieldCheck, UserRound } from "lucide-react";
import { apiRequest } from "@/lib/api";
import { usePanelTweaks } from "@/lib/panelTweaks";
import { PageHeader, StatusDot } from "@/components/ui/PageChrome";
import { useAuthStore } from "@/stores/auth";

interface SecurityMe {
  two_factor_enabled: boolean;
  must_change_password: boolean;
}

export function PreferencesManager({ title }: { title: string }) {
  const user = useAuthStore((state) => state.user);
  const { tweaks } = usePanelTweaks();
  const [language, setLanguage] = useState(() => localStorage.getItem("vzone-lang") || "fr");
  const [saved, setSaved] = useState(false);
  const { data: security } = useQuery({
    queryKey: ["security-me"],
    queryFn: () => apiRequest<SecurityMe>("/security/me/"),
  });

  useEffect(() => {
    setLanguage(tweaks.panel_locale);
  }, [tweaks.panel_locale]);

  function saveLanguage(e: FormEvent) {
    e.preventDefault();
    localStorage.setItem("vzone-lang", language);
    setSaved(true);
    window.setTimeout(() => setSaved(false), 2000);
  }

  return (
    <div className="space-y-4 animate-fade-up">
      <PageHeader
        title={title}
        subtitle="Consultez votre profil et personnalisez les réglages locaux du panneau."
        stats={[
          { label: "Compte", value: user?.username || "—" },
          { label: "Langue", value: language.toUpperCase() },
        ]}
      />
      {tweaks.enable_2fa_prompt && !security?.two_factor_enabled && user?.role === "administrator" ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-100">
          Tweak Settings recommande d&apos;activer la 2FA pour les administrateurs.{" "}
          <Link to="/panel/security" className="font-semibold underline">
            Configurer la 2FA
          </Link>
        </div>
      ) : null}
      <div className="grid gap-4 lg:grid-cols-2">
        <section className="vz-panel space-y-4 p-4 sm:p-5">
          <div className="flex items-center gap-2">
            <UserRound className="h-4 w-4 text-cp-orange" />
            <h2 className="text-sm font-semibold text-cp-text">Profil du compte</h2>
          </div>
          <div>
            <p className="text-xs font-medium text-cp-muted">Nom d’utilisateur</p>
            <p className="mt-1 font-semibold text-cp-text">{user?.username || "—"}</p>
          </div>
          <div>
            <p className="flex items-center gap-1.5 text-xs font-medium text-cp-muted">
              <Mail className="h-3.5 w-3.5" />
              E-mail de contact
            </p>
            <p className="mt-1 break-all text-cp-text">{user?.email || "—"}</p>
            <p className="mt-1 text-xs text-cp-muted">
              La modification de l’adresse e-mail n’est pas encore disponible en libre-service.
            </p>
          </div>
        </section>
        <form onSubmit={saveLanguage} className="vz-panel space-y-4 p-4 sm:p-5">
          <div className="flex items-center gap-2">
            <Languages className="h-4 w-4 text-cp-orange" />
            <h2 className="text-sm font-semibold text-cp-text">Langue d’affichage</h2>
          </div>
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-cp-muted">Langue préférée</span>
            <select className="vz-input w-full" value={language} onChange={(e) => setLanguage(e.target.value)}>
              <option value="fr">Français</option>
              <option value="en">English</option>
            </select>
          </label>
          <p className="text-xs text-cp-muted">
            La langue du panneau est aussi pilotée par Tweak Settings (UI → Langue). Ce réglage navigateur
            reste un complément local.
          </p>
          <div className="flex items-center gap-3">
            <button className="vz-btn-primary">Enregistrer</button>
            {saved && <span className="text-sm font-medium text-emerald-600">Préférence enregistrée</span>}
          </div>
        </form>
      </div>
      <section className="vz-panel space-y-4 p-4 sm:p-5">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-cp-orange" />
            <h2 className="text-sm font-semibold text-cp-text">Sécurité du compte</h2>
          </div>
          <StatusDot
            status={security?.two_factor_enabled ? "active" : "inactive"}
            label={security?.two_factor_enabled ? "2FA activée" : "2FA désactivée"}
          />
        </div>
        <p className="text-sm text-cp-muted">
          Gérez votre mot de passe et la double authentification depuis la page de sécurité.
        </p>
        <Link className="vz-btn-primary inline-flex" to="/panel/security">
          Ouvrir la sécurité
        </Link>
      </section>
      <section className="vz-panel flex items-start gap-3 p-4 sm:p-5">
        <Moon className="mt-0.5 h-4 w-4 shrink-0 text-cp-orange" />
        <div>
          <h2 className="text-sm font-semibold text-cp-text">Thème</h2>
          <p className="mt-1 text-sm text-cp-muted">
            Le thème clair ou sombre se règle depuis le bouton d’apparence dans l’en-tête du panneau.
          </p>
        </div>
      </section>
    </div>
  );
}
