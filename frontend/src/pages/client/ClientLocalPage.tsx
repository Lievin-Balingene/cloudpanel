import { Wifi } from "lucide-react";
import { useLocalProfile } from "@/lib/localContext";
import { PageHeader } from "@/components/ui/PageChrome";

export function ClientLocalPage() {
  const { data: profile } = useLocalProfile();

  return (
    <div className="space-y-4 animate-fade-up">
      <PageHeader
        title="Connexion et coupures"
        subtitle="Ce panneau est fait pour un lien mobile et un serveur qui peut redémarrer. Rien à payer ici."
      />
      <div className="vz-panel space-y-3 p-4 text-sm leading-relaxed">
        <p className="flex items-start gap-2 font-semibold">
          <Wifi className="mt-0.5 h-4 w-4 text-cp-orange" />
          {profile?.data_saver
            ? "Économie de données activée : le panneau se rafraîchit moins souvent."
            : "Si votre 3G est chère ou instable, demandez à l’admin d’activer l’économie de données."}
        </p>
        <p className="text-cp-muted">
          Si le site ne répond pas après une coupure de courant, attendez quelques minutes : le
          serveur relance nginx et le panneau. Un bandeau orange apparaît si votre téléphone n’a
          plus de réseau — vous pouvez quand même lire cette page.
        </p>
        <p className="text-cp-muted">
          Les sauvegardes lourdes partent la nuit (heure locale {profile?.timezone || "—"}) pour ne
          pas saturer le lien pendant la journée.
        </p>
      </div>
    </div>
  );
}
