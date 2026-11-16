# Les papiers — petites tâches

Une tâche = une personne, moins d'une heure, avec son test. Cocher quand le test passe. Rien ne touche un vrai robot ; rien ne part vers GitHub sans Hiba.

- [ ] Valider les trois papiers de la patiente sur l'écran de l'accueil et vérifier le carnet. Test : `python3 lancer.py tests briques/clinique/tests/test_papiers.py` passe.
- [ ] Imprimer une image d'un papier inventé, la photographier, et lancer la lecture sur la photo ; noter ce qui est lu. Test : le texte lu et le nom de la photo sont notés dans `NON_TESTE.md` ; `python3 lancer.py tests` passe.
- [ ] Essayer de ranger la feuille sans nom et noter le refus affiché. Test : `python3 lancer.py tests briques/clinique/tests/test_papiers.py` passe.
- [ ] Relire `docs/projet/MESURE_PAPIERS_APERTUS.md` et lister les papiers où Apertus n'est pas sûr. Test : `python3 lancer.py tests briques/clinique/tests/test_papiers_apertus.py` passe.
