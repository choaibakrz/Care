# La flotte — petites tâches

Une tâche = une personne, moins d'une heure, avec son test. Cocher quand le test passe. Rien ne touche un vrai robot ; rien ne part vers GitHub sans Hiba.

- [ ] Sur le tableau de flotte, provoquer une panne de R2 en course, puis « Reprendre » ; noter qui reprend et pourquoi. Test : `python3 lancer.py tests briques/clinique/tests/test_tableau_de_flotte.py` passe.
- [ ] Changer la carte de R3 dans `flotte.yaml` (une autre carte existante) et regarder le tableau. Test : `python3 lancer.py tests briques/clinique/tests/test_cartes_de_role.py` passe.
- [ ] Lire la carte Accueil et vérifier avec le gardien qu'un ordre vers la cuisine est refusé. Test : `python3 lancer.py tests briques/clinique/tests/test_carte_pas_contournable.py` passe.
- [ ] Lancer l'essai de la panne et de la reprise et raconter le résultat en trois lignes. Test : `python3 lancer.py panne-reprise` finit sans erreur.
