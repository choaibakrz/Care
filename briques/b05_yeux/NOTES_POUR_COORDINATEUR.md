# Brique 5 (les yeux) — notes pour le coordinateur

Branche `brique-5` (partie de `9c0ef26`). Tout est **testé sur faux robot, caméra simulée**, sur le Linux du nuage.
**Non testé sur vrai robot**, ni avec une vraie caméra, ni sur Mac. Rien publié, rien poussé.

## Ce qui est fait
- **Prise des yeux** (`prise_yeux.py`) : `Yeux.voir(image) -> Vue` (personnes, objets nommés, marqueurs ArUco, textes ;
  position dans l'image, et au sol si la caméra est calibrée). Un branchement absent ou en panne est dit, les autres
  continuent. `personnes_fiables` : vrai seulement si un outil qui voit les personnes a marché sur CETTE image.
- **Branchements** (`branchements/`) : `simule` (vérité du dessin, caméra simulée seulement), `aruco` (OpenCV),
  `mediapipe` (EfficientDet-Lite0 : personnes + 80 objets COCO), `rapidocr` (textes, lieux reconnus même avec une faute).
- **Caméra simulée** (`camera_simulee.py`, numpy seul) : le faux monde vu par le robot (humanoïde, chien, bras), personnes
  et objets aux positions de `monde.yaml` / de l'état du faux robot, marqueurs au sol, panneaux écrits. Refuse un vrai robot.
- **Calibration au sol** (`geometrie.py`, `calibrer.py`) : homographie (calcul numpy) depuis 3 marqueurs ArUco posés au sol.
- **Lien gardien** (`lien.py`) : personnes → `Perception.annoncer_personnes(…, heure=photo)`. Rien d'annoncé si caméra en
  panne (ou bloquée plus de 2 s), non calibrée, position inconnue, ou aucun outil pour les personnes → le gardien
  demande un humain (2 s). Une caméra bloquée n'empêche jamais le programme de s'arrêter. Pieds hors de l'image → personne mise à la place du robot (pire cas). **Vrai robot : jamais de personnes au gardien ; `gardien_vrai_robot: true` refusé au démarrage (corrections du lot D, plus bas).**
- **Lien cerveau** : « prends X » → X vu (moins de 3 s) : l'action continue, direction et distance maximale notées
  (événement `yeux`) ; pas vu : question `question_pas_vu` (5 langues) ; yeux qui ne savent pas : rien ne change.
- **Mesures** (`banc_yeux.py`, `MESURES.md`), **guide** (`GUIDE.md`), **tâches** (`TACHES.md`), **64 tests** (`tests/`,
  1 saute ici : MediaPipe). `python3 lancer.py tests` : toute la suite passe.

## Fichiers partagés modifiés (exactement)
| Fichier | Changement |
|---|---|
| `commun/systeme.py` | (1) `yeux_actifs = reglages.yeux.actif is True` ; `Perception(simulation=faux and not yeux_actifs, personnes=… seulement si simulées)`. (2) Après `creer_cerveau` : `self.yeux = None` ; si allumés, `LesYeux(…)` et `self.yeux.relier_au_cerveau(self.cerveau)`. (3) `demarrer()` : `await self.yeux.allumer()` après `prise.connecter()`. (4) `arreter()` : `await self.yeux.eteindre()` avant `prise.deconnecter()`. Éteints : rien ne change. |
| `briques/b07_gardien/perception.py` | `annoncer_personnes(…, heure=None)` : la fraîcheur se compte depuis l'heure de la photo, jamais dans le futur ; NaN ignoré ; sans `heure` : comme avant. **Relecteur sécurité.** |
| `commun/evenements.py` | Nouveau type `yeux` (une ligne). |
| `briques/b13_ecran/exemples_flux.py` | `yeux` ajouté à `CHAMPS` et à `A_LA_MAIN` (comme la brique 14) : le test de l'écran exige un exemple par type. |
| `briques/b13_ecran/FLUX_POUR_MOTION_DESIGN.md` | Seulement la section `### \`yeux\`` ajoutée avant `EXEMPLES:FIN` (le reste n'a pas été régénéré). |
| `commun/phrases.yaml` | `question_pas_vu` en fr, de, it, en, zh (une ligne chacune, après `question_choix`). |
| `reglages.exemple.yaml` | Nouvelle section `yeux:` (`actif: false`, caméra, branchements, calibration, périodes, `gardien_vrai_robot: false`). |
| `briques/etat_des_briques.yaml` | Entrée 5 : `socle`, faux robot oui, vrai robot jamais. |
| `requirements-yeux.txt` (nouveau, racine) | Paquets épinglés, à installer avec `--no-deps`. |

Non touchés : `lancer.py`, `briques/b01_prise/`, `commun/chaine.py`, `briques/b07_gardien/gardien.py`.
**À savoir pour la fusion avec la brique 11** : les seuls morceaux de `systeme.py` touchés sont autour de `Perception`,
après `creer_cerveau`, et au début de `demarrer`/`arreter`.
**Choix à relire** : le filet du cerveau est posé en remplaçant `cerveau.decider` sur l'objet (une fonction qui appelle
l'ancienne). Ainsi la cascade reste une `CerveauCascade` (le chef de démonstration la cherche) et `chaine.py` n'est pas
touché. Autre possibilité : un appel explicite dans `chaine.py`, après `filet_plusieurs_choix`.

## Paquets ajoutés (lus sur PyPI et dans les paquets le 11.11.2026 ; Linux x86_64, Python 3.13)
Taille = fichier téléchargé (Linux) / installé. Total ≈ 170 Mo téléchargés, ≈ 440 Mo installés. Chacun < 200 Mo.

| Paquet | Version | Licence | Taille |
|---|---|---|---|
| opencv-contrib-python-headless | 5.0.0.93 | Apache-2.0 ; contient FFmpeg (**LGPL-2.1**), OpenSSL ; Mac : aussi libgmp, libidn2, libunistring (**LGPL-3**). Contient aussi libgfortran et libquadmath, NON citées dans son fichier de licences (d’ordinaire GPL-3 avec exception d’exécution GCC : **à vérifier**) | 69 / 172 Mo (Mac : 56 Mo) |
| mediapipe | 1.2.2 | Apache-2.0 (NOTICE : composants tiers, dont la bibliothèque d'exécution gfortran, GPL-3 avec exception) | 43 / 127 Mo (Mac : 40 Mo) |
| rapidocr | 3.10.0 | Apache-2.0 ; modèles PP-OCRv6 small + cls mobile v2.0 inclus, Apache-2.0 (Baidu/PaddleOCR, `MODEL_LICENSES.md`) | 27 / 33 Mo |
| **matplotlib** | 3.11.2 | **licence « matplotlib » (type PSF, permissive, compatible BSD) : pas MIT/Apache/BSD au sens strict** — MediaPipe l'importe au démarrage | 10 / 34 Mo |
| **pillow** | 13.0.0 | **MIT-CMU** (permissive, de type HPND) | 7 / 23 Mo |
| fonttools | 4.68.0 | MIT | 5 / 29 Mo |
| shapely | 2.2.0 | BSD-3-Clause | 2 / 10 Mo |
| kiwisolver, contourpy, cycler | 1.5.1, 1.4.0, 0.12.1 | BSD | < 2 Mo chacun |
| pyclipper, pyparsing, six, colorlog, urllib3, charset-normalizer, sounddevice | 1.4.0, 3.3.3, 1.17.0, 6.12.0, 2.8.0, 3.5.2, 0.5.6 | MIT | < 1 Mo chacun |
| absl-py, requests, tzdata | 2.5.1, 2.34.2, 2026.6 | Apache-2.0 | < 1 Mo chacun |
| omegaconf, python-dateutil | 2.4.0, 4.0.0 | BSD (dateutil : BSD-3-Clause d'après PyPI) | < 1 Mo chacun |

**Modèle** : EfficientDet-Lite0 int8 v1 pour MediaPipe, 4 602 795 octets, sha256 `0720bf24…c723bb`
(`telecharger_modele.py`, « oui » tapé). Licence : **Apache-2.0 d'après son origine** (dépôt `google/automl`) ; la fiche
du modèle sur le site de MediaPipe (ai.google.dev) est **bloquée par le proxy : à vérifier**. Entraîné sur COCO.
Rangé dans `modeles/` (hors dépôt) de ma copie seulement.

**`--no-deps`** : mediapipe demande `opencv-contrib-python` (avec Qt, LGPL-3) et rapidocr `opencv-python-headless` ;
les deux écrivent le même dossier `cv2`. Un seul OpenCV (contrib, sans écran) les sert tous les deux. `pip check`
signale ces deux faux manques.

## Feu orange : NON fait, à proposer à Hiba
- **MediaPipe sur ce Linux** : il faut `libEGL.so.1` et `libGLESv2.so.2` (paquets Ubuntu `libegl1`, `libgles2` ; installer
  un programme = feu orange). Sans eux, MediaPipe n'a jamais tourné ici. Sur Mac : pas besoin a priori (**à vérifier**).
- Aucun paquet GPL/AGPL, payant ou > 500 Mo. OWLv2 : pas touché (option plus tard, DECISIONS.md).

## Lignes à ajouter dans LICENCES.md
```
## Brique 5 (les yeux) — en option, requirements-yeux.txt (installé avec --no-deps), testé sur Linux seulement

| Paquet | Version | Licence | Rôle |
|---|---|---|---|
| opencv-contrib-python-headless | 5.0.0.93 | Apache-2.0 ; contient FFmpeg (LGPL-2.1, bibliothèque séparée, non modifiée), OpenSSL ; sur Mac aussi libgmp, libidn2, libunistring (LGPL-3) ; libgfortran et libquadmath non citées dans son fichier de licences (à vérifier) | images, marqueurs ArUco |
| mediapipe | 1.2.2 | Apache-2.0 (NOTICE : composants tiers, dont gfortran, GPL-3 avec exception) | personnes et objets courants |
| matplotlib | 3.11.2 | licence matplotlib (type PSF, permissive) — importé par MediaPipe | (aucun usage direct) |
| rapidocr | 3.10.0 | Apache-2.0 ; modèles PP-OCRv6 inclus, Apache-2.0 (Baidu / PaddleOCR) | lire un texte |
| pillow | 13.0.0 | MIT-CMU | images (tiré par matplotlib, rapidocr) |
| fonttools, pyparsing, six, pyclipper, colorlog, urllib3, charset-normalizer, sounddevice | — | MIT | dépendances |
| contourpy, cycler, kiwisolver, shapely, omegaconf, python-dateutil | — | BSD | dépendances |
| absl-py, requests, tzdata | — | Apache-2.0 | dépendances |

Modèle : EfficientDet-Lite0 int8 v1 (Google, pour MediaPipe), 4,6 Mo, Apache-2.0 d'après son origine (google/automl) ;
fiche MediaPipe à vérifier. Images d'essai : toutes fabriquées par le projet (dessins, marqueurs générés), aucune
image téléchargée. Aucun code copié : la brique 5 est écrite pour ce projet (noms de fonctions des paquets cités).
```

## Lignes à ajouter dans DECISIONS.md (prises pendant la brique 5, à relire par Hiba)
```
- **Yeux éteints par défaut** (`reglages.yaml → yeux.actif`). Allumés avec le faux robot : caméra simulée, et les
  personnes du gardien viennent de la caméra (plus de monde.yaml directement).
- **Vrai robot : les personnes vues ne vont au gardien que si `yeux.gardien_vrai_robot: true`** (éteint) : la caméra ne
  voit que devant elle. À décider après la relecture sécurité. Proposition : le gardien demande un humain pour un
  chemin hors du champ de la caméra (les yeux savent le calculer).
- Pas d'annonce sans nouvelles sûres (caméra en panne, non calibrée, pas d'outil pour les personnes, place au sol
  inconnue) → le gardien demande un humain. Fraîcheur comptée depuis la photo. Pieds hors de l'image → collée au robot.
- Calibration au sol par 3 marqueurs ArUco posés à plat devant le robot (1,5 m ; 2,5 m ± 0,8 m), imprimés en A3.
- « Prends X » : X pas vu depuis 3 s → une question ; caméra en panne → comme sans les yeux. Objet sur une table :
  direction juste, distance trop grande (notée « distance maximale »).
- RapidOCR toutes les 5 s (lent) ; un texte proche d'un nom de lieu (une lettre fausse, mot ≥ 5 lettres) compte.
- OpenCV : un seul paquet (contrib, sans écran), installation `--no-deps`.
```

## Lignes à ajouter dans NON_TESTE.md
```
## Brique 5 (les yeux)
- Aucune vraie caméra (USB, flux du robot, kit du fabricant) : jamais essayée. Tout est sur caméra simulée.
- MediaPipe : jamais lancé (Linux du nuage sans libEGL). La détection de vraies personnes et d'objets est inconnue.
- Calibration avec de vrais marqueurs imprimés, un vrai objectif (déformation), une vraie lumière : jamais faite.
- Personnes aux jambes cachées, dans la foule, de dos, assises : jamais essayé (la place au sol peut être trop loin).
- RapidOCR : accents, allemand, chinois, écriture à la main : jamais essayés.
- Sur Mac : ni installé, ni mesuré (mémoire, temps par image).
```

## À signaler à Hiba
- Aucun texte lu (paquets, pages, dépôts) ne m'a demandé quoi que ce soit. Pages bloquées par le proxy : ai.google.dev,
  Wikimedia (pas de photo libre téléchargée : toutes les images d'essai sont fabriquées).
- Le lancement des tests a créé `reglages.yaml` dans ma copie (hors dépôt, comme prévu par `preparer_reglages`).

## Corrections après la relecture sécurité du lot D (branche `corrections-b5`, partie de `fe3565a`)

Chaque point a son test (faux robot, caméra simulée). `python3 lancer.py tests` : tout passe.

| Point | Correction | Test |
|---|---|---|
| 1 GRAVE (angles morts) | Les yeux donnent la **zone du sol vue** (`ZoneVue` : dans l'image moins 4 % aux bords, devant, à portée ; pas l'angle mort au pied de la caméra). Le gardien répond **humain** (`personnes_inconnues`, `hors_du_champ`) si le sol à moins d'1 m du chemin ou du geste sort de la zone. La zone est **obligatoire** dans `annoncer_personnes`. `gardien_vrai_robot` autre que `false` → **le programme refuse de démarrer** (même yeux éteints). Faux robot avec yeux : même règle. | `test_angles_morts_…`, `test_camera_du_robot_aucun_mouvement_sans_humain_…`, `test_zone_couvre_…`, `test_annoncer_des_personnes_demande_la_zone_vue`, `test_gardien_vrai_robot_true_le_programme_refuse_de_demarrer` |
| 4 MOYEN (photo fixe) | Caméra `fichier:` = **photo fixe** : jamais de personnes au gardien (même faux robot), jamais « je ne vois pas » au cerveau, mention « photo fixe ». | `test_une_photo_fixe_ne_donne_jamais_de_personnes_au_gardien` |
| 5 MOYEN (heure) | Heure de photo > maintenant + 0,1 s, ou pas un nombre fini → **rien d'annoncé** et l'annonce d'avant est oubliée (« personnes inconnues »). Le test qui vérifiait l'ancien comportement est corrigé. | `test_la_fraicheur_se_compte_depuis_la_photo_et_une_heure_fausse_est_refusee` |
| 6 PETIT (vraie caméra) | 5 images identiques de suite = image figée = panne ; position du robot lue **après** l'image ; lecture plus longue que `delai_camera_s` = image jetée. | `test_une_image_figee_est_une_panne`, `test_vraie_camera_la_position_du_robot_est_lue_apres_l_image`, `test_une_lecture_plus_longue_que_le_delai_est_jetee` |
| 11 PETIT (modèle) | Empreinte vérifiée sur le fichier **partiel** avant de le mettre en place (un mauvais téléchargement ne remplace jamais un bon modèle) ; **revérifiée** à chaque chargement par MediaPipe. | `test_le_modele_est_verifie_par_son_empreinte`, `test_mediapipe_reverifie_le_modele_au_chargement` |

**Conséquence à connaître** : avec la caméra du robot, le pied du robot n'est jamais vu → **tout déplacement ou geste
demande un humain** quand les yeux sont allumés (le « non » d'une personne vue trop près passe avant). Pour bouger
sans humain, il faut une caméra qui voie tout autour du chemin : une caméra **fixe** calibrée en repère « monde »
(`camera: simulee_fixe` le montre en simulation ; en vrai : à essayer). Ajouté pour les tests : `simulee_fixe`.

**Fichiers partagés modifiés par ces corrections (exactement)** :
- `briques/b07_gardien/perception.py` : `PARTOUT`, `Vue.zone_vue`, `zone_couvre()` ; `annoncer_personnes(…, *, zone)`
  (zone obligatoire) ; heure fausse ou dans le futur → plus rien d'annoncé. **Relecteur sécurité.**
- `briques/b07_gardien/gardien.py` : import de `zone_couvre` ; dans la boucle `distance_personnes`, le test de zone
  (humain si hors du champ) avant la distance ; une liste vide de personnes ne fait plus sauter la vérification quand
  une zone est donnée. Sans zone (personnes simulées) : comme avant. **Relecteur sécurité.**
- `briques/b07_gardien/tests/test_gardien.py` : une ligne, `zone=PARTOUT` dans l'appel existant à `annoncer_personnes`.
- `briques/b07_gardien/GUIDE.md` : deux lignes (zone obligatoire, heure fausse).
- `commun/systeme.py` : 3 lignes, `verifier_reglages(reglages["yeux"])` avant de créer `Perception` (refus de démarrer).
- `reglages.exemple.yaml` : commentaires de `yeux.camera` (`simulee_fixe`, photo fixe) et de `gardien_vrai_robot`.
Non touchés : `briques/b01_prise/`, `briques/b11_main_humaine/`, `commun/chaine.py`.

**À remplacer dans DECISIONS.md** (la ligne « Vrai robot : les personnes vues ne vont au gardien que si… ») :
```
- **Vrai robot : les personnes vues ne vont jamais au gardien** ; `yeux.gardien_vrai_robot: true` empêche le programme
  de démarrer tant que la relecture sécurité ne l'a pas permis (relecture du lot D).
- **« Pas vue » n'est pas « pas là »** : qui annonce des personnes donne aussi la zone du sol vue (obligatoire) ; si le
  sol à moins d'1 m du chemin ou du geste en sort → « demande à un humain ». Caméra sur le robot → tout mouvement
  demande un humain ; bouger sans humain demande une caméra qui voit tout le chemin (caméra fixe).
- Photo fixe (`fichier:`) : jamais de personnes au gardien. Heure de photo fausse ou dans le futur : rien d'annoncé.
- Vraie caméra : image figée (5 identiques) = panne ; position lue après l'image ; lecture trop lente = image jetée.
```
**À ajouter dans NON_TESTE.md** : « Brique 5 : zone vue avec une vraie caméra et un vrai objectif ; ce qui est caché
derrière un objet compte encore comme vu ; caméra fixe en repère monde jamais essayée en vrai. »

**Vu en passant, non corrigé (pas dans ma liste)** : « prends la valise » (objet interdit) hors du champ donne la
question « Je ne vois pas : valise » au lieu du refus du gardien ; sans danger (rien ne part), mais l'explication est
moins juste. Piste : ne poser la question qu'après un « oui » du gardien.
