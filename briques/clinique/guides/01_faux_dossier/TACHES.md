# Le faux dossier — petites tâches

Une tâche = une personne, moins d'une heure, avec son test. Cocher quand le test passe. Rien ne touche un vrai robot ; rien ne part vers GitHub sans Hiba.

- [ ] Relire les douze fichiers patients et noter dans `NON_TESTE.md` une incohérence trouvée (date, chambre, langue). Test : la ligne est dans `NON_TESTE.md`, avec le nom du fichier ; `python3 lancer.py tests` passe toujours.
- [ ] Vérifier à la main que chaque nom d'établissement contient « Exemple » ; corriger s'il en manque un. Test : `python3 lancer.py tests briques/clinique/tests/test_faux_dossier.py` passe.
- [ ] Ajouter une habitude neutre à un patient autre que p01 (pas de maladie), avec la marque « inventé » gardée. Test : `python3 lancer.py tests briques/clinique/tests/test_faux_dossier.py` et `python3 lancer.py repetition` passent.
- [ ] Faire relire par une personne germanophone les textes allemands d'un patient, et noter ses corrections. Test : la personne signe la ligne dans `NON_TESTE.md` ; `python3 lancer.py tests` passe.
