# Brique 5 — Les yeux : tâches

Fait (testé sur faux robot, caméra simulée, Linux) : voir `GUIDE.md`. Reste, du plus urgent au moins urgent.

## Avant samedi
- [ ] **Mac** : installer `requirements-yeux.txt` (`--no-deps`) et le modèle ; lancer
      `python3 lancer.py tests briques/b05_yeux` et `.venv/bin/python -m briques.b05_yeux.banc_yeux` ; écrire les
      chiffres dans `MESURES.md` (marqués « mesuré sur Mac »). **MediaPipe n'a jamais tourné** (Linux du nuage sans libEGL).
- [ ] **MediaPipe sur une vraie image** : une personne devant la webcam du Mac, `yeux.camera: opencv:0`,
      `branchements: [mediapipe]` ; vérifier qu'elle est vue et à peu près à la bonne distance (après calibration).
- [ ] **Relecture sécurité** (obligatoire) : le petit ajout dans `briques/b07_gardien/perception.py` (paramètre `heure`),
      `lien.py` (ce qui est donné au gardien), et la décision `gardien_vrai_robot`.
- [ ] Imprimer les marqueurs en A3 (3 de calibration + les lieux du défi), mesurer le carré noir.

## Samedi (avec le vrai robot)
- [ ] Trouver la caméra du robot (USB, flux réseau, ou kit du fabricant : fonction de lecture seule à écrire).
- [ ] Calibrer (GUIDE.md, étapes 1 à 5). Refaire si la tête du robot bouge.
- [ ] Changer `marqueurs.yaml` (lieux et objets du défi) et `monde.yaml` (avec la personne de la brique 2).

## Proposé (à décider par Hiba, relecteur sécurité pour le gardien)
- [x] Champ de la caméra dans le gardien (fait après la relecture du lot D : zone vue obligatoire, « humain » hors champ).
- [ ] **Caméra fixe en vrai** (repère « monde », calibrée avec des marqueurs posés à des places connues de la halle) :
      seul moyen de bouger sans humain avec les yeux. À essayer (en simulation : `camera: simulee_fixe`).
- [ ] **Ce qui est caché** derrière un objet ou une personne compte encore comme vu : retirer de la zone vue l'ombre
      des grandes choses vues (relecteur sécurité).
- [ ] **Distance par la largeur** d'une personne (épaules ≈ 0,45 m) en plus du bas de la boîte : garder la plus petite
      des deux distances (jambes cachées derrière une table).
- [ ] **Se situer avec les marqueurs** des lieux : un marqueur vu donne la position du robot (utile au vrai robot,
      dont la position est souvent inconnue : le gardien demande alors un humain).
- [ ] Paramètre `position` pour `saisir` (décision de l'architecte, brique 1) : donner à l'adaptateur la place vue.
- [ ] Mode silence et panneaux pour robots (idées 14 et 16) : les textes lus et les marqueurs sont prêts, l'écran non.
- [ ] Image de la caméra à l'écran de l'équipe (brique 13), avec les boîtes ; panne « caméra » dans le pupitre du faux
      robot (brique 2) pour les répétitions du chef de démonstration (brique 15).
- [ ] OWLv2 (« trouve n'importe quel objet nommé ») : en option seulement si la mémoire le permet (DECISIONS.md) ;
      taille et licence à vérifier avant (feu orange au-delà de 500 Mo).
