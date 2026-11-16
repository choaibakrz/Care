# Brique 5 — Les yeux (guide d'une page)

**Rôle** : dire ce que la caméra voit — personnes, objets nommés, marqueurs ArUco, textes. Les yeux ne commandent
**jamais** le robot : ils donnent les personnes vues au **gardien** et les objets vus au **cerveau**. Tout ordre passe
toujours par cerveau → gardien (ticket) → prise → adaptateur. Tout est **testé sur faux robot, caméra simulée** ;
**non testé sur vrai robot**, ni avec une vraie caméra.

## Allumer
1. Paquets (une fois) : `.venv/bin/python -m pip install --no-deps -r requirements-yeux.txt` (≈ 170 Mo à
   télécharger, ≈ 440 Mo sur le disque ; `--no-deps` obligatoire : un seul OpenCV). Modèle MediaPipe (4,6 Mo) :
   `.venv/bin/python -m briques.b05_yeux.telecharger_modele`.
2. `reglages.yaml → yeux.actif: true`. **Éteints, rien ne change.** Un outil absent : les yeux le disent (boîte noire,
   événement `yeux`) et continuent sans lui.
3. Avec le faux robot : caméra **simulée** (image dessinée du faux monde), les personnes du gardien viennent alors de
   cette caméra (plus de `monde.yaml` directement). `camera: simulee_fixe` : une caméra fixe simulée qui voit toute
   la halle. `camera: fichier:photo.png` : une **photo fixe**, pour essayer les outils (jamais de personnes au gardien).

## Ce qui change pour le gardien et le cerveau
- Personne vue à moins d'1 m du chemin → **refus expliqué** (« Je serais trop près d'une personne : 0,37 m »).
- **« Pas vue » n'est pas « pas là »** : les yeux donnent aussi la **zone du sol vue**. Si le sol à moins d'1 m du
  chemin ou du geste sort de cette zone (derrière, à côté, au pied de la caméra, au-delà de 6 m) → **humain**.
  Avec la caméra du robot, son pied n'est jamais vu : **tout déplacement ou geste demande un humain** (le refus d'une
  personne vue trop près passe avant). Pour bouger sans humain : une caméra fixe qui voit toute la zone (`simulee_fixe`
  en simulation ; en vrai : **à essayer**, calibrée en repère « monde »).
- Caméra en panne, bloquée plus de 2 s, image figée, pas calibrée, photo fixe, ou aucun outil qui voit les personnes →
  les yeux **ne disent rien** → après 2 s, le gardien **demande un humain** (comme sans yeux). La fraîcheur se compte
  depuis la **photo** ; une heure de photo fausse ou dans le futur → personnes inconnues.
- Pieds hors de l'image (personne tout près) → comptée **collée au robot** : aucun déplacement.
- « Prends la bouteille » : vue → l'action continue, sa direction est notée ; pas vue → « Je ne vois pas : bouteille.
  Pouvez-vous me montrer où c'est ? » (5 langues). Caméra en panne → rien ne change.

## Samedi : brancher la caméra du vrai robot (feu orange pour tout ordre au robot ; ici, on ne fait que LIRE)
1. **Trouver l'image** : caméra USB sur le Mac → `opencv:0` ; flux du robot → `opencv:rtsp://…` (adresse dans la doc
   du fabricant : **à vérifier**) ; image seulement par le kit du fabricant → une petite fonction qui ne fait que lire
   (à écrire, relecteur sécurité). Vérifier : `.venv/bin/python -m briques.b05_yeux.calibrer --camera opencv:0 --photo vue.png`.
2. **Imprimer** : `.venv/bin/python -m briques.b05_yeux.marqueurs --imprimer marqueurs_a_imprimer/` (A3). **Mesurer** le
   côté du carré noir ; l'écrire dans `marqueurs.yaml → calibration.taille_m`.
3. **Poser 3 marqueurs à plat au sol**, robot immobile, tête fixe, texte imprimé **du côté du robot**. Mesurer depuis
   le **centre** du robot : n° 0 à 1,5 m droit devant ; n° 1 à 2,5 m devant et 0,8 m à gauche ; n° 2 à 2,5 m devant et
   0,8 m à droite. Ils doivent être **en entier** dans la photo.
4. **Calibrer** : `.venv/bin/python -m briques.b05_yeux.calibrer --camera opencv:0` (autres places :
   `--marqueur 0:1.5:0 --marqueur 1:2.5:0.8 --marqueur 2:2.5:-0.8`). Lire « Erreur moyenne » (bien : < 3 cm) et
   « le bas de l'image voit le sol à … m » (plus près : angle mort). Écrit `briques/b05_yeux/calibration.yaml`.
   Essai sans caméra : `--essai` (caméra simulée, mesuré 0,6 cm d'erreur).
5. `reglages.yaml → yeux.camera: opencv:0`, relancer. La caméra **bouge** par rapport au robot (tête qui tourne) →
   calibration fausse : refaire.
6. **Vrai robot : les personnes vues ne vont jamais au gardien** → il continue de demander un humain avant de bouger.
   `gardien_vrai_robot: true` est **refusé au démarrage** (message clair) tant que la relecture sécurité ne l'a pas permis.

## Limites connues (à vérifier)
- La caméra ne voit **que devant** : une personne derrière ou à côté n'est pas vue ; le gardien le sait (zone vue) et
  demande un humain. Ce qui est **caché** derrière un objet ou une personne compte encore comme vu (à vérifier).
- Position au sol = bas de la boîte : juste si les pieds sont visibles ; jambes cachées (derrière une table) → la
  personne paraît **plus loin**. Objet sur une table : direction juste, distance trop grande.
- **MediaPipe jamais lancé** ici (Linux du nuage : bibliothèque libEGL absente). La détection de vraies personnes
  est **à vérifier sur Mac** avec la vraie caméra. Ici, les personnes viennent de la vérité de la caméra simulée.
- RapidOCR : majuscules sans accent essayées ; accents, allemand, chinois : à vérifier.

## Commandes
- `python3 lancer.py tests briques/b05_yeux` — 74 tests, ceux qui demandent un paquet absent sautent.
- `.venv/bin/python -m briques.b05_yeux.banc_yeux` — temps par image et mémoire sur CET ordinateur (`MESURES.md`).
- `.venv/bin/python -m briques.b05_yeux.calibrer --essai --genre chien` — essai de calibration simulée.
