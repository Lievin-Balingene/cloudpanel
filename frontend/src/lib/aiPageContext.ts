/** Helpers frontend : page courante → besoin immédiat assistant. */

export type UiPageContext = {
  path: string;
  section: string;
  portal: "client" | "whm" | "shared";
  label: string;
  need: string;
  auto_prompt: string;
  runtime?: string;
};

const SECTIONS: Record<
  string,
  { label: string; need: string; auto_prompt: string; runtime?: string }
> = {
  home: {
    label: "Accueil",
    need: "Vue d'ensemble",
    auto_prompt: "Je suis sur l'accueil. Donne-moi un aperçu de mon compte et ce que je peux déployer.",
  },
  python: {
    label: "Applications Python",
    need: "Statut, logs, dépendances Python",
    auto_prompt:
      "Je suis sur Setup Python App. Vérifie le statut de mes apps, lis les logs et signale les erreurs.",
    runtime: "python",
  },
  node: {
    label: "Applications Node.js",
    need: "Statut, logs, npm",
    auto_prompt: "Je suis sur Node.js. Vérifie le statut, lis les logs et signale les erreurs.",
    runtime: "node",
  },
  git: {
    label: "Git",
    need: "Dépôts et déploiements",
    auto_prompt: "Je suis sur Git. Montre mes dépôts et les erreurs de déploiement éventuelles.",
  },
  domains: {
    label: "Domaines",
    need: "Config domaines / SSL",
    auto_prompt: "Je suis sur Domaines. Vérifie ma configuration domaines et le serveur web.",
  },
  dns: {
    label: "DNS",
    need: "Zones DNS",
    auto_prompt: "Je suis sur Zone Editor. Résume mes domaines et points d'attention DNS.",
  },
  databases: {
    label: "Databases",
    need: "Bases MySQL/PG",
    auto_prompt: "Je suis sur Databases. Liste mes bases (sans secrets).",
  },
  wordpress: {
    label: "WordPress",
    need: "Sites WP",
    auto_prompt: "Je suis sur WordPress. Aide installation ou diagnostic domaine/web.",
  },
  files: {
    label: "File Manager",
    need: "Fichiers home / jail",
    auto_prompt: "Je suis sur File Manager. Propose une commande jail pour lister mon home.",
  },
  terminal: {
    label: "Terminal",
    need: "Commandes jail contrôlées",
    auto_prompt:
      "Je suis sur le Terminal. Liste les commandes jail autorisées et propose un diagnostic.",
  },
  docker: {
    label: "Docker",
    need: "Conteneurs",
    auto_prompt: "Je suis sur Docker. Aide-moi sur l'état de mes conteneurs.",
  },
  backups: {
    label: "Backups",
    need: "Sauvegardes",
    auto_prompt: "Je suis sur Backups. Explique comment vérifier mes sauvegardes.",
  },
  email: {
    label: "Email",
    need: "Comptes mail",
    auto_prompt: "Je suis sur Email. Points de contrôle utiles.",
  },
  ftp: {
    label: "FTP",
    need: "Comptes FTP",
    auto_prompt: "Je suis sur FTP. Conseils et vérifications.",
  },
  cron: {
    label: "Cron",
    need: "Tâches planifiées",
    auto_prompt: "Je suis sur Cron Jobs. Aide à vérifier mes tâches.",
  },
  php: {
    label: "PHP",
    need: "Version PHP",
    auto_prompt: "Je suis sur Select PHP Version. Conseils de version.",
  },
  security: {
    label: "Sécurité",
    need: "2FA / sécurité",
    auto_prompt: "Je suis sur Sécurité. Rappels 2FA et bonnes pratiques.",
  },
  package: {
    label: "Package",
    need: "Quotas",
    auto_prompt: "Je suis sur Mon package. Résume ce que mon package autorise.",
  },
};

export function buildUiPageContext(pathname: string): UiPageContext {
  const path = pathname || "/";
  const parts = path.split("/").filter(Boolean);
  const portal = parts[0] === "whm" ? "whm" : parts[0] === "panel" ? "client" : "shared";
  let section = "home";
  if (parts.length >= 2) {
    section = parts[1] === "files" ? "files" : parts[1];
  } else if (parts.length === 1) {
    section = "home";
  }
  const meta = SECTIONS[section] || SECTIONS.home;
  return {
    path,
    section,
    portal,
    label: meta.label,
    need: meta.need,
    auto_prompt: meta.auto_prompt,
    runtime: meta.runtime,
  };
}
