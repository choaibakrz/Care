# Brique 3 — Petites tâches

Chaque tâche : une personne, moins d'une heure, avec son test. Cocher quand le test passe.

- [ ] Samedi : brancher le robot du défi avec `BRANCHER_UN_ROBOT.md` (skill `brancher-un-robot`), en commençant par l'arrêt.
- [x] Relecture sécurité indépendante (9c0ef26, 18 constats) : corrigée, un test par constat (`tests/test_adaptateurs_relecture.py`).
- [ ] Relecteur sécurité : relire les corrections (fils d'arrêt neufs, ordres revérifiés, garde du trajet, empreintes).
- [ ] Coordinateur : donner le bus au registre dans `commun/systeme.py` (remarques de l'adaptateur dans la boîte noire).
- [ ] Chronomètre « robot inconnu » à l'écran du jury (idée 12) : lire `robots/NOM/branchement.yaml` (brique 13).
- [ ] Aller à un lieu nommé avec l'odomètre : caler le repère de l'odomètre sur `commun/monde.yaml`, puis `dx, dy` (test sur le faux kit).
- [ ] Mesurer sur le vrai robot le chien de garde du fabricant (ordres qui cessent → arrêt en combien de temps ?) ; l'écrire dans la fiche.
- [ ] Faux kit : ajouter une panne « obstacle » (le robot s'arrête à mi-chemin) et vérifier le message.
- [ ] Une carte d'exemple « roues » dans le faux robot (brique 2), pour essayer le genre `roues` de bout en bout.
- [ ] Bras : poses nommées (« devant », « table ») pour `montrer` et `poser`, enregistrées dans la carte.
- [ ] Test : deux adaptateurs du même robot dans le même programme sont refusés (une seule liaison).
- [ ] Mesurer sur le vrai robot le bruit de l'odomètre (les marges du trajet : 5 cm de recul, 15 cm d'écart).
