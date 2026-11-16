# La porte de lecture (cahier 5.2)

Un guide d'une page. Données inventées. Rien n'a été essayé sur un vrai robot ni avec de vrais patients.

## Rôle
Toute lecture du faux dossier passe par elle. Elle sait qui demande (le badge) et ne donne que ce que ce rôle a le droit
de voir : le soignant voit les patients de son étage, la direction ne voit que des comptes, le robot ne voit rien de la
santé, l'assistant (le cerveau) voit ce que voit la personne pour qui il travaille. Chaque lecture est écrite au journal.

## Fichiers
- `briques/clinique/porte.py` : la porte, le journal des accès, les refus.
- `briques/clinique/badges.yaml` : les badges (patient, soignant, thérapeute, médecin, accueil, direction, assistant, robot).
- La page `/clinique/journal` : qui a lu quoi, quand (des numéros de dossier, jamais un nom).

## Lancer et voir
`python3 lancer.py`, puis ouvrir `/clinique/journal` après avoir ouvert un écran.
Une demande d'écriture est refusée et notée : rien ne s'écrit dans le faux dossier.

## Les essais
`python3 lancer.py tests briques/clinique/tests/test_porte_lecture.py`, `python3 lancer.py tests briques/clinique/tests/test_cerveau_par_la_porte.py`, `python3 lancer.py tests briques/clinique/tests/test_accueil_sans_texte_medical.py`.

## Ce qui n'est pas testé
- Pas de vrai mot de passe : un badge est un nom dans l'adresse. C'est une démonstration, pas une sécurité.
- Le journal des accès : un fichier par séance, gardé sur l'ordinateur dans `journal/clinique/` (jamais vers GitHub).

Les petites tâches : `TACHES.md`, dans ce dossier. Avant de dire « fini » : `python3 lancer.py tests` passe.
