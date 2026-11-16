# Brique 5 — Mesures des yeux

**Mesuré sur Linux, pas sur Mac.** Machine : Linux du nuage, x86_64, 4 cœurs, Python 3.13.18, le 11.11.2026
(charge de la machine ≈ 0,2 au départ). Images dessinées par la caméra simulée. Sur les Mac (puce Apple), les chiffres
seront différents : **à mesurer** avec `.venv/bin/python -m briques.b05_yeux.banc_yeux`.

## Temps par image et mémoire, outil par outil (`banc_yeux`, 40 images 320×240)

| Outil | ms par image (médiane) | 90 % des images en moins de | mémoire en plus | remarque |
|---|---|---|---|---|
| caméra simulée (dessin) | 8,2 | — | 80 Mo | dont le chargement de numpy et d'OpenCV |
| simule (vérité du dessin) | 0,0 | 0,0 | 0 Mo | |
| aruco (OpenCV) | 0,4 | 0,5 | 8 Mo | |
| mediapipe | **non mesuré** | — | — | ne démarre pas ici : `libEGL.so.1` absent (bibliothèque du système) |
| rapidocr | 303 | 330 | 162 Mo | chargement 0,26 s ; un panneau écrit |

En 640×480 (même jour) : dessin 22 ms, ArUco 1,1 ms, RapidOCR 295 ms ; mémoire semblable.

## Le programme entier (faux robot, cerveau à règles, 4 s de mesure)

| Yeux | Mémoire du programme | Processeur |
|---|---|---|
| éteints (défaut) | 39 Mo | ≈ 0 % |
| allumés, `[simule, aruco]` | 131 Mo | 7 % d'un cœur (5 images/s) |
| allumés, `[simule, aruco, rapidocr]`, textes toutes les 2 s | 320 Mo | 64 % d'un cœur |

→ RapidOCR coûte l'essentiel : textes toutes les **5 s** par défaut (`periode_textes_s`), ou l'enlever de la liste si la
mémoire manque. Marge du Mac : ≈ 4 Go (docs/projet/ORDINATEUR_CERVEAU.md) : les yeux complets (≈ 0,3 Go ici, MediaPipe non
compté) devraient tenir ; **à mesurer sur Mac** avec MediaPipe.

## Calibration au sol (caméra simulée, ArUco réel sur image dessinée)

| Montage simulé | Marqueurs vus | Erreur sur les coins | Écart avec la vraie transformation, jusqu'à 3 m |
|---|---|---|---|
| humanoïde (1,30 m, −25°) | 3 sur 3 | 0,6 cm | 0,8 cm en moyenne |
| chien (0,35 m, −8°) | 3 sur 3 | 0,2 cm | 2,0 cm en moyenne |
| bras (1,10 m, −35°, vers la gauche) | 3 sur 3 | 0,5 cm | 0,8 cm en moyenne |

Coins affinés au sous-pixel (réglage d'ArUco). Avec **un seul** marqueur (humanoïde) : 0,9 cm en moyenne jusqu'à 4 m,
aussi bien que trois — mais l'image simulée est parfaite. Sans l'affinage, un marqueur seul semblable (0,30 m à 1,5 m) donnait 0,6 m
d'erreur à 3 m et 1,5 m à 4 m. En vrai (bruit, objectif qui déforme) : **3 marqueurs** (l'erreur est alors mesurée et
affichée) ; écart réel **à vérifier samedi**.

## Personnes remises au sol (caméra simulée, humanoïde au départ)

- Visiteur de `monde.yaml` en (8,6 ; 2,2), à 7,7 m : vu en (8,72 ; 2,29), écart 0,15 m.
- Personne placée en (3,0 ; 1,3) : vue en (2,77 ; 1,37), écart 0,24 m, **du côté du robot** (le bas de la boîte
  est le bord avant des pieds) : ici, le gardien la croit un peu plus près. Jambes cachées (derrière une table) : elle
  paraîtrait plus LOIN (limite, voir GUIDE.md).
