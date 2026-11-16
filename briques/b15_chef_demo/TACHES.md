# Brique 15 — Petites tâches

## Avant samedi
- [ ] Répéter `essai_3_minutes.yaml` à ×1 sur chaque Mac, avec la vraie cascade (Apertus 8B → 4B → règles) ; noter la durée.
- [ ] Aligner avec la brique 17 (kit du samedi) : ses brouillons de scénario passent `python3 -m briques.b15_chef_demo.verifier`.
- [ ] Écrire le vrai scénario du jury (lieux de la halle dans `commun/monde.yaml`, puis `robot:` et les `attendu`).
- [ ] Une répétition « pagaille » de 10 minutes (idée du mode pagaille) : `--pagaille`, plusieurs graines, lire les comptes rendus.

## Améliorer
- [ ] Lancer un scénario depuis l'écran (brique 13), dans le MÊME système que l'écran et la voix : les annonces
      s'affichent et se disent, les boutons d'arrêt d'urgence de l'écran arrêtent le chef.
- [ ] Mode présentateur : le chef attend que la personne DISE la phrase (oreilles de la brique 4) au lieu de la jouer,
      et ne la joue lui-même (tablette) que si rien n'est compris à temps.
- [ ] Brique 11 (pilotage) : `OperateurEcran` existe (consigne sur l'écran de l'équipe, testé sur faux robot) ; reste à
      le choisir depuis la commande (`--operateur ecran`), une fois le scénario lancé depuis l'écran (tâche ci-dessus).
- [ ] Écran (brique 13) : afficher `scenario_etape` et `plan_b` (une ligne chacun dans `ecran.js`), et un chronomètre.
- [ ] Bouton « étape suivante » à l'écran, pour avancer à la main pendant une démonstration.
- [ ] Retour à la voix après la tablette (aujourd'hui : tablette jusqu'à la fin du scénario).
- [ ] Pagaille : pannes au hasard dans le temps (et pas seulement au début d'une étape), et pannes du faux robot
      (`lenteur`, `perte_liaison`).
- [ ] Vérifier dans `verifier.py` que l'`attendu` correspond à ce que le cerveau à règles comprend (jouer à sec).
