# Les écrans (cahier 5.4)

Un guide d'une page. Données inventées. Rien n'a été essayé sur un vrai robot ni avec de vrais patients.

## Rôle
Les pages pour chaque rôle : patient (quatre langues), soignant, médecin, accueil, thérapeute, direction, et les pages
de travail (listes, pauses, tableau de flotte, Invité…). Chacune montre ce que la porte lui donne et le bandeau
« DONNÉES INVENTÉES » ; la plupart affichent l'âge de l'information (pas le journal, la pré-admission, le faux logiciel).

## Fichiers
- `briques/clinique/ecrans.py` : les pages, le style, la mise à jour sans perdre un clic.
- `briques/clinique/traductions.py`, `briques/clinique/traductions_ecrans.yaml` : les mots des écrans dans les langues.
- `briques/clinique/reseau_local.py` : la page `/clinique/telephones` (les adresses du Wi-Fi).
- `briques/clinique/lisibilite.py` : la taille du texte des écrans Patient et Invité.

## Lancer et voir
`python3 lancer.py`, puis ouvrir `/clinique` : la liste de tous les écrans.
`python3 lancer.py telephones` : chaque écran ouvert par l'adresse du Wi-Fi, comme un téléphone.
`.venv/bin/python outils/pages_vues_chrome.py --n02` : les pages dans Chrome (46 ouvertes sur 48 au dernier passage), images dans `pages_vues/n02/` ; le compte rendu, écrit à la main : `docs/projet/PAGES_VUES.md`.

## Les essais
`python3 lancer.py tests briques/clinique/tests/test_ecrans.py`, `python3 lancer.py tests briques/clinique/tests/test_pages_sur_telephone.py`, `python3 lancer.py tests briques/clinique/tests/test_pages_n02.py`, `python3 lancer.py tests briques/clinique/tests/test_clic_dans_le_navigateur.py`, `python3 lancer.py tests briques/clinique/tests/test_age_de_l_information.py`, `python3 lancer.py tests briques/clinique/tests/test_reseau_local.py`.

## Ce qui n'est pas testé
- Les pages ont été vues par un programme dans Chrome, pas par une personne sur un vrai téléphone, ni dans Safari.
- Les langues sont mêlées : sur l'écran du patient, le programme reste en français ; les écrans allemands du soignant et du médecin sont presque tout en français (Q19, Q25). Traductions pas relues.
- Les pages sont en http, sans code pour les lire : n'importe qui sur le même Wi-Fi peut les ouvrir (données inventées).
- Les codes QR attendent la réponse de Hiba (question Q29).

Les petites tâches : `TACHES.md`, dans ce dossier. Avant de dire « fini » : `python3 lancer.py tests` passe.
