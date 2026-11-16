# La flotte (cahier 5.10)

Un guide d'une page. Données inventées. Rien n'a été essayé sur un vrai robot ni avec de vrais patients.

## Rôle
Quatre robots : R1 est le robot branché (le faux robot, aujourd'hui) ; R2, R3, R4 sont simulés. Chacun a une carte de
rôle (Accueil, Étage, Thérapie, Visite, Nuit) qui dit ses lieux, sa vitesse et ses gestes ; pour R1, le gardien
l'applique. Le répartiteur choisit le plus proche qui a le droit, et dit pourquoi. Quand un robot est branché, une vraie
course ne va jamais à un robot simulé : R1 ou un humain. Une panne : la course est reprise.

## Fichiers
- `briques/clinique/flotte.yaml`, `briques/clinique/flotte.py` : les quatre robots, la page simple `/clinique/flotte`.
- `briques/clinique/cartes.py`, `briques/clinique/cartes_de_role/`, `briques/clinique/cartes_gardien.py` : les cartes, et le gardien.
- `briques/clinique/monde_robots.py`, `briques/clinique/repartiteur.py`, `briques/clinique/panne_reprise.py`.
- `briques/clinique/tableau_flotte.py` : la page `/clinique/tableau-de-flotte` (plan, batterie, « Pourquoi ? »).

## Lancer et voir
`python3 lancer.py cartes` · `python3 lancer.py monde-robots` · `python3 lancer.py panne-reprise`.
`python3 lancer.py`, puis `/clinique/tableau-de-flotte` : avancer d'un pas, provoquer une panne, reprendre.

## Les essais
`python3 lancer.py tests briques/clinique/tests/test_flotte_simple.py`, `python3 lancer.py tests briques/clinique/tests/test_cartes_gardien.py`, `python3 lancer.py tests briques/clinique/tests/test_carte_pas_contournable.py`, `python3 lancer.py tests briques/clinique/tests/test_repartiteur.py`, `python3 lancer.py tests briques/clinique/tests/test_panne_et_reprise.py`, `python3 lancer.py tests briques/clinique/tests/test_tableau_de_flotte.py`, `python3 lancer.py tests briques/clinique/tests/test_place_de_r1.py`.

## Ce qui n'est pas testé
- R2, R3, R4 n'existent que dans l'ordinateur : rien ne bouge. Le relais entre deux robots est proposé, pas joué.
- La carte de R1 n'a été appliquée qu'au faux robot ; les cartes Thérapie et Visite jamais avec le gardien. Un lieu interdit est un rond de 0,3 m.
- L'étape 12 de la grande répétition joue encore la flotte simple.

Les petites tâches : `TACHES.md`, dans ce dossier. Avant de dire « fini » : `python3 lancer.py tests` passe.
