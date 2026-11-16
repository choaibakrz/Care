# Brique 11 — Petites tâches

## Fait (testé sur faux robot)
- [x] Bouton « Je prends la main » / « Je rends la main » sur l'écran de l'équipe (code d'équipe), événement
      `pilotage_humain` (reprise, rendu, qui).
- [x] Pendant la main humaine : voix, tablette, agents → « un humain pilote » ; « stop » et ARRÊT passent toujours.
- [x] Ordres par boutons (actions de la carte, avec leurs précisions), chacun par le gardien ; refus expliqué.
- [x] Panneau « Demandes à un humain » : accepter / refuser, temps restant, apprendre un mot, vote du public.
- [x] Écran du jury : bandeau « UN HUMAIN PILOTE » + qui ; fiche : part de l'humain, ordres, réussites pilotées.
- [x] Chef de démonstration : `OperateurEcran` (consigne à l'écran, « Fait » / « Pas pu »).
- [x] Tests (API, chaîne, fiche, chef) et un test dans Chromium.

## Après la relecture sécurité indépendante (lot D, faits, testé sur faux robot)
- [x] Prendre la main envoie TOUJOURS un arrêt (par le gardien) : une action de la voix en train de démarrer ne
      continue plus (test avec la panne « lenteur ») ; l'arrêt de la reprise n'est pas une réussite du robot.
- [x] Changement de main : les demandes à un humain de l'autre camp sont oubliées (chaîne ET gardien) ; une demande
      ne part que pour la main où elle a été faite.
- [x] Numéro de main (au lieu d'un oui/non) : un ordre parti avant un changement de main ne part jamais après.
- [x] Jeton de la tablette qui a pris la main (ordres, rendu) ; « Libérer la main » depuis une autre tablette, noté.
- [x] Fiche : « Réussites : dont N par l'humain » ; main simulée du chef comptée à part.
- [x] `OperateurEcran` : attente maximale du rendu (5 min) ; deuxième demande du chef refusée.

## Avant samedi
- [ ] Faire relire par le relecteur sécurité les corrections : `commun/chaine.py` (numéro de main, demandes oubliées,
      `ordre_humain` sans la main), `briques/b07_gardien/gardien.py` (`oublier_demandes(lesquelles)`).
- [ ] Essayer sur une vraie tablette (Safari / iPad) sur le Wi-Fi, avec le code d'équipe : boutons assez grands ?
- [ ] Décider avec Hiba : prendre la main arrête TOUJOURS le robot (choix actuel, après la relecture). Garder ?
- [ ] Décider avec Hiba : « Libérer la main » depuis une autre tablette (avec le code d'équipe, noté) : garder ?
- [ ] Faire relire par l'équipe la phrase « humain_pilote » en de, it, en, zh (`commun/phrases.yaml`) et l'étiquette
      « pilote » de l'écran du jury (`briques/b13_ecran/static/jury.js`).

## Améliorer
- [ ] `lancer.py scenario --operateur ecran` : lancer le chef DANS le même programme que l'écran (tâche de la
      brique 15 « lancer un scénario depuis l'écran »). Aujourd'hui `OperateurEcran` ne sert que dans ce cas ;
      `lancer.py scenario` n'a pas d'écran (voir le test `test_le_chef_passe_la_main_a_l_ecran_puis_la_reprend`).
- [ ] Visite à distance (idée 13) : piloter depuis un autre lieu. Aujourd'hui : Wi-Fi local seulement. Par Internet :
      feu orange (réseau, sécurité), décision de Hiba ; brancher l'interrupteur `visite_a_distance`.
- [ ] Une flèche « avancer de 20 cm » / « tourner » en gros boutons (aujourd'hui : dx/dy à écrire).
- [ ] Afficher sur l'écran du jury la consigne du chef de démonstration en plus gros, pendant la main humaine.
- [ ] Un « qui » vérifié (liste des prénoms de l'équipe dans reglages.yaml) : aujourd'hui, un texte libre (le jeton
      dit QUELLE tablette pilote, pas QUI la tient).
- [ ] Quand le programme redémarre, la main humaine est perdue (personne n'a la main, l'ancien jeton ne sert plus) :
      le dire à l'écran.
