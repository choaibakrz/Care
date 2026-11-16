# Le tableau des tâches et les demandes au robot — petites tâches

Une tâche = une personne, moins d'une heure, avec son test. Cocher quand le test passe. Rien ne touche un vrai robot ; rien ne part vers GitHub sans Hiba.

- [ ] Faire trois demandes différentes depuis l'écran du soignant et noter le choix du robot donné par « Pourquoi ? ». Test : `python3 lancer.py tests briques/clinique/tests/test_choix_explique.py` passe.
- [ ] Taper « il manque un coussin » dans « La tablette a entendu » et noter la question posée. Test : `python3 lancer.py tests briques/clinique/tests/test_demander_a_la_voix.py` passe.
- [ ] Lancer un tirage avec un autre numéro et noter « gestes interdits exécutés ». Test : `python3 lancer.py tirage 7` affiche 0 geste interdit exécuté.
- [ ] Lire la boîte noire d'une course et retrouver les trois temps (demandé, confirmé, constaté). Test : `python3 lancer.py tests briques/clinique/tests/test_trois_temps.py` passe.
