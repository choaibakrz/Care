# Le tableau des tâches et les demandes au robot (cahier 5.6)

Un guide d'une page. Données inventées. Rien n'a été essayé sur un vrai robot ni avec de vrais patients.

## Rôle
« Il manque un coussin en chambre 12 » devient une tâche. Un objet flou fait poser une question (« le grand, ou celui
pour la nuque ? »). Le faux robot va de la réserve à la chambre ; chaque geste passe par le gardien. La livraison coche
le point en attente. Un objet absent passe la tâche à un humain. Trois temps sont notés : demandé, confirmé, constaté.

## Fichiers
- `briques/clinique/taches.py` : le tableau des tâches, les états (demandée, attribuée, en route, livrée, échouée, reprise).
- `briques/clinique/coursier.py` : la course du robot branché, sous le gardien ; le robot sans bras (plateau).
- `briques/clinique/aide_humaine.py` : chaque aide humaine comptée.

## Lancer et voir
`python3 lancer.py`, puis une demande sur l'écran du soignant ; le bouton « Pourquoi ? » montre le choix.
`python3 lancer.py a-vous --objet "une guitare"` : un objet absent de la réserve.
`python3 lancer.py tirage 1` : trente demandes au hasard, et « gestes interdits exécutés ».

## Les essais
`python3 lancer.py tests briques/clinique/tests/test_demande_au_robot.py`, `python3 lancer.py tests briques/clinique/tests/test_course_du_robot.py`, `python3 lancer.py tests briques/clinique/tests/test_demander_a_la_voix.py`, `python3 lancer.py tests briques/clinique/tests/test_trois_temps.py`, `python3 lancer.py tests briques/clinique/tests/test_robot_a_plateau.py`, `python3 lancer.py tests briques/clinique/tests/test_choix_explique.py`, `python3 lancer.py tests briques/clinique/tests/test_tirage.py`.

## Ce qui n'est pas testé
- Tout est fait sur le faux robot. « Constaté » vient du monde simulé, pas d'une personne qui a regardé.
- Une demande n'est comprise qu'en français, avec quatre tournures. Si le gardien demande l'accord d'un humain, la tâche échoue.
- Le tirage se joue avec le cerveau de test (ce n'est pas un chiffre de compréhension) ; « gestes interdits exécutés » ne compte que « saisir » et « aller au Hall ».
- Quel point le coussin doit cocher reste à décider avec Hiba.

Les petites tâches : `TACHES.md`, dans ce dossier. Avant de dire « fini » : `python3 lancer.py tests` passe.
