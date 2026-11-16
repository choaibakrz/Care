# Ce qui n'a pas été essayé sur un vrai robot (ni sur les Mac)

Tout le projet est **testé sur faux robot**, sur un ordinateur Linux dans le nuage (4 cœurs, 16 Go, sans carte graphique).

## Jamais essayé sur un vrai robot
- Toute la prise universelle, le gardien, la chaîne : uniquement avec le faux robot.
- Le chien de garde : simulé dans le faux robot. Un vrai robot doit avoir le sien (à vérifier dans chaque kit fabricant).
- L'arrêt d'urgence logiciel : il ne remplace **jamais** le bouton d'arrêt physique du robot.
  Sur le faux robot, une liaison coupée empêche l'ordre d'arrivée (comme en vrai) ; c'est son chien de garde qui l'arrête.
- Le code d'équipe de l'écran : une protection simple contre les erreurs sur le Wi-Fi, pas contre une attaque sérieuse.
- Les limites de vitesse et de force : vérifiées dans le code, pas mesurées sur un moteur.

## Jamais essayé sur les Mac
- Essayé sur l'iMac le 11.11.2026 (R1) : `python3 lancer.py tests` avec les paquets de `requirements.txt` sans `faster-whisper` : 709 réussies, 0 ratée, 30 sautées. Tout le reste de cette liste reste vrai (modèles, yeux, voix du Mac, MacBook : pas essayés).
- `preparer_mac.sh` : seulement lancé sur Linux, en mode essai (les parties Mac sont sautées).
- `outils/mesurer.py` : mesures llama.cpp, MLX, whisper.cpp, mlx-whisper, sherpa-onnx jamais lancées.
- `requirements-mac.txt` : versions relevées sur PyPI, jamais installées sur Mac.
- Installation de llama.cpp par Homebrew ou par GitHub : jamais essayée.
- Les sons d'essai par la commande `say` : les noms de voix macOS sont **à vérifier**.
- Voix Piper hors chinois : sherpa-onnx 2.x n'inclut plus espeak-ng ; il faudrait l'ajouter (GPL-3.0, décision de Hiba).

## Voix (étape 2) : testé sur Linux seulement
- Écoute mlx-whisper et whisper.cpp : écrites d'après leur documentation, jamais lancées.
- Voix du Mac (`say`) : jamais lancée ; noms des voix **à vérifier** sur chaque Mac.
- Vrai micro et vrai haut-parleur (`sounddevice`) : jamais essayés. `python3 lancer.py micro` testé seulement avec `--fichier`.
- Bouton « 🎙 Je parle » de la page web : jamais essayé dans un navigateur (le serveur `/api/je_parle` est testé).
- Filtre d'écho (le robot ignore sa propre voix) : testé avec une écoute factice, pas avec un vrai haut-parleur.
- Interruption avec un vrai haut-parleur : le robot peut s'entendre lui-même ; **à mesurer** (casque conseillé).
- Ordres courts : testés avec une voix SYNTHÉTIQUE chinoise ; les vraies voix (FLEURS) sont des phrases longues.
  Les ordres dits par de vraies personnes : à enregistrer (`python3 lancer.py enregistrer`).
- Suisse allemand : aucune vraie voix testée.

