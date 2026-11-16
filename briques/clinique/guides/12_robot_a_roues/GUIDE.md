# Le robot à roues : préparer sans toucher (cahier 5.12)

Un guide d'une page. Données inventées. Rien n'a été essayé sur un vrai robot ni avec de vrais patients.

## Rôle
Tout est prêt pour brancher un robot à roues à deux bras, sans l'avoir vu : une carte d'exemple pour le faux robot, une
ébauche d'adaptateur tirée du modèle vide, et la liste des questions du samedi matin. Avec un vrai robot : feu orange,
un humain tape la commande, le responsable sécurité est là, la main sur l'arrêt physique.

## Fichiers
- `briques/b02_faux_robot/cartes/roues_deux_bras.yaml` : la carte d'exemple (5 kg par bras, à vérifier ; vitesse lente).
- `briques/b03_adaptateurs/robots/roues_deux_bras/` : l'ébauche (« NON TESTÉ SUR VRAI ROBOT »).
- `briques/b03_adaptateurs/robots/roues_ros2/` : l'ébauche d'un robot à roues qui parle ROS 2.
- `docs/projet/SAMEDI_MATIN.md`, `docs/projet/PREMIERE_HEURE.md`, `BRANCHER_UN_ROBOT.md` : les questions et les gestes de la première heure.

## Lancer et voir
`python3 lancer.py brancher-carte roues_deux_bras` : le test de conformité sur le faux robot.
`python3 lancer.py brancher roues_deux_bras --conformite` : l'ébauche avec le faux kit.

## Les essais
`python3 lancer.py tests briques/clinique/tests/test_robot_a_roues.py`, `python3 lancer.py tests briques/clinique/tests/test_premiere_heure.py`, `python3 lancer.py tests briques/clinique/tests/test_brancher_carte.py`.

## Ce qui n'est pas testé
- Aucun robot de ce genre n'a été vu. Chaque chiffre est à vérifier avec la documentation du fabricant.
- Les questions du samedi matin (navigation, arrêt qui coupe le courant, rouler près du public) n'ont pas de réponse.

Les petites tâches : `TACHES.md`, dans ce dossier. Avant de dire « fini » : `python3 lancer.py tests` passe.
