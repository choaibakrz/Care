# Les papiers (cahier 5.8)

Un guide d'une page. Données inventées. Rien n'a été essayé sur un vrai robot ni avec de vrais patients.

## Rôle
L'écran de l'accueil propose où ranger chaque papier (type, date, auteur, patient, endroit), avec une confiance (une règle, pas une mesure).
Une confiance basse donne « je ne suis pas sûr ». Un humain valide d'un doigt ; la validation va au carnet, pas au faux
dossier. La feuille sans nom n'est jamais rangée. L'accueil ne voit pas le texte médical.

## Fichiers
- `briques/clinique/papiers.py` : la proposition, les règles, la validation.
- `briques/clinique/ecrans_papiers.py` : la page de l'accueil.
- `briques/clinique/papiers_images.py` : lire un papier depuis une image (lecture de texte du Mac).
- `briques/clinique/papiers_apertus.py` et `docs/projet/MESURE_PAPIERS_APERTUS.md` : le rangement par Apertus, mesuré.

## Lancer et voir
`python3 lancer.py`, puis `/clinique/accueil/papiers?badge=accueil`.
`python3 lancer.py papiers-images` : le taux d'erreur de lecture des images.
`python3 lancer.py papiers-apertus` : la mesure avec le vrai Apertus.

## Les essais
`python3 lancer.py tests briques/clinique/tests/test_papiers.py`, `python3 lancer.py tests briques/clinique/tests/test_papiers_images.py`, `python3 lancer.py tests briques/clinique/tests/test_papiers_apertus.py`, `python3 lancer.py tests briques/clinique/tests/test_papiers_cerveau.py`.

## Ce qui n'est pas testé
- Les papiers sont des textes et des images inventés, pas de vrais papiers scannés.
- Dans les écrans, ce sont les règles qui proposent (pas Apertus) et les images ne sont pas lues. Avec Apertus, mesuré à part : 2 papiers sur 9 bien rangés et sûrs ; aucun mal rangé dit sûr.
- La date proposée est la première trouvée (peut-être une date de naissance) ; le patient est trouvé par « prénom + initiale ».

Les petites tâches : `TACHES.md`, dans ce dossier. Avant de dire « fini » : `python3 lancer.py tests` passe.
