# Samedi matin — la liste du premier jour

Samedi 14 novembre 2026, de 9 h à midi. Cocher chaque ligne, dans l'ordre. Une ligne qui coince : le dire tout de suite au chef.

**Feu orange** : tout ce qui touche un vrai robot attend le « oui » de Hiba, avec le responsable sécurité présent,
la main sur le bouton d'arrêt **PHYSIQUE**. Rien n'a encore été essayé sur un vrai robot (`NON_TESTE.md`).

## 1. Arrivée (9 h)
- [ ] Appel des 35 personnes avec l'annexe A du plan ; écrire les prénoms à la main.
- [ ] Le responsable sécurité et son adjoint sont nommés ; tout le monde sait qui ils sont.
- [ ] Repérer la zone de démonstration, les prises électriques, la sortie de secours (à vérifier avec les organisateurs).
- [ ] Demander aux organisateurs : l'heure de passage devant le jury, les règles de sécurité du lieu, où charger les batteries.

## 2. Réseau local
- [ ] Le Wi-Fi de l'équipe marche ; noter l'adresse de chaque Mac (Réglages Système → Réseau).
- [ ] Rappel : le projet n'a pas besoin d'Internet. Les tests tournent avec Internet coupé.
- [ ] Une solution de secours si le Wi-Fi tombe (câble ou partage de connexion : à vérifier sur place).

## 3. Les deux Mac (iMac = cerveau, MacBook = secours)
- [ ] Les deux Mac sont sur le secteur ; la mise en veille est coupée pour le week-end.
- [ ] Les deux Mac ont la même version du projet (`git log -1` donne la même ligne).
- [ ] iMac : `python3 lancer.py tests` → tout passe.
- [ ] MacBook : `python3 lancer.py tests` → tout passe.
- [ ] `python3 lancer.py demo` : la petite démonstration et la fiche de vérité s'affichent.
- [ ] `say -v '?'` sur chaque Mac : noter les voix fr, de, it, en, zh (tâche de la brique 4 ; noms **à vérifier**).
- [ ] iMac : `python3 lancer.py cerveau` dit « prêt ». Sinon, le cerveau à règles prend le relais : le noter.

## 4. Le code d'équipe et l'écran
- [ ] Hiba choisit le code d'équipe et l'écrit **à la main** dans `reglages.yaml` → `ecran.code_equipe`, sur chaque Mac. Jamais dans le dépôt.
- [ ] `python3 lancer.py`, puis ouvrir `http://localhost:8000` sur l'iMac.
- [ ] Depuis un autre ordinateur du Wi-Fi : `http://<adresse-du-mac>:8000`. Le code est demandé une fois. Le bouton ARRÊT marche sans code.
- [ ] L'écran du jury (grand écran ou projecteur) est branché et montre la page. La page du jury en grand : brique 13, à faire.

## 5. Lire le défi avec le kit (10 h)
- [ ] Copier le texte du défi dans `defi.md` (ou `defi.txt`).
- [ ] `python3 lancer.py kit-samedi defi.md --sortie plan.md` → `plan.md` et `plan_scenario.yaml` (hors ligne, quelques secondes).
- [ ] Relire le plan à deux : le kit repère des mots-clés, il ne comprend pas. Corriger à la main ce qui est faux.
- [ ] Poser aux organisateurs les questions de la partie 1 du plan.
- [ ] Réunion de 20 minutes : le plan, les chantiers, les équipes, les feux.
- [ ] Distribuer les tâches (partie 3 du plan) : une tâche = une personne, moins d'une heure, avec son test.

## 6. Brancher le vrai robot — feu orange (11 h)
- [ ] Accord de Hiba. Responsable sécurité présent. Zone vide autour du robot.
- [ ] Lire la documentation du fabricant : arrêt d'urgence, vitesse maximale, chien de garde, batterie. Tout chiffre non écrit dans la documentation : **à vérifier**, jamais inventé.
- [ ] Créer le dossier du robot : `python3 lancer.py brancher NOM --genre … --chemin sdk|ros2` (brique 3), puis suivre
      `BRANCHER_UN_ROBOT.md` (skill `brancher-un-robot`) : carte d'identité, liaison, test de conformité.
- [ ] Dans `reglages.yaml` : `robot.adaptateur` = le nouvel adaptateur ; `robot.vrai_robot: true` (la fiche de vérité le dira d'elle-même).

## 7. Le test de conformité
Le test de conformité vérifie qu'un adaptateur respecte la prise universelle (`briques/b01_prise/conformite.py`).
- [ ] Sur le faux robot d'abord : `python3 lancer.py tests briques/b02_faux_robot -k conformite` → passe.
- [ ] Sur le vrai robot, mode **sans mouvement** d'abord (`complet=False` : lit la carte et l'état, vérifie l'arrêt d'urgence, rien ne bouge). Commande : `python3 lancer.py brancher NOM --conformite --vrai` (une personne la tape ; voir BRANCHER_UN_ROBOT.md). Feu orange.
- [ ] Puis le mode complet (petits gestes sûrs, mode lent) : `python3 lancer.py brancher NOM --conformite --vrai --complet`, seulement après le « oui » de Hiba. Feu orange.
- [ ] Noter le résultat (réussi / échec, et quels contrôles) dans le plan.

