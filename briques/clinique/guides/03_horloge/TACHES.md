# L'horloge de démonstration — petites tâches

Une tâche = une personne, moins d'une heure, avec son test. Cocher quand le test passe. Rien ne touche un vrai robot ; rien ne part vers GitHub sans Hiba.

- [ ] Ajouter à `briques/clinique/tests/test_horloge.py` un essai : sauter de « visite » à « arrivée » est refusé (l'horloge ne recule pas). Test : le nouvel essai passe dans `python3 lancer.py tests briques/clinique/tests/test_horloge.py`.
- [ ] Regarder l'écran du patient avant et après un saut, et noter où s'affiche « temps accéléré ». Test : `python3 lancer.py tests briques/clinique/tests/test_horloge.py` et `python3 lancer.py tests briques/clinique/tests/test_ecrans.py` passent.
- [ ] Relire les heures du cahier (6.8) et les comparer à `heures_scenario.yaml` ; noter un écart. Test : `python3 lancer.py repetition` passe.
