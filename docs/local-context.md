# Contexte local (exploitation du panneau)

Ce n’est **pas** un module de facturation. Le panneau s’adapte au terrain : lien lent, coupures, petit VPS, téléphone comme contact opérationnel.

| Contrainte | Fonction |
|------------|----------|
| Data mobile chère / 3G | Économie de données (moins de rafraîchissements) + bandeau hors-ligne |
| VPS 2–4 Go | Panneau allégé : masque Docker / Kubernetes |
| Coupure électrique / générateur | WHM → Après une coupure : état des services + relance |
| Lien saturé le jour | Sauvegardes seulement la nuit (fuseau Africa/…) |
| Le client n’ouvre pas l’e-mail | Téléphone à la création ; messages WhatsApp/SMS (site prêt, disque, SSL, reprise) |
| Densité de comptes | Pulse : plafonds CPU/RAM par offre |

WHM : `/whm/local`  
Client : `/panel/local`
