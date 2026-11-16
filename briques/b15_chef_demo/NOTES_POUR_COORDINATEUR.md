# Brique 15 — Notes pour le coordinateur

Tout est **testé sur faux robot** (faux humanoïde, cerveau à règles, Linux). Rien n'a touché un vrai robot.

## Ce qui est fait
- **Format de scénario** YAML vérifié à la lecture (pydantic, clés inconnues refusées) : `scenario.py`,
  modèle commenté `scenarios/modele.yaml`, format complet dans `GUIDE.md` (pour aligner les brouillons de la brique 17).
  Vérification sans robot : `python3 -m briques.b15_chef_demo.verifier --tous` (format + lieux, objets, gestes, actions).
- **Chef d'orchestre** asynchrone (`chef.py`) : chaque `dire` passe par `systeme.chaine.traiter` (cerveau → gardien →
  prise) ; l'attendu est lu dans les événements du bus (même conversation). Raté ou trop long → plan B dans l'ordre,
  sans les moyens inutiles pour la cause devinée. `tablette`, `mode_local`, `main_humaine` (`pilotage_humain`
  reprise / rendu + consigne ; opérateur simulé ou clavier), `sauter`. Arrêt d'urgence : le chef s'arrête et le dit,
  ne réarme jamais.
- **Répétition** : `--panne robot@3`, `voix@2`, `reseau@4` (numéro ou nom d'étape), `--pagaille --graine N`,
  chronomètre, compte rendu Markdown (`compte_rendu.py`) dans `mesures/` ou `--rapport DOSSIER`.
- **Scénario d'essai** `scenarios/essai_3_minutes.yaml` : accueil en fr, gsw, en, zh ; aller à la table ; ordre
  dangereux refusé et expliqué ; ordre flou → question ; prendre la bouteille avec « oui » ; « stop » en route ; état ;
  fiche de vérité. Joué à ×1 une fois sur ce Linux : voir « Mesuré » plus bas.
- **Sous-commande** `python3 lancer.py scenario CHEMIN [--repetition] [--panne …] [--acceleration N] …`.
- **Tests** : `briques/b15_chef_demo/tests/test_chef_demo.py` (28 tests, environ 22 s). Suite complète : voir plus bas.

## Changements hors de la brique (petits ajouts, rien d'autre)
- `commun/evenements.py` : 4 types ajoutés **à la fin** de `TYPES` : `scenario_debut`, `scenario_etape`, `plan_b`,
  `scenario_fin` (une phrase d'explication chacun).
- `briques/b12_boite_noire/fiche.py` : 2 champs (`plans_b`, `plans_b_reussis`) et 3 lignes dans `Compteur.ajouter`
  (événement `plan_b` avec `etat` reussi / rate / saute).
- `lancer.py` : une ligne de documentation, la fonction `scenario`, la sous-commande (options dans `commande.py`).
- **Aucun changement** dans `commun/chaine.py`, `commun/systeme.py`, `briques/b01_prise/`, `briques/b07_gardien/`,
  ni dans les tests existants.

## Choix à faire relire (pas des mesures)
- **Mode local sans toucher la cascade** : le chef met en pause (jusqu'à la fin du scénario, puis rend comme avant)
  les étages de `CerveauCascade` dont l'adresse n'est pas sur cet ordinateur, ou qui ont émis `cerveau_secours`.
  Le dernier étage (règles) n'est jamais mis de côté. Si le cerveau n'est pas une cascade : rien à faire (« inutile »).
- **Panne réseau simulée** : le cerveau d'un étage distant est remplacé, le temps de la panne, par un cerveau qui ne
  répond jamais ; la cascade attend son délai puis passe au suivant. Sans cerveau distant : la panne ne change rien (dit).
- **Panne voix simulée** : la phrase arrive à la chaîne sous la forme « … » avec une confiance de 0,1.
- **Panne robot** = panne « refus » du faux robot. Sur un vrai robot : aucune panne, aucune accélération (refusées).
- Accélération : limites divisées, mais jamais sous **2 s** (le cerveau et le bus ne vont pas plus vite).
- Si l'attendu est là, même en retard, on ne rejoue **jamais** (le robot agirait deux fois). Si le robot a fait autre
  chose que prévu (cause « inattendu »), pas de rejeu non plus. Étape pas finie à temps avec le robot en mouvement :
  le chef dit « stop » par la chaîne avant le plan B.
- `tablette` et `mode_local` durent jusqu'à la fin du scénario ; `main_humaine` et `sauter` valent pour l'étape.
- Plan B tablette sur un « oui » : le chef retape d'abord l'ordre (la chaîne n'accepte le « oui » que de la même source).
- La fiche dite à la fin = la fiche de **cette** démonstration (ses événements), pas toute la session.
- Opérateur par défaut : automatique (5 s, divisées par l'accélération) sur faux robot ; clavier (Entrée) sur vrai robot.

## Ce qui reste (voir `TACHES.md`)
- Lancer un scénario **depuis l'écran**, dans le même système que l'écran et la voix (aujourd'hui `lancer.py scenario`
  a son propre système : terminal + boîte noire seulement).
- Mode présentateur (le chef attend la vraie voix au lieu de jouer la phrase) ; brique 11 (vrai pilotage).
- Afficher `scenario_etape` et `plan_b` sur l'écran (brique 13).
- Répéter à ×1 sur les Mac avec la vraie cascade Apertus.

## Vu en passant (hors de ma brique, non corrigé)
- `briques/b04_oreilles_voix/conversation.py`, `fermer()` : `self.s.bus.desabonner(self._reponse)` ne désabonne rien,
  car `Bus.desabonner` compare avec `is` et chaque `self._reponse` est un nouvel objet (vérifié : l'abonné reste).
  Correction possible : garder la méthode dans un attribut au moment de `abonner` (comme `chef.py`, `self._abonne`).

## Lignes à ajouter (je n'ai pas modifié ces fichiers)

**LICENCES.md**
```
## Brique 15 (chef de démonstration)
Aucun nouveau paquet. Aucun code copié : tout a été écrit pour ce projet. Utilise pydantic et PyYAML, déjà listés.
```

**DECISIONS.md** (section « à relire par Hiba »)
```
- **Chef de démonstration (brique 15)** : plan B dans l'ordre écrit, sans les moyens inutiles pour la cause devinée
  (robot → ni tablette ni mode local ; voix → pas de mode local ; réseau → pas de tablette). Tablette et mode local
  jusqu'à la fin du scénario. Jamais de rejeu quand l'attendu est là ou que le robot a déjà agi.
- **Mode local** : étages distants ou en échec de la cascade mis en pause jusqu'à la fin du scénario, puis rendus.
  Engagé aussi après une étape réussie si le cerveau est passé au secours.
- **Répétition** : pannes provoquées seulement en répétition et seulement sur faux robot ; accélération : limites
  divisées, plancher 2 s.
- **Fiche de vérité** : compte les plans B (`plans_b`, `plans_b_reussis`) ; 4 nouveaux types d'événements
  (`scenario_debut`, `scenario_etape`, `plan_b`, `scenario_fin`).
```

**NON_TESTE.md**
```
## Chef de démonstration (brique 15) : testé sur faux robot seulement
- Jamais avec un vrai robot, ni sur les Mac, ni avec la vraie cascade Apertus (panne réseau testée avec un cerveau
  « en ligne » factice dans les tests).
- La voix est simulée (phrase donnée à la chaîne) ; jamais avec les vraies oreilles de la brique 4.
- Annonces dites par la voix : jamais essayé (lancer.py scenario n'a ni écran ni voix).
- Main humaine : opérateur simulé ; la brique 11 n'existe pas. Opérateur clavier : essayé avec une touche Entrée
  envoyée par un tube, pas par une personne.
- Durée du scénario de trois minutes : mesurée une seule fois à ×1 (174,81 s), sur Linux, faux robot, cerveau à règles.
```

## Mesuré (11.11.2026, Linux du nuage, faux robot)
- Suite complète depuis ma copie (`.venv/bin/python -m pytest -q`) : **144 réussis, 11 sautés** (modèles absents), 68 s.
- Tests de la brique : 28 réussis, environ 22 s, trois fois de suite.
- Scénario d'essai à **×1** (cerveau à règles, sans panne) : **174,81 s**, 21 étapes réussies sur 21.
- `python3 lancer.py scenario essai_3_minutes.yaml --repetition --panne robot@salut_fr --panne voix@aller_table
  --acceleration 40` avec les réglages par défaut (cascade, modèles absents ici) : 19 réussies, 2 rattrapées
  (main humaine, tablette), et mode local préventif dès la première phrase (8B et 4B injoignables).
  Les longues traces affichées viennent de la cascade (brique 6) quand un modèle manque, pas du chef.
- Essayé aussi à la main : `lenteur` (étape pas finie à temps → « stop » → l'action avait fini : réussie en retard),
  `perte_liaison` (refus « liaison_perdue » → main humaine).

## À faire vérifier
« Celui qui écrit n'est pas celui qui vérifie » : personne d'autre n'a encore relu cette brique. À relire surtout :
`_tenter`, `_plan_b` et `_etape_surveillee` dans `chef.py` (arrêt d'urgence, rejeu, nettoyage d'une étape trop longue).
