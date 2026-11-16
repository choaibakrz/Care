# L'horloge de démonstration (cahier 5.3)

Un guide d'une page. Données inventées. Rien n'a été essayé sur un vrai robot ni avec de vrais patients.

## Rôle
Elle fait sauter le temps du scénario : l'arrivée à 9 h, le soir à 19 h, le lendemain à 7 h 30. Dès le premier saut,
la marque « temps accéléré » s'affiche sur les écrans et la fiche de vérité le note. Elle ne recule jamais.

## Fichiers
- `briques/clinique/horloge.py` : l'horloge, les sauts, la marque.
- `briques/clinique/heures_scenario.yaml` : les repères (arrivée, papiers, installation en chambre, questions du soir, visite…).
- La page `/clinique/heure` : l'heure du scénario.

## Lancer et voir
`python3 lancer.py repetition` : l'horloge saute de scène en scène.
`python3 lancer.py seance-unique` : une seule horloge pour les sept scènes.

## Les essais
`python3 lancer.py tests briques/clinique/tests/test_horloge.py`.

## Ce qui n'est pas testé
- Chaque pièce qui a sa propre horloge (une étape de la répétition) compte ses sauts à part : la fiche le dit.

Les petites tâches : `TACHES.md`, dans ce dossier. Avant de dire « fini » : `python3 lancer.py tests` passe.
