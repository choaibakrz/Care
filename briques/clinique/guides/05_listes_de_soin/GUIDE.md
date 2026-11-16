# Les listes de soin (cahier 5.5)

Un guide d'une page. Données inventées. Rien n'a été essayé sur un vrai robot ni avec de vrais patients.

## Rôle
La soignante coche les points d'une liste (au doigt, ou par une phrase). En sortant de la chambre, la tablette affiche le point
oublié : « Il reste un point : la sonnette. » En fin de poste, trois choix pour chaque point restant. La direction ne
voit que des comptes. Chaque coche est écrite au carnet, avec l'heure et le badge. La phrase s'affiche ; elle n'est pas dite.

## Fichiers
- `briques/clinique/listes.py` : cocher, « je sors », fin de poste, prise de poste.
- `briques/clinique/ecrans_listes.py` : la page de la liste, les boutons, la tablette hors ligne.
- `briques/clinique/faux_dossier/listes_de_soin.yaml` : les points, leur nom court et leurs mots en français ; `briques/clinique/mots_des_points.yaml` : les mots en allemand, italien, anglais.
- `briques/clinique/carnet.py` : le carnet de la séance.

## Lancer et voir
`python3 lancer.py`, puis `/clinique/soignant/liste?badge=soignant-etage-2&patient=p01&liste=installation`.
`python3 lancer.py a-vous --point 5` : un autre point oublié, sans toucher au code.

## Les essais
`python3 lancer.py tests briques/clinique/tests/test_listes_de_soin.py`, `python3 lancer.py tests briques/clinique/tests/test_ecran_listes.py`, `python3 lancer.py tests briques/clinique/tests/test_cocher_a_la_voix.py`, `python3 lancer.py tests briques/clinique/tests/test_panne_tablette.py`.

## Ce qui n'est pas testé
- Les listes sont des exemples inventés, non médicaux.
- « Cocher à la voix » : la page n'a pas de micro ; la phrase est tapée dans « La tablette a entendu ». Aucun vrai son ne dit ces phrases.
- L'accueil et le thérapeute ne peuvent pas cocher. Après un redémarrage, les coches ne reviennent pas à l'écran. Hors ligne, seules les coches sont gardées.

Les petites tâches : `TACHES.md`, dans ce dossier. Avant de dire « fini » : `python3 lancer.py tests` passe.
