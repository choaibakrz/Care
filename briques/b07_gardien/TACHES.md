# Brique 7 — Petites tâches

## Fait (étape 4) — testé sur faux robot
- [x] `regles.yaml` : une règle = une phrase simple + des valeurs ; lue au démarrage ; phrase et valeurs vérifiées.
- [x] Poids (avant d'agir), objets interdits, objets fragiles (humain), gestes avec humain (verser).
- [x] Zones interdites (cercle autour d'un lieu, rectangle), chemin en ligne droite, rester dans la halle.
- [x] Distance aux personnes (chemin et gestes) ; interface `Perception` prête pour la brique 5.
- [x] Verdict « humain » + `aide_demandee` ; accepter / refuser depuis l'écran ; le gardien revérifie tout.
- [x] Règle changée en direct (`regle_changee`), règles relues, vote du public (exemple : vitesse, cuisine).
- [x] 10 ordres dangereux d'essai, tous refusés avec explication (par la chaîne et directement au gardien).
- [x] Chien de garde : programme figé → le faux robot s'arrête seul en moins d'1 s (test).
- [x] Corrections de la relecture sécurité du lot B (testé sur faux robot) : clés inconnues refusées ; pas de
      démarrage sans distance aux personnes ni zone permise ; `en_direct` faux par défaut ; la distance ne peut que
      grandir en direct et ne s'éteint jamais ; « relire les règles » garde ce qui a été rendu plus strict en direct
      (et le dit). À revérifier par quelqu'un d'autre que l'auteur.

## Avant samedi
- [ ] **Relecture sécurité** par quelqu'un d'autre (obligatoire pour cette brique, voir AGENTS.md).
- [ ] Remplacer l'escalier, la cuisine et la personne simulée par les vrais lieux de la halle (`commun/monde.yaml`).
- [ ] Choisir avec Hiba : `distance_personnes` (1 m ?) ; pour un vrai robot sans les yeux, faut-il demander un humain
      avant chaque mouvement (`si_personnes_inconnues: humain`, réglage actuel) ?
- [ ] Vrai robot : vérifier qu'il a son propre chien de garde, et son délai (kit du fabricant). **À vérifier.**
- [ ] Vrai robot : sait-il donner sa position (x, y, cap) ? Sinon, chaque déplacement demandera un humain.

## Après
- [ ] Brique 5 : appeler `systeme.gardien.perception.annoncer_personnes(...)` plusieurs fois par seconde.
- [ ] Écran du jury (brique 13) : boutons « accepter / refuser » (`/api/aides`, `/api/aide/repondre`),
      « allumer la cuisine », « résultat du vote » (`/api/gardien/vote`), liste des règles en phrases.
- [ ] Chemin réel du robot (s'il contourne les obstacles) au lieu de la ligne droite.
- [ ] Zones avec horaires (« pendant le service » de 12 h à 14 h) au lieu de l'allumer à la main.
- [ ] Étape 5 : la porte des agents IA passe par `gardien.verifier(..., demandeur="agent")`.

## Petits constats de la relecture sécurité du lot B (pas encore corrigés)
- [ ] Vérifier les personnes PENDANT les actions longues (trajet, geste), pas seulement au départ : une personne qui
      s'approche pendant le trajet devrait arrêter le robot (aujourd'hui : seulement « stop » ou l'arrêt d'urgence).
- [ ] Vérifier le point visé par la main (saisir, poser, geste d'un bras) : zones et personnes sont mesurées depuis le
      corps du robot, pas depuis la main.
- [ ] Une phrase de règle = un seul chiffre, avec son unité vérifiée (« 0,3 mètre par seconde ») : aujourd'hui seul le
      chiffre est cherché dans la phrase. Avec deux chiffres (« pendant 15 minutes, pas plus de 20 newtons » et
      `n: 15`), la vérification passe alors que la phrase dit autre chose, et la mise à jour en direct peut changer
      le mauvais chiffre.
- [ ] Noter dans la décision (`non_verifie`) chaque fois que les personnes ne sont pas vérifiées : par exemple
      `si_personnes_inconnues: oui` sans nouvelles des yeux, où le robot part aujourd'hui sans que ce soit écrit.
- [ ] Après l'accord d'un humain : garder l'action d'origine (celle demandée) et la recompléter au nouveau contrôle.
      Aujourd'hui, c'est l'action déjà complétée (vitesse, force d'alors) qui est revérifiée : si une limite a baissé
      entre-temps (vote), c'est un « non » au lieu de partir à la nouvelle limite.
