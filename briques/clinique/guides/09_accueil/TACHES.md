# L'accueil — petites tâches

Une tâche = une personne, moins d'une heure, avec son test. Cocher quand le test passe. Rien ne touche un vrai robot ; rien ne part vers GitHub sans Hiba.

- [ ] Lancer l'essai de l'accueil à la voix, écouter la phrase italienne et la réponse, et noter ce qui sonne mal. Test : la commande `python3 lancer.py accueil-voix --essai` finit sans erreur ; la note est dans `NON_TESTE.md`.
- [ ] Poser trois questions de santé différentes dans le hall et vérifier qu'aucune ne reçoit de réponse médicale. Test : `python3 lancer.py tests briques/clinique/tests/test_accueil.py` passe.
- [ ] Changer la langue dans `a_vous.yaml` et lancer « À vous ». Test : `python3 lancer.py a-vous` dit À VOUS : RÉUSSI.
- [ ] Taper un nom qui n'est pas dans la liste des arrivées et noter ce que dit le robot. Test : `python3 lancer.py tests briques/clinique/tests/test_accueil.py` passe.
