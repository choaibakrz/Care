# La première heure avec un vrai robot

Une page, à imprimer. Les gestes dans l'ordre, du câble au premier mouvement lent.
**Cette page n'a jamais été essayée : tout est non testé sur vrai robot.** Les deux ébauches (`unitree_go2`,
`roues_ros2`) sont « PRÉPARÉES SANS LE ROBOT » : elles n'ont parlé qu'à une doublure. Le détail : `BRANCHER_UN_ROBOT.md`.

Règle de la page : **on essaie l'arrêt avant tout mouvement.** Si un geste ne marche pas, on s'arrête là et on le dit.
Tout ordre au vrai robot est un **feu orange** : Hiba dit « oui », et c'est **un humain** qui tape la commande, pas un agent.

## Avant de toucher au clavier
1. **Les personnes.** Hiba donne son accord. Le responsable sécurité se place à côté du robot et y reste.
   Une personne garde la main sur l'arrêt pendant tous les essais. Zone vide autour du robot (distance : à vérifier
   avec les organisateurs).
2. **Le bouton d'arrêt physique.** Le trouver avec la personne du fabricant, le montrer à tous, l'essayer
   **robot immobile**. Demander ce qui se passe quand on appuie : le robot reste-t-il debout, ou tombe-t-il ?
   Sans arrêt physique trouvé et essayé : on ne va pas plus loin.
3. **La pose du robot.** Robot à jambes : suspendu ou posé de façon stable, comme le dit le fabricant (à vérifier).
   Robot à roues : roues décollées du sol ou sur cales pour le premier essai, si c'est possible (à vérifier).
4. **Noter le robot.** Fabricant, modèle exact, version de son logiciel : dans la carte (`docs/projet/CARTE_A_REMPLIR.md`).
   Remplacer chaque « à vérifier samedi » de la carte et de la liaison par ce que le fabricant dit, avec son nom.

## Du câble à la connexion (rien ne bouge)
5. **Le câble.** Brancher le câble réseau entre notre ordinateur et le robot (ou rejoindre son réseau sans fil).
   Adresse du robot, réglage de notre carte réseau : à vérifier avec le fabricant. Un Mac suffit-il ? À vérifier.
6. **Le kit du fabricant.** S'il faut installer son kit ou ROS 2 : feu orange — dire la taille et la licence,
   attendre le « oui » de Hiba. Rien n'est installé d'avance.
7. **La répétition sur la doublure.** `python3 lancer.py brancher unitree_go2 --conformite` (ou `roues_ros2`) :
   doit dire « RÉUSSI », « testé sur faux robot ». Le vrai robot n'a rien reçu.
8. **Le vrai robot, sans mouvement.** Un humain tape : `python3 lancer.py brancher unitree_go2 --conformite --vrai`
   et la phrase demandée. Le programme se connecte, lit l'état, et n'envoie aucun ordre de mouvement.
   Lire chaque ligne ✘ avec la personne du fabricant, corriger, recommencer.

## L'arrêt, puis le premier mouvement
9. **L'arrêt logiciel, robot immobile.** Pendant le test sans mouvement, le programme envoie son arrêt d'urgence.
   Regarder le robot : que fait-il ? Décider avec le responsable sécurité si cet arrêt est le bon
   (les ébauches proposent seulement « vitesse nulle »). L'arrêt logiciel ne remplace jamais le bouton.
10. **Le robot se lève** (robot à jambes seulement). Avec la télécommande du fabricant, ou par notre ordre « se_lever »,
    main sur l'arrêt. Notre programme ne lève jamais le robot tout seul.
11. **Premier mouvement lent : 0,1 m/s, quelques centimètres.** Un humain tape :
    `python3 lancer.py brancher unitree_go2 --conformite --vrai --complet` et la phrase demandée.
    Main sur le bouton. Le test fait un petit déplacement, puis un arrêt d'urgence pendant un mouvement.
12. **Regarder à l'œil.** Le robot est-il allé dans le bon sens ? S'est-il arrêté net ? S'arrête-t-il seul quand
    le programme se tait (couper le programme pendant un mouvement lent, main sur le bouton) ? Noter les réponses.

## Après
13. **Compter.** Chaque essai, réussi ou raté, se compte sur la page des essais réels (`docs/projet/PROTOCOLE_ESSAIS_REELS.md`).
    Seule l'équipe compte : un agent n'a pas vu le robot.
14. **Écrire.** Ce qui a marché : « testé sur vrai robot », avec la date. Ce qui n'a pas été essayé reste
    « non testé sur vrai robot ». Enlever la marque « PRÉPARÉE SANS LE ROBOT » seulement de ce qui a été vu.
