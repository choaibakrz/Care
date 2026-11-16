# Les listes de soin — petites tâches

Une tâche = une personne, moins d'une heure, avec son test. Cocher quand le test passe. Rien ne touche un vrai robot ; rien ne part vers GitHub sans Hiba.

- [ ] Cocher les six points sur une tablette, puis appuyer sur « Je sors » ; noter la phrase dite. Test : `python3 lancer.py tests briques/clinique/tests/test_listes_de_soin.py` passe.
- [ ] Ajouter un mot français à un point (champ `mots` de `faux_dossier/listes_de_soin.yaml`), puis taper une phrase avec ce mot dans « La tablette a entendu ». Test : le point se coche ; `python3 lancer.py tests briques/clinique/tests/test_cocher_a_la_voix.py` passe.
- [ ] Jouer la fin de poste avec un point restant et essayer les trois choix ; noter ce que voit la soignante suivante. Test : `python3 lancer.py tests briques/clinique/tests/test_listes_de_soin.py` passe.
- [ ] Couper le lien d'une tablette (page « Pannes ») pendant qu'on coche, puis le rétablir ; vérifier qu'aucune coche n'est perdue. Test : `python3 lancer.py tests briques/clinique/tests/test_panne_tablette.py` passe.
