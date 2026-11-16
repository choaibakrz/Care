# Les écrans — petites tâches

Une tâche = une personne, moins d'une heure, avec son test. Cocher quand le test passe. Rien ne touche un vrai robot ; rien ne part vers GitHub sans Hiba.

- [ ] Ouvrir trois écrans sur un vrai téléphone du même Wi-Fi et noter ce qui gêne (taille, couleurs, mots coupés). Test : les notes, avec le modèle du téléphone et la date, sont dans `docs/projet/PAGES_VUES.md`, signées par la personne.
- [ ] Faire relire l'écran du patient en italien par une personne italophone ; écrire ses corrections dans `traductions_ecrans.yaml`. Test : `python3 lancer.py tests briques/clinique/tests/test_traductions_ecrans.py` passe.
- [ ] Ouvrir la même page sur deux téléphones et vérifier qu'un changement fait sur l'un apparaît sur l'autre. Test : le résultat (combien de secondes) est noté et signé dans `docs/projet/PAGES_VUES.md`.
- [ ] Couper le Wi-Fi d'un téléphone pendant quinze secondes et noter ce que dit la page (zone grisée, « information vieille »). Test : ce qui s'est affiché est noté et signé dans `docs/projet/PAGES_VUES.md`.