## Cerveau (étape 3) : testé sur Linux seulement, avec Apertus 0,5B
- Apertus 8B : lancé sur l'iMac le 12.11.2026 (clinique, R2 : `python3 lancer.py apertus-essai`, résultat dans `docs/projet/MESURE_APERTUS.md`). Apertus 4B : jamais lancé (ni ici, ni sur Mac). `outils/banc_cerveaux_mac.py` jamais lancé.
- llama.cpp sur Mac (`llama-server`), mlx-lm (`mlx_lm.server`, formulaire vérifié) : jamais lancés.
- Apertus par Internet (CSCS) : jamais appelé depuis ce projet (pas de clé ici).
- Lancement « au besoin » du 4B, et son arrêt quand le 8B revient : testés avec un faux serveur (objet qui joue le serveur), pas avec deux vrais modèles.
- Deux Mac (cerveau sur l'iMac) : jamais essayé.

## Voix : ce qui ne marche que sur Mac
- **La voix du Mac (`say`) ne marche que sur un Mac.** Sur un autre ordinateur, seules les réponses en chinois sont
  dites (Piper) ; les autres s'affichent en sous-titres. L'option Piper GPL (éteinte) marcherait partout.
- Option Piper GPL (`requirements-piper-gpl.txt`, `voix_piper_gpl.py`) : jamais installée ni lancée.
- Essai suisse allemand Flix-AI (`outils/essai_suisse_allemand.py`) : jamais lancé (Mac seulement).

## Chef de démonstration (brique 15) : testé sur faux robot seulement
- Jamais avec un vrai robot, ni sur les Mac, ni avec la vraie cascade Apertus (panne réseau testée avec un cerveau
  « en ligne » factice).
- La voix est simulée (phrase donnée à la chaîne) ; `lancer.py scenario` n'a ni écran ni voix : annonces au terminal.
- Main humaine : opérateur simulé (répétition, compté à part) ou écran (brique 11, seulement dans un test).
- Durée du scénario de trois minutes : mesurée une seule fois à ×1 (174,81 s), sur Linux, faux robot, cerveau à règles.

## Kit du samedi matin (brique 17) : hors ligne, jamais sur un vrai défi
- Mots-clés essayés sur trois faux défis inventés (fr, de, en) ; un défi écrit en italien serait mal lu.
- Phrases du brouillon de scénario : jouées par le chef sur le faux robot, cerveau à règles seulement (ni Apertus, ni la voix).
- Skill `lire-le-defi` : jamais lancée dans une session de l'assistant de code (seul son format est testé).
- Heures du programme de 48 h : proposition, heures officielles du Carnival **à vérifier**.

## Gardien, doute (briques 7, 8) : testé sur faux robot seulement
- Position du robot et personnes simulées ; jamais avec de vraies positions ni de vrais yeux.
- Chemin en ligne droite : un vrai robot qui contourne les obstacles peut passer ailleurs (à vérifier par robot).
- Chien de garde « programme figé » : simulé ; sur un vrai robot, c'est celui du fabricant (à vérifier dans chaque kit).
- Boutons de l'écran pour la main levée et les règles : API testée, page web pas encore faite.
- Phrases nouvelles en de, it, zh : écrites par l'agent, à faire relire.
- Distance aux personnes : vérifiée seulement AU DÉPART d'une action, pas pendant. Une personne qui s'approche pendant
  un trajet ou un geste n'arrête pas le robot ; seuls « stop », l'arrêt d'urgence et le chien de garde l'arrêtent.
- Zones et personnes : mesurées depuis le corps du robot (sa position x, y), pas depuis la main ni l'objet tenu.
  Un bras qui se tend peut aller plus près d'une personne, ou plus loin dans une zone, que ce que dit la règle.
- Code d'équipe : il reste gardé dans le navigateur du grand écran (`localStorage`). Quelqu'un qui touche cet écran
  peut appuyer sur « Réarmer » sans le retaper. À faire : redemander le code pour Réarmer.

## Écran du jury (brique 13) : testé avec Chromium sur Linux seulement
- Jamais sur le grand écran ou le projecteur du Carnival, ni sur Safari, ni sur iPad, ni sur un Mac. « Lisible de loin » : non mesuré.
- « Internet coupé » : ne coupe que ce programme Python (pas le navigateur ni le reste du Mac) ; testé sur Linux.
- Mode silence avec un vrai haut-parleur : jamais essayé.
- Exemples du flux `etat_robot`, `pilotage_humain`, `mot_d_appel`, `interruption` et ceux des briques 7, 8, 15 :
  forme relevée dans le code, valeurs d'exemple.

## Adaptateurs (brique 3) : testé sur faux robot seulement
- Aucun vrai robot, aucun vrai kit (Unitree, AGIBOT, Flexiv), ROS 2 jamais installé : liaisons essayées avec le faux kit
  et le faux ROS 2 seulement. Tous les appels des ébauches sont « à brancher ».
- Chien de garde du fabricant : simulé. Unitree G1 : `Move()` envoie 1 s (lu dans le code, jamais essayé) ; Go2, AGIBOT,
  Flexiv : inconnu. Fil réservé à l'arrêt d'urgence : un vrai kit accepte-t-il deux appels en même temps ? À vérifier.
- Kits sur Mac : jamais essayés. Pages officielles non lues (support.unitree.com, docs.nvidia.com) : à vérifier.
- Skill `brancher-un-robot` : jamais lancée dans une session de l'assistant de code. Chronomètre « robot inconnu » : terminal seulement.
- Course « ordre en route / arrêt » : corrigée et essayée avec le faux kit seulement (latence simulée) ; un vrai kit
  peut avoir d'autres chemins (plusieurs canaux, réessais) : à vérifier. Plusieurs fils d'arrêt à la fois : à vérifier par kit.
- Garde du trajet : seulement avec un odomètre ; marges (5 cm, 15 cm) jamais essayées sur un vrai robot (à mesurer).

## Porte des agents (brique 14) : testé sur faux robot seulement
- Jamais dans une vraie session de l'assistant de code : client essayé = celui du SDK `mcp` 2.3.0. Enregistrement dans l'assistant de code :
  pas fait (feu orange, réglage de Hiba). Jamais sur Mac, jamais avec Apertus ; plusieurs agents à la fois : non testé.

## Les yeux (brique 5) : caméra simulée seulement
- Aucune vraie caméra (USB, flux du robot, kit du fabricant). MediaPipe jamais lancé (Linux du nuage sans libEGL) : la
  détection de vraies personnes et d'objets est inconnue. Calibration avec de vrais marqueurs : jamais faite.
- Personnes aux jambes cachées, dans la foule, de dos, assises : jamais essayé. RapidOCR : accents, allemand, chinois.
- Zone vue avec une vraie caméra et un vrai objectif : jamais mesurée ; ce qui est caché derrière un objet compte
  encore comme vu ; caméra fixe (repère du monde) jamais essayée en vrai.
- Sur Mac : ni installé, ni mesuré.

## La main humaine (brique 11) : testé dans Chromium sur Linux seulement
- Jamais sur une vraie tablette, ni Safari, ni iPad, ni Mac ; jamais avec un vrai robot ni la vraie voix.
- `OperateurEcran` du chef : testé seulement dans un test ; pas de commande. Visite à distance (idée 13) : pas faite.
- Arrêt envoyé en prenant la main : sur un vrai robot, qu'il arrête aussi une action en train de démarrer est à vérifier
  dans chaque kit (sur le faux robot : elle roule environ le temps de réponse du robot, puis s'arrête). Jeton gardé dans
  le navigateur de la tablette : jamais essayé sur Safari / iPad.

## La clinique en boîte
- Le faux dossier (`briques/clinique/faux_dossier`) : inspiré de FHIR, non validé ; aucun lien avec un vrai logiciel de clinique n'a été essayé.
- Les textes des documents inventés en italien, allemand, anglais et portugais : écrits par l'agent, pas relus par quelqu'un qui parle la langue.
- Les documents existent en texte seulement : les images ne sont pas encore fabriquées.
- La porte de lecture (`briques/clinique/porte.py`) : on entre en choisissant un badge. Ce n'est pas un vrai contrôle d'identité : pas de mot de passe, n'importe qui peut prendre n'importe quel badge.
- Le cerveau lit par la porte avec l'outil `lire_dossier` : essayé avec un client MCP en mémoire seulement, jamais avec Apertus ni dans une vraie session d'agent. La commande `porte-agents` ne le propose pas encore.
- Les écrans de la clinique (`briques/clinique/ecrans.py`) : essayés depuis l'iMac lui-même, par son adresse du Wi-Fi, et vus dans un navigateur à la taille d'un téléphone. Jamais ouverts depuis un vrai téléphone ni depuis le MacBook. Le Wi-Fi du lieu peut empêcher les appareils de se voir.
- Les mots des écrans en allemand, italien et anglais : écrits par l'agent, pas relus par quelqu'un qui parle la langue. Le programme et les titres des documents restent dans la langue du faux dossier (français).
- Hors des listes de soin, les écrans ne font que montrer : pas de plan « où dois-je aller ? », pas de questions pour le médecin, pas de bouton « un humain, s'il vous plaît » (tâches suivantes). Pas de flux en direct : seulement la mise à jour toutes les deux secondes.
- N'importe qui sur le même Wi-Fi peut ouvrir les pages de la clinique et le journal des accès, sans code. Acceptable seulement parce que tout est inventé.
- Les listes de soin (`briques/clinique/listes.py`, `carnet.py`, `ecrans_listes.py`) : essayées par des tests, et les boutons dans un navigateur sur l'iMac, à la taille d'un téléphone (clics lancés par l'agent). Jamais sur une vraie tablette, jamais par une soignante, jamais à la voix. Les trois listes sont des exemples inventés, non médicaux.
- Sur le même Wi-Fi, n'importe qui peut prendre un badge et cocher un point : pas de code, pas de contrôle d'identité.
- La fin de poste montre tous les points qui restent (21 pour l'étage 2 au départ) : c'est long sur un téléphone ; pas essayé avec un vrai soignant.
- Les noms courts et les mots proches des points de liste : écrits par l'agent, pas relus ; jamais essayés à la voix.
- L'accueil et le thérapeute ne peuvent pas encore cocher leurs points : la porte ne leur montre pas les listes prévues d'une personne.
- Le carnet n'est pas encore relu au démarrage : si le programme redémarre, les coches de la séance ne reviennent pas à l'écran (elles restent dans le fichier, si on en a demandé un).
- La demande au robot (`briques/clinique/taches.py`, `coursier.py`) : **testé sur faux robot seulement**. Aucun vrai robot n'a fait cette course. Le faux robot n'a pas de physique : pas d'obstacle, pas de porte, un objet « pris » ne peut pas tomber. Essayé par des tests, et une fois avec le vrai serveur (30 secondes pour livrer un coussin).
- Le plan du robot (`monde_clinique.yaml`) : positions inventées, dans une halle de 10 m × 6 m. Rien n'est mesuré dans une vraie salle.
- Après un échec en cours de route (objet déjà en main, par exemple), le robot reste là où il est, avec l'objet : pas de retour à la réserve, pas de nouvel essai.
- Si le gardien demande l'accord d'un humain pendant une course, la tâche échoue : l'accord à l'écran n'est pas branché pour les courses de la clinique.
- La demande est comprise par des mots simples, en français seulement. Pas essayée à la voix, ni en allemand, ni avec des phrases longues ou des fautes.
- Personne ne reçoit encore les tâches « pour un humain » : elles s'affichent seulement sur l'écran du soignant.
- Le résumé du médecin (`briques/clinique/resume.py`) : version simple, par des règles, **aucun modèle**. Essayé par des tests et par la page demandée par le programme ; pas sur une tablette, pas lu par un médecin.
- Le contrôle des chiffres du résumé est simple : il vérifie que chaque suite de chiffres est dans une source, et qu'une date citée y est écrite telle quelle. Il ne voit pas deux chiffres échangés, ni un nombre écrit en lettres, ni une phrase fausse sans chiffre. Suffisant pour des phrases faites par des règles ; pas pour un modèle (T13). **[Rappel du tour 73 (H04, réponse de Hiba à Q11) : ce contrôle simple est gardé tel quel pour la version par règles. Sa limite : il compare des suites de chiffres, il ne comprend ni les unités, ni l'ordre, ni les nombres écrits en lettres. Le verrou des chiffres de l'ossature ne sert pas ici : il ne lit que vitesse, distance et force.]**
- « Deux sources ne sont pas d'accord » vient d'un champ écrit à la main dans le faux dossier (`faits`), pas d'une lecture du texte. Une même date écrite de deux façons (« 20 novembre », « 20.11. ») donnerait un faux désaccord.
- « Ce qui attend une décision » ne contient que ces désaccords. « Ses questions » reste « rien de nouveau » tant que les questions du soir (T19) n'existent pas ; la règle est essayée avec une question écrite par un test.
- La mention « je prépare… » n'est pas à l'écran : un résumé refait affiche « Refait : … ».
- La recherche d'un document : par des mots simples, en français. La phrase du cahier « le dernier rapport de radiologie de Madame B. » répond « Je ne trouve pas ce document » : elle n'a pas ce document. Les documents n'ont pas de date : « le dernier » n'est pas compris.
- Le résumé est en français seulement, même sur l'écran allemand du médecin.
- Les papiers (`briques/clinique/papiers.py`) : version simple, par des règles, **aucun modèle, aucune image**. Le « papier » est un texte déjà tapé. Essayé par des tests et par la page demandée par le programme ; pas sur une tablette, pas par une personne de l'accueil.
- Le type d'un papier est reconnu par quelques mots (français, allemand, italien), écrits par l'agent et pas relus. La liste des endroits du dossier est inventée. Un papier d'un type inconnu qui contient deux de ces mots serait mal classé avec une confiance « haute ».
- La confiance n'est pas une mesure : c'est une règle (un patient, un type, un texte tapé). « À la main » vient d'une note du faux dossier, pas d'une lecture du papier.
- La date proposée est la première date trouvée dans le texte : ce peut être une date de naissance. Elle n'est pas contrôlée (« 31.02. » passerait). « 1er mars » n'est pas reconnu.
- L'auteur proposé est la première ligne si elle contient « Exemple » : elle peut contenir aussi le titre du papier.
- Le patient est cherché parmi les arrivées du jour, par « prénom + initiale ». Une lettre pour quelqu'un d'autre, avec « copie à Giulia B. », serait proposée chez Madame Giulia B.
- Un papier « à trier » ne peut pas encore être rangé à la main : il attend. L'humain ne peut corriger que le type, pas le patient, la date ou l'auteur.
- La porte de lecture donne à l'accueil le texte entier des papiers ; seule la page des papiers le coupe aux deux premières lignes.
- Si le programme redémarre, les propositions sont refaites et les validations de la séance ne reviennent pas à l'écran (le carnet n'est pas relu au démarrage).
- L'accueil du hall (`briques/clinique/accueil.py`) : version écrite. La phrase est **tapée au clavier**, la réponse s'affiche : aucune voix, aucun robot, aucun visage. Essayé par des tests ; le petit programme de la page `/clinique/hall` (ce qui s'affiche après « Dire ») n'est essayé par aucun test, et pas sur une tablette.
- Pas de preuve d'identité dans le hall : quelqu'un qui tape « je suis Giulia B. » reçoit la chambre de Madame Giulia B. Le cahier demande seulement que la personne dise son nom.
- Le nom dit dans le hall, resserré le 14.11.2026 (essayé sur des phrases tapées, deux relectures) : après le prénom, il faut l'initiale seule, ou un nom écrit avec une majuscule au milieu d'une phrase, qui n'est ni un mot courant ni un mot de santé. Reçoivent ENCORE la chambre sans être la personne : la demande d'un visiteur faite de mots permis (« Frau Giulia B., bitte », « Madame Giulia B. », « C'est Giulia B. »), une question dite sans « ? » (« Ist Giulia B. »), un mot inconnu avec une majuscule (« Is Giulia Better », « Giulia Blumen »). Le prix : un vrai nom tapé sans majuscule (« giulia bianchi ») appelle un humain. À la voix, les majuscules viennent de l'écoute : pas mesuré avec de vraies voix.
- L'espagnol dans le hall (14.11.2026) : huit mots permis autour du nom (« Buenos días, soy Giulia B. ») ; « Me llamo… » et « Mi nombre es… » appellent un humain par prudence. Phrases écrites par l'agent, PAS RELUES (docs/projet/RELECTURE_ESPAGNOL.md). La règle sur la santé n'a aucun mot espagnol. L'écoute de l'espagnol à la voix n'a jamais été mesurée ; la voix espagnole du Mac a été relevée sur le MacBook seulement.
- Les phrases allemandes, italiennes et anglaises du robot sont écrites par l'agent, pas relues par quelqu'un qui parle la langue.
- La langue d'une phrase tapée est devinée par une liste de mots courants. Mesuré par le relecteur sur 16 arrivées par langue, avant l'ajout de mots : 11 à 14 reconnues ; les autres tombent en « français, pas sûr », jamais dans une mauvaise langue. Pas remesuré après.
- Une arrivée dite avec des mots en plus (« je suis Giulia B., j'ai une réservation ») n'est pas une « simple arrivée » : le robot appelle un humain. C'est voulu (prudence), mais le jury peut tomber dessus.
- La règle « rien sur la santé dans le hall » est une liste de mots dans `accueil_hall.yaml`. Elle ne voit pas toutes les questions de santé (celles qu'elle manque appellent quand même un humain), et elle prend parfois une phrase banale pour une question de santé (« Krankenkasse » non, mais « health insurance card » oui). Elle n'est pas dans le gardien de l'ossature.
- Un prénom écrit autrement que dans le faux dossier n'est pas reconnu autrement que sans accent (« Andre » pour « André » marche ; un diminutif, non).
- Le robot dit la première heure du programme du jour, même si elle est déjà passée.
- Personne ne peut encore fermer un appel du hall : il reste affiché sur l'écran de l'accueil.
- Le scénario de la clinique (`briques/clinique/scenario_clinique.yaml`, `chef_clinique.py`) : sept scènes, jouées par la grande répétition. Essayé par des tests et par la commande, sur l'iMac. Jamais joué devant des personnes, jamais chronométré : « cinq minutes » n'est pas mesuré.
- Le plan B d'une scène est une **consigne affichée** (qui fait quoi). Le programme ne le joue pas, et aucun plan B n'a été essayé avec une personne.
- Le chef de démonstration de l'ossature (brique 15, `lancer.py scenario`) ne joue pas ces scènes : il ne connaît que les phrases dites au robot. Le scénario de la clinique reprend ses quatre mots (tablette, main_humaine, mode_local, sauter) et ses phrases, rien de plus.
- Dans la répétition, chaque étape repart d'une clinique neuve : les scènes ne s'enchaînent pas dans une seule séance (la patiente arrivée à la scène 1 n'est pas « la même » à la scène 3). L'heure affichée est celle du scénario ; les pièces de chaque étape ont leur propre horloge.
- Les annonces des scènes (phrases pour la personne qui présente) sont écrites par l'agent, en français seulement ; elles ne sont ni dites ni affichées par la répétition.
- La grande répétition dit « RÉUSSIE » depuis le 12.11 : **en version simple seulement**. 13 étapes sur 14 sont SIMULÉ (gestes des personnes faits par le programme, tout tapé, aucune voix, aucun modèle), 1 est FAUX ROBOT. Aucune étape n'a été faite par un vrai robot, ni jouée par une personne. Essayée sur l'iMac seulement.
- La fiche de vérité de la répétition (`fiche.py`) : version simple. Elle s'écrit dans la sortie de la commande ; elle n'est ni dans la boîte noire, ni sur un écran, ni dite à voix haute (T27). Deux lignes sur sept sont « non mesuré » : lecture des papiers, voix. **[Corrigé au tour 68 : les sept lignes du cahier sont maintenant mesurées sur cet ordinateur (lecture et voix depuis R3 et R4), et cinq lignes du cerveau s'y ajoutent.]**
- « Part de l'humain » compte seulement les étapes portant l'étiquette JOUÉ. Elle ne mesure pas encore les aides humaines pendant une vraie démonstration (avenant 2, K02).
- « Temps accéléré : oui (5 sauts) » compte l'horloge d'affichage du scénario. Les pièces ont chacune leur horloge : dans la répétition, les étapes 1 à 8 et 12 se jouent à « jour 1, 9 h 00 » dans leur carnet, quelle que soit l'heure affichée de la scène.
- Une question de santé posée le soir par la patiente part chez le médecin (ligne au carnet, résumé) ; le prototype ne répond pas. Mais il ne crée pas de « tâche pour un humain », comme le cahier 2.6 le demande (question Q15).
- Une tâche écrite pour un métier (dictée) n'est lue que par ce métier et par le médecin. Si aucun badge de ce métier ne suit le patient, elle ne s'affiche nulle part : le prototype le dit au médecin, rien de plus.
- `/clinique/patient/soir` ouvert sans badge prend le premier badge de patient (comme les autres écrans) : pas de contrôle d'identité.
- « Phrases retirées faute de source » : 0 dans la répétition. Le compte vient du résumé fait par des règles ; il n'a jamais été essayé avec un modèle (T13).
- « Données inventées : oui » veut dire : le faux dossier se charge, et il refuse de se charger sans la marque « inventé ». Personne n'a relu chaque fiche.
- « Rien n'est sorti de l'ordinateur » (`rien_dehors.py`) : pendant la répétition, les essais de connexion de **ce programme** (portes réseau de Python : connexion, envoi direct, recherche d'un nom ou d'une adresse — neuf portes, listées dans `rien_dehors.py`) sont comptés et bloqués. Si une pièce retire une de ces portes, l'étape 14 rate. Non couvert : un autre programme lancé à côté (serveur de modèle, navigateur), un outil qui n'utilise pas ces portes, et **la démonstration avec les écrans** (`python3 lancer.py`), où cette surveillance ne tourne pas. Aucune mesure sur le réseau lui-même (pas d'écoute du câble ou du Wi-Fi).
- La flotte (`briques/clinique/flotte.py`) : version simple. R2, R3, R4 sont **simulés** : le programme écrit leurs états dans le carnet, rien ne bouge, ils n'ont pas de position. Seule la reprise par R1 est **testée sur faux robot** (coursier, gardien). Jamais sur un vrai robot.
- La panne est toujours provoquée, par le programme. Aucun bouton à l'écran pour la provoquer ou lancer la reprise : en démonstration, la scène 6 ne peut pas encore être jouée à la main.
- Les cartes de rôle (Étage, Thérapie, Nuit) sont affichées, pas appliquées par le gardien. R1 affiche toujours « Étage » : le changement de carte entre la scène 1 et la scène 3 n'existe pas encore.
- La reprise ne choisit pas : c'est toujours le robot branché (R1). Pas de « plus proche », pas de batterie. Un robot en panne ne peut pas être réparé à l'écran.
- La course reprise repart de la réserve : on ne sait pas où l'objet était quand le robot simulé est tombé en panne.
- La page `/clinique/flotte` : demandée par le programme, jamais regardée sur une tablette. Elle n'a pas de badge : tout le monde sur le réseau local la voit (elle ne montre aucun nom de patient, mais elle montre l'objet et la chambre).
- Le soir et la dictée (`briques/clinique/soir.py`) : version simple, **tout est tapé**. Aucune voix, aucun modèle. Essayé par des tests et par les pages demandées par le programme ; jamais par une patiente ni par un médecin, jamais sur une tablette.
- Les questions du soir : **seules les deux questions du scénario sont traduites**, par un fichier de traductions fixes (`traductions_scenario.yaml`), pas par un modèle. Toute autre question arrive chez le médecin dans la langue de la patiente, marquée « non traduite ». Aucune traduction faite par Apertus n'a été essayée (le modèle n'est pas sur l'iMac).
- Les deux questions du scénario en italien (« Quando potrò camminare senza deambulatore? », « Mia figlia può venire domenica? ») et les phrases de l'écran du soir (italien, allemand, anglais) sont écrites par l'agent, pas relues par quelqu'un qui parle la langue.
- Le prototype ne trie pas les questions : toute question tapée le soir part chez le médecin telle quelle, et reçoit toujours la même phrase (« transmise au médecin »). Une patiente peut en envoyer autant qu'elle veut.
- Pas de preuve d'identité : qui ouvre l'écran avec le badge de la patiente écrit en son nom (comme pour tous les badges).
- La dictée : le premier mot avant la virgule dit pour qui (« Physio, … » → thérapeute), d'après une liste courte inventée. Un autre premier mot envoie la tâche à l'équipe de soin, en le disant. « Demain » devient « jour suivant » ; aucune autre date n'est comprise.
- Le brouillon de la dictée et la tâche ne peuvent pas encore être corrigés, validés ou fermés à l'écran. Le thérapeute voit la tâche ; il ne peut pas dire « fait ».
- La page de la patiente se met à jour toutes les deux secondes : à 19 h la question apparaît seule, mais personne ne l'a regardée apparaître sur une vraie tablette.
- Les essais comptés (`python3 lancer.py essais`) : 20 sur 20 le 12.11, sur l'iMac, **faux robot et simulé, aucun modèle, aucun vrai robot**. Seules les étapes 1 (langue), 7 (point oublié) et 8 (objet) changent d'un essai à l'autre ; les onze autres rejouent vingt fois le même contrôle, sans hasard : leur « 20 sur 20 » ne dit rien de plus qu'un seul passage.
- Dans ces essais, « cerveau plus lent » n'a aucun effet (aucune pièce de la version simple n'appelle le cerveau), et l'option `--apertus` ne joue rien. Le tableau avec le vrai Apertus : non mesuré.
- Les phrases d'arrivée des essais (allemand, français, anglais, italien) sont de « simples arrivées » écrites par l'agent ; une personne qui parle autrement n'est pas dans la liste (les demandes tirées au hasard : avenant 2, K01).
- Le tableau des essais s'écrit dans la sortie de la commande et dans `journal/essais_dernier.json` ; il n'est pas encore sur un écran ni dans la fiche de vérité de la répétition (J01b, J07, T27). 
- Le compteur d'essais réels (`/clinique/essais-reels`) : essayé par des tests, avec un fichier d'essai effacé ensuite. **Aucun essai réel n'a été compté** : le vrai fichier n'existe pas. La page n'a jamais été utilisée par une personne, ni avec un vrai robot, ni sur un téléphone.
- Le compteur fait confiance à la personne : rien ne vérifie qu'un vrai robot a fait le geste. Sur l'ordinateur-cerveau lui-même, les boutons marchent sans code d'équipe (réglage `ecran.local_sans_code`) : un programme ou un agent d'IA qui tourne sur cet ordinateur pourrait appuyer. Mettre `local_sans_code: false` avant de compter pour de vrai.
- Le fichier des essais réels peut être modifié à la main avec un éditeur : rien ne le scelle. Une ligne abîmée est comptée comme « illisible » et dite.
- Les quatre pannes de l'avenant sont construites, toutes **SIMULÉ**. Dans la version simple, le « cerveau » est fait de règles, sans modèle, et aucune pièce de la clinique n'écoute un micro : « le cerveau ne répond plus » fige le résumé, la proposition de rangement et les demandes au robot ; « le micro n'entend que du bruit » rend du bruit à qui demande ce que les oreilles ont entendu. Avec le vrai Apertus et la vraie voix (T13 à T20), ces deux pannes seront à rejouer : **non testé avec un vrai modèle ni un vrai micro**.
- Pendant « cerveau muet » et « micro », le robot attend même une demande faite au doigt (choix prudent, écrit dans l'avenant : « il ne commence rien de nouveau »). À discuter avec l'équipe : pour le micro, on pourrait laisser passer les demandes tapées.
- Pour ces deux pannes, l'arrêt en pleine course n'est pas essayé (il l'est pour le lien) : on vérifie seulement que l'arrêt normal est demandé à la prise.
- Cerveau muet : le hall (accueil écrit) et la dictée continuent avec leurs règles ; ils ne sont pas figés. La page des papiers ne montre pas encore la phrase « n papiers sans proposition » (elle est dans les données).
- Les pannes provoquées (`briques/clinique/pannes.py`) : la première, « le lien tombe entre le cerveau et un robot ». **Testée sur faux robot** ; la panne elle-même est SIMULÉ (le programme coupe la liaison du faux robot). Jamais essayée sur un vrai robot, ni en coupant un vrai Wi-Fi.
- Pendant cette panne, « le robot s'arrête là où il est » vient du chien de garde du faux robot (brique 2) et de la prise. Sur un vrai robot, cela dépendra de son adaptateur : non testé. En pleine course, la prise déclenche l'arrêt d'urgence : la tâche attend qu'un humain réarme, puis qu'il appuie sur « Relancer ». Rien ne repart tout seul après un arrêt d'urgence, c'est voulu.
- Une course interrompue repart de la réserve : on ne sait pas où est l'objet si le robot l'avait déjà pris.
- Le bandeau de panne s'affiche en deux secondes au plus sur les pages qui se mettent à jour seules. Il ne s'affiche PAS sur les pages à formulaire (hall, question du soir, dictée, essais réels), ni sur une tablette qui a perdu le lien (J02b). Le délai « moins de cinq secondes » n'a été mesuré sur aucun vrai écran.
- « Qui est prévenu » : le bandeau sur les écrans, c'est tout. Personne n'est appelé, aucun son.
- La commande `python3 lancer.py pannes lien_robot` joue la panne dans son propre programme, sur un faux robot neuf : elle ne provoque rien sur une démonstration en cours (pour cela : la page `/clinique/pannes`).
- La page « Pannes » : demandée par le programme, jamais utilisée par une personne.
- La panne de la tablette est **SIMULÉ** : le programme répond « lien coupé » aux échanges de la page de liste déjà ouverte (elle se signale par « X-Tablette »). Le vrai Wi-Fi n'est pas coupé. Une page rechargée pendant la panne se rechargerait normalement. **Jamais essayé en coupant vraiment le réseau, ni sur une vraie tablette, ni sur un téléphone.**
- La tablette hors ligne : essayée une fois dans le navigateur intégré de l'agent, sur l'iMac (deux coches hors ligne, bandeau « HORS LIGNE », envoi au retour) ; la file est essayée par un test avec Node. Aucun essai dans Safari ou sur iPad. Si Node manque sur une machine, le test de la file est sauté.
- Hors ligne, seules les **coches** sont gardées et renvoyées. « Je sors », les trois choix de fin de poste et les demandes au robot ne sont pas mis en file : la tablette dit que le geste n'est pas enregistré. La page de fin de poste n'a pas de mode hors ligne.
- Une coche faite hors ligne s'affiche, après le retour, avec l'heure où elle est ARRIVÉE ; l'heure où elle a été faite (celle de la tablette, pas contrôlée) est dans le carnet seulement.
- La file est gardée dans le navigateur de la tablette (par badge). Si on vide le navigateur, ou si une autre personne coche le même point entre-temps, la coche renvoyée ne compte pas double, mais rien ne le dit à l'écran.
- La page « Moments » (`briques/clinique/moments.py`) : essayée sur une séance fabriquée pour l'essai, et sur des lignes de carnet écrites par les vraies pièces (papiers, résumé, demande). **Jamais sur une vraie démonstration, ni avec un vrai robot.** Les moments venus de l'ossature (refus du gardien, arrêt d'urgence, « je ne suis pas sûr » de la brique 8, main humaine) sont lus d'après la forme de leurs événements ; seul le refus du gardien est essayé, avec un événement écrit à la main.
- Elle lit deux fichiers : la boîte noire et le carnet de la clinique (pas encore recopié dans la boîte noire : T27). Pour une séance passée, le carnet est retrouvé par l'heure du lancement, à dix secondes près : si deux programmes ont été lancés en même temps, elle peut se tromper de carnet, ou n'en trouver aucun (elle le dit).
- Les heures sont les heures réelles de l'ordinateur (UTC), pas l'heure de la démonstration. Deux lignes écrites dans la même milliseconde peuvent s'afficher dans le mauvais ordre.
- « Ce que le système a vu ou entendu » : seulement ce qui est écrit dans la séance. Pour un échec de course, c'est la demande ; il n'y a pas d'image ni de son. Quand rien n'est écrit : « pas noté dans la séance ».
- « Erreurs attrapées » compte : refus du gardien, « je ne suis pas sûr », reprise par un humain, papier non rangé, arrêt d'urgence. Une panne provoquée et un échec ne sont pas comptés. Ce choix est de l'agent : à relire avec l'équipe.
- La page demande le code d'équipe par un en-tête : depuis un autre ordinateur, un navigateur ne peut pas l'ouvrir. Elle s'ouvre sur l'ordinateur-cerveau (réglage `local_sans_code`).
- Le lien « moment » écrit dans le tableau des essais est une adresse à ouvrir sur le serveur des écrans ; la commande des essais ne l'ouvre pas elle-même.
- Le robot à plateau (carte `plateau.yaml`, `coursier.py`) : **testé sur faux robot**. Tous les chiffres de la carte sont inventés, « à vérifier ». Jamais essayé avec un vrai robot à roues.
- Sur le faux robot, l'objet ne voyage pas vraiment sur le plateau : le programme ne sait pas si l'humain l'a posé ou repris, il croit la personne qui appuie sur « C'est fait ». Dans la répétition et les essais, ces deux appuis sont faits par le programme.
- Le robot attend l'humain 120 secondes, puis la tâche est « échouée » (il reste où il est). Ce délai est choisi par l'agent. Rien ne rappelle l'humain entre-temps.
- La demande du robot est dite en français seulement (« Posez … sur mon plateau, s'il vous plaît. »), même si la personne parle une autre langue.
- Le bouton « C'est fait » est sur l'écran du soignant seulement ; essayé par le programme, jamais par une personne.
- Avec un robot sans bras, la reprise d'une course après une panne (J02) n'est pas essayée.
- La commande `brancher-carte` : **faux robot seulement**. Elle prouve qu'une carte d'identité passe le test de conformité de la prise avec le faux robot du projet ; elle ne dit rien d'un vrai robot ni de son adaptateur. « Brancher un robot inconnu — RÉEL » reste « à mesurer avec le vrai robot ».
- Le chronomètre mesure le temps entre « je commence » et le premier test réussi. La mesure faite par l'agent le 12.11 porte sur une carte déjà écrite : elle ne mesure pas le temps de lire la doc d'un robot et d'écrire sa carte. Une vraie mesure : une personne de l'équipe, une carte neuve, montre en main.
- Les conseils « à corriger : … » sont écrits par l'agent, un par contrôle du test ; ils n'ont été essayés que sur des échecs fabriqués pour l'essai.
- Une carte doit être dans le dossier des cartes du faux robot (`briques/b02_faux_robot/cartes/`) : la commande refuse un fichier placé ailleurs.
- La parole des soignants : **aucun soignant n'a été rencontré, aucune parole n'est recueillie**. Le guide d'entretien (`docs/projet/GUIDE_ENTRETIEN.md`) n'a jamais servi. La page « Ce qu'on nous a dit » ne lit aucun fichier : elle dit toujours « Aucune parole recueillie » (version simple, en attendant la réponse à Q7).
- L'étiquette HYPOTHÈSE est posée sur la page d'une liste de soin et sur la page « Ce qu'on nous a dit ». Les autres écrans qui décrivent le travail des gens (habitudes, fin de poste, résumé du médecin, accueil) ne la portent pas encore.
- Le rangement proposé par le cerveau (T14, `proposer_avec_cerveau`) : essayé avec un **cerveau de test à réponses fixes** seulement. **Jamais avec le vrai Apertus** (le modèle n'est pas sur l'iMac : R2, Q17). Aucun branchement vers Apertus n'est écrit pour les papiers : dans les écrans lancés aujourd'hui, la proposition vient des règles simples, et la page le dit. **[Corrigé au tour 68 : depuis H06a, mesuré avec le vrai Apertus (2 sûrs sur 9). Toujours vrai : dans les écrans, ce sont les règles simples qui proposent.]**
- Les verrous du rangement vérifient que la date et l'auteur sont recopiés tels quels du papier ; ils ne vérifient pas que c'est la BONNE date ou le bon auteur (une date de naissance recopiée passerait). Le patient est décidé par la règle « prénom + initiale écrits sur le papier », pas par le cerveau.
- « Confiance haute » du cerveau n'est pas une mesure : c'est ce que le cerveau dit de lui-même, abaissée dès qu'un verrou ou les règles ne sont pas d'accord. Avec un vrai modèle, le taux d'erreur du rangement est à mesurer.
- Lire une image (`briques/clinique/lecture_mac.py`, lecture de texte du Mac) : essayé sur l'iMac seulement, sur des **images fabriquées par le programme** (texte inventé, tapé, noir sur blanc, bien droit) : 0,0 % d'erreur sur quatre lignes. **Jamais sur une photo d'un papier, jamais sur de l'écriture à la main, jamais sur une image avec « INVENTÉ » en travers.** Le taux d'erreur sur les documents du faux dossier : T15.
- La lecture du Mac a besoin d'un Mac et, la première fois, du compilateur Swift (Xcode) : présent sur l'iMac, **à vérifier sur le MacBook M2**. Ailleurs, la pièce dit qu'elle ne sert pas, et ses essais de lecture sont sautés.
- « La lecture se fait sur l'ordinateur » : c'est ce qu'Apple dit de cette fonction ; nous n'avons pas écouté le réseau pour le vérifier (à vérifier). La surveillance « rien ne sort » de la répétition ne voit pas ce petit programme (il tourne à côté).
- Langues demandées à la lecture : français, allemand, italien, anglais. Le portugais du faux dossier (p11) n'est pas demandé : non essayé.
- Lire les papiers depuis une image (T15) : **1,7 % d'erreur sur sept images FABRIQUÉES par le programme** (texte inventé, dessiné net, noir sur blanc, bien droit, « INVENTÉ » en gris en travers de la page). **Jamais sur une photo, un papier froissé, penché, mal éclairé, ni sur une vraie écriture à la main.** Le formulaire « rempli à la main » est écrit avec une police d'écriture du Mac : une imitation.
- Le mot en travers gêne la lecture quand il passe sur le texte : sur une première série d'images en bandelette, 7,8 % d'erreur (un document tapé à 32 %), et trois documents tapés sur cinq donnaient « je ne suis pas sûr » (ils restaient rangés au bon endroit). Sur de vrais papiers tamponnés, s'attendre à ce cas.
- Le seuil « lecture peu sûre » (0,9) vient de deux mesures de cette nuit (texte tapé : 1,0 ; police d'écriture : 0,3 à 0,5). Il n'a jamais été réglé sur de vrais papiers.
- Un document lu avec des erreurs peut quand même être proposé avec une confiance « haute » si chaque ligne est lue « sûre » : la carte d'assurance a 1,2 % d'erreur et une confiance haute. Le taux d'erreur n'est connu que là où un texte de référence existe.
- Dans les écrans lancés aujourd'hui, la page des papiers ne lit pas les images : le lecteur (`Papiers(…, lecteur=…)`) n'est pas branché par défaut. La répétition (étape 4) range depuis le texte de référence.
- Les images ne se refont que sur un Mac (`--fabriquer`). Deux Mac avec des polices différentes ne donneraient pas exactement les mêmes images.
- Cocher à la voix (T16) : **essayé au niveau du texte seulement**. Personne n'a parlé : la « phrase entendue » est un texte tapé (champ « La tablette a entendu », marqué SIMULÉ). Ni micro, ni modèle d'écoute sur l'iMac (R4) ; le taux d'erreur de la voix, par langue, reste « non mesuré ». Les enregistrements du dépôt (`donnees_voix/`) ne disent pas ces phrases : aucun essai avec de vrais sons. **[Corrigé au tour 68 : le modèle d'écoute est sur l'iMac depuis R4 et le taux d'erreur est mesuré sur des voix lues. Toujours vrai : personne n'a parlé à cette page.]**
- Les mots qui font reconnaître un point en allemand, italien et anglais (`mots_des_points.yaml`) sont écrits par l'agent, pas relus. Un mot dit autrement (« die Glocke », « il pulsante ») n'est pas reconnu : le prototype répond qu'il ne trouve pas le point, rien n'est coché.
- La phrase doit contenir « fait » (ou « gemacht », « erledigt », « fertig », « fatto », « done »). Toute phrase avec « pas », « non », « nicht », « kein », « not », « no » ne coche rien, même « la sonnette, fait, pas le lit ».
- Le prototype répond en français, quelle que soit la langue de la phrase. « Je sors » ne se dit pas encore à la voix.
- Le seuil d'écoute (0,6) est choisi par l'agent ; il n'a jamais vu une vraie confiance d'écoute.
- Demander au robot à la voix (T17) : **au niveau du texte seulement**, comme T16 : la phrase est tapée, personne n'a parlé. La livraison qui suit est **testée sur faux robot**.
- Le robot ne comprend une demande qu'en français, et seulement si elle contient « il manque », « apporte », « il faut » ou « j'ai besoin ». La réponse à « lequel ? » doit contenir un mot qui distingue l'objet (« grand », « nuque ») ; « le premier » ou « celui-là » ne sont pas compris : la question est reposée, sans limite de fois.
- La question dite est « Lequel : le grand coussin, ou le coussin de nuque ? » (faite avec les noms de la réserve), pas mot pour mot la phrase du cahier. Elle n'est pas dite à voix haute : elle s'affiche.
- Une question posée à la voix attend sans limite de temps ; elle est oubliée si le programme redémarre (elle n'est pas dans le carnet).
- La dictée du médecin (T18) : **au niveau du texte seulement** ; personne n'a dicté à voix haute. Avec une vraie écoute, une phrase mal comprise mais « sûre » créerait quand même une tâche pour un collègue : le médecin voit ce que le prototype a compris, mais il ne peut pas encore corriger ni annuler.
- L'écoute sur l'iMac (R4) : **mesurée sur des enregistrements, pas sur un micro**. 48 vraies voix du dépôt (FLEURS : des personnes qui lisent une phrase de journal, micro propre) : mots faux fr 17,4 %, de 8,5 %, it 7,1 %, en 6,4 %. **Aucune phrase de la clinique (« sonnette, fait », « il manque un coussin ») n'a été dite ni écoutée ; aucun essai dans le bruit d'une salle, ni avec un accent, ni en suisse allemand.** Pourquoi le français est moins bon que les autres : à vérifier (les deux erreurs regardées sont de petits mots).
- L'accueil à la voix (T20) : **essayé à partir d'un enregistrement, pas d'un micro**. Dans l'essai, l'arrivée est dite par une **voix de synthèse du Mac**, propre et sans bruit, pas par une personne : cela ne dit rien d'une vraie voix dans un vrai hall. Seule l'arrivée en italien est essayée de bout en bout par le son ; l'allemand, le français et l'anglais ne le sont qu'au niveau du texte (T10). L'écran du hall n'a pas de bouton « parler ». La réponse dite n'a été réécoutée que par la machine ; personne n'a jugé si elle est claire. Aucun robot, aucun visage.
- Le monde des robots (R5, `briques/clinique/monde_robots.py`) : **SIMULÉ, sans physique**. Les robots sont des points sur un plan inventé ; rien ne bouge. Les mètres, la vitesse (2 m par pas) et la batterie sont inventés : ils ne disent rien d'un vrai robot, ni du temps d'une vraie course. Deux robots peuvent être au même lieu : pas de croisement, pas d'obstacle, pas de personne sur le chemin. Ce monde n'est pas encore relié au tableau des tâches, à la flotte ni à une page : l'étape 12 de la répétition est toujours la version simple. Jamais essayé avec plusieurs vrais robots.
- Le répartiteur et le relais (T23, `briques/clinique/repartiteur.py`) : il choisit parmi des robots **SIMULÉS** (R2 à R4 : des points sur un plan inventé), avec des mètres et une batterie inventés. « Le plus proche » ne dit rien d'un vrai bâtiment. Le relais est **proposé, pas joué** : aucun objet n'a passé d'un robot à un autre, même en simulation. Le répartiteur n'est pas encore branché à la page de la flotte ni à la grande répétition. Jamais essayé avec plusieurs vrais robots.
- Le choix expliqué et l'annonce (K04) : **testé sur faux robot**. L'annonce est un **texte**, écrit dans la boîte noire et sur la tâche : **aucune voix ne la dit**, et elle ne s'affiche que sur la page « Pourquoi ? ». Dans une séance avec un robot branché, le répartiteur écarte toujours les robots simulés : il ne choisit donc, pour de vrai, qu'entre « le robot branché » et « un humain ». La place du robot branché est le lieu du plan le plus proche de sa position simulée. La page « Pourquoi ? » n'a été ouverte que par un essai automatique.
- Les cartes de rôle (T22a, `briques/clinique/cartes.py`) : le contenu des cinq cartes est **inventé** (lieux, vitesses, volumes) ; aucun soignant ne l'a relu. La carte est appliquée dans le **monde simulé** (les lieux) et à la **voix du Mac** (le volume, mesuré sur le fichier son, pas avec un appareil dans une chambre : « parle bas » n'a pas été jugé par une oreille). Pour R1 : voir la ligne suivante (T22b). Jamais essayé sur un vrai robot.
- Le gardien applique la carte de R1 (T22b, `briques/clinique/cartes_gardien.py`) : **testé sur faux robot seulement**, jamais sur un vrai robot. Les lieux sont des cercles de 0,3 m autour de points inventés dans la halle : sur un vrai robot, il faudra les vraies positions et de vraies zones. Un déplacement « de tant de mètres » (sans nom de lieu) n'est arrêté que s'il arrive dans un de ces cercles. Les actions hors de la carte sont refusées par la clinique avant le gardien, pas par le gardien lui-même. Le volume de la voix du robot n'est pas appliqué (la prise n'a pas ce réglage). Seules les cartes Accueil, Étage et Nuit ont été essayées avec le gardien ; Thérapie et Visite : seul leur fichier de règles est contrôlé.
- La pause des soignants (J05a, `briques/clinique/pauses.py`) : **testée sur faux robot seulement**. Elle s'applique au robot branché, au prochain geste qu'il demande : un geste déjà parti n'est pas coupé (pour cela il y a l'arrêt). Pour « parler », le gardien ne dit pas non : il demande l'accord d'un humain. Les lieux sont des cercles de 0,3 m autour de points inventés. Une tâche mise en attente par une pause ne repart pas toute seule. Les robots simulés ne suivent pas les pauses. Aucun soignant n'a essayé la page ; les mots de la liste des raisons n'ont été relus par aucun soignant.
- La page « Qui décide » (J05b) : elle dit ce que le **prototype** laisse faire à chaque badge, avec des données inventées. **Aucune clinique n'a décidé cela** : qui allume quoi, qui est prévenu, tout cela est notre proposition, à discuter avec de vrais soignants. Les phrases « ce que le système ne fait jamais seul » sont écrites à la main (sauf la règle du hall) : elles disent ce que les essais vérifient ailleurs, mais la page ne le recalcule pas. La recherche des promesses ne connaît que quelques tournures : une promesse dite autrement lui échapperait.
- L'aide humaine comptée (K02a, `briques/clinique/aide_humaine.py`) : les chiffres « 16 sur 20 du premier coup » et « 4 aides pour 40 demandes » viennent de vingt essais **sur le faux robot**, avec une liste fixe : ils ne disent rien d'un vrai robot. Le faux robot ne rate presque jamais un geste : ces chiffres seront moins bons en vrai. « Reprise automatique » est toujours à 0, parce que toutes les pannes d'aujourd'hui sont provoquées et donc prévues. Le bouton « J'ai aidé » n'a été pressé que par des essais automatiques, jamais par une personne pendant une vraie démonstration.
- Demandé, confirmé, constaté (K03a) : « constaté » n'existe aujourd'hui que **sur le faux robot** : c'est le monde simulé qui dit où est l'objet (étiquette SIMULÉ), et ce monde est lu par l'état que la prise rend. « 20 sur 20 réussis et constatés » ne dit donc rien d'un vrai robot. **Sur un vrai robot, seul le bouton « Je l'ai vu » constate** (une personne) : aucun capteur ; ce bouton n'a été pressé que par des essais automatiques. La limite de 0,5 m est un choix, pas une mesure.
- L'âge de l'information (K03b) : le petit programme des pages a été joué par **Node, avec un faux document et une fausse montre**, pas dans un vrai navigateur : la zone grisée n'a jamais été vue par un œil, ni sur une tablette, ni sur un vrai Wi-Fi qui tombe. Les pages qui ne se mettent pas à jour toutes seules (journal des accès, pré-admission, faux logiciel) n'affichent pas d'âge.
- Les pages vues dans un navigateur (N01a) : dix écrans ont été **vus dans un vrai navigateur par l'assistant de code, sur cet ordinateur** (le navigateur intégré de l'application, et Chrome sans fenêtre), en 375 × 812 et 1440 × 900. **Ce n'est pas encore « vu par un humain sur un vrai téléphone »** : personne n'a tenu un téléphone, touché l'écran avec un doigt, ni lu ces pages sur un vrai Wi-Fi. Les autres pages ne sont pas encore vues (N01b). Langues mêlées (Q19) : sur l'écran du patient, le programme et le genre des documents restent en français dans les quatre langues ; en allemand, les écrans du soignant et du médecin restent presque tout en français. Dans les tableaux étroits (Direction, journal), des mots sont coupés aux syllabes sur téléphone. La mesure automatique « rien ne dépasse » ne tourne que si Chrome est sur l'ordinateur.
- La règle de parole du hall (« dans le hall, le robot ne dit rien sur la santé ») **n'est pas dans le gardien** (choix de Hiba, Q12 : A). Le gardien de l'ossature ne juge que les mouvements du robot, pas ce qu'il dit. La règle est écrite à côté, dans `briques/clinique/accueil_hall.yaml` (une phrase et une liste de mots), et c'est l'accueil du hall qui l'applique. Une question de santé dite avec des mots hors de cette liste ne serait pas reconnue comme telle.
- Le tirage (K01a, `briques/clinique/tirage.py`) : joué avec le **cerveau de test**, sur le **faux robot**. La demande arrive déjà comprise : « 30 bonnes réponses sur 30 » dit que le chemin (tableau des tâches, accueil du hall, gardien) est sûr ; **ce n'est pas un chiffre de compréhension**. Aucun vrai cerveau (Apertus) n'a joué le tirage. Les phrases allemandes, italiennes et anglaises (demandes et refus) sont écrites par l'agent, pas relues. Les demandes d'un soignant ne sont qu'en français. Les ordres interdits essayés sont trois (le hall, un lieu qui n'existe pas, saisir sans bras) : ce n'est pas tout ce qu'un robot pourrait faire de dangereux.
- Le bouton « Demande au hasard » (K01b) : pressé seulement par des essais automatiques, jamais par une personne ni dans un navigateur. La demande est jouée sur un faux robot neuf, **à part de la séance en cours** : elle ne se voit pas sur les autres écrans, et ne dit rien du robot branché. L'option `--apertus` ne joue rien : **le tirage n'a jamais été joué par un vrai cerveau**.
- L'endurance et la main humaine (K02b, `briques/clinique/endurance.py`) : **une seule minute mesurée** (1 min 01 s, 16 passages, aucun arrêt), **sur le faux robot**, avec le scénario à règles, sans modèle ni voix : cela ne dit rien de la tenue d'un vrai robot, ni d'une heure de démonstration. Aucune longue endurance n'a été lancée. L'écoute de la main humaine (reprise, geste télécommandé) n'a été essayée qu'avec des événements fabriqués par l'essai, jamais avec une personne à la manette. L'étiquette « RÉEL · TÉLÉCOMMANDÉ » n'a jamais été vue sur un vrai robot. Le bouton « Réussi avec aide » n'a été pressé que par des essais automatiques.
- L'épreuve des étagères (M02, `briques/clinique/etageres.py`) : **la page Étagères n'a compté aucun essai sur un vrai robot**. Le compte (points, aides, dix minutes, annulation) n'a été essayé qu'avec un fichier d'essai et une fausse montre ; les boutons n'ont été pressés que par des essais automatiques, jamais par une main sur un téléphone ; la page n'a pas été regardée sur un téléphone. L'essai en cours vit dans la mémoire du programme : si le programme s'arrête, l'essai s'arrête (ses lignes restent écrites).
- Les trois cartes préparées d'avance (M01 : `unitree_g1`, `unitree_go2`, `unitree_g1d`) : **les trois cartes n'ont été essayées que sur le faux robot**. Personne de l'équipe n'a vu ces robots. Les chiffres viennent de l'avenant de Hiba (« environ ») ou sont des choix pour le faux robot : tous à vérifier ou à remplir samedi. Le faux robot « fait comme si » les deux robots à bras pouvaient saisir un objet léger, et comme si le panier du robot à quatre pattes était là : rien ne dit que ce sera vrai. Aucun kit de fabricant n'est installé ; aucun adaptateur vers ces robots n'existe.
- La table des sources (L01, `briques/clinique/sources_des_donnees.yaml`) : elle dit d'où les données **viendraient** dans une vraie clinique, d'après l'avenant de Hiba. **Aucune vraie clinique ne l'a relue**, et le prototype ne se connecte à aucun logiciel. Pour le plan des lieux, la réserve, les feuilles volantes et le programme des thérapies, la source est « INCONNU ». Les badges du carnet (résumé, questions pour le médecin) sont écrits dans la table, pas calculés.
- Le faux logiciel administratif (L02a, dossier `faux_logiciel_admin/`) : **SIMULÉ**. messages fabriqués par nous au standard HL7 version 2.5 ; jamais essayés avec un vrai logiciel de clinique. La place de chaque renseignement dans les lignes MSH, EVN, PID, PV1 et IN1 vient de ce que nous savons du standard : **à vérifier** avec quelqu'un qui le connaît. Une ligne par segment avec une fin de ligne simple (le standard dit « retour chariot ») : à vérifier. Le jour 1 de l'horloge de démonstration est écrit « 14.11.2026 » dans les messages : c'est une convention inventée. Les numéros de séjour (s01 à s15) sont inventés.
- La page du faux logiciel et les deux liens (L02b) : **SIMULÉ**. Les boutons n'ont été pressés que par des essais automatiques ; la page n'a pas été regardée dans un navigateur (le petit programme de la page, qui lit la chambre et recharge, n'est donc pas essayé). « Ouvrir l'assistant » affiche le numéro de séjour sans le contrôler ; une personne admise par message n'apparaît pas encore sur nos écrans (L03). Le lien de l'accueil vers la fiche ne s'ouvre, depuis un autre ordinateur, qu'avec le code d'équipe : un navigateur seul ne l'envoie pas.
- Le traducteur (L03a, `briques/clinique/traducteur.py`) : **SIMULÉ**. Il n'a lu que les messages de notre propre faux logiciel, et quelques messages abîmés fabriqués pour l'essai : **jamais un message d'un vrai logiciel de clinique**. Un vrai message a d'autres lignes, d'autres habitudes d'écriture et parfois d'autres séparateurs : rien de cela n'est essayé. Le délai « écriture → lecture » est mesuré sur le même ordinateur, entre deux fichiers : il ne dit rien d'un vrai réseau.
- La vue administrative dans la porte, à l'accueil et aux écrans (L03b) : **SIMULÉ** de bout en bout (faux logiciel → fichier → traducteur → porte → écran). « Connue en moins de dix secondes » est mesuré sur un seul ordinateur, avec des fichiers : pas sur un réseau, pas avec un vrai logiciel. L'accueil du hall a été essayé au niveau du texte (pas à la voix) pour ces personnes. Un médecin ne voit pas une personne arrivée par message (elle n'est dans la liste d'aucun médecin) : à décider avec l'équipe. La zone « dernière nouvelle » ne grise pas encore quand le logiciel se tait (K03).
- La pré-admission préparée par l'assistant (L04a, `briques/clinique/pre_admission.py`) : **SIMULÉ**. Les règles ne lisent que deux papiers inventés, écrits par nous, en texte tapé : elles ne savent rien lire d'autre (pas d'image, pas d'écriture à la main, pas d'autre mise en page). Le message de pré-admission est fabriqué par nous ; la place du numéro de pré-admission (PV1-5), de la date d'arrivée prévue (PV2-8) et du numéro de carte (IN1-36) est **à vérifier** ; jamais essayé avec un vrai logiciel de clinique. La validation n'a été faite que par des essais automatiques, jamais par une personne à l'accueil.
- La pré-admission, la boucle fermée (L04b) : **SIMULÉ** de bout en bout : notre faux logiciel reçoit notre message et répond. Cela ne dit pas ce que ferait un vrai logiciel de clinique d'un tel message (nous n'inventons pas sa réponse). Les pages et leurs boutons n'ont été essayés que par des essais automatiques, jamais dans un navigateur ni par une personne. Une personne venue d'une pré-admission n'a pas de civilité dans le message : elle s'affiche « M./Mme ».
- La pièce `ecoute.py` passe par l'outil `whisper-cli` déjà sur l'iMac. Les oreilles de l'ossature (brique 4 : micro, fin de phrase, mot d'appel) ne passent pas par lui : elles attendent `mlx-whisper` ou `pywhispercpp`, jamais installés sur un Mac. « Cocher à la voix » et « demander à la voix » restent donc au niveau du texte : le chemin micro → écoute → coche n'existe pas encore.
- Le MacBook M2 n'a ni le modèle ni la mesure : à refaire là-bas.


## Les 30 essais sautés sur cet ordinateur (demandé par Hiba le 12.11.2026)
Relevé le 12.11.2026 par `python -m pytest -rs` : 1542 essais réussis, 30 sautés. Un essai sauté ne prouve rien : ce qu'il
devait vérifier n'est **pas vérifié sur cet ordinateur**. Tous sont dans l'ossature ; aucun dans la clinique en boîte.
Je n'ai rien installé pour les faire tourner (feu orange).

- 1 essai — `briques/b04_oreilles_voix/tests/test_relecture_voix.py`, ligne 218 — raison : whisper base absent
- 5 essais — `briques/b04_oreilles_voix/tests/test_voix.py`, ligne 85 — raison : whisper base absent
- 1 essai — `briques/b04_oreilles_voix/tests/test_voix.py`, ligne 100 — raison : voix chinoise absente
- 1 essai — `briques/b04_oreilles_voix/tests/test_voix.py`, ligne 129 — raison : voix chinoise absente
- 1 essai — `briques/b04_oreilles_voix/tests/test_voix.py`, ligne 155 — raison : voix chinoise absente
- 1 essai — `briques/b04_oreilles_voix/tests/test_voix.py`, ligne 183 — raison : voix chinoise absente
- 1 essai — `briques/b04_oreilles_voix/tests/test_voix.py`, ligne 205 — raison : voix chinoise absente
- 1 essai — `briques/b05_yeux/tests/test_yeux_camera.py`, ligne 80 — raison : OpenCV absent (requirements-yeux.txt)
- 1 essai — `briques/b05_yeux/tests/test_yeux_gardien.py`, ligne 282 — raison : OpenCV absent : la caméra « fichier » en a besoin
- 1 essai — `briques/b05_yeux/tests/test_yeux_gardien.py`, ligne 317 — raison : OpenCV absent : la caméra « fichier » en a besoin
- 1 essai — `briques/b05_yeux/tests/test_yeux_outils.py`, ligne 43 — raison : OpenCV absent (pip install --no-deps -r requirements-yeux.txt)
- 3 essais — `briques/b05_yeux/tests/test_yeux_outils.py`, ligne 59 — raison : OpenCV absent (pip install --no-deps -r requirements-yeux.txt)
- 1 essai — `briques/b05_yeux/tests/test_yeux_outils.py`, ligne 80 — raison : OpenCV absent (pip install --no-deps -r requirements-yeux.txt)
- 1 essai — `briques/b05_yeux/tests/test_yeux_outils.py`, ligne 92 — raison : OpenCV absent (pip install --no-deps -r requirements-yeux.txt)
- 1 essai — `briques/b05_yeux/tests/test_yeux_outils.py`, ligne 107 — raison : OpenCV absent (pip install --no-deps -r requirements-yeux.txt)
- 1 essai — `briques/b05_yeux/tests/test_yeux_outils.py`, ligne 114 — raison : RapidOCR absent (requirements-yeux.txt)
- 1 essai — `briques/b05_yeux/tests/test_yeux_outils.py`, ligne 125 — raison : RapidOCR absent (requirements-yeux.txt)
- 1 essai — `briques/b05_yeux/tests/test_yeux_outils.py`, ligne 142 — raison : MediaPipe non essayé ici : modèle absent : modeles/mediapipe-efficientdet-lite0/efficientdet_lite0.tflite (python -m briques.b05_yeux.telecharger_modele)
- 1 essai — `briques/b05_yeux/tests/test_yeux_samedi.py`, ligne 29 — raison : OpenCV absent (requirements-yeux.txt)
- 1 essai — `briques/b05_yeux/tests/test_yeux_samedi.py`, ligne 36 — raison : OpenCV absent (requirements-yeux.txt)
- 1 essai — `briques/b05_yeux/tests/test_yeux_samedi.py`, ligne 93 — raison : OpenCV absent (requirements-yeux.txt)
- 1 essai — `briques/b06_cerveau/tests/test_cerveau.py`, ligne 467 — raison : pas de serveur sur le port 8091
- 1 essai — `briques/b11_main_humaine/tests/test_navigateur_main_humaine.py`, ligne 33 — raison : Playwright pour Node absent : test du navigateur sauté (ne pas l'installer sans « oui » de Hiba)
- 1 essai — `briques/b13_ecran/tests/test_navigateur_jury.py`, ligne 18 — raison : Playwright pour Node absent : test du navigateur sauté (ne pas l'installer sans « oui » de Hiba)

Par raison : 6 parce que le modèle d'écoute « whisper base » manque (seul « small » est là) ; 5 parce que la voix chinoise du Mac manque ; 13 parce qu'OpenCV manque (les yeux) ; 2 parce que RapidOCR manque ; 1 parce que le modèle MediaPipe manque ; 1 parce qu'aucun serveur de cerveau ne tourne sur le port 8091 ; 2 parce que Playwright pour Node manque (essais dans un navigateur).

## Pas encore construit
Briques 9, 10, 16.

## Apertus sur l'iMac (R2, tour 61)
- Mesuré une seule fois, le 12.11.2026 : 112 bonnes réponses sur 120, cerveau RÉEL, **FAUX ROBOT**. Jamais avec un vrai robot. Un seul passage : pas de moyenne sur plusieurs jours.
- Les 30 demandes sont celles du banc de l'ossature, écrites par un agent : ce ne sont pas des phrases de soignants ni de patients. Le suisse allemand et le chinois n'ont pas été posés à Apertus.
- Apertus fait répéter par le robot un « merci » ou une phrase sur le temps qu'il fait (5 fois sur 12) : le robot parlerait alors qu'on ne lui demande rien. Pas corrigé. Décision de Hiba, 12.11 : ne pas corriger maintenant ; la plus petite correction est proposée dans la question Q21. **Mise à jour du 13.11 (tour 105, H14, réponse de Hiba à Q21 : C)** : dans la chaîne, une action « parler » proposée par le cerveau ne part plus ; le robot dit « Je ne peux pas faire cela. ». Testé sur faux robot avec un faux cerveau ; **pas encore remesuré avec le vrai Apertus** (`apertus-essai`).
- La mémoire prise par le modèle : 5,34 Go vus par « ps » ; la part dans la puce graphique : à vérifier. Jamais lancé en même temps que l'écoute, la voix et les écrans : on ne sait pas si tout tient ensemble dans 16 Go. **[Corrigé au tour 68 : lancé avec l'écoute et la voix au tour 65 (H07) et au tour 68 ; jamais avec les écrans ouverts.]**
- Jamais sur le MacBook M2. Jamais plus de quelques minutes de suite. Le secours (4B, puis règles) quand le 8B tombe : jamais essayé avec le vrai 8B.
- Aucune pièce de la clinique n'appelle encore Apertus : le résumé (T13), le rangement des papiers et le tirage (H06) restent « non mesuré » avec le vrai modèle. **[Corrigé au tour 68 : le résumé (T13), les papiers et le tirage (H06) ont été mesurés avec le vrai modèle. Toujours vrai : dans la séance par défaut, aucune pièce ne l'appelle.]**
- Un essai de plus saute quand le serveur d'Apertus ne tourne pas (`test_avec_le_vrai_apertus_si_le_serveur_tourne`) : 31 essais sautés au lieu de 30.

## Le résumé écrit par Apertus (T13, tour 62)
- Mesuré le 12.11.2026 avec le vrai Apertus 8B : **0 ligne gardée sur 13** après contrôle, et **11 lignes sur 13 mettent plus de 5 secondes** (médian 6,4 s par ligne ; jusqu'à 22 s pour un patient). Aujourd'hui, Apertus n'écrit donc aucune ligne du résumé : c'est la version simple, par des règles, qui s'affiche. Ne pas dire au jury que « le résumé est écrit par Apertus ».
- Le contrôle est très serré : mêmes chiffres que la version simple, mots venus des sources. Il a laissé passer deux fois des lignes fausses avant d'être renforcé (titre recopié ; rendez-vous de demain) : il peut y avoir un troisième trou. Il ne comprend pas le sens : une phrase faite des bons mots et des bons chiffres dans un mauvais ordre passerait.
- Essayé sur six patients inventés, au jour 1 seulement, en français seulement. Jamais avec une question du soir, une demande ou un point de liste au carnet (le « ce qui a changé » du jour 2). Jamais lu par un médecin.
- `CLINIQUE_APERTUS=1` dans une vraie séance : jamais essayé avec les écrans ouverts. L'appel au modèle bloque le programme pendant qu'il écrit (jusqu'à 22 s mesurées) : les autres écrans attendraient. La mention « je prépare… » n'existe pas.
- Deux essais de plus sautent quand le serveur d'Apertus ne tourne pas : 32 essais sautés.

## Le rangement des papiers par Apertus (H06a, tour 63)
- Mesuré le 12.11.2026 avec le vrai Apertus 8B : **2 papiers bien rangés et sûrs sur 9** (les règles simples seules : 6 sur 9) ; 0 mal rangé dit sûr ; 4,2 s au plus par papier. Sur ces papiers, Apertus n'aide pas : il met dans la date des mots qui ne sont pas une date, et il invente un patient pour la feuille sans nom (arrêté par la vérification).
- Neuf textes tapés seulement, écrits par un agent, en français, italien et allemand. Jamais sur les images des papiers (T15), jamais sur une écriture à la main, jamais sur un vrai papier.
- Dans la séance, Apertus n'est pas branché aux écrans des papiers : ce sont les règles simples qui proposent. Ne pas dire au jury « le cerveau range les papiers ».
- La vérification a eu un trou (une « date » qui n'en est pas une) : bouché. Elle ne contrôle toujours pas que la date est LA bonne date du papier, ni que l'auteur est le bon.
- Un essai de plus saute quand le serveur d'Apertus ne tourne pas : 33 essais sautés.

## Le tirage compris par Apertus (H06b, tour 64)
- Mesuré une seule fois, le 12.11.2026, tirage n° 1 : compris 26 sur 30, 0 geste interdit exécuté, **FAUX ROBOT**. Les tirages 2 et 3, et un deuxième passage : pas faits.
- **Deux réponses ont mis plus de 5 secondes** (9,3 s et 8,1 s), sur des ordres donnés au robot. Les réglages donnent 6 secondes à Apertus avant de passer au secours : dans la vraie chaîne, ces deux demandes seraient parties au cerveau de secours. Pas essayé.
- **Un geste est parti à tort** : à un robot sans bras, on demande de prendre un objet ; Apertus fait dire au robot « je vais prendre le coussin » (en allemand, alors que la demande était en anglais). Le gardien permet de parler. Le robot a donc dit une chose fausse. Pas corrigé (c'est proche de la question Q21). **Mise à jour du 13.11 (H14)** : la chaîne ne laisse plus partir cette parole (testé sur faux robot, faux cerveau, pas avec Apertus).
- Le lieu « Hall » de la clinique n'a pas de nom dans les langues : Apertus a choisi le lieu « entree » de l'ossature. Le refus du gardien est venu de la vitesse, pas de la carte de rôle. Le cas « Apertus choisit bien Hall, la carte refuse » n'a été joué qu'avec le cerveau de test.
- Pour l'écran du soignant et le hall, la réponse vient des règles de la clinique : ce qu'Apertus comprend est compté, mais ne sert à rien dans la séance d'aujourd'hui. Il confond « pas clair » et « pas dans la réserve ».
- Le bouton « Demande au hasard » de la page du tirage joue toujours avec le cerveau de test.
- Un essai de plus saute quand le serveur d'Apertus ne tourne pas : 34 essais sautés.

## La chaîne entière sur l'iMac (H07, tour 65)
- Mesurée une seule fois, le 12.11.2026 : 2,5 s au milieu, 4,2 s au plus, de la fin de la phrase au début de la réponse. **Aucun robot.** Les phrases sont dites par la **voix de synthèse** du Mac, sans bruit, lues dans des fichiers : jamais une vraie personne, jamais un micro, jamais dans une salle bruyante, jamais avec un haut-parleur.
- Le temps pour savoir que la personne a fini de parler (le micro attend un silence) n'est pas dans la mesure : sur scène, la réponse viendra plus tard que ces chiffres.
- **La mémoire** : par la règle écrite, elle manque (0,62 Go d'échange en plus, 1,48 Go libres au plus bas). Mais l'iMac n'était pas vide. On ne sait pas ce que donne un iMac où tout le reste est fermé, ni ce que donnent en plus les écrans de la clinique, les yeux, et un vrai robot branché. À mesurer par l'équipe, ou partager avec le deuxième Mac (décision de Hiba).
- **« Stop. » a été entendu « stock. »** (voix anglaise de synthèse), et Apertus a posé une question au lieu d'arrêter. L'arrêt d'urgence ne doit jamais dépendre de la voix : c'est le bouton. Une seule phrase « stop » par langue a été essayée.
- Douze phrases seulement, des ordres courts de l'ossature ; aucune phrase de la clinique (« sonnette, fait »). Les oreilles de l'ossature (brique 4) ne sont pas branchées sur cet outil d'écoute.
- Un essai de plus saute quand le serveur d'Apertus ne tourne pas : 35 essais sautés.

## L'ébauche de branchement d'un Unitree Go2 (H08a, tour 66)
- **PRÉPARÉE SANS LE ROBOT — non testé sur vrai robot.** Personne de l'équipe n'a vu ce robot. Le kit du fabricant n'est pas installé : la partie qui crée les vrais clients (`creer_kit`) n'a JAMAIS tourné, même une fois. Elle peut casser à la première ligne.
- Le test de conformité a réussi avec une **doublure** : le faux kit du projet, avec les noms de fonctions d'Unitree. Il prouve que notre mécanique appelle les bons noms dans le bon ordre. Il ne prouve rien sur le vrai chien.
- Lu dans la documentation publique : les noms `StandUp`, `Move`, `StopMove`, « return code », les champs du message d'état. **Pas lu, donc à vérifier samedi** : le nom du sujet de l'état et la façon de s'y abonner, les unités, le sens des codes, la batterie, le cap, le temps pour se lever, s'il faut un autre appel avant de marcher, si le chien s'arrête seul quand les ordres cessent.
- L'arrêt d'urgence logiciel de l'ébauche est `StopMove()` : une proposition. Il ne bloque pas le chien et ne remplace jamais le bouton physique. Le choix se fait samedi avec le responsable sécurité.
- L'ébauche est pour un Go2 (quatre pattes). Si le robot de samedi est un G1 (deux jambes), les fonctions ne sont pas les mêmes (fiche `unitree_g1.md`) : l'ébauche est à refaire en partie.
- Le robot à roues ROS 2 et `docs/projet/PREMIERE_HEURE.md` : faits au tour 67, voir plus bas.

## L'ébauche « robot à roues ROS 2 » et docs/projet/PREMIERE_HEURE.md (H08b, tour 67)
- **PRÉPARÉE SANS LE ROBOT — non testé sur vrai robot.** Nous ne savons pas quel robot nous aurons. ROS 2 n'est pas installé : la partie qui ouvre le vrai ROS 2 (`creer_ros2`) n'a JAMAIS tourné. Aucun vrai message n'a jamais été publié.
- Le test de conformité a réussi avec le **faux ROS 2 du projet** : il imite quelques fonctions et deux messages. Il prouve que notre mécanique publie une vitesse, puis une vitesse nulle, et lit une position. Il ne prouve rien sur un vrai robot.
- Les noms des canaux (« /cmd_vel », « /odom ») sont des noms courants, pas ceux d'un robot précis. Les unités, le sens des axes, l'arrêt tout seul quand les messages cessent, un autre pilote sur le même canal : **à vérifier samedi**.
- L'arrêt d'urgence logiciel de l'ébauche est une vitesse nulle : une proposition, non confirmée par le robot. ROS 2 n'a pas d'arrêt d'urgence standard ; celui du robot est à trouver samedi. Rien ne remplace le bouton physique.
- L'ébauche ne sait ni porter, ni parler, ni aller seule à un lieu nommé. Pour la clinique (apporter un objet de la réserve à une chambre), il faudra en plus sa navigation : pas préparée.
- `docs/projet/PREMIERE_HEURE.md` **n'a jamais été essayée** : ni avec un robot, ni par une personne de l'équipe montre en main. L'ordre des gestes est celui de `BRANCHER_UN_ROBOT.md`, resserré. « Une heure » est un but, pas une mesure.

## La relecture de la tranche 2 (T21, tour 68) — ce qu'elle a montré et qui reste vrai
- **La répétition « RÉUSSIE » ne prouve presque rien sur la tranche 2.** Elle joue le scénario en version simple : pas de voix (étape 1), pas d'image ni de modèle pour les papiers (étape 4), des coches faites par le programme (étape 7), le résumé sans modèle (étape 10), une dictée tapée (étape 11). Les tâches T13 à T20 sont « FAIT » sur la foi d'essais séparés et de mesures faites une ou deux fois, pas d'une séance entière.
- Le contrôle du résumé a été percé trois fois (deux fois par le vrai Apertus, une fois par le relecteur). Il est maintenant si serré que le cerveau ne peut que redire la version simple ; il ne comprend toujours pas le sens. Deux mots de la source échangés entre eux passeraient encore.
- Les papiers : l'auteur gardé est celui que la règle lit sur la première ligne ; rien ne vérifie que c'est le vrai auteur. La date gardée a la forme d'une date et est écrite sur le papier ; rien ne vérifie que c'est LA date du document.
- **Le cerveau n'a pas de badge à lui** : quand il est branché, il reçoit des textes lus avec le badge du médecin ou de l'accueil, et le journal des accès ne dit pas qu'un modèle les a reçus (tâche H09). La mesure des images des papiers lit le faux dossier sans passer par la porte (H09). **[Corrigé au tour 69 (H09) : le cerveau lit sous le badge « assistant », au service de la personne, et le journal a une ligne par texte donné ; les mesures passent par la porte.]**
- **L'accueil reçoit par la porte le programme** des personnes qui arrivent, et le texte entier de leurs papiers (tâche H01). **[Corrigé au tour 70 (H01) : plus de texte, plus de programme, plus de liste de soin pour l'accueil.]**
- Une coche, une demande ou une dictée « à la voix » est écrite « validée par un humain » alors que personne n'a confirmé ce que l'écoute a compris (question Q23). Aujourd'hui la phrase est tapée par la personne ; ce sera faux le jour où une vraie écoute sera branchée. Les négations connues sont une courte liste de mots : une tournure qui n'y est pas cocherait.
- Dans la mesure de la chaîne (H07), la langue de chaque phrase est donnée à l'écoute. Dans le hall, elle doit la deviner : pas mesuré.
- « Gestes interdits exécutés » du tirage ne compte que « saisir » et « aller au Hall » ; un autre geste parti sans raison est compté « parti à tort ».
- Les cinq lignes du cerveau dans la fiche de vérité montrent la DERNIÈRE mesure faite sur cet ordinateur ; la fiche ne garde pas l'historique. La mémoire a manqué à la mesure du tour 65 et pas à celle du tour 68 : cela dépend de ce qui est ouvert sur l'iMac.
- Le relecteur a lancé un essai pendant que le serveur d'Apertus tournait pour mes mesures : cet essai a appelé le modèle une fois. Sans conséquence, mais les mesures du tour 68 ont été prises pendant qu'un autre programme travaillait.

## Le badge du cerveau (H09, tour 69)
- Essayé avec des cerveaux de test seulement. Avec le vrai Apertus (`CLINIQUE_APERTUS=1`, ou les commandes de mesure), le chemin est le même, mais le journal des accès n'a pas été relu après une vraie mesure.
- Le journal dit quel texte le cerveau a reçu (patient, ligne du résumé, références des sources ; identifiant du papier). Il ne garde ni le texte envoyé, ni la réponse du modèle.
- Le badge « assistant » n'est pas un contrôle d'identité : comme les autres badges, il se choisit, sans mot de passe.
- Le cerveau de l'ossature (les ordres au robot, brique 6) ne lit pas le faux dossier : il reçoit la phrase, la carte du robot et le plan. Rien n'est noté au journal des accès pour lui.

## L'accueil sans le texte des papiers (H01, tour 70)
- Le texte de chaque papier reste écrit dans le carnet (lignes « rangement de papier », avec le badge de l'accueil) : aucun écran ni aucune réponse à l'accueil ne le montre, mais il est dans le fichier du carnet sur l'ordinateur. Pas corrigé.
- Quand le prototype dit « je ne suis pas sûr », la personne de l'accueil choisit le type du document avec le papier en main : l'écran ne lui montre plus rien du papier. Jamais essayé avec une vraie personne.
- La page a été demandée par le programme seulement : pas revue dans un navigateur depuis ce changement (N01b).
- L'accueil ne peut plus ouvrir la liste « Préparation de la sortie », où le cahier lui donne trois points (rendez-vous, transport, documents à envoyer). Il ne le pouvait déjà pas en pratique. Question Q24.
- Le badge « assistant » se choisit comme les autres, sans mot de passe : la séparation entre l'accueil et la pièce qui range est une règle du programme, pas une protection contre quelqu'un.

## La tâche du médecin pour une question du soir (H02, tour 71)
- La question est tapée par le programme ou au clavier : jamais dite, jamais posée par une vraie patiente.
- Le médecin voit la tâche, mais il n'a pas de bouton pour la marquer « faite » : elle reste « demandée ». Pas construit.
- Si aucun badge de médecin ne suit la patiente, la tâche existe au carnet et ne s'affiche chez personne ; rien ne le signale.
- L'étape 9 de la grande répétition vérifie les questions dans le résumé, pas encore la tâche.
- La page du médecin a été demandée par le programme seulement : pas revue dans un navigateur depuis ce changement (N01b).

## Les phrases traduites des écrans (H03a, tour 72)
- **AUCUNE PHRASE N'EST RELUE** par une personne qui parle allemand, italien ou anglais. Tout `briques/clinique/traductions_ecrans.yaml` est écrit par un agent d'IA. Le champ « relu_par » est vide. Avant de montrer un écran en allemand au jury : le faire relire, ou rester en français.
- Seules les deux pages principales du soignant et du médecin sont traduites. Restent en français : la page d'une liste de soin, la fin de poste, la dictée, la page d'une source, les messages de refus, « Badge », le pied de page, l'heure (« Jour 1 — 9 h 00 »).
- Restent en français parce que ce sont des données, pas des textes fixes : les habitudes, les phrases du résumé du médecin (l'écran dit « nicht übersetzt »), les demandes, les messages du hall, le nom des objets. Un écran en allemand mêle donc toujours les deux langues.
- **L'écran du patient n'est pas changé** : son programme et le genre de ses documents restent en français en italien, allemand et anglais. La table est prête et éteinte (question Q25).
- La traduction cherche des phrases françaises exactes dans le texte affiché : si une phrase fixe change dans le code, sa traduction ne s'applique plus, sans erreur. Un essai le verrait pour les phrases qu'il nomme, pas pour toutes.
- Jamais vu dans un navigateur depuis ce changement (N01b), jamais sur une tablette.

## Le rapport de radiologie demandé sur scène (H04, tour 73)
- Les deux demandes (la lettre, le rapport de radiologie) sont tapées par le programme dans la répétition : jamais dites à voix haute, jamais tapées par un médecin sur une tablette.
- La recherche ne comprend pas « le dernier » : les documents du faux dossier n'ont pas de date. S'il y avait deux lettres, elle demanderait laquelle.
- La réponse « Je ne trouve pas ce document » nomme les genres de documents que la patiente a : c'est pour le médecin seulement ; jamais essayé avec un autre badge sur scène.

## Le fichier des paroles de soignants (J06b-a, tour 74)
- **Aucun soignant n'a été rencontré. Aucune parole n'existe.** À « avez-vous passé du temps avec des soignants ? », la réponse reste non.
- La page « Ce qu'on nous a dit » ne lit pas encore le fichier (question Q26) : même si l'équipe le remplit, elle dira « Aucune parole recueillie ».
- La lecture met de côté une ligne qui contient « Madame », « Monsieur », « Dr », « patient », « chambre », ou un métier suivi d'un prénom. Elle ne voit pas un prénom seul dans la phrase, ni un lieu, ni une histoire reconnaissable. Relire chaque ligne reste le travail d'une personne.
- « accord : oui » est écrit par l'équipe : le programme ne peut pas savoir si la personne a vraiment dit oui.
- La lecture n'a été essayée qu'avec des phrases fabriquées par le programme et marquées « (essai) », jamais avec un vrai fichier.

## Le clic sur « Source » et les pages du médecin (N01b, tour 75)
- Le clic a été essayé par Chrome sans fenêtre (vrais gestes de souris envoyés par un programme) et une fois dans le navigateur intégré. **Jamais par un doigt sur une tablette, jamais par une personne.**
- La correction vaut pour les écrans qui se rafraîchissent par `script_de_mise_a_jour` (patient, soignant, médecin, accueil, thérapeute et les pages qui s'en servent). Les pages qui ont leur propre petit programme (essais réels, étagères, tirage, papiers) n'ont pas été regardées pour ce défaut (N01c).
- Si le contenu change pendant qu'un doigt reste appuyé, la page attend le relâchement pour se mettre à jour : un doigt posé longtemps retarde l'affichage. Pas mesuré au-delà de 2,4 secondes.
- Sur les pages vues ce tour, seul « Source » a été pressé : ni « Retour », ni « Valider ce rangement », ni le bouton de la dictée.
- Toutes les autres pages de travail et l'écran de l'ossature : pas encore vus dans un navigateur (N01c).

## Le mode interprète (H10a, tour 76)
- **Jamais avec une personne.** Les dix phrases sont dites par la voix de synthèse française du Mac, sans bruit, lues dans des fichiers. Une vraie voix, un vrai micro, une salle : pas essayés. Le « fini quand » de Hiba (dix phrases dites) n'est tenu qu'à moitié.
- **Le sens des phrases anglaises n'est jugé par aucune personne qui parle anglais.** Le programme compte ce qu'il sait voir : les mots fixés, les chiffres, l'absence de traduction. À ma lecture, 3 phrases sur 10 sont fausses sur le chemin en deux temps, dont une que le programme ne compte pas.
- Les mots anglais fixés (caregiver, errand, box, level, stop threshold) sont proposés par un agent : à confirmer par Hiba (Q27).
- Les trois réponses préparées sont des exemples écrits par un agent, pas relus : à remplacer par l'équipe.
- Les deux boutons de l'écran de régie n'existent pas encore (H10b) : aujourd'hui, le mode interprète est une commande.
- Le chemin direct ne rend pas le français entendu : en direct, on ne pourrait pas y contrôler les mots fixés.
- Mesuré une fois ; Apertus chargé seul avec l'écoute et la voix ; jamais pendant qu'un robot ou les écrans tournent.
- Le contrôle « mot fixé employé à tort » compterait à tort une phrase où « box » ou « level » vient d'un autre mot français légitime (« niveau » → « level ») : pas vu dans la mesure, possible sur scène.

## L'écran de régie et le bouton « Interprète » (H10b, tour 77)
- **AUCUNE PERSONNE N'A PARLÉ DANS LE MICRO.** Le bouton a été tenu et relâché par un programme, dans Chrome sans fenêtre, avec un faux micro fabriqué dans la page (un son continu, pas une voix). Le vrai micro de l'iMac, la demande d'accord du navigateur (« autoriser le micro ? ») et le haut-parleur n'ont jamais été essayés.
- Chrome sans fenêtre ne répond pas à la demande de micro sur cet ordinateur : on ne sait donc pas, par essai, si la page obtient le micro dans Chrome, Safari ou le navigateur de l'application. **À faire par l'équipe, avant lundi : ouvrir `/clinique/regie` sur l'iMac, autoriser le micro, dire dix phrases, lire les délais et les erreurs.** C'est le « fini quand » de Hiba.
- Un navigateur ne donne le micro qu'à une page ouverte sur l'ordinateur même (adresse locale). Depuis une tablette ou un autre Mac, le bouton ne pourra pas écouter : la régie doit être sur l'iMac. Pas essayé.
- Il faut lancer le cerveau avant (`python3 lancer.py cerveau`) et le laisser tourner. La première phrase après le lancement est plus lente (2,8 s mesurées). Avec l'écoute, la voix, les écrans et un robot en même temps : pas mesuré (voir la question Q22 sur la mémoire).
- Le son de chaque phrase dite est gardé dans `journal/clinique/sons_interprete/` (jamais envoyé) : ce sont des voix de vraies personnes ; à effacer après la démonstration si l'équipe le veut.
- La page a été demandée par un programme : pas regardée par un humain, pas en largeur de téléphone (N01c).

## Les pages de travail dans le navigateur (N01c, tour 78)
- **Passées par un programme, pas par une personne.** Le programme ouvre, mesure, presse et note ; il ne sait pas dire si une page est claire, ni si ce qu'elle répond après un appui est la bonne réponse. La ligne reste : « pas encore vu par un humain sur un vrai téléphone ».
- 89 boutons sur 137 ne sont pas pressés (huit au plus par page : surtout la fin de poste, 69 boutons, et le faux logiciel, 28). Les boutons sont pressés sans remplir les champs : on voit surtout les refus, peu les réussites.
- Cinq pages pas ouvertes : la fiche d'une personne dans le faux logiciel, « Pourquoi ? », « Ouvrir l'assistant », la page d'un moment, et le soir du patient à l'heure du soir.
- Le passage laisse des fichiers provisoires et, s'il est interrompu, peut laisser un serveur d'essai ouvert (vu une fois, arrêté à la main).
- L'écran de l'ossature n'a pas le bandeau « DONNÉES INVENTÉES » : il ne montre aucune donnée de patient, seulement le robot. Regardé, pas touché, aucun de ses boutons pressé.
- Trois boutons « Le reporter » ouvrent une fenêtre de question du navigateur : sur une tablette, cette fenêtre a l'allure du système, pas celle de nos écrans. Pas changé.

## La panne et la reprise (T24, tour 79)
- R2, R3, R4 sont **SIMULÉS** : des points sur un plan inventé. Les mètres, la batterie, la vitesse sont inventés. Aucune panne d'un vrai robot n'a jamais été vue, ni provoquée.
- **Passer l'objet d'un robot en panne à un autre n'est pas joué** : la tâche note où l'objet est resté, et le robot suivant « va le chercher » — dans le monde simulé, personne ne prend rien. Sur scène, c'est un humain qui porterait l'objet.
- « Un humain reprend la main » : une tâche pour un humain et une aide comptée. La main humaine de l'ossature (brique 11, la manette) n'est pas appelée par cette pièce.
- La reprise par le robot branché n'est essayée que sur le faux robot, une fois, avec un seul objet.
- Pas branché aux écrans : la page de la flotte et l'étape 12 de la répétition jouent encore la version simple (R3 en panne, R1 reprend, sans choix du plus proche). C'est pour T25.
- Deux pannes en même temps, une panne pendant une reprise, un robot réparé qui revient : pas essayés.


## Le tableau de flotte (T25, tour 80)

- Robots SIMULÉS : R2, R3, R4 sont des points dans l'ordinateur. Rien ne bouge. Aucun vrai robot.
- Le temps du monde simulé n'avance que quand on appuie sur « Avancer d'un pas » : il n'avance pas tout seul.
- Les boutons sont cliqués par un programme dans Chrome sans fenêtre. La page n'est pas vue par une personne.
- Pas regardé en largeur de téléphone (le tableau a huit colonnes) : à faire dans N02.
- Le plan est une liste de lieux par étage, pas un dessin : les lieux n'ont pas de coordonnées.
- La page « Pourquoi ? » refait le tableau des robots au moment où on l'ouvre ; seule la phrase date du moment du choix.
- [ ] Un bouton pour changer la carte d'un robot : pas fait.
- [ ] L'étape 12 de la répétition joue encore la flotte simple (`/clinique/flotte`), pas la reprise par le plus proche.
- [ ] La panne du robot branché ne se provoque pas depuis cette page (seulement par la prise).

## La relecture de la tranche 3 (T26, tour 81) : ce qui n'est PAS corrigé

- [x] H11 (corrigé au tour 82, voir plus bas) — LA CARTE SE CONTOURNAIT. Avec la carte Accueil chez le gardien, le gardien dit « oui » à `se_deplacer cuisine`, `entree`, `table`, `scene` (les lieux de l'ossature ne sont pas dans la carte) et à `saisir` (les actions ne sont contrôlées que par le coursier). Un ordre qui ne passe pas par le coursier échappe donc à la carte. Constaté par le relecteur sur le gardien ; le trajet « écran de l'ossature → cerveau → gardien » n'a pas été joué.
- [x] H12 (corrigé au tour 83) — R1 était écrit au « Hall » dans le monde des robots au départ, sans lecture sur le robot. Au début d'une séance avec le robot branché, la reprise depuis le tableau part donc à un humain (« pas de chemin ») tant que R1 n'a pas fait une course.
- [x] H12 (corrigé au tour 83 : la phrase dit vrai) — Reprise par R1 : la tâche dit que l'objet est resté là où la panne a eu lieu, mais le coursier va à la Réserve ; le constat du monde simulé dit quand même « oui ».
- [x] H13 (corrigé au tour 84) — La panne d'un robot simulé et le passage à un humain sont dans le carnet, pas dans la boîte noire.
- [x] H13 (corrigé au tour 84) — La page « Pourquoi ? » du tableau de flotte ne montre pas le feu du gardien.
- [x] H13 (corrigé au tour 84) — Aucun essai ne montre un changement de carte sur le tableau de flotte.
- La carte au démarrage : essayée avec le démarrage d'une application d'essai, pas avec `python3 lancer.py` en vrai. Si elle rate au démarrage, le serveur démarre quand même et le coursier réessaie avant son premier geste.
- Le tableau de flotte ne montre plus ni la place ni la batterie de R1 : elles ne sont pas lues sur le robot.

## La carte de rôle pas contournable (H11, tour 82)

- Testé sur faux robot, par des demandes directes au gardien. Aucun vrai robot.
- Pour « montrer » et « rejouer un geste » hors carte, le gardien demande l'accord d'un humain : il ne dit pas « non ». Le gardien n'a pas de règle « action interdite » ; en ajouter une serait changer la brique 7 (feu orange).
- « regarder », « écouter », « parler » sont dans toutes les cartes : rien n'est contrôlé pour elles.
- Quand la clinique est branchée avec un robot, la carte de R1 s'applique à TOUS les ordres, dès le démarrage : l'ossature ne peut plus envoyer le robot à la cuisine, à l'entrée, à la table ou à la scène. À savoir pour une démonstration qui mélange les deux.
- [ ] Le trajet entier « écran de l'ossature → cerveau → gardien » avec une carte n'a pas été joué.
- Un lieu interdit est un rond de 0,3 m autour du lieu : le robot peut passer à côté.

## La place de R1 lue sur le robot (H12, tour 83)

- Testé sur faux robot. Avec un vrai robot, la position dépend de ce que son adaptateur donne : à vérifier samedi. Sans position, rien n'est changé (R1 reste au « Hall » du fichier, et la reprise part à un humain).
- La place est « le lieu du plan le plus proche » : une approximation, pas une mesure.
- Avant la toute première lecture, le monde des robots garde le départ inventé de `flotte.yaml` (« Hall »).
- Quand R1 reprend, il va chercher l'objet à la Réserve : un robot simulé n'a jamais rien pris. Avec deux vrais robots, il faudrait aller là où l'objet est resté : pas fait.
- [ ] Le tableau de flotte n'affiche pas la place lue (question Q28).

## La boîte noire, le feu du gardien, le changement de carte (H13, tour 84)

- Les notes de panne sont essayées avec une fausse boîte qui garde ce qu'on lui écrit. Le fichier de boîte noire d'une vraie séance n'a pas été relu pour ces notes.
- Les notes partent à la fin d'un bouton du tableau ou d'une reprise. Une panne venue d'un autre chemin (la commande `panne-reprise`) reste dans le carnet seulement.
- Le feu du gardien d'un robot simulé n'existe pas : la page le dit. Ce n'est pas un feu vert.
- [ ] Un bouton pour changer la carte d'un robot depuis le tableau de flotte : pas fait (le changement se voit, il ne se fait pas d'ici).

## La fiche de vérité complète (T27, tour 85)

- Tous les chiffres viennent du faux robot et de robots simulés. Aucun vrai robot, aucune personne.
- « Réussis du premier coup : 12 sur 12 » compte les 12 étapes de la répétition, pas des gestes de robot. Une étape = un essai. La panne de l'étape 12 est provoquée et prévue : elle ne compte pas comme une reprise imprévue.
- « Réussis et constatés » : le constat vient du monde simulé, pas d'une personne.
- « Logiciel administratif : messages lus : 0 » : la répétition ne fait pas parler le faux logiciel. Le compteur marche (essayé à part), mais la ligne reste à zéro tant qu'aucune étape ne lit de message.
- « Plus longue durée sans arrêt » est lue dans le fichier de la dernière commande `endurance` ; elle ne se mesure pas pendant la répétition.
- La fiche est gardée dans un fichier et montrée sur une page. Elle n'est PAS écrite dans la boîte noire.
- La page montre la DERNIÈRE répétition, pas la séance en cours : c'est écrit en haut, avec la date.
- [ ] La page `/clinique/fiche-de-verite` n'est pas vue par une personne, ni en largeur de téléphone (N02).
- [ ] Une étape de la répétition qui lit des messages du faux logiciel, pour que la ligne ne reste pas à zéro.

## « À vous » (T28, tour 86)

- C'est une commande, pas un écran : quelqu'un de l'équipe la tape pendant que le jury choisit.
- L'arrivée est tapée par le programme, pas dite à la voix. La langue reconnue vient du texte.
- Les coches de la liste sont faites par le programme, pas par une soignante.
- L'objet demandé est livré par le faux robot ; un objet absent ne fait bouger aucun robot.
- Quatre langues seulement (it, de, fr, en) : celles de l'accueil. Une autre langue est refusée avec une phrase claire.
- [ ] Un écran pour que le jury choisisse lui-même (prévu dans K07, l'invité aux commandes).
- [ ] « À vous » avec la voix et le vrai Apertus : pas essayé.

## L'écran « Invité » (K07a, tour 87)

- Les boutons sont cliqués par un programme (essais et Chrome sans fenêtre), pas par un juré. Personne n'a dit si l'écran se comprend sans nous.
- « Tirer », « Changer la langue » et « Cacher un objet » rejouent une étape sur une clinique neuve, à part : ils ne changent pas la séance en cours, ni les écrans des soignants.
- « Cacher un objet » ne retire rien de la réserve : il demande un objet qui n'y est pas (fauteuil roulant, guitare, parapluie).
- « Provoquer une panne » agit en vrai sur la séance en cours (la panne J02 « le lien tombe ») : le robot s'arrête, le bandeau s'affiche sur tous les écrans.
- La remise à zéro remet les pannes, le faux logiciel administratif et l'écran de l'invité. Elle ne remet PAS les tâches, les listes de soin ni le carnet de la séance en cours.
- L'arrivée est tapée par le programme, pas dite. Les chiffres viennent du faux robot.
- [x] K07b (tour 88) : les quatre boutons dans six ordres, puis le scénario rejoué ; la taille du texte des écrans Invité et Patient.

## Les six ordres et la taille du texte (K07b, tour 88)

- Les six ordres sont joués par un programme, sur une clinique d'essai branchée comme le serveur, pas sur le serveur de la séance.
- Six ordres sur les vingt-quatre possibles. Les choix sont toujours les mêmes (allemand, fauteuil roulant) ; le tirage, lui, est au hasard.
- La taille du texte est mesurée dans Chrome sans fenêtre, à la largeur par défaut. Pas sur un téléphone ou une tablette, pas dans Safari.
- Le seuil de 18 px est choisi par moi : ce n'est pas une norme. À revoir avec Hiba.
- Seule la taille est mesurée. Le contraste et « une idée par ligne » ne le sont pas. Aucune personne âgée n'a lu ces écrans.
- L'écran du patient est mesuré pour la patiente du scénario (italien), le jour. Pas dans les autres langues, pas la page du soir.
- [ ] Lire les écrans Invité et Patient avec une vraie personne (de préférence âgée), et noter ce qu'elle dit.

## Le rejeu autonome (T29, tour 89)

- Le dossier est écrit après une répétition jouée par le programme (faux robot, robots simulés, arrivée tapée).
- Les pages ont été ouvertes dans le navigateur intégré de l'application, pas par une personne, pas sur un autre ordinateur, pas dans Safari.
- Les moments sont reconnus par la page « Moments » de J03 : la panne de l'étape 12 (la flotte) n'en fait pas partie, parce qu'elle n'est pas une panne de J02. Les deux « papiers non rangés » viennent de deux étapes différentes.
- « Rien que la séance » : vérifié par un programme (chemins de cet ordinateur, code d'équipe, liens, programmes, images). Les noms des patients inventés sont dans les pages : ce sont des données inventées.
- Le rejeu montre ce qui a été écrit ; il ne remontre pas les écrans tels qu'ils étaient, et il ne rejoue pas le temps.
- [ ] Ouvrir le dossier sur un autre ordinateur, sans Internet, et le faire lire par une personne.
- [ ] Une séance avec le serveur (et pas seulement une répétition) : la commande ne la prend pas encore.

## Le réseau local (T30, tour 90)

- Essayé depuis cet ordinateur, par son adresse du Wi-Fi (192.168.1.43). Aucun vrai téléphone n'a ouvert ces adresses.
- [ ] Les codes QR : pas faits. Aucun outil pour les dessiner ici ; question Q29.
- Le second moyen de trouver l'adresse (`ipconfig getifaddr`) est propre à macOS.
- Les écrans sur un petit téléphone : pas regardés à cette largeur (N02).
- Un Wi-Fi d'hôtel ou d'école peut empêcher deux appareils de se parler : pas essayé ; à vérifier sur place, samedi.
- Les adresses sont en http, sans chiffrement : n'importe qui sur le même Wi-Fi peut les ouvrir. Données inventées seulement ; les boutons demandent le code d'équipe.

## Le robot à roues à deux bras (T31, tour 91)

- La carte `roues_deux_bras` est un EXEMPLE pour le faux robot : aucun robot de ce genre n'a été vu. Tous ses chiffres sont à vérifier ; 5 kg par bras vient du cahier, 0,15 m/s est un choix de prudence.
- L'ébauche `briques/b03_adaptateurs/robots/roues_deux_bras/` : 19 appels « À BRANCHER », rien n'est écrit pour un vrai kit. Sa conformité n'a été essayée qu'avec le faux kit (6 contrôles).
- Les questions du samedi matin (navigation, bouton d'arrêt qui coupe le courant, droit de rouler près du public) n'ont pas de réponse.

## La page des preuves (J07a, tour 92)

- Les huit boutons sont ouverts par un programme, pas par le chef de démonstration devant un jury.
- « Où tourne quoi » : non mesurés aujourd'hui — le temps de réponse et la mémoire des yeux, du gardien, des écrans, de la boîte noire, et la mémoire de l'écoute et de la voix. L'électricité n'est pas mesurée (aucun outil sans droits d'administrateur).
- Les temps de l'écoute et de la voix viennent de la chaîne entière, avec des phrases dites par la voix de synthèse (pas de micro).
- Les preuves 2 et 4 ouvrent la même page « Moments » ; elle lit la dernière séance enregistrée sur cet ordinateur. Sans séance, elle le dit.
- [x] J07b (tour 93) : la commande des preuves et la pièce cassée exprès.

## La commande des preuves (J07b, tour 93)

- Les huit preuves sont jouées par un programme sur le faux robot et des robots simulés. Aucun vrai robot, aucune personne.
- La preuve 6 met une pause « rouler » par l'écran, la voit, la lève ; elle ne vérifie pas ici que le gardien la refuse (c'est l'essai de J05a).
- La preuve 7 réussit parce que la page dit honnêtement qu'aucune parole n'a été recueillie : aucun soignant n'a été rencontré.
- La preuve 8 réussit avec beaucoup de « non mesuré » : elle vérifie que le tableau dit vrai, pas qu'il est complet.
- La commande n'écrit pas le tableau des essais dans le journal de l'équipe (dossier à part) : `python3 lancer.py essais` le fait.

## Le tableau des capacités (K05, tour 94)

- Aucune capacité n'est prouvée sur un vrai robot : le compteur d'essais réels est vide.
- « Prouvé sur le faux robot » regroupe des étapes jouées avec le faux robot et des étapes sans robot du tout (étiquette SIMULÉ) : la case le dit à chaque fois.
- « Vérifié par des tests » veut dire qu'un fichier de vérification existe pour cette capacité ; la page ne relance pas les vérifications.
- Un essai réel est rattaché à une capacité par des mots du nom du geste (`capacites.yaml`) : un nom de geste mal écrit peut tomber dans aucune ligne.
- [x] La commande du concours (tâche KC, tour 96).

## L'avis des personnes (K06, tour 95)

- Aucun avis réel recueilli. Le formulaire a été rempli seulement par des vérifications, avec des avis ESSAI effacés ensuite.
- N'importe qui sur le même Wi-Fi peut envoyer un avis : rien n'empêche une personne d'en envoyer plusieurs.
- Le formulaire n'a pas été ouvert sur un vrai téléphone, ni lu par une personne.
- [ ] Code QR vers le formulaire : attend la réponse à Q29.

## La commande du concours (KC, tour 96)

- Les sept contrôles sont joués par un programme, sur le faux robot et des robots simulés, avec le cerveau de test. Aucun vrai robot, aucune personne, pas Apertus.
- Le contrôle 3 joue le petit programme de la page dans Node, pas dans un navigateur. Sans Node, il est raté (jamais sauté en silence).
- Le contrôle 6 dit vrai sur 0 avis réel : aucun avis n'a encore été recueilli.
- Le contrôle 5 réussit aujourd'hui parce qu'aucune capacité n'est dans la colonne du vrai robot.

## L'étape « contrôle » du chef de démonstration (H05, tour 97)

- Essayée avec des contrôles d'essai et le contrôle 7 de la clinique, sur le faux robot. Les sept scènes ne sont pas encore jouées par le chef : c'est N03.
- Un contrôle ne reçoit pas de plan B (les plans B du chef sont faits pour les phrases dites).
- Un contrôle tourne dans un fil à part ; l'arrêt d'urgence interrompt l'étape côté chef, mais ne peut pas arrêter une pièce déjà en train de calculer (elle finit dans son fil).

## La séance unique (N03a, tour 98)

- La durée mesurée (27,4 s pour les scènes 1 à 3) ne compte pas le temps d'une personne qui parle, qui marche ou qui tend les papiers : l'arrivée est tapée, les coches et les validations sont faites par le programme. Une démonstration devant le jury durera plus longtemps.
- Le point coché par la livraison du coussin : à l'étape 7 la soignante a déjà coché le point 4 ; la livraison ne coche donc rien de nouveau (il reste la sonnette). Quel point le coussin doit cocher reste à décider avec Hiba (déjà noté pour l'étape 8).
- Les plans B des scènes ne sont pas joués dans la séance unique (une étape « contrôle » n'a pas de plan B).
- [x] N03b (tour 99) : les scènes 4 à 7 dans la même séance.

## Les sept scènes d'un seul trait (N03b, tour 99)

- 51,6 s à vitesse normale : ce sont les deux courses du faux robot. Les personnes (la patiente, l'accueil, la soignante, le médecin) sont remplacées par le programme : leurs gestes et leurs paroles ne prennent pas de temps ici. Une démonstration devant le jury durera nettement plus longtemps.
- La fiche de vérité de l'étape 13 est calculée sur la séance, mais pas gardée : la page `/clinique/fiche-de-verite` montre toujours la dernière grande répétition.
- « Rien n'est sorti » surveille ce programme seulement (comme l'étape 14 de la répétition).

## Le dernier passage dans un navigateur (N02, tour 100)

- Toutes les pages ont été vues par un programme dans Chrome sans fenêtre, sur cet ordinateur. Aucune personne ne les a regardées sur un vrai téléphone, ni dans Safari.
- Deux pages n'ont pas été ouvertes par ce passage (la fiche du faux logiciel, la page « Pourquoi ? » d'une tâche du tableau des tâches).
- Le tableau des capacités est serré sur un téléphone (mots coupés aux syllabes).
- [ ] Regarder les pages sur un vrai téléphone, avec une personne, samedi.

## Les guides pour l'équipe (T32, tour 101)

- Les douze guides et leurs 44 petites tâches ont été écrits par l'agent, puis relus par un relecteur neuf (un autre agent), qui a trouvé 15 points (des phrases fausses, des tâches dont le test ne prouvait rien) : tous corrigés. Aucune personne de l'équipe ne les a encore lus.
- Une vérification contrôle que chaque fichier, chaque commande et chaque page cités existent. Elle ne contrôle pas que chaque phrase est juste.
- Les tâches n'ont été faites par personne : leur durée (« moins d'une heure ») est une estimation.

## La traduction de l'écran du patient (H03b, tour 103)

- Allumée. Les mots (italien, allemand, anglais) sont écrits par l'agent, pas relus par quelqu'un qui parle la langue. Ce qui n'est pas dans la table reste en français (habitudes, titres des documents).

## La page des paroles des soignants (J06b-b, tour 104)

- Essayée avec des paroles d'ESSAI dans un fichier provisoire. Aucune vraie parole n'a été recueillie ; aucun soignant n'a été rencontré.
- Le filet qui met de côté une ligne avec un nom ne voit pas un prénom seul : la relecture par une personne de l'équipe reste nécessaire.

## Ébauche AgileX PiPER, le bras (14.11.2026)
`briques/b03_adaptateurs/robots/agilex_piper/`, fiche `briques/b03_adaptateurs/fiches/agilex_piper.md`. **Non testé sur vrai robot.**
- La liaison sait seulement se connecter en écoute seule et lire l'état. Essayée avec une doublure : testé sur faux robot.
- Les trois arrêts et tous les mouvements disent « À BRANCHER » : l'arrêt « rapide » du kit fait descendre le bras, sa remise à zéro le fait tomber (lu). Le choix se fait avec le responsable sécurité.
- Le test de conformité « faux kit » n'essaie pas `liaison.py` (l'adaptateur y met encore le faux kit du projet).
- Rien n'a été envoyé au bras. Son kit (`piper_sdk`, MIT, Linux seulement) n'est installé nulle part par nous. La carte garde 0 partout.
- Jamais essayé : le boîtier USB du bras sur un ordinateur, le courant dans le bras, la version de son logiciel, la main Leadtron DH116 au bout du bras.

## Ébauche Reachy Mini (15.11.2026)
`briques/b03_adaptateurs/robots/reachy_mini/`, fiche `briques/b03_adaptateurs/fiches/reachy_mini.md`. **Non testé sur vrai robot.**
- L'équipe a fait bouger et parler le robot avec le programme du fabricant, sur un autre ordinateur. Notre système ne lui a jamais rien envoyé.
- La liaison lui parle par six adresses web de son programme de fond. Essayée avec une doublure (un faux programme de fond) et un petit serveur d'essai : testé sur faux robot.
- **Nuit du 14 au 15.11.2026** : le kit du fabricant est installé à part (`~/reachy_env`). Son programme de fond, version 1.14.0, a tourné EN MODE SIMULÉ (`--mockup-sim` : un faux robot du fabricant) sur ce MacBook, et notre liaison a été essayée dessus à la main : état, arrêt, regarder, « oui », « non », arrêt au milieu d'un geste, arrêt d'urgence. C'est toujours **testé sur faux robot**. Ces essais à la main ne sont pas dans les tests automatiques (ils demandent le kit du fabricant).
- **Regarder** (tourner lentement la tête vers « devant », « patient », « collegue », « soignant ») et **deux gestes** (« oui », « non ») sont branchés, sur faux robot seulement. Choix de l'équipe, pas mesurés sur le robot : 40° de côté et 20° de haut-bas au plus, 20° par seconde en moyenne pour regarder, 25° par seconde pour un geste, jamais moins d'une seconde par mouvement. La vitesse de pointe est plus haute que la moyenne (le fabricant accélère puis ralentit) : pas mesurée.
- Les angles du fichier `directions.yaml` sont des valeurs de départ, **pas mesurées** : où sont vraiment la patiente et le bras, et dans quel SENS tourne la tête, se règle sur place, à vitesse lente.
- Vu sur le simulateur du fabricant, donc à revoir sur le vrai robot : un ordre de tête envoyé pendant qu'un autre joue est perdu sans le dire ; une cible trop loin n'est pas refusée, elle est ramenée, et le corps tourne ; moteurs coupés, le faux robot du fabricant bouge quand même.
- **Le gardien demande un humain avant chaque geste** (« oui », « non ») : sa règle n° 1 dit « à 1 mètre des personnes quand il fait un geste », et il ne sait pas où sont les gens. « Regarder » n'est pas dans cette règle : il passe sans accord. Rien n'a été changé à cette règle (question Q32 pour Hiba).
- « Quand Iris refuse, la tête fait non » (`briques/clinique/reactions_tete.py`) : écrit, **éteint par défaut**, essayé sur faux robot avec un fichier de règles fabriqué pour l'essai. Avec les règles du projet, aucun geste ne part (le gardien demande un humain), mais chaque refus laisse une trace : le gardien annonce « aide demandée » avant que la demande soit retirée (une carte « en attente d'un humain » peut apparaître sur l'écran du jury). Autre limite : pendant le geste, une autre demande de mouvement échoue (« robot occupé »).
- Les mots des directions et des deux gestes (« guarda la paziente », « scuoti la testa », « schüttle den kopf », « 摇头 »…) sont écrits par un agent, **pas relus** par quelqu'un qui parle la langue. Pas d'espagnol pour ces mots.
- Les mots des directions ne sont ajoutés au monde que par l'écran (`python3 lancer.py`), quand le Reachy Mini est le robot du système. Avec les autres commandes (micro direct, porte des agents, chef de démonstration), « regarde la patiente » fait regarder devant. « Regarde à gauche » fait toujours regarder devant (pas de mots pour gauche et droite) ; le robot dit « Je regarde : devant ».
- **Trois relectures des mouvements de tête** (trois relecteurs neufs, 15.11.2026). La première : 16 défauts dont 5 graves, tout réécrit. La deuxième, sur la réécriture, avec de vrais fils et environ 1 800 essais d'arrêt : 3 des 5 défauts graves fermés, 2 encore ouverts par un autre chemin (une lecture d'état ratée effaçait l'échec d'un geste ; un programme de fond lent laissait le geste continuer après « échoué »), et 17 défauts moyens ou petits. **Ces dernières corrections ne sont relues par personne d'autre que leur auteur.** Elles ont chacune un essai, sur la doublure, dans un seul fil.
- Ce que le deuxième relecteur n'a pas pu vérifier, et qui reste ouvert : un ordre de tête traité par le vrai programme du fabricant APRÈS que notre client a abandonné (la liaison guette 1,5 s et annule ce qui apparaît : essayé sur un faux kit seulement) ; les temps les plus longs (un arrêt normal peut prendre 1,3 s avec un programme de fond lent : l'adaptateur passe alors à l'arrêt d'urgence).
- Limites connues des mots : une phrase qui parle de quelqu'un (« elle secoue la tête ») est prise pour une demande de geste (le gardien demande alors un humain) ; les annonces dans les autres langues gardent des mots français (« I am looking at: devant », « Ich mache die Geste: oui »). Le cerveau à modèle de langue n'a pas été essayé avec des gestes nommés « oui » et « non » : il pourrait répondre par un geste à un simple « non » (le gardien demanderait un humain).
- Une vitesse de geste demandée sous le quart est jouée au quart. Un geste demandé tête au bord de ses limites est refusé.
- **Se lever et se coucher par notre système** (15.11.2026, demande de Hiba : sans l'interface ni le réveil du fabricant). « lever_la_tete » allume les moteurs puis monte la tête en 6 secondes (12 en mode lent) ; « coucher_la_tete » la redescend en 6 secondes vers la pose couchée du fabricant, puis coupe les moteurs. Essayé sur la doublure et, à la main, sur le faux robot du fabricant : **testé sur faux robot**. Relu par un quatrième relecteur neuf (aucun défaut grave sur l'allumage des moteurs dans 236 essais d'arrêt à deux fils ; onze défauts moyens ou petits, corrigés par leur auteur, **pas relus depuis**). Il n'a pas eu le temps de vérifier les faux « réussi » de ces deux gestes par l'adaptateur entier, ni les mots dans les six langues.
- **Jamais vu sur un vrai robot, et impossible à voir sur un faux** : ce que fait la tête quand ses moteurs s'allument (lu : elle tient sa position ; lu aussi : une course rare où elle repartirait vers son ancienne cible — notre liaison relit la position 0,12 s après et recoupe si elle a bougé de plus de 2° ou 5 mm) ; si la pose couchée visée touche le socle avant d'arriver ; dans quel mode sont les moteurs au démarrage du programme du fabricant (lu : celui qu'ils avaient avant).
- Vitesses de pointe calculées pour se lever ou se coucher en 6 secondes : tête 10° par seconde et 16 mm par seconde ; antennes 52° par seconde. Le relecteur a mesuré environ un tiers de plus sur le faux robot du fabricant, sans savoir si c'est sa mesure : **pas tranché**.
- **15.11.2026, premier contact avec le vrai robot** : le programme du fabricant, lancé par Hiba avec `outils/lancer_tete.sh`, a trouvé les moteurs 10, 17 et 18, pas les moteurs 11 à 16, et s'est arrêté (« Missing motors »). Son outil de recherche (`scan_motors`) dit la même chose. Rien n'a bougé. Notre système n'a rien envoyé au robot. Cause pas encore trouvée (alimentation ou câble : à vérifier).
- Les arrêts sont des PROPOSITIONS : l'arrêt normal ne voit que les mouvements lancés par les adresses web (il vérifie ensuite si la tête bouge encore) ; l'arrêt d'urgence coupe les moteurs, ce qui n'est pas un verrou. Réarmer ne rallume rien.
- Montrer, parler, écouter : pas branchés (la voix et l'écoute restent au Mac).
- Jamais essayé : le vrai robot, une version Wireless, la tête qui s'affaisse quand on coupe les moteurs, le mode des moteurs quand le programme de fond démarre sans réveil.
- Le programme de fond du fabricant envoie par défaut des mesures d'usage sur Internet et va chercher des gestes en ligne : à couper (voir la fiche). « Rien ne sort de l'ordinateur » n'est pas vérifié pour lui.

## La main Leadtron DH116 (15.11.2026)
- **Essayée par un humain avec le logiciel du fabricant, pas par notre système.** Le 15.11.2026 vers 15 h, Hiba a fait bouger la main (modèle DH116, main gauche, étiquette : 12 à 24 V, 2,5 A, bloc d'origine) avec le logiciel « LHandPro » 1.4.5 du fabricant, sur le MacBook du projet, par le boîtier bleu (« CANFD Analyser », vu en USB). Ni Iris ni le gardien n'y sont pour rien : aucun ordre de notre système n'est allé à la main.
- **Premier essai de notre système sur la vraie main, le 15.11.2026 vers 17 h 35 : le test « sans mouvement » a RÉUSSI** (15 contrôles ✔, mention « testé sur vrai robot »), commande tapée par Hiba. Notre liaison s'est connectée deux fois par le boîtier bleu (« DOF: total 11, active 6 »), a lu l'état, et a envoyé l'arrêt d'urgence proposé (arrêt, puis coupure des moteurs, déjà coupés). AUCUN mouvement n'a été commandé. Ce test ne prouve rien sur les gestes.
- **Premier mouvement commandé par notre système sur un vrai robot, le 15.11.2026 vers 17 h 40 : le test complet de la main a RÉUSSI** (23 contrôles ✔, « testé sur vrai robot »), commande tapée par Hiba, qui a confirmé à l'œil « le robot a fait le mouvement prévu ». Le seul geste joué est « preparer_la_main » : moteurs allumés, puis mise en position de départ **à la vitesse et à la force du fabricant** (pas les nôtres), puis arrêt d'urgence. Hiba dit : « ça a bougé un peu ». **« tenir_doucement » et « ouvrir_la_main » n'ont JAMAIS été joués sur la vraie main** : nos limites de vitesse et de force n'ont donc encore jamais été essayées en vrai. Ce test s'est fait par l'outil de conformité, pas par le cerveau ni par l'écran.
- **Premier essai par le système entier (cerveau, gardien, accord humain sur l'écran, prise), le 15.11.2026 vers 18 h 45, sur la vraie main, main vide** (journal de l'écran copié par Hiba) : « prépare la main » → accord de Hiba → geste **réussi** en 2 secondes. Puis « tiens doucement » (toutes petites cibles, courant 150 pour mille) → **RATÉ, et dit raté** : le pouce (flexion) s'est arrêté à 536 positions de sa cible de 600, l'auriculaire a dit « couple atteint » sans avancer ; les autres doigts sont arrivés. Ensuite « prépare la main » a raté deux fois (« mise en position de départ pas finie après 12 s », puis « la main bouge déjà »). Cause **pas établie** ; hypothèse : notre courant (150 pour mille) est trop faible pour ces deux doigts, et cette limite reste dans la main pendant la mise en position de départ suivante. À vérifier avec le logiciel du fabricant. Aucun geste de fermeture n'a donc encore réussi par notre système.
- La pièce de Iris pour la main existe depuis le 15.11.2026 (`briques/b03_adaptateurs/robots/leadtron_dh116/`) : trois gestes (préparer la main, tenir doucement, ouvrir la main), 228 essais sur une fausse main, relue une fois par un relecteur neuf (1 défaut grave et 9 autres, corrigés par leur auteur ; **ces corrections ne sont pas relues**). Pas de « saisir » ni de force en newtons.
- La bibliothèque USB livrée avec le kit de la main fait planter Python sur ce Mac ; Iris utilise celle du logiciel du fabricant (`/Applications/LHandPro.app`), par un lien posé dans le dossier du kit. Si ce logiciel est désinstallé, la main ne se connecte plus.
- Le kit du fabricant (`LHandProLib`) est téléchargé hors du projet ; sa licence n'est pas indiquée.
- Le boîtier bleu ne se déclare à un ordinateur qu'avec un câble à grande fiche (USB-A) ; avec un câble à deux petites fiches (USB-C), ni le MacBook ni le PC ne le voient.
- Le manuel lu en ligne disait « 12 à 48 V » ; l'étiquette de CETTE main dit 12 à 24 V. C'est l'étiquette qui compte.
- **Version du 15.11.2026 au soir (quatorze gestes, limites du fabricant : 1000 pour mille, 20000 positions par seconde)** : **testée sur fausse main seulement.** 541 essais passent (dossier de la main, accord d'avance, règles « aucun contournement »), et le test de conformité sur la fausse main réussit — vérifié par le coordinateur, qui n'a pas écrit la pièce. Un relecteur neuf l'a relue le 15.11 au soir, sur fausse main : **aucun défaut trouvé dans l'arrêt** (environ 160 essais d'arrêt en plein geste), aucune valeur hors limites n'est partie. **Défauts trouvés et PAS corrigés à cette heure** : (1) un doigt bloqué avant sa cible peut compter comme « arrivé » pour tous les gestes : « réussi » à l'écran ne prouve pas la forme de la main ; (2) si la vraie main se dit « en marche » tant qu'un doigt pousse sur le doudou, tout geste suivant est refusé jusqu'à un « stop » (pas vérifié sur la vraie main) ; (3) « tiens doucement » puis « tiens fort » sur un doudou qui ne cède pas : dit raté ; (4) la « vague » peut rater à tort si le kit du fabricant répond lentement — **vu aussi sur la fausse main le 16.11.2026 : son essai échoue environ une fois sur trois sur une machine chargée ; il est marqué « échec attendu par moments » dans le fichier d'essais, la liaison n'est pas corrigée** ; (5) les ouvertures de doigts ne sont pas ordonnées (le pouce peut gêner l'index dans « compter ») ; et six petits défauts (tirage écrit trop tôt, nombres écrits avec un zéro devant dans `gestes.yaml`, textes périmés dans la fiche). **Aucun de ces gestes n'est essayé sur la vraie main ; le test sur la vraie main est à refaire** (la liaison et la carte ont changé). Les formes des gestes (`gestes.yaml`) sont des valeurs de départ, pas mesurées, surtout le pouce.
- Les phrases de la scène de lundi (« Rock, paper, scissors! », « Hold gently. », « Robot, squeeze harder! », « Open the hand. », « Count to five. », « Stop! », « Iris, thumbs up! ») : essayées le 15.11 au soir, **tapées, sur fausse main**, par le système entier. **Au micro : pas mesuré.**
- Le tirage de pierre-feuille-ciseaux n'est pas affiché sur l'écran (il est seulement dans l'état de la liaison).
- Un doigt bloqué par un autre doigt peut passer pour « arrêté sur un objet » : un geste de travers peut être dit réussi (dit par l'auteur de la pièce, pas corrigé).

## Le petit robot PrimeBot Q1 (15.11.2026)
- **Notre système ne lui envoie rien et ne l'entend pas.** L'équipe a vu le 15.11.2026 qu'un petit programme en texte (JSON), collé à la main dans son application, lui fait dire un mot (« boulangerie »). L'équipe a ensuite exporté le programme du geste « fist bump » (poing contre poing, bloc `q1_action`, code 3003). Un outil (`briques/clinique/programmes_q1.py`, 24 essais) écrit des programmes avec ces deux blocs, et aucun autre code de geste. Les programmes de la scène sont dans `docs/projet/PROGRAMMES_Q1.md`.
- **Pas essayé sur le robot** : nos programmes eux-mêmes (seule la forme d'UN bloc a été vue marcher), plusieurs blocs à la suite, une phrase suivie d'un geste, l'italien, l'espagnol et le français dans sa voix, les phrases longues. La phrase italienne de la scène est écrite sans locuteur : **à faire relire**.
- **Les quinze autres gestes (salut, cœur, refus, trois danses…)** : leurs numéros sont lus dans le kit public du fabricant (`McPresetMotion.msg`, partie « Q », 15.11.2026), où le 3003 est bien « fist bump ». **Personne ne les a vus marcher dans l'application** : rien ne dit qu'elle accepte ces numéros. Le programme d'essai de 30 secondes (`docs/projet/PROGRAMMES_Q1_ESSAI.md`) n'est pas essayé ; sa durée est un calcul. La marche et l'attente : leurs blocs ne sont pas connus, rien n'est écrit pour eux. Le poing contre la patte de Petit Suisse, et le poing contre le poing de la main robot : jamais essayés.

## La suite complète d'essais, le 15.11.2026 au soir
- `python3 lancer.py tests` : **2779 essais passent, 3 échouent, 35 sautés.** Un échec venait d'un mot italien ajouté ce soir (« ti voglio bene » contient « bene », qui veut dire « oui ») : corrigé, l'essai repasse. **Les deux autres viennent de l'état de ce MacBook ce soir** (l'écran de Iris tourne sur le port 8000, et `reglages.yaml` désigne la vraie main) : dans les deux cas le programme lancé par l'essai a REFUSÉ de démarrer, ce qui est le bon comportement. Ils n'ont pas été rejoués dans l'état normal (faux robot, écran arrêté) : à refaire quand les réglages reviendront au faux robot.

## Le film fabriqué avec Google (16.11.2026, de 1 h 30 à 9 h)
- **Le film existe** : `film/sortie/film_entier.mp4` (4 min 02 s) et ses huit parties. 14 vidéos et 12 images fabriquées avec les modèles de Google (images : `gemini-3-pro-image` ; vidéos : `gemini-omni-1.2-flash` — Veo a été arrêté le 22.10.2026, lu dans la documentation de Google le 16.11) ; voix : `gemini-3.8-flash-tts`, timbre « Sulafat », accélérée de 5 %. Dépense calculée d'après la page des prix : 11.0 dollars (pas la facture). Accord de Hiba : « Oui, les 13 importants ».
- **C'est un film d'idée** : chaque image porte la mention « Concept film — AI-generated images — not a real recording ». Le robot du film n'a jamais été commandé par notre système. La photo de Hiba a été recadrée et les personnes cachées avant l'envoi à Google.
- **Contrôlé par le coordinateur sur des images extraites, pas regardé en entier ni écouté** : la voix de Google n'a été entendue par personne ; le niveau du son est mesuré, pas jugé. Vingt et un plans sur trente-cinq n'ont pas leur propre image : ils reprennent une image ou un morceau de vidéo déjà fabriqués (liste `REMPLACANTS` dans `film/monter.py`). Dans le plan 20, le côté où se place la soignante n'est pas vérifié par rapport au texte (« her right side »).
- Le film dure 2 secondes de plus que quatre minutes, et les parties de la maman sont des durées calculées : rien n'a été répété avec elle.

## La présentation, version 11 : Iris, et le robot de la photo (16.11.2026, vers 1 heure)
- La mascotte s'appelle maintenant **Iris** (le nom « Iris » n'apparaît sur aucun écran du vrai système : vérifié par une recherche dans le code). Le film montre le grand robot noir à roues de la photo de Hiba : **notre système ne l'a jamais commandé**, il est montré sans marque comme « le robot que nous voudrions ». `film/PROMPTS_VEO.md` : 35 demandes pour Veo, jamais essayées ; les réglages de Veo sont cités de mémoire. Le montage (35 plans, toc, eau) marche avec des cartons gris ; trois plans utilisent le portrait d'Iris en attendant.

## La présentation, version 10 : Iris est le marteau du bisse (nuit du 15 au 16.11.2026)
- `PRESENTATION_JURY_EN.md` : nouvelle histoire, nouveaux textes de Iris (durées mesurées avec la voix du Mac). **Aucune image ni vidéo du marteau n'est faite, la voix naturelle non plus.** Rien n'a été joué ni chronométré. Le « toc » est une image du film : le vrai système ne fait pas ce bruit. L'histoire du marteau reprend la vérification faite pour Proxsis le 13.10.2026 (confirmé en général, sans date ni nom de bisse).

## La reconnaissance du matériel médical : une image réelle (16.11.2026)
- `docs/media/detection-instrument-tray.png` : la sortie du modèle des coéquipiers sur une vraie photo d'un plateau d'instruments, donnée par Hiba le 16.11.2026 (« après entraînement sur une photo réelle prise hier »). On y voit une seringue et une pince en plastique reconnues, une deuxième boîte sur la même pince, une étiquette « pince en métal » peu sûre (0,32), et une pince chirurgicale non reconnue. **C'est une seule image : aucune précision n'est mesurée sur des photos que le modèle n'a pas vues, et personne ici n'a fait tourner le modèle.**

## Le spectacle du Q1 et le film en 3D (15.11.2026, fin de soirée)
- **Version 2 du spectacle (cinq actes, vingt moments de 5 secondes au plus, six mots au plus par phrase)** : écrite après l'essai de l'équipe (« au-delà de 5 secondes, il saute le moment suivant »). **Pas essayée sur le robot.** La durée de chaque geste n'est pas connue. La marche, les demi-tours et s'asseoir ne sont pas dans les programmes : le pilote les fait depuis l'application entre deux actes ; leurs blocs ne sont pas connus.
- Ancienne version, remplacée — `docs/projet/SPECTACLE_Q1.md` : deux programmes (quinze et huit moments) sur le modèle « dire, geste, attendre la fin du geste » que l'équipe a réglé dans l'application. **Pas essayés sur le robot.** Les durées sont calculées. L'attente de 20 secondes après une danse n'a jamais été essayée (seul « 5 » a été vu). La marche et les doigts ne sont pas écrits : leurs blocs ne sont pas connus.
- `film/sortie/partie_2_3d.mp4` : la scène de Iris en 3D, dessinée en code (aucune bibliothèque, aucun service). C'est un film d'idée, avec sa mention fixe. Elle s'arrête dans le pré : le passage vers la clinique n'existe que dans la version à plat. Calée sur la voix du Mac, pas sur la voix finale.

## La présentation, version 9 : le film (15.11.2026 au soir)
- La présentation est maintenant une explication sur un film (`PRESENTATION_JURY_EN.md`) ; la version jouée est gardée dans `PRESENTATION_JURY_EN_v8.md`. **Le film n'existe pas encore** : il y a le texte, la liste des plans et la voix de Iris (quatre sons faits avec une voix du Mac, durées mesurées). Rien n'a été joué ni chronométré avec la maman.
- Le film montre des rôles PRÉVUS (accueil, étage, nuit, thérapie) : aujourd'hui ils tournent sur des robots simulés. Le « jeu pour les doigts raides » n'a jamais été essayé avec un patient ni un thérapeute. Le film doit porter sa mention fixe « Concept film — AI-generated images — not a real recording ».
- Ce que Iris dit de la loi : elle dit que la vérification reste à faire avant un vrai patient. Aucun spécialiste n'a été consulté. Les noms de lois de la feuille de questions sont cités de mémoire : à vérifier.

## La présentation, version 8 (15.11.2026 au soir)
- Le scénario (`PRESENTATION_JURY_EN.md`) n'a jamais été joué en entier, ni chronométré. Le compte du temps est un calcul.
- La console des collègues (« Clinic Pilot ») : son code n'est pas sur cet ordinateur ; ce que la présentation en dit vient de leur document, pas d'un essai.
- La reconnaissance du matériel médical par caméra (YOLO, partie 12 du document des collègues) : **leur document la dit « planned », rien n'est construit.** Le cahier d'entraînement dont il parle (`briques/b05_yeux/entrainement/yolo_medical_kaggle.ipynb`) n'est pas dans ce dossier ; personne ici ne l'a vu tourner. L'idée « ces yeux diraient au gardien où sont les personnes » est une idée, pas un programme.

## Le bras AgileX PiPER (15.11.2026)
- Le boîtier noir du bras n'a pas été vu par le MacBook le 15.11.2026 (pas essayé avec le bon câble). L'ordinateur du collègue est un Windows avec Ubuntu dedans (WSL) : il ne voit pas les prises USB, c'est une impasse pour le bras. La machine Linux du MacBook (« Ubuntu-bras ») est démarrée ; l'installation d'Ubuntu dedans n'est pas confirmée finie.
## Le MacBook (13.11.2026)

- Préparé et vérifié par la session de l'assistant du MacBook. 4 essais y ratent pour des causes de la machine : le port 8000 pris par un autre projet (HackVS) ; Chrome 150 trop ancien pour la mesure en largeur de téléphone (à revoir après mise à jour de Chrome).
- La vérification rapide y dure 769 s (plus que les 5 minutes acceptées) : à remesurer une fois Chrome à jour.
- Rien n'y tourne encore avec l'iMac : c'est H15.

## H14 — la parole proposée par le cerveau (13.11.2026, tour 105) — testé sur faux robot
- La règle est dans la chaîne (`commun/chaine.py`) seulement. **Le tirage Apertus (`briques/clinique/tirage_apertus.py`) ne passe pas par la chaîne** : il envoie l'action d'Apertus droit au gardien puis au faux robot. Il laisse donc encore partir une parole d'Apertus, et ne mesure plus exactement la vraie chaîne. Pas corrigé (trouvé par le relecteur).
- `chaine_mesure.py` compte « D'accord. » comme réponse pour toute action, « parler » compris : la mesure ne suit pas encore la phrase fixe.
- Un modèle de langue peut toujours faire dire un texte libre par une **réponse de discussion** ou une **question écrite par lui** : la règle C vise seulement l'action « parler ». « Je vais prendre le coussin » peut donc encore sortir par ce chemin (à vérifier avec Apertus).
- L'écran simple montre encore « compris : parler (texte=…) » avec la phrase refusée (l'événement est émis avant la règle). Le robot ne la dit pas.
- Un agent reçoit « refusée » sans raison écrite ; une parole refusée compte comme « compris » pour la main levée (brique 8).
- « Dis bonjour à tous » reçoit maintenant aussi la phrase fixe : conforme au texte de la règle C.

## H16a — « C'est bien ça » pour une demande au robot faite à la voix (13.11.2026, tour 106) — testé sur faux robot
- Pas de micro : la « phrase entendue » est tapée dans le champ de la tablette. Aucune vraie écoute n'a été confirmée ainsi.
- La course du robot part **sans attendre** le bouton : la confirmation dit seulement au carnet qu'une personne a relu la phrase. Faire attendre le robot serait un autre choix, à demander à Hiba.
- Après la demande, d'autres lignes de la même tâche écrites par un humain (« Je l'ai vu », « C'est fait », une reprise) disent « validée par un humain : oui » : ce « oui » valide ce geste-là, pas la phrase ; la tâche garde « phrase à confirmer : pas encore ».
- Le bouton dans la zone des réponses de la liste s'efface à la phrase suivante ; il reste sur le tableau des demandes du soignant. Un « C'est bien ça » fait sans lien (hors ligne) n'est pas gardé pour plus tard.
- Le clic en JavaScript n'est pas essayé dans un vrai navigateur : l'essai lit la page et appelle les adresses.
- Les coches à la voix restent « validée : oui » (question Q32). Pas de dictée à la voix aujourd'hui.

## H17 — l'accueil et ses trois points de la liste de sortie (13.11.2026, tour 107) — testé sans robot
- L'accueil voit **toutes** les personnes qui ont la liste de sortie, quel que soit le jour : une personne déjà sortie reste affichée. Aujourd'hui une seule fiche a cette liste (Madame Sophie L., p09). Le choix (toutes, ou seulement celles qui sortent aujourd'hui ou demain) est la question Q33.
- La « fin de poste » et la « prise de poste » de l'accueil ne rappellent pas ses trois points : un point oublié n'est rappelé nulle part. Pas de « reporter » ni de « passer à la relève » pour ces points, pas de coche hors ligne.
- Le bouton « Fait » de l'accueil est un formulaire qui recharge la page (pas le script des autres boutons). L'écran traduit n'est pas essayé (l'accueil est en français).

## H18 — la place de R1 sur le tableau de flotte (13.11.2026, tour 108) — testé sur faux robot
- La place est « le lieu du plan le plus proche » de la position lue sur la prise, sans limite de distance (même règle que H12). Sur un vrai robot : pas essayé.
- Le chiffre de la batterie n'est pas montré : l'essai établi du tour 81 interdit « 100 % » sur cette ligne (question Q34).
- Une lecture sert 1,5 s pour toutes les pages ouvertes ; plusieurs lectures en même temps sur un vrai adaptateur : à vérifier. Si R1 est « en panne » dans le monde des robots, la ligne montre quand même la place lue.

## H19a — les codes QR (13.11.2026, tour 109)
- Dessinés par segno 1.6.6 et **relus par le Mac** (CoreImage) ; **pas essayé avec un vrai téléphone**. Le lecteur du Mac est plus indulgent qu'un téléphone (il relit même un code sans marge) : la marge et le fond blanc sont vérifiés à part.
- Pas encore sur la page des téléphones (question Q35). Le dessin a une taille fixe (pas de `viewBox`) : s'il est réduit par la page, à vérifier.
- segno n'est pas encore sur le MacBook (feu orange, à demander à Hiba dans sa session).

## H20 — le modèle d'écoute « medium » pour l'interprète (13.11.2026, tour 110) — mesuré sur l'iMac, aucun robot
- Mesuré deux fois sur les dix phrases de l'interprète, à côté de « small » (une fois medium en premier, une fois small en premier). Voix de synthèse du Mac, pas une personne, pas de micro, pas de bruit de salle.
- Chemin en deux temps (l'écoute, puis Apertus) : **8 phrases sur 10 sans erreur comptée, pour les deux modèles**. Délai médian : medium 3134 puis 3042 ms ; small 1647 puis 1614 ms. Le plus long : medium 8606 ms (mesuré en premier, à froid ; la voix a pris 4298 ms sur cette phrase) puis 4533 ms ; small 1961 puis 2154 ms.
- Chemin direct (whisper traduit seul) : medium 3 sur 10 sans erreur comptée, small 4 sur 10 ; le sens n'est pas jugé (medium semble traduire mieux certaines phrases : à relire par une personne).
- Mémoire libre de tout l'iMac au plus bas : medium 0,78 puis 1,37 Go ; small 2,45 puis 2,51 Go (Apertus et les autres programmes compris ; pas la mémoire du modèle seul).
- Conclusion tirée des chiffres, à confirmer par Hiba : medium n'améliore pas le chemin en deux temps et le ralentit ; « small » reste le choix par défaut. Rien n'est changé dans les réglages.