## 8. L'arrêt d'urgence, PHYSIQUE et logiciel
- [ ] Bouton d'arrêt **PHYSIQUE** du robot : trouvé, essayé robot immobile, puis pendant un mouvement lent. Feu orange.
- [ ] Bouton ARRÊT de l'écran : le robot s'arrête et reste bloqué jusqu'à « Réarmer » (par un humain).
- [ ] Dire « stop » au robot : il s'arrête (« stop » passe avant tout).
- [ ] Liaison coupée : le robot s'arrête-t-il seul ? Son chien de garde est **à vérifier** (NON_TESTE.md). Feu orange.
- [ ] Rappel pour tous : l'arrêt logiciel ne remplace **jamais** le bouton physique.

## 9. Les limites de vitesse et de force
- [ ] `reglages.yaml` → `securite` : 0,3 m/s et 15 N par défaut. Ne pas les monter sans le « oui » de Hiba.
- [ ] Si le défi ou le fabricant donne une limite plus basse : mettre la plus basse.
- [ ] Ordre dangereux d'essai : « Va à la cuisine à 5 mètres par seconde » → le robot refuse et explique.
- [ ] La carte d'identité du vrai robot ne dépasse pas ce que dit le fabricant.

## 10. Avant midi
- [ ] `python3 lancer.py tests` encore une fois, sur les deux Mac.
- [ ] Copier le dossier `journal/` sur le second Mac.
- [ ] Hiba : cinq lignes à l'équipe — ce qui marche, ce qui manque, les chantiers de l'après-midi.

## En plus, pour le matériel
Avenant 3 (M01). À demander aux organisateurs et à la personne du fabricant, avant de toucher un robot.
- [ ] Quels modèles sont là, et dans quelle version : celle qu'on peut programmer ?
- [ ] Combien de robots pour notre équipe, et pour combien de temps ?
- [ ] Qui, chez le fabricant, peut nous aider sur place ?
- [ ] Que fait le robot quand on appuie sur l'arrêt : il se fige, il s'assoit, il tombe ?
- [ ] Un robot à jambes a-t-il besoin d'un support ou d'une sangle au début ?
- [ ] A-t-il des mains ou des pinces ? Que peut-il saisir, et jusqu'à quel poids ?
- [ ] Peut-on le télécommander ? Avec quoi, et qui en a le droit ?
- [ ] Pour un robot sans bras : y a-t-il un panier ou un plateau ?
- [ ] Y a-t-il trois niveaux d'étagère et une table pour l'épreuve (M02) ?
Trois cartes sont prêtes d'avance (`unitree_g1`, `unitree_go2`, `unitree_g1d`), marquées « préparée sans le robot ». Pour un autre robot : `docs/projet/CARTE_A_REMPLIR.md`.

## Le robot à roues (cahier 5.12)
Avant de toucher un robot à roues. Une carte d'exemple est prête (`roues_deux_bras`, faux robot) et une ébauche d'adaptateur (`briques/b03_adaptateurs/robots/roues_deux_bras/`), toutes deux non testées sur vrai robot.
- [ ] Quel robot, et pour combien d'heures ?
- [ ] Peut-on le piloter depuis nos ordinateurs ?
- [ ] Y a-t-il un vrai bouton d'arrêt qui coupe le courant ?
- [ ] Sa navigation marche-t-elle dans la salle ?
- [ ] La prise d'objet est-elle prête ?
- [ ] A-t-on le droit de rouler près du public, et à quelle vitesse ?
- [ ] Micro et haut-parleur : les siens ou les nôtres ?
- [ ] Batterie et recharge : combien de temps, et où recharger ?

## La vraie salle (avenant 2, K05)
- [ ] La lumière de la salle est-elle celle de nos essais ?
- [ ] Y a-t-il des reflets ou des objets brillants ?
- [ ] Quel est le bruit ?
- [ ] Le Wi-Fi tient-il quand la salle est pleine ?
- [ ] A-t-on répété une fois dans la vraie salle, à l'heure de la démonstration ?
- [ ] L'heure exacte de la démonstration finale est-elle confirmée par les organisateurs ?

## Le MacBook, secours (réponse de Hiba à Q31 : tout sur l'iMac)
Le MacBook Air (192.168.1.42) a le projet, son `.venv`, whisper.cpp 1.9.5 et le modèle d'écoute « small ». Il n'a pas Apertus : sur lui, le cerveau à règles prend le relais.
- [ ] Mettre le MacBook à la même version que l'iMac : sur l'iMac `git log -1 --format=%h`, puis sur le MacBook un nouveau bundle (`git bundle create leukerbad.bundle clinique-en-boite`, puis `git pull` depuis ce fichier).
- [x] Mettre Chrome à jour sur le MacBook : fait par Hiba le 13.11 (157.0.8103.79) ; les essais de largeur de téléphone y passent.
- [ ] Le port 8000 du MacBook est pris par un autre projet (HackVS) : pour l'écran de la clinique sur le MacBook, mettre un autre port dans son `reglages.yaml` (ecran.port), ou arrêter HackVS (c'est à Hiba de décider).
- [ ] Si l'iMac tombe pendant la démonstration : sur le MacBook, `python3 lancer.py`, puis ouvrir l'adresse affichée. Pas d'Apertus : les réponses viennent des règles (la fiche de vérité le dit).
