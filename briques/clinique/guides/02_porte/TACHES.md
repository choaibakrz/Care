# La porte de lecture — petites tâches

Une tâche = une personne, moins d'une heure, avec son test. Cocher quand le test passe. Rien ne touche un vrai robot ; rien ne part vers GitHub sans Hiba.

- [ ] Ouvrir l'écran de la direction et vérifier à l'œil qu'aucun nom de patient n'apparaît ; noter le résultat. Test : `python3 lancer.py tests briques/clinique/tests/test_porte_lecture.py` passe.
- [ ] Ajouter un essai : le badge du thérapeute ne voit pas un patient qui n'est pas dans sa liste. Test : le nouvel essai passe dans `python3 lancer.py tests briques/clinique/tests/test_porte_lecture.py`.
- [ ] Ouvrir l'écran du soignant, puis le journal des accès, et retrouver la lecture qu'il vient de faire. Test : le journal (`/clinique/journal`) montre une ligne pour le badge soignant-etage-2.
- [ ] Essayer d'ouvrir l'écran du médecin avec un badge inconnu et noter ce que dit la page. Test : `python3 lancer.py tests briques/clinique/tests/test_ecrans.py` passe.
