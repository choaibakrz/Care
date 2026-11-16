# Décisions

## Prises (validées par Hiba le 11.11.2026)

| Sujet | Choix | Autre option gardée prête |
|---|---|---|
| Langage | Python 3.11+ | — |
| Installation | pip + dossier `.venv` | — |
| Courrier interne | bus d'événements dans un seul programme | MQTT |
| Cerveau | llama.cpp ou MLX : **le plus rapide mesuré sur le Mac** | l'autre |
| Modèle | Apertus 8B v1.0 compressé 4 bits | Apertus v1.1 4B (officiel, MLX) ; cerveau « à règles » |
| Écoute | whisper.cpp ou mlx-whisper : **le plus rapide mesuré** | faster-whisper (processeur) |
| Voix | voix Piper lues par sherpa-onnx (Apache-2.0), licence de chaque voix vérifiée | Kokoro |
| Suisse allemand | compris, réponse en allemand, le robot le dit | — |
| Conversation | petite chaîne maison (fin de parole + interruption) | pipecat |
| Yeux | OpenCV + RapidOCR ; objets nommés et personnes : à proposer | — |
| Écran | FastAPI + page web locale | NiceGUI |
| Boîte noire | une ligne JSON par événement | + SQLite plus tard |
| Ordinateur-cerveau | iMac M4 16 Go et MacBook M2 16 Go ; chacun peut tout faire seul | — |

## Prises pendant l'étape 1 (à relire par Hiba)

- **Ticket du gardien** : signé (HMAC, une signature secrète), à usage unique, valable 5 s. La prise refuse tout sans ticket.
- **Double vérification** : le gardien ET la prise vérifient la carte d'identité et les limites.
- **Limites par défaut** : 0,3 m/s et 15 N, même si la carte autorise plus. Au-dessus : refus expliqué.
- **Après un arrêt d'urgence**, le robot reste bloqué jusqu'à ce qu'un humain le réarme.
- **Cerveau « hors carte »** : s'il comprend une action que le robot ne sait pas faire, il ne la propose pas ; le robot explique.
- **Le cerveau à règles lit les vitesses** dites en chiffres (« 5 mètres par seconde ») pour que le gardien puisse refuser.
- **Après relecture sécurité** (12 constats, tous corrigés et testés : `tests_bout_en_bout/test_relecture.py`) :
  ticket lié à un robot et à une copie de l'action ; nombres non valides refusés ; plafonds appliqués aussi par la prise ;
  une seule action longue à la fois ; « arreter » jamais refusé ; action perdue de vue → arrêt d'urgence ;
  arrêt d'urgence vérifié et réessayé ; réarmement annulé par un nouvel arrêt.
- **Contre-relecture** (8 points, corrigés et testés) : entiers géants refusés ; distance totale dx/dy bornée ;
  place réservée avant de démarrer une action longue ; action perdue de vue après **1 s** sans nouvelles
  (et non 0,15 s, trop sensible au Wi-Fi) ; un appui = un arrêt compté ; noms d'hôte locaux vérifiés (contre le « rebond DNS »).
- **Écran** : l'arrêt d'urgence est ouvert à tous ; parler, réarmer et provoquer une panne demandent d'être sur
  l'ordinateur-cerveau ou d'avoir le **code d'équipe** (`reglages.yaml → ecran.code_equipe`, à choisir samedi).
- **Taux d'erreur par langue** : en direct, on compte les demandes « non comprises » ; le vrai taux se mesure au banc d'essai (étape 3).

## Prises par Hiba le 11.11.2026 (après l'étape 1)

- Dépôt privé `sahimhiba-debug/leukerbad`, aucun secret dedans. `reglages.yaml` hors du dépôt ; `reglages.exemple.yaml` sans code.
- Code d'équipe : choisi par Hiba, écrit à la main sur chaque Mac. Les tests utilisent « code-de-test ».
- Yeux : **MediaPipe** pour les personnes et objets courants. **OWLv2** plus tard, en option qu'on allume seulement
  si la mémoire le permet (4 Go de marge seulement) : aucune grosse bibliothèque chargée en permanence.
- Deux Mac : partage accepté (cerveau sur l'iMac, le reste sur le MacBook) ; chaque Mac peut tout faire seul.
- Voix italienne : « paola » écartée (dérivée de lessac, non commercial) → **serena** (CC-BY-4.0, apprise de zéro).

## Prises pendant l'étape 2 (à relire par Hiba)

- Écoute : faster-whisper sur Linux ; sur Mac, le plus rapide entre mlx-whisper et whisper.cpp (banc-voix le mesure).
- **Ordres courts** (moins de 4 s) : l'écoute reçoit le vocabulaire du robot (verbes × lieux et objets) comme contexte.
  Mesuré : « 去厨房 » (va à la cuisine) n'était pas compris sans, il l'est avec.
- Écoute **déterministe** (temperature = 0) : le même son donne toujours le même texte.
- Fin de phrase : 600 ms de silence. Interruption : 300 ms de parole pendant que le robot parle.
- Confirmation avant `saisir` et `poser` (réglable) : le robot répète l'ordre et attend un « oui ».
- Suisse allemand : repéré par des mots typiques (« Chuchi », « isch »…) ; sinon traité comme de l'allemand.
  Réponse en allemand, dite une fois. Le modèle Flix-AI (article arXiv 2606.07608) est une option à décider.
- Enregistrements de l'équipe : gardés sur le Mac (`donnees_voix/equipe/`, hors dépôt), avec accord demandé avant.

- **Après relecture indépendante de la voix** (12 constats, tous corrigés et testés : `briques/b04_oreilles_voix/tests/test_relecture_voix.py`) :
  « stop » prioritaire partout ; « oui » strict et lié à la même source ; aucun mot « oui » dans les questions du
  robot ; filtre d'écho ; phrases traitées dans l'ordre ; bouton relâché seul après 15 s ; mode bouton qui filtre
  vraiment ; langue gardée seulement si très sûre ; phrases d'essai figées ; faster-whisper retiré des Mac (PyAV/GPL).

## Prises par Hiba le 11.11.2026 (après l'étape 2)

- Voix : la voix du Mac pour fr, de, it, en ; Piper sans GPL pour le chinois. espeak-ng / Piper GPL : option ÉTEINTE.
- Suisse allemand : Whisper normal. Flix-AI : seulement un essai en option dans le script du Mac.
- Français : mesurer un modèle d'écoute plus gros sur Mac ; aider l'écoute avec les mots attendus ; compter les ordres compris.
- Cerveau : Apertus 8B v1.0 d'abord, 4B en secours, règles en dernier recours ; formulaire toujours ; banc de 30 × 6.

## Prises pendant l'étape 3 (à relire par Hiba)

- Cascade avec passage automatique (délai 6 s), cerveau en échec mis de côté 30 s, 4B lancé au besoin (mémoire).
- Le 8B et le 4B ne tournent jamais ensemble sur un Mac de 16 Go (environ 8,5 Go à eux deux).
- Formulaire FORCÉ (grammaire llama.cpp) ; MLX : formulaire VÉRIFIÉ après coup. Instructions en anglais, avec
  quelques exemples adaptés à la carte du robot ; la langue de la personne est dite à chaque demande.
- Filet « cible non nommée » et « verrou des chiffres » : indépendants du modèle, ajoutés après le premier banc.
- Écoute : moteur « auto » (mlx-whisper sur Mac). Liste des mots attendus élargie (tous les verbes, lieux, objets, gestes).
- Apertus par Internet : option éteinte, réglée pour l'API du CSCS (vue par l'équipe le 01.10.2026), clé dans le trousseau.

- **Après relecture de l'étape 3** (12 constats, corrigés et testés dans `briques/b06_cerveau/tests/test_cerveau.py`) :
  un « stop » pendant que le cerveau réfléchit annule sa réponse ; le verrou des chiffres garde l'axe et le sens
  (reculer, à gauche) ; distance ou geste jamais dits → question ; « avance un peu » = 50 cm ; négation → question ;
  pluriels et mots composés reconnus ; plus de façons de dire une vitesse ; le 4B n'est lancé que si le 8B TOMBE (pas
  pendant son chargement) et il est arrêté quand le 8B revient ; deux Mac : pas de 8B local si l'adresse est l'iMac ;
  clé lue une fois hors de la boucle ; réponse hors formulaire → cerveau suivant sans mise de côté ; le banc compte les
  pannes comme des erreurs ; une seule mesure à la fois sur le Mac.

- **Chef de démonstration (brique 15)** : plan B dans l'ordre écrit, sans les moyens inutiles pour la cause devinée
  (robot → ni tablette ni mode local ; voix → pas de mode local ; réseau → pas de tablette). Tablette et mode local
  jusqu'à la fin du scénario. Jamais de rejeu quand l'attendu est là ou que le robot a déjà agi. Mode local : étages
  distants ou en échec de la cascade mis en pause jusqu'à la fin du scénario. Pannes provoquées seulement en
  répétition et sur faux robot. La fiche compte les plans B.

- **Kit du samedi matin (brique 17)** : lecture du défi hors ligne, par mots-clés (fr, de, en), sans modèle de langue :
  même défi → même plan. Le kit repère ; un humain relit et ajuste. 35 personnes : 11 rôles fixes (responsable,
  sécurité ×2, relecteurs ×2, architecte, tests ×2, rédacteur, démonstration ×2), 14 en équipes de base, 10 renforts
  (au plus 4 par brique). L'adaptateur (brique 3) est toujours le premier chantier. Sommeil par rotation la nuit 1,
  tout le monde la nuit 2 ; gel des fonctions dimanche 12 h, du code dimanche 20 h ; démonstration lundi 8 h
  (**à vérifier** : heures officielles inconnues). Vrai robot la nuit : seulement si le responsable sécurité ou son
  adjoint est réveillé. Le scénario contient toujours un ordre flou, un ordre dangereux, l'arrêt d'urgence et la fiche.
- **Brouillon de scénario du kit = format de la brique 15** : `python3 lancer.py scenario` le joue tel quel ; un test le
  joue sur le faux robot (humanoïde, chien, bras). Les gestes à l'écran (arrêt d'urgence) et les briques pas encore
  construites deviennent une attente avec la consigne pour l'équipe.
- **Skill `lire-le-defi`** (`savoir-faire/`) : écrite par nous, comme demandé par Hiba au début (« écris nos propres
  skills »). Ce n'est pas une skill venue d'ailleurs ; elle ne fait que lancer le kit et relire le plan.
- **Nombres en lettres** : le verrou des chiffres lit aussi « cinq », « fünf », « five », « cinque », « 五 »… jusqu'aux
  centaines (« deux cents », « fünfundzwanzig », « zéro virgule cinq »). Un ordre trop rapide dit en lettres est refusé.
- **Raison d'un échec** dite dans la langue de la personne (code d'erreur traduit), plus en français partout.

## Prises pendant le lot B (briques 7, 8, 13 — à relire par Hiba)

- **Gardien** : règles dans `briques/b07_gardien/regles.yaml`, en phrases ; phrase et valeurs doivent dire la même
  chose, sinon pas de démarrage. Entre `reglages.yaml → securite` et les règles, la plus stricte gagne ; en direct,
  jamais au-dessus de `securite`. Chemin = ligne droite ; un robot dans une zone interdite peut en sortir.
- **Distance aux personnes : 1 m**, aussi pour prendre, poser et les gestes (**à confirmer par Hiba** : tendre un objet
  à quelqu'un devient impossible).
- Vrai robot sans les yeux, ou position inconnue : verdict « demande à un humain » avant chaque mouvement.
- Verdict « humain » : le robot lève la main ; demande valable 2 min ; après l'accord, tout est revérifié.
- Changement en direct : allumer, éteindre ou changer le chiffre ; certaines règles verrouillées (personnes, escalier,
  halle, valise, poids). Vote du public : égalité = rien ne change.
- Main levée : deux « pas compris » de suite (même personne) ou deux échecs de suite. Mots appris : lieux et objets.
- **Écran du jury** `/jury` : page à part, sans défilement, clair et sombre. 2e langue : les réponses du robot redites
  exactement depuis `phrases.yaml` ; ce que dit la personne n'est pas traduit sans modèle (l'écran le dit).
- **« Internet coupé »** : coupe les sorties du programme (garde le réseau local) et met de côté Apertus par Internet.
- Mode silence : sous-titres seulement, pictogrammes en grand.
- Chef de démonstration : nouvel attendu « aide » (le robot demande l'accord d'un humain, rien ne part).

## Corrections après la relecture du lot A (à relire par Hiba)

- **Un « stop » dit par une personne** (micro, tablette, agent) pendant un scénario **arrête tout le scénario**, comme
  l'arrêt d'urgence. Le chef n'annule jamais une phrase en route : trop long → « stop » par la chaîne, puis il attend.
- Après un **refus du gardien**, le chef ne propose jamais la main humaine : seul « sauter ».
- `lancer.py scenario` **refuse un vrai robot** pour l'instant (ni bouton ARRÊT de l'écran, ni « stop » à la voix).
- **Verrou des chiffres** : séparateurs de milliers (« 5,000 », « 5.000 », « 5'000 », « 1 000 » : on lit le plus grand),
  « 5 mètres 50 », « 一米八 », « et demi », cm et km, milliers, 13 à 19 et 60 à 90, suisse allemand ; plusieurs
  distances s'additionnent ; « 2 m par seconde » n'est jamais une distance. Si le cerveau et la phrase ne disent pas
  le même chiffre : on garde le plus grand ; s'il est permis, le robot **demande** au lieu de choisir.
- Le cerveau à règles sait « avance / recule / à gauche / à droite de N mètres » (avant : une question).
- Négation : « n' » cherché avec son apostrophe (« 20 N » n'est plus une négation) ; en chinois, « 对不起 » n'en est pas une.
- Secours du cerveau lancé ou arrêté : nouvel événement `cerveau_serveur` (ce n'est pas une panne) ; l'arrêt du 4B
  ne retarde plus la réponse du 8B.

## Corrections après la deuxième relecture (lots A et B, à relire par Hiba)

- **« Stop » pendant que le gardien vérifie** : la chaîne note le compteur de stops avant le gardien et abandonne
  l'action s'il a changé ; la **prise refuse tout ticket fabriqué avant le dernier stop** ou arrêt d'urgence.
- Le chef de démonstration n'envoie plus rien après un stop, et la chaîne oublie une phrase partie au moment du stop.
- **Faux ou vrai robot décidé par l'adaptateur**, pas par la carte : une carte qui dit autre chose empêche le démarrage
  (sinon : personnes simulées et « testé sur faux robot » avec un vrai robot).
- Cerveau à règles : « right? », « all right », « 左右 » (environ) ne sont pas des sens ; deux sens, deux distances, un
  lieu avec une distance, ou « plus de / au moins » → une question. L'annonce dit le sens (« … 2 mètre(s) en arrière »).
- Vitesses aussi en cm/s, mm/s, m/min, « 2 mètres en une seconde », « m.s-1 » ; « zéro virgule zéro cinq » = 0,05 ;
  « 0,125 » n'est pas un millier ; découpage des mots collés seulement en allemand et en italien.

## Prises pendant le lot C (briques 3, 14 — à relire par Hiba)

- **Adaptateur** = la mécanique commune (écrite et testée une fois : arrêt d'urgence d'abord sur un fil réservé, chien
  de garde, vitesse bridée, ordres de vitesse répétés toutes les 0,1 s) + une **liaison** par robot (les seuls appels du
  fabricant, « À BRANCHER »). Deux chemins : kit Python du fabricant ou pont ROS 2, chacun avec un faux pour les tests.
- **Vrai robot** : test de conformité en deux temps (sans mouvement, puis complet en mode lent 0,1 m/s), chaque temps
  confirmé par une phrase tapée au clavier par un humain ; le système refuse un vrai robot sans test complet réussi.
- Une carte de vrai robot commence avec `arreter` et `etat` seulement ; une capacité s'ajoute quand elle est branchée ET
  essayée. Chiffre inconnu = 0 (refus de bouger). Fermer le programme = arrêt normal, jamais l'arrêt du fabricant.
- **Porte des agents** : un agent d'IA parle au robot comme une personne (MCP, stdio), source « agent:nom » ; cinq
  outils (dire, carte, état, fiche, arrêter) ; rien pour les règles, le réarmement, les pannes. « arreter » = arrêt
  d'urgence (un humain réarme). **Accord d'un humain pour chaque action d'un agent : allumé par défaut** ; 10 ordres
  par minute au plus. `porte-agents` sur faux robot seulement tant que la version HTTP n'est pas dans l'écran principal.
- Corrections moyennes du lot B : clés inconnues refusées dans `regles.yaml` ; distance aux personnes seulement plus
  stricte en direct, jamais éteinte ; relire les règles garde ce qui a été rendu plus strict ; mots appris filtrés et
  rangés dans `journal/` (hors du dépôt) ; « Internet coupé » laisse passer le réseau local et une liste à régler.

## Corrections après la relecture du lot C (à relire par Hiba)

- **Arrêt d'urgence d'un robot à jambes — À DÉCIDER par Hiba et le responsable sécurité** : « arrêt de marche »
  (G1 `SetVelocity(0, 0, 0)`) ou « moteurs coupés » (`Damp`, chute possible). L'arrêt de marche **ne bloque pas le
  robot** : il accepte l'ordre suivant ; notre adaptateur bloque NOS ordres jusqu'au réarmement, mais rien contre un
  autre programme ou la télécommande.
- Après un arrêt, un arrêt normal suit l'ordre qui était en route ; chaque ordre est revérifié juste avant de partir.
  Chaque tentative d'arrêt part dans un fil neuf ; une tentative sautée est notée. Pour un arrêt, `None` = « non confirmé ».
- Un déplacement s'arrête si le robot recule de 5 cm, s'écarte de 15 cm du trajet ou dépasse le but de 15 cm (odomètre).
- Test de conformité : une action qui bouge et finit « échouée » le fait échouer. Le vrai robot est refusé si la carte,
  la liaison ou l'adaptateur ont changé depuis le test complet (empreintes). La phrase tapée au clavier (avec un nombre
  au hasard) protège contre l'oubli, **pas contre un agent** : la vraie garde reste le feu orange.
- Porte des agents : **code d'équipe exigé même en local** ; la commande refuse sans code. Un agent avec terminal ou
  accès aux fichiers de l'ordinateur-cerveau peut lire ce code : **la vraie garde = un agent sans terminal ni accès
  aux fichiers ici** (réglage de l'assistant de code, feu orange, décision de Hiba). Écran principal : `ecran.local_sans_code`.

## Prises pendant le lot D (briques 5, 11 — à relire par Hiba)

- **Yeux éteints par défaut** (`yeux.actif`). Allumés avec le faux robot : caméra simulée ; les personnes du gardien
  viennent de la caméra. **Vrai robot : les personnes vues ne vont jamais au gardien** ; `yeux.gardien_vrai_robot: true`
  empêche le programme de démarrer tant que la relecture sécurité ne l'a pas permis.
- **« Pas vue » n'est pas « pas là »** (relecture du lot D) : qui annonce des personnes donne aussi la zone du sol vue ;
  si le sol à moins d'1 m du chemin ou du geste en sort → « demande à un humain ». **Caméra sur le robot → tout
  mouvement demande un humain** ; bouger sans humain demande une caméra fixe qui voit tout le chemin (`simulee_fixe`).
  Photo fixe (`fichier:`) : jamais de personnes au gardien. Heure de photo fausse ou dans le futur : rien d'annoncé.
  Image figée (5 identiques) = panne. Pas de nouvelles sûres (caméra en panne, non calibrée…) → un humain.
- Calibration au sol par 3 marqueurs ArUco posés à plat devant le robot, imprimés en A3. « Prends X » : X pas vu → une
  question. RapidOCR toutes les 5 s.
- **Main humaine** : un seul humain à la fois ; pendant ce temps, toutes les phrases (voix, tablette, agents, chef)
  reçoivent « un humain pilote » ; « stop » et ARRÊT passent toujours. Les ordres de l'humain sont des boutons (actions
  de la carte), chacun passe par le gardien. **Prendre la main envoie toujours un arrêt normal** (par le gardien ; choix
  prudent, à confirmer par Hiba), qui ne compte pas comme réussite du robot. À chaque changement de main, les demandes
  à un humain de l'autre camp sont oubliées. Un jeton remis à la tablette qui a pris la main est exigé pour les ordres
  et le rendu ; une autre tablette peut seulement « Libérer la main » (noté). La fiche compte à part les ordres de
  l'humain et la main simulée du chef (affichée « SIMULÉE » au jury). Le chef attend au plus 5 minutes le rendu.

## Nouvelles règles de travail (Hiba, 11.11.2026)

- Feu vert sans demander : paquets MIT, Apache ou BSD de moins de 200 Mo ; modèles de moins de 500 Mo pour les tests ;
  lecture de GitHub et de Hugging Face ; fusion sur main quand les tests passent (3 fois) et que le relecteur n'a plus rien de grave.
- Feu orange : GPL et AGPL, payant, plus de 500 Mo, vrai robot, réglages de l'ordinateur.
- Travail par lots, en parallèle (3 ou 4 sous-agents au plus, chacun dans sa copie), une relecture par lot.

## À décider par Hiba

- Après les mesures des Mac : modèle d'écoute (small ou large-v3-turbo), moteur du cerveau (llama.cpp ou MLX), délais.
- STT4SG-350 : vérifier la licence sur swissnlp.org (je n'accepte pas de conditions à votre place).
- Apertus par Internet (CSCS) : conditions et coût à vérifier avant de l'allumer.
- **PyAV (GPL x264/x265)** : tiré par faster-whisper, utilisé seulement dans le nuage pour les tests. Sur Mac : retiré.

## Clinique en boîte — installation sur l'iMac (R1, 11.11.2026)

- Paquets installés dans `.venv` seulement, à partir de `requirements.txt` **sans `faster-whisper`** (PyAV, partie GPL :
  décision déjà prise pour les Mac), plus `onnxruntime` 1.31.1 installé à part (fin de phrase, voix).
- `requirements.txt` n'est pas modifié. L'exception est écrite dans `outils/verifier_installation.py`, qui contrôle aussi
  que `faster-whisper` reste absent sur Mac. Aucune brique de l'ossature touchée.

## Clinique en boîte — le squelette (T01, 11.11.2026)

- La clinique vit dans `briques/clinique` (pas de numéro : ce n'est pas une des 17 briques). Ses essais sont pris par
  `python3 lancer.py tests` sans changer `pytest.ini`.
- Seul fichier de l'ossature touché : `lancer.py`, deux commandes en plus (`verif-rapide`, `repetition`). Rien d'autre.
- Vérification rapide : tout, sauf les essais de l'ossature de 1,5 s ou plus (34, mesurés sur l'iMac). Aucun essai
  n'est modifié ni supprimé : ils restent tous dans `python3 lancer.py tests`.
- Grande répétition : une étape ne réussit que si sa pièce rend un résultat avec une étiquette connue. Pièce absente,
  cassée ou sautée = ratée.

## Clinique en boîte — la porte de lecture (T03, 11.11.2026)

- La brique 14 n'est pas modifiée : la clinique ajoute son outil de lecture au serveur MCP de l'extérieur
  (`brancher_sur_la_porte_des_agents`). Le badge de l'assistant est fixé par l'équipe au branchement, pas par l'agent.
- Le journal des accès est un fichier à part (`journal/clinique/`), pas encore dans la boîte noire : la liste fermée
  des événements de l'ossature (`commun/evenements.py`) n'est pas touchée.
- Vues plus étroites que le tableau du cahier quand il y avait un doute : le robot ne reçoit ni l'âge ni les habitudes ;
  le soignant ne reçoit pas la raison du séjour.

## Clinique en boîte — les écrans (T05, 11.11.2026)

- Les écrans vivent dans `briques/clinique/ecrans.py` et s'ajoutent de l'extérieur à l'application de la brique 13
  (pages `/clinique/…`). La brique 13 n'est pas modifiée. Fichier de l'ossature touché : `lancer.py` (la commande
  `serveur` branche les écrans et affiche la vraie adresse du réseau local).
- Les pages sont fabriquées par le serveur, sans fichier venu d'Internet. Secours : chaque page redemande son contenu
  toutes les deux secondes. Pas encore de flux en direct pour ces pages.
- Un écran n'accepte que les badges de son métier. Un autre badge est refusé par la porte et noté au journal
  (`PorteDeLecture.refuser`, ajouté à la porte).
- L'essai « adresse du réseau local » tourne dans un programme à part (`essai_reseau.py`) : `conftest.py`, qui coupe
  Internet pendant les essais, n'est pas touché. Sans réseau local, l'essai est compté « sauté », pas « réussi ».

## Clinique en boîte — le carnet et les listes de soin (T06a, 11.11.2026)

- Le carnet (`briques/clinique/carnet.py`) : on ajoute des lignes, on n'en change et on n'en efface aucune. L'état
  d'un point de liste est sa dernière ligne. Un fichier par séance dans `journal/clinique/` si on le demande.
- `listes_de_soin.yaml` a reçu, pour chaque point, un nom court et quelques mots proches (le cahier 5.5 les demande).
  Le texte des points n'a pas changé. Les noms et les mots sont écrits par l'agent : à relire par l'équipe.
- Seul un humain coche (soignant, thérapeute, médecin, accueil), et seulement les points de son métier. L'assistant
  (le cerveau) est refusé : à la voix (T16), la coche se fera sous le badge de la personne qui parle.
- « Je sors » ne parle que des listes commencées. La fin de poste montre aussi les listes pas commencées.
- Les comptes de la direction viennent du carnet : points faits, reportés, passés à la relève, par étage. Ni nom,
  ni numéro de dossier, ni soignant, ni raison.
- Étape 7 de la grande répétition : étiquette SIMULÉ (les coches sont faites par le programme).

## Clinique en boîte — les listes de soin à l'écran (T06b, 11.11.2026)

- Les gestes (cocher, choisir, « je sors ») sont des routes à part, sans le code d'équipe de l'ossature : une tablette
  doit pouvoir cocher. Une page venue d'un autre site est refusée. Ces gestes n'envoient aucun ordre à un robot ; ils
  écrivent seulement dans le carnet.
- Un refus dit pourquoi : 403 si le badge n'a pas le droit, 400 si le geste n'est pas possible.
- Le serveur ouvre un carnet par lancement (`journal/clinique/carnet_….jsonl`, jamais envoyé vers GitHub).
- « Ce que le poste d'avant n'a pas fini » = les points reportés ou passés à la relève, tant qu'ils ne sont pas faits.
  Il n'y a pas encore de vraie notion de poste (matin, soir, nuit).
- La page de la direction n'a pas de choix de badge : elle prend le badge « direction ».
- Étape 6 de la grande répétition : étiquette SIMULÉ (la page est demandée par le programme).

## Clinique en boîte — le tableau des tâches et la demande (T07a, 11.11.2026)

- Une tâche est une suite de lignes dans le carnet (genre « tâche ») ; son état est sa dernière ligne.
- Comprendre la demande se fait par des mots, sans modèle : le nom entier d'un objet de la réserve d'abord, sinon un
  mot en commun. Plusieurs objets possibles = une question courte, jamais un choix au hasard.
- Ce qui n'est pas dans la réserve passe à un humain, avec les mots de la personne tels quels, sans commentaire
  (pas de médecine). Une chambre absente du plan, ou à un autre étage que la réserve, passe aussi à un humain.
- `reserve.yaml` a reçu l'article de chaque objet (« le », « la »), pour écrire la question. Les quantités de la
  réserve ne sont pas décomptées (le faux dossier ne change jamais).
- Le robot ne voit d'une tâche que : quoi, d'où, où, pour quand, l'état, le prénom et la langue.
- Brique 8 (« je ne suis pas sûr ») pas encore utilisée pour la question : à brancher avec T07b ou T17.

## Clinique en boîte — la course du faux robot (T07b, 11.11.2026)

- **Ossature touchée, le moins possible** : `commun/systeme.py`, `Systeme(..., monde=None)`. Sans ce réglage, rien ne
  change. Avec, le système prend le monde donné. `lancer.py` donne le monde de l'ossature plus le plan de la clinique.
- Le plan de la clinique pour le robot : `briques/clinique/monde_clinique.yaml`. Positions inventées, posées dans la
  halle de l'ossature (10 m × 6 m) : elles ne suivent pas les distances de `lieux.yaml`. Les lieux et objets de la
  clinique n'ont pas de nom dans les langues : le cerveau de l'ossature ne les entend pas (pas de confusion entre
  « bouteille » et « bouteille d'eau »).
- Le coursier (`coursier.py`) demande chaque geste au gardien, puis donne le ticket à la prise. Il ne passe pas par
  la chaîne de la voix (pas de phrase à comprendre). Il ne connaît ni l'adaptateur ni le faux robot.
- Si le gardien demande l'accord d'un humain, le coursier n'attend pas : la demande est retirée, la tâche « échouée ».
- Une course à la fois. Après un échec, la tâche reste « échouée » : pas de nouvel essai tout seul.
- L'étiquette de la tâche vient de la carte d'identité du robot : « FAUX ROBOT », ou « RÉEL » pour un vrai robot.
- Étape 8 de la répétition : le coussin coche un point d'exemple (« le lit ») ; le vrai point est à décider avec Hiba.

## Clinique en boîte — le résumé du médecin, version simple (T08, 11.11.2026)

- Cinq lignes fixes par patient, toujours dans le même ordre : pourquoi il est là ; ce qui a changé depuis hier ; ce qui
  attend une décision ; ses questions ; prévu aujourd'hui. Une ligne vide dit « rien de nouveau ».
- Quatre sortes de sources : un document, la fiche du séjour (`sejour`), le programme (`programme`), une ligne du carnet
  (`carnet-12`). Une source s'ouvre seulement pour un patient que le badge du médecin montre.
- Le verrou des chiffres de l'ossature (`commun/chaine.py`) ne sert que pour un ordre au robot (vitesse, distance,
  force). Pour le résumé, même idée, écrite dans `resume.py` : chaque suite de chiffres d'une phrase doit se trouver dans
  une de ses sources, et chaque date citée doit y être écrite telle quelle, sinon la phrase est retirée. C'est un
  contrôle simple : il ne regarde ni l'ordre des chiffres, ni les mots (voir `NON_TESTE.md`). C'est un écart au cahier
  (« sers-t'en ») : à valider par Hiba. Le verrou de l'ossature n'est pas changé.
- Un désaccord ne disparaît jamais sans rien dire : si la phrase avec les deux dates est retirée par le contrôle, une
  phrase sans date la remplace (« Deux sources ne sont pas d'accord… Ouvrir les deux. »).
- La source d'un document montre son texte, puis ce que le faux dossier note pour lui (son champ `faits`).
- Ouvrir une source ajoute une ligne au journal des accès (`porte.noter`, méthode ajoutée à la porte).
- « Deux sources ne sont pas d'accord » vient du champ `faits` des documents du faux dossier (un événement, une date).
  La version simple ne lit pas les dates dans le texte libre : c'est le travail de T13 et T15.
- « Ce qui a changé depuis hier » : l'arrivée, si elle date d'hier ou d'aujourd'hui, et les lignes du carnet depuis hier
  (points de liste, demandes au robot).
- Chaque résumé préparé est une ligne du carnet (« résumé du médecin », pas validé par un humain). Il est refait
  seulement si une source change ou si le jour change.
- La recherche : par des règles. Le nom de la personne (prénom, ou « Madame B. »), puis les mots du genre et du titre.
  Elle ne cherche que parmi les patients du médecin. Les documents n'ont pas de date : s'il y en a plusieurs du même
  genre, elle demande lequel, elle ne devine pas « le dernier ».
- Dans le faux dossier, Madame Giulia B. n'a pas de rapport de radiologie (le seul est chez Monsieur Hans K., que le
  Médecin Exemple ne suit pas). La phrase du cahier donne donc, avec vérité : « Je ne trouve pas ce document ».
- Étape 10 de la répétition : étiquette SIMULÉ (page demandée par le programme, aucun modèle, aucun robot).

## Clinique en boîte — les papiers, version simple (T09, 11.11.2026)

- Le « papier » est son texte de référence (les textes des documents du faux dossier, et la feuille sans nom). La
  lecture d'une image viendra avec T15.
- Les papiers du jour : ceux des personnes qui arrivent aujourd'hui (ce que la porte montre à l'accueil), plus les
  feuilles sans nom. La porte a une lecture de plus, `feuilles_sans_patient`, pour l'accueil seulement.
- La proposition se fait avec le texte seul : ni le genre, ni le titre, ni l'identifiant du faux dossier. Un essai
  compare ensuite le type proposé au genre écrit dans le faux dossier.
- Le patient : on cherche « prénom + initiale » dans le texte, parmi les arrivées du jour. Aucun ou plusieurs : pas de
  rangement, le papier va dans « à trier ».
- Le type : des mots par type, en français, allemand, italien (`TYPES` dans `papiers.py`). L'endroit du dossier vient
  du type. La liste des endroits est inventée par l'agent : à remplacer par ceux de la clinique.
- La date et l'auteur sont recopiés du texte. S'ils n'y sont pas : « non trouvé ». L'auteur : la première ligne, si elle
  contient « Exemple » (règle 2.5).
- La confiance, version simple : « haute » si un seul patient, un seul type reconnu par deux mots au moins (en début de
  mot) et un texte tapé ; sinon « basse », et le prototype dit « je ne suis pas sûr ». Ce n'est pas une mesure. Avec une
  confiance basse, l'humain doit choisir le type.
- L'écriture (tapée, à la main) vient du faux dossier : elle tient lieu de ce que la lecture d'une image dira (T15).
- Le texte du papier est gardé dans la ligne du carnet : un papier pas encore validé attend les jours suivants.
- L'accueil ne voit que les deux premières lignes d'un papier, à l'écran et par l'API : une lettre peut dire la raison
  du séjour, que l'accueil ne doit pas voir (cahier 5.2). La porte, elle, donne encore le texte entier à l'accueil.
- La pièce ne croit que les lignes « rangement de papier » écrites avec un badge de l'accueil.
- Les propositions sont écrites au carnet au nom du badge de l'accueil (« pas validé par un humain », version « règles
  simples »), comme le résumé l'est au nom du médecin. À décider par Hiba : un badge à part pour « le prototype » ?
- Seul le badge de l'accueil voit la pile et valide. Proposition et validation sont des lignes du carnet
  (« rangement de papier ») ; la validation porte « validée par Accueil, à Jour 1 — 9 h 00 ».
- Étapes 4 et 5 de la répétition : étiquette SIMULÉ (texte de référence, validation faite par le programme).

## Clinique en boîte — l'accueil du hall, version écrite (T10, 11.11.2026)

- La phrase d'arrivée est tapée sur la page `/clinique/hall`. Aucune voix, aucun robot ne bouge : étiquette SIMULÉ.
  Comme rien ne bouge, il n'y a pas d'ordre au robot, donc pas de ticket du gardien.
- La langue d'une phrase tapée est devinée par ses mots courants (`accueil_hall.yaml`). La brique 4 reconnaît la langue
  d'un son, pas d'un texte : elle servira à la voix (T20). On répond dans la langue entendue, pas dans celle du dossier.
  Langue pas reconnue : français, et la réponse le dit.
- La porte a une lecture de plus pour le robot du hall, `arrivees_pour_le_hall` : nom, langue, chambre, étage,
  première heure du programme. Rien d'autre : ni la raison du séjour, ni ce qui est au programme.
- Le robot dit seulement l'heure du premier rendez-vous, pas ce que c'est (ce serait parler de soin dans le hall).
- La règle « dans le hall, le robot ne dit rien sur la santé » est écrite en clair dans `accueil_hall.yaml` (une
  phrase et des mots, comme les règles du gardien). Elle n'est PAS dans le gardien de l'ossature (brique 7), qui ne
  juge que les mouvements. Le cahier dit « c'est une règle du gardien » : écart signalé à Hiba (question Q12).
  La règle passe avant la recherche du nom : le robot ne dit même pas si la personne est là.
- Le robot ne donne la chambre que pour une « simple arrivée » : pas de question ; le prénom suivi du nom ou de son
  initiale ; autour, seulement des mots pour saluer et dire « je suis » (liste `mots_d_arrivee`). « Où est Giulia ? »,
  « je cherche Giulia B. », « je ne suis pas Giulia B. », le prénom seul : il appelle un humain et ne dit rien.
  C'est cette règle qui protège ; la liste de mots sur la santé choisit seulement la phrase de refus.
- Étage inconnu (neuf fiches sur douze n'ont pas d'étage) : le robot ne promet pas « on vous attend », il appelle un humain.
- La réponse affichée dans le hall ne contient ni numéro de dossier, ni nom de famille, ni le texte du message à l'étage.
- La pièce ne croit que les lignes du carnet écrites avec le badge du robot du hall.
- Nom inconnu, ou plusieurs personnes possibles : le robot appelle un humain. Ni la phrase, ni le nom dit ne sont gardés.
- Le message à l'étage et l'appel d'un humain sont des lignes du carnet, écrites avec le badge du robot. Le message
  s'affiche sur l'écran du soignant de l'étage, l'appel sur l'écran de l'accueil. Un message par personne.
- Le chemin : du hall à l'ascenseur, puis de l'ascenseur à la chambre, sur le plan lu par la porte. Pas de distance
  inventée pour l'ascenseur. Chambre hors du plan : le chemin s'arrête à l'ascenseur.
- **T11a, le scénario de la clinique** : il est dans le dossier de la clinique (`scenario_clinique.yaml`, lu par
  `chef_clinique.py`), pas dans la brique 15. Raison : le chef de l'ossature ne sait jouer que des phrases dites au
  robot ; les scènes de la clinique passent surtout par les écrans. Lui ajouter une nouvelle sorte d'étape, c'était
  toucher à une brique qui marche. On lui reprend ses quatre moyens de plan B et ses phrases (« Je passe à la
  tablette. »). Aucune brique de l'ossature n'est touchée. `repetition.py` : la boucle est coupée en deux petites
  fonctions (`jouer_etape`, `conclure`) ; ses essais n'ont pas changé.
- Un plan B sauve la démonstration, jamais la répétition : une étape ratée ou manquante reste comptée.
- **T11b, le soir et la dictée, version simple** : une seule petite pièce (`soir.py`) pour les deux, car les deux ne font
  qu'écrire au carnet. La question du soir reste dans la langue de la patiente (pas de traduction sans modèle : on
  n'invente pas une traduction). Le prototype répond toujours la même phrase : il transmet, il ne répond pas.
  La dictée crée une tâche « pour un humain » avec un métier (`pour`) : `taches.py` a une méthode de plus,
  `pour_un_humain`. Les tâches d'objets ne changent pas. Le thérapeute ne voit que les tâches pour son métier.
- **T11c, la flotte, version simple** : les robots simulés ne font qu'écrire des états au carnet. Ils ne passent pas
  par le gardien, car ils ne font rien bouger ; en échange, ils ne peuvent jamais écrire « livrée ». La reprise
  est faite par le robot branché (R1), par le coursier, donc par le vrai chemin : gardien, ticket, prise. C'est le
  choix le plus honnête sans la brique « plusieurs robots » (R5). L'étape 12 porte l'étiquette SIMULÉ (la plus
  modeste), et son détail dit que la reprise est faite par le faux robot. `coursier.py` : une seule ligne changée,
  il accepte une tâche à l'état « reprise ». Les robots R2 à R4 ne sont pas dans `badges.yaml` (ils n'ouvrent
  aucun écran) : ils sont dans `flotte.yaml`.
- **T11d, la fiche et « rien dehors », version simple** : la répétition tient une « séance » (`repetition.Seance`) : l'issue de
  chaque étape, les sauts de l'horloge, la surveillance du réseau. Les étapes 13 et 14 se calculent dessus ; hors d'une
  répétition, elles ratent. Une pièce peut rendre des « mesures » avec son résultat (le résumé rend son compte de
  phrases retirées). La surveillance bloque en plus de compter : pendant une répétition, rien ne doit sortir, donc
  autant l'empêcher. Étiquette SIMULÉ pour ces deux étapes (la plus modeste) : le contrôle est vrai, mais ce qu'il
  contrôle est une répétition simulée. La fiche complète, depuis la boîte noire, reste T27.
- Les essais qui ont besoin de la vraie commande `lancer.py repetition` la lancent une seule fois
  (`briques/clinique/tests/la_vraie_repetition.py` ; pas de `conftest.py` dans ce dossier : il cacherait celui de la racine), pour garder la vérification rapide sous deux minutes.
- **T12, après la relecture** : une tâche qui porte un métier (`pour`) n'est donnée par le tableau qu'à ce métier et au
  médecin. Raison : la dictée est une phrase libre du médecin, elle peut parler de santé ; l'accueil ne lit rien sur
  la santé, et un autre métier n'en a pas besoin. « Accueil » n'est plus un destinataire de dictée. Le tableau refuse
  « livrée » pour une tâche portée par un robot simulé.
- **J01a, les essais comptés** : les changements d'un essai passent par `repetition.variation(...)` ; les étapes 1, 7 et 8
  les lisent (langue, point oublié, objet). Sans changement, elles jouent le scénario du cahier. Pour un objet absent,
  l'étape 8 réussit si le prototype le dit, passe la tâche à un humain et ne fait rien bouger (cahier 4.3) ; son
  étiquette est alors SIMULÉ, car aucun robot n'a servi. La liste des vingt essais a été écrite avant le premier
  passage et n'a pas été retouchée. Chaque étape de chaque essai est un événement « note » dans une boîte noire.
- Pour tenir la vérification rapide sous deux minutes (115 s) : `test_la_commande_repetition_tourne` (T01) se sert
  de la même sortie de commande que les autres essais (une seule exécution) ; ses contrôles n'ont pas changé. Les
  essais de l'ossature restants durent tous moins de 1,5 s (mesuré le 12.11) : aucun ne peut aller dans
  `essais_longs.txt`. La limite sera dépassée bientôt : question Q16.
- **J01b, le compteur d'essais réels** : un fichier à part (`journal/clinique/essais_reels.jsonl`), une ligne par appui, jamais
  dans le dépôt. Pas de bouton pour effacer ou corriger. Les boutons passent par le contrôle du code d'équipe de la
  brique 13 (`controle_acces`), sans la toucher. Les essais du dépôt n'écrivent que dans un dossier d'essai ; un essai
  vérifie que le vrai fichier ne bouge pas. Dans la fiche, les essais sur faux robot et les essais réels sont deux
  lignes séparées (trois niveaux de preuve, jamais mélangés).
- **J02a, les pannes provoquées** : la panne du lien se sert de la panne « perte_liaison » du faux robot (brique 2) ; rien
  n'est ajouté à l'ossature. Pendant la panne, le coursier ne demande rien au gardien (rien ne peut partir) : la
  tâche reste « demandée », avec « en attente ». Une course coupée en route passe « reprise », pas « échouée ».
  Après un arrêt d'urgence, rien ne repart seul : un humain réarme, puis appuie sur « Relancer ». Le bandeau passe
  par le petit morceau « heure » que toutes les pages redemandent déjà. Les quatre pannes sont listées dès
  maintenant ; celles qui ne sont pas construites ne peuvent pas être provoquées.
- **J02b, la tablette sans lien** : la panne est simulée côté programme (les échanges marqués « X-Tablette » reçoivent
  « lien coupé »), parce qu'on ne coupe pas un vrai Wi-Fi par un bouton. Le vrai travail est sur la tablette : une
  file de coches, écrite en JavaScript simple, sans outil, gardée par le navigateur. Elle marche pareil si le réseau
  tombe pour de vrai (une erreur de réseau met aussi la coche dans la file). Seules les coches sont gardées : une
  demande au robot faite hors ligne ne part jamais plus tard toute seule (un ordre vieux ne doit pas surprendre).
  Node, déjà sur l'iMac, sert à essayer la file ; rien n'a été installé.
- **J02c, cerveau muet et micro** : trois pannes sur quatre mettent le robot « à l'abri » (`ABRI`) : arrêt normal demandé à
  la prise (`arreter_tout`), puis le coursier attend. C'est la lecture la plus prudente de l'avenant (« il s'arrête là
  où il est, et il ne commence rien de nouveau », pour chaque panne). Le cerveau muet ne refait aucun résumé : il sert
  celui d'avant, marqué ; il n'invente pas un résumé qui n'était pas prêt. Pas de proposition de rangement pendant la
  panne. Le micro : `Pannes.entendre()` est la porte par où passeront les pièces à la voix.
- **J03, les moments** : la page lit la boîte noire ET le carnet de la clinique, rangés par l'heure réelle, plutôt que de
  faire entrer le carnet dans le bus de l'ossature maintenant (T27 le fera). Un moment a pour numéro celui de sa ligne
  (l'événement de la boîte noire, ou « c » + le numéro de la ligne du carnet) : le tableau des essais peut y mener.
  Les sortes de moments sont reconnues par les noms que les pièces écrivent vraiment (constantes importées), pas par des
  mots recopiés. La page est derrière le code d'équipe, car elle montre des lignes du carnet.
- **J04a, le robot à plateau** : la carte est un fichier de plus dans `briques/b02_faux_robot/cartes/` (le faux robot ne lit
  ses cartes que là) : un ajout dans l'ossature, sans changer une ligne de code ; son essai (« au moins humanoïde,
  chien, bras ») passe toujours. Le coursier choisit d'après ce que la carte sait faire (`carte.sait("saisir")`),
  jamais d'après le nom ou la sorte du robot ; un essai le vérifie. Sans bras : deux demandes à un humain, chacune
  attendue (120 s), dites par la voix du robot si la carte a « parler » (par le gardien) et écrites sur la tablette.
  Si personne ne répond, le robot ne part pas à vide.
- **J04b, la commande « brancher » de l'avenant** s'appelle `brancher-carte` : `lancer.py brancher` existe déjà (brique 3 :
  créer le dossier d'un vrai robot) et n'est pas touchée. `brancher-carte` réutilise le test de conformité de la prise
  (`verifier_conformite`, brique 1) tel quel, sur le faux robot. Elle refuse toute carte de vrai robot : le vrai robot
  reste un feu orange, tapé par un humain. Le chronomètre est un petit fichier dans `journal/clinique/` (hors du dépôt).
  **Une brique de l'ossature touchée** : `commun/systeme.py` a une fonction de plus, `fabrique_du_faux_robot` (cinq
  lignes). Raison : un garde-fou de l'ossature interdit de fabriquer un robot, même faux, hors de ce fichier ; la
  commande lui demande donc la fabrique, au lieu de la faire elle-même. Le garde-fou n'a pas été changé.
- **J06, version simple** (Q7 sans réponse) : pas de fichier de paroles, et le code n'en cherche aucun (un essai le
  vérifie). Tant qu'il n'y a pas de parole, tout ce qui décrit le travail des soignants est une HYPOTHÈSE.
- **T14, le cerveau propose le rangement, les règles vérifient** : le cerveau a une seule porte, `lire(texte, types, noms
  possibles)`, et rend un petit formulaire (type, date, auteur, patient, confiance). Il ne reçoit rien d'autre que le
  texte du papier. Les règles de T09 restent le juge : elles décident du patient, retirent une date ou un auteur que
  le papier ne contient pas, et font tomber la confiance au moindre désaccord. Sans cerveau, ou s'il ne répond pas :
  les règles simples, comme avant. Le cerveau de test (réponses fixes, cahier 2.8) est dans `papiers.py`. Le
  branchement du vrai Apertus sur cette porte attend R2 (T13 fera le premier, pour le résumé).
- **R3, lire une image : la lecture du Mac plutôt que RapidOCR.** Les deux étaient autorisés (A et B). La lecture du Mac
  (cadre Vision) est déjà là : rien à installer ni à télécharger, et cette nuit l'outil refuse ce qui vient de
  l'extérieur (voir Q17). Un petit programme Swift de 90 lignes (`outils/lecture_mac.swift`) est construit une fois
  avec le compilateur du Mac ; le fichier construit va dans `outils/bin/` (hors du dépôt). Les yeux de l'ossature
  (brique 5, RapidOCR) ne sont pas touchés et restent non installés ; si la lecture du Mac ne suffit pas sur de vrais
  papiers, ce sera une question pour Hiba (cahier 5.8).
- **T15, les papiers depuis une image** : les sept images sont fabriquées par le programme (`papiers_images.fabriquer`) et
  rangées dans le dépôt (`briques/clinique/images_papiers/`, 60 Ko en tout), pour que tout le monde lise les mêmes.
  « Je ne suis pas sûr » ne peut pas venir de la confiance annoncée par la lecture du Mac (elle vaut 1 même quand elle
  se trompe : mesuré). On fait donc deux lectures, et on prend la confiance de la lecture SANS correction automatique ;
  une ligne sous 0,9 rend le papier « lecture peu sûre », et le rangement n'est alors jamais « sûr ». Une ligne qui
  n'est qu'un morceau du mot en travers est écartée. Les règles de rangement (T09) et les verrous (T14) ne changent
  pas : ils reçoivent le texte lu au lieu du texte de référence. Le lecteur n'est pas branché par défaut dans les
  écrans : la répétition reste sur les textes de référence tant que l'équipe n'a pas essayé de vrais papiers.
- **T16, cocher à la voix, au niveau du texte** : `ListesDeSoin.entendre(badge, patient, liste, phrase, confiance)` reçoit ce que
  les oreilles ont compris et ne fait que des choses sûres : il faut le nom d'un point (mots du faux dossier en
  français ; `mots_des_points.yaml` pour l'allemand, l'italien, l'anglais) ET le mot « fait » ; une négation, deux points
  possibles ou une écoute peu sûre ne cochent rien. La voix passe par les mêmes droits que le doigt. La route de l'écran
  demande d'abord à `Pannes.entendre` (micro en panne : du bruit). Les vraies oreilles (brique 4) se brancheront là
  quand le modèle d'écoute sera sur l'iMac (R4).
- **T17, demander au robot à la voix** : `TableauDesTaches.entendre` garde en mémoire la question posée à une personne (par badge
  et par patient) ; la phrase suivante de cette personne est sa réponse. Le choix se fait par les mots qui distinguent
  les objets entre eux (« grand », « nuque »), tirés des noms de la réserve : rien n'est écrit en dur pour le coussin.
  Sur l'écran, un seul champ : `Clinique.entendre` regarde d'abord si le robot attend une réponse, puis essaie de cocher
  un point, puis de comprendre une demande d'objet. La tâche porte « par la voix » et la phrase entendue.
- **T19, la traduction des questions du soir** : sans modèle, on ne traduit pas. Un fichier donne le français des deux questions
  du scénario (c'est celui du cahier, 6.1) ; `TraducteurDuScenario` rend « rien » pour toute autre phrase. Le traducteur a
  une seule porte, `traduire(texte, de, vers)` : le vrai cerveau s'y branchera. La traduction est écrite au carnet avec la
  question, avec le nom de ce qui l'a faite ; le médecin lit la traduction d'abord, le texte d'origine à côté. Une
  traduction vide, en erreur, ou identique au texte d'origine est jetée : la question part quand même, « non traduite ».
- **R4, l'écoute** : le modèle est rangé à `modeles/ggml-small.bin` (hors du dépôt), contrôlé par sa taille et son empreinte
  (celles de `outils/catalogue.yaml`). Pour l'essai, on prend l'outil `whisper-cli` déjà installé (Homebrew) plutôt que
  d'installer `pywhispercpp` ou `mlx-whisper` : rien de plus à installer. La mesure compte les mots faux sans la
  ponctuation ni les majuscules. Brancher les oreilles de l'ossature (micro en direct) sur ce modèle reste à faire, avec
  T20 ; si cela demande un paquet de plus, c'est l'autorisation A, à noter avec sa taille.
- T11 coupée en quatre (T11a à T11d), pour que la répétition puisse réussir avant la relecture T12 (question Q14).

## Restent à faire

- Yeux : choisir l'outil pour trouver un objet nommé et repérer les personnes (propositions dans la réponse à Hiba).
- Partage entre deux Mac : à décider après mesure (`preparer_mac.sh --autre-mac`).
- Sortie pour le motion design : WebSocket + flux texte prêts ; OSC si l'expert le demande.
- Apertus par Internet (bonus) : gratuit ou payant ? **à vérifier**, feu orange.
- Dépôt GitHub privé : lien à faire par Hiba.
- **T20, l'accueil à la voix** (tour 37) : on n'a pas branché la brique 4 ; la pièce appelle `ecoute.ecouter` (R4) et la
  commande `say` du Mac, déjà là : rien d'installé. La langue de la réponse est celle que l'accueil reconnaît dans la phrase
  entendue (règles de T10), pas celle devinée par le modèle d'écoute. Une phrase pas comprise ne reçoit jamais de réponse :
  on passe à l'écran. Les sons vont dans `journal/clinique/sons/` (hors du dépôt).
- **R5, le monde des robots** (tour 38) : une pièce à part dans le dossier de la clinique, qui ne touche à aucune brique de
  l'ossature (un essai le vérifie). Le plan est celui du faux dossier (`lieux.yaml`, les couloirs et leurs mètres), pas la
  halle du faux robot (`monde_clinique.yaml`) : les robots simulés n'ont pas besoin de x et de y. R1 n'avance jamais par ce
  monde : son seul chemin reste coursier → gardien → prise ; on y note seulement sa place, pour que le répartiteur (T23)
  puisse le compter. Le temps avance par `pas()`, appelé par celui qui joue la scène : pas d'horloge cachée. La règle
  `permis(robot, lieu)` est la porte prévue pour les cartes de rôle (T22). Les lieux de départ sont dans `flotte.yaml`.
- **T22 coupée en T22a et T22b** (tour 39). T22a : les cartes sont des fichiers à part (`cartes_de_role/`), contrôlés au
  chargement ; la carte d'un robot est le mot « carte » de `flotte.yaml`. Une carte ne fait que retirer des droits : elle ne
  remplace jamais le gardien. La carte Thérapie reste au deuxième étage (salon, chambres, réserve), parce que R3 y vit et que
  les robots ne prennent pas l'ascenseur. Le volume : `say` ne baisse pas le son d'un fichier, donc `accueil_voix.baisser`
  multiplie chaque point du son ; le haut-parleur joue ce fichier (`afplay`), au lieu de redire la phrase. Aucune brique de
  l'ossature touchée. T22b devra faire appliquer la carte de R1 par le gardien, sans réécrire la brique 7.
- **T22b, la carte chez le gardien** (tour 40) : on ne touche pas à la brique 7. Le gardien lit déjà un fichier de règles ;
  la clinique fabrique ce fichier (règles de l'ossature + règles de la carte) et le fait relire (`gardien.recharger`). La
  vitesse de la carte est une règle à part (`carte_vitesse`, pas changeable en direct) : le vote du public peut baisser la
  vitesse, jamais la remonter au-dessus de la carte. Les lieux : des zones interdites (le gardien n'accepte qu'UNE forme par
  zone permise, donc pas une liste de lieux permis). Les actions : le gardien n'a pas de règle « action interdite » ; le
  contrôle se fait avant lui, dans le coursier, et ne fait que refuser. Le Hall et l'Accueil ne sont PAS ajoutés au plan du
  robot de l'étage (un essai de T07 l'interdit, et il a raison) : ils ne s'ajoutent que sur demande, quand la même salle joue
  le hall et l'étage. Le fichier fabriqué va dans le dossier de la boîte noire de la séance.
- **K02 coupée en K02a et K02b** (tour 41). K02a : l'événement AIDE HUMAINE est une « note » de la boîte noire (quoi =
  « AIDE HUMAINE ») : on n'ajoute pas de type à `commun/evenements.py`. Une demande faite au robot et passée à un humain
  (objet absent, carte, robot sans bras) compte comme une aide, et compte aussi dans le nombre de demandes : c'est le choix
  le plus sévère. La panne provoquée de la scène 6 est prévue par le scénario : sa reprise est comptée à part, pas dans la
  case « reprise automatique » (sinon les vingt essais y tomberaient tous, et le chiffre ne dirait plus rien). Les aides
  sont gardées sur le tableau des tâches (`tableau.aides`) et écrites dans la boîte noire par les pièces qui ont le bus
  (coursier, pannes, bouton). Les lignes et les essais de J01 ne changent pas : K02 ajoute des lignes après le tableau.
- **K02b** (tour 42) : l'endurance rejoue la grande répétition entière (les quatorze contrôles), pas seulement la course
  du robot : c'est « le scénario » de l'avenant. La durée tenue ne compte que des passages entiers et réussis ; un passage
  n'est pas coupé en route. Chaque mesure s'ajoute à `journal/endurance.jsonl` (hors du dépôt) ; le chiffre affiché est la
  meilleure mesure, avec sa date et son nombre de passages. Sur le faux robot, un geste télécommandé porte « FAUX ROBOT ·
  TÉLÉCOMMANDÉ » : l'avenant dit « RÉEL · TÉLÉCOMMANDÉ », mais écrire « RÉEL » sur le faux robot serait faux (feu rouge du
  cahier). « Réussi avec aide » est compté à part de « réussi » dans la ligne RÉEL : la ligne d'avant ne change pas.
- **M02, les étagères** (tour 43) : les appuis vont dans le même fichier que les essais réels de J01. Les lignes qui ne
  sont pas des essais (départ, aide, arrêt, fin, annulation) portent « evenement » : le compteur les saute sans les compter
  ni les dire « illisibles ». Une annulation nomme l'appui annulé par son « id » : il ne compte plus, mais rien n'est retiré
  du fichier. Un objet tombé s'appelle « étagères, tombé en route » (on ne sait pas de quel niveau il venait). L'arrêt de
  sécurité ne s'annule pas. La fonction s'appelle `annuler_le_dernier`, parce que « annuler » est une commande du robot,
  réservée à la prise par un essai de garde.
- **M01, les trois cartes** (tour 44) : elles sont dans le dossier des cartes du faux robot (trois fichiers ajoutés à la
  brique 2, aucun fichier changé), parce que c'est là que la commande `brancher-carte` et la répétition les lisent, comme
  pour `plateau.yaml`. `vrai_robot: false` : ce sont des cartes pour le faux robot, tant que personne n'a vu le robot. Le
  format n'a que quatre chiffres (vitesse, portée, charge, force) : pour les deux robots à bras, portée, charge et force sont
  des valeurs « pour le faux robot seulement », écrites comme telles. Le Go2 n'a ni « parler » ni gestes sur sa carte
  (inconnu) : sa demande à un humain passe par la tablette seulement. Le genre du G1-D est « roues ».
- **L01, la table des sources** (tour 45) : le fichier est à côté du faux dossier, pas dedans (le faux dossier se contrôle
  et se signe fichier par fichier ; y ajouter un fichier l'aurait changé). Les badges de chaque ligne ne sont pas écrits à la
  main : on demande à la vraie porte ce qu'elle donne à un badge de chaque métier, et on relie ses réponses aux lignes de la
  table (colonnes « vue » et « acces »). Si la porte change un jour, la page change avec elle. Ce que l'avenant ne classe pas
  (lieux, réserve, feuilles volantes, liste des rendez-vous) est « INCONNU » : pas de source inventée.
- **L02 coupée en L02a et L02b** (tour 46). Le faux logiciel est un dossier à la racine (`faux_logiciel_admin/`), pas dans
  `briques/clinique/` : « un petit programme à part ». Il ne connaît pas notre système : l'heure lui est donnée par celui qui
  le lance. Sa liste de départ est dans le dépôt ; son état et ses messages vivent sous `journal/faux_logiciel_admin/` (hors
  du dépôt). Les numéros de séjour sont dans sa liste : c'est la « petite table à côté » de l'avenant ; le faux dossier ne
  change pas. Type de message : « ADT^A01 » (deux morceaux ; le troisième, la structure, est laissé de côté : à vérifier).
  Après une annulation d'admission (A11), le message porte encore la chambre annulée, puis la personne attend de nouveau.
  La sortie prévue n'est pas dans les messages (seulement la sortie faite) : sa place dans le standard est à vérifier.
- **L02b** (tour 47) : la page du faux logiciel est servie par le même petit serveur que nos écrans (un seul programme à
  lancer), mais son code est dans son dossier (`faux_logiciel_admin/page.py`) et n'importe rien de la clinique ; la clinique
  la branche par `lien_logiciel.py`. Cette page montre des noms inventés sans badge : elle est donc protégée comme les
  boutons de l'équipe (libre sur cet ordinateur ; code d'équipe ailleurs). « Ouvrir l'assistant » n'a pas d'écran par
  patient chez nous : une page `/clinique/ouvrir` montre la seule fiche que la porte donne au badge choisi. Un refus dit la
  même phrase pour « pas le droit » et « personne inconnue » : on ne révèle pas si une personne existe. Aucune vérification
  existante n'a été changée ; l'écran de l'accueil a seulement un lien de plus par arrivée.
- **L03 coupée en L03a et L03b** (tour 48). L03a : le traducteur ne garde pas un état qu'il modifie message après message ;
  il garde les messages (par leur numéro unique) et refait la vue en les rejouant dans l'ordre de leur heure, puis de leur
  numéro. Ainsi le désordre d'arrivée et les doublons ne comptent pas. Une personne est une paire (numéro de patient, numéro de
  séjour). Chaque message porte les renseignements du moment (nom, langue, chambre) : le dernier dans l'ordre gagne. Une
  admission annulée : « attendu » si une pré-admission existait, sinon la personne sort de la vue. Rien n'est gardé sur le
  disque : au démarrage, le traducteur relit le dossier. Le jour 1 = 14.11.2026 est la convention du faux logiciel, recopiée
  ici (`JOUR_1`).
- **L03b, la porte touchée le moins possible** (tour 49). Ce qui a changé dans `porte.py` : un champ `vue_admin` (vide par
  défaut), une fonction `_tous()` (faux dossier + personnes présentes arrivées par message, changées en fiches de la même
  forme, sans rien de médical), et trois lectures qui appellent `_tous()` au lieu de lire le faux dossier directement
  (patients visibles, comptes, arrivées pour le hall) ; plus la mention « dossier de soins : rien pour ce patient » dans la
  vue des métiers de soin, et la marque « par_message » dans les arrivées pour le hall. Les règles des badges n'ont pas
  bougé. Sans message, la porte rend exactement la même chose (un essai compare à une porte nue). Le faux dossier garde la
  main : un message ne change jamais une de ses fiches. Les « attendus » (pré-admission seule) et les sortis ne sont pas
  donnés. L'accueil répond dans la langue de la fiche seulement pour une personne arrivée par message et quand la langue de
  la phrase n'est pas sûre : l'étendre à tous aurait changé le comportement vérifié depuis T10.
- **L04 coupée en L04a et L04b** (tour 50). L04a : la pré-admission est une pièce à part (`pre_admission.py`) ; la pièce des
  papiers (T09) n'a reçu que deux champs (`arrives`, `retires`), vides par défaut : ses règles et ses essais ne changent pas.
  Les règles de la proposition ne lisent que des lignes simples (« Nom : », « Prénom : », « Née le », « Arrivée prévue le »,
  « Concerne : ») ; elles ne lisent jamais la ligne « Motif » ni la signature. Deux papiers d'accord : confiance haute ; un
  seul : moyenne ; désaccord ou absence : vide. Le message écrit porte le nom de notre système et pas de numéro de patient
  (c'est le logiciel administratif qui le donnera) ; le numéro de pré-admission (PA-0001) fera le lien avec la réponse.
  Un champ vide (la langue) n'empêche pas de valider ; seuls le nom et le prénom sont exigés.
- **L04b, la boucle fermée** (tour 51) : le faux logiciel lit lui-même le dossier « de nous vers le logiciel » (avec son
  propre petit lecteur : il n'importe toujours rien de la clinique). C'est lui qui donne le numéro de patient et le numéro de
  séjour ; son message d'admission porte le numéro de la pré-admission (PV1-5), et le traducteur s'en sert pour relier. La
  marque « admise » du carnet est écrite par le système (badge « suivi-des-pre-admissions ») : c'est la seule ligne de
  pré-admission qui ne vient pas de l'accueil, et elle ne décide rien. Le message de pré-admission n'a pas de civilité : la
  porte affiche « M./Mme » devant le prénom, pour garder la forme de nom que le reste attend. Les fonctions ne s'appellent ni
  « suivre » ni « annuler » : ces mots sont réservés aux commandes du robot par un essai de garde.
- **K03 coupée en K03a et K03b** (tour 52). K03a : les trois temps sont des notes de la boîte noire (quoi =
  « temps_d_un_geste », temps = DEMANDÉ, CONFIRMÉ ou CONSTATÉ), une par course, pas par petit geste. Les états du cahier ne
  changent pas : « livrée » veut toujours dire « le robot a fini » ; « constate » (oui / pas encore) et « constat » (la
  raison) s'ajoutent à la ligne de la tâche. Le constat du faux robot lit la place de l'objet dans le monde simulé, par
  l'état que la prise rend : c'est autre chose que « geste réussi », mais cela vient encore du programme du faux robot ; d'où
  l'étiquette SIMULÉ. Un essai « réussi et constaté » : réussi, et chaque livraison constatée (un essai sans livraison de
  robot compte aussi ; c'est écrit dans la ligne). La ligne commence par « EN PLUS » : les trois lignes « CHIFFRE » de K02
  restent trois.
- **K03b** (tour 53) : l'âge est compté dans la page, par le navigateur, depuis la dernière mise à jour RÉUSSIE (le milieu
  et l'heure reçus tous les deux). Un seul script pour tous les écrans : la limite est `LIMITE_VIEUX_S` (dix secondes),
  et chaque page peut en donner une autre. La zone grisée est tout le milieu de l'écran. « Je l'ai vu » est une fonction du
  tableau des tâches (`constater`), pas du coursier : elle marche même sans robot branché, et seul un humain de l'équipe y
  a droit. L'accord d'un humain pour un papier est noté dans la boîte noire par la route de la page (c'est elle qui a le
  bus) ; le carnet l'écrivait déjà.
- **K01 coupée en K01a et K01b** (tour 54). K01a : le tirage n'est pas tout à fait « au hasard » : il compose toujours
  dix demandes d'objet, dix arrivées et dix demandes impossibles, floues ou interdites (chaque sorte au moins une fois),
  puis il tire au hasard les mots, les langues et l'ordre. Ainsi « environ un tiers » est tenu et chaque refus est essayé
  à chaque tirage. Chaque course et chaque ordre se joue sur un faux robot neuf (les objets reviennent à la réserve). Les
  ordres interdits vont droit au gardien, sans le contrôle de la carte fait avant lui par la clinique : le tirage doit
  prouver que c'est le gardien qui dit non. « retirer_du_gardien » ne sert qu'à la vérification, sur une copie d'essai des
  règles. Les essais du tirage restent dans la vérification rapide (ils coûtent trente secondes) : les mettre de côté est
  la question Q16.
- **K01b** (tour 55) : le bouton joue la demande sur un faux robot neuf, pas sur le robot de la séance : une demande au
  hasard (un ordre interdit, par exemple) ne doit pas déranger la démonstration en cours. La route du bouton n'est pas
  « async » : le jeu fait tourner son propre petit monde, dans un fil à part. La dernière demande jouée est gardée en
  mémoire pour l'afficher ; rien n'est écrit dans le carnet de la séance.
- **J05 coupée en J05a et J05b** (tour 56). J05a : une pause n'est pas un nouveau mécanisme : ce sont des règles de plus dans
  le fichier que le gardien relit déjà pour la carte de rôle (`cartes_gardien.ecrire_les_regles(..., en_plus=…)`). Le coursier
  redonne le fichier au gardien avant un geste dès que la carte ou la liste des pauses en cours a changé (une pause finie à
  l'heure dite fait partie de ce changement). Pour « parler », on utilise la règle « demander d'abord à un humain » : le
  gardien n'a pas de règle qui interdit une action, et on ne touche pas à la brique 7. La durée est en minutes de l'horloge
  de démonstration (240 au plus). Une pause est par étage : celui du badge du soignant. La tâche qui attend revient à
  « demandée » avec « en_attente » : le même champ que pour les pannes.
- **J05b, « Qui décide »** (tour 57) : pour connaître les droits d'un badge, on ne lit pas une liste : on essaie le geste
  sur une clinique neuve, en mémoire. Un refus de la porte veut dire non ; toute autre réponse (même « ce n'est pas
  l'heure ») veut dire que la porte laisse passer. Ainsi la page suit le code qui décide vraiment. Les robots cités sont ceux
  dont la carte permet le geste (hall et parler ; se déplacer, saisir et poser). La recherche des promesses lit les pages
  servies et les fichiers du programme, pas les essais (qui citent ces phrases pour les interdire).
- **T23, le répartiteur** (tour 58) : une pièce à part, qui lit le monde des robots (R5) et les cartes (T22) et ne fait
  bouger que des robots simulés. R1 compte dans le choix (là où on l'a placé), mais le répartiteur ne le fait jamais bouger :
  la tâche garde son état et attend le coursier. « Assez de batterie » : la batterie moins le trajet (jusqu'au départ, puis
  jusqu'à l'arrivée) doit rester au-dessus du seuil de batterie basse du monde. À égalité de mètres, le robot au plus petit
  numéro gagne (pas de hasard). Le relais ne se cherche que si aucun robot ne peut faire tout le trajet ; le lieu de passage
  est celui qui donne le trajet total le plus court ; il est proposé dans la tâche (« relais_propose »), et la tâche passe à
  un humain tant que le relais n'est pas joué.
- **K04** (tour 59) : dans une séance avec un robot branché, le répartiteur choisit « pour de vrai » : un robot simulé ne
  peut pas livrer, il est donc écarté, et c'est dit. Sans cela, le plus proche serait souvent un robot simulé, et plus rien ne
  serait livré pour de vrai. L'annonce n'est pas un geste du robot : c'est un texte que la clinique écrit juste avant de
  demander au gardien (une annonce par la voix du robot serait un ordre de plus, à faire passer par le gardien : plus tard).
  Les annonces ne créent pas de ligne de tâche en plus (les états du carnet ne changent pas) : la dernière est gardée sur la
  ligne « livrée ». Dans la boîte noire, le champ s'appelle « robot_choisi » : le bus range « robot » ailleurs.
- **N01, les pages dans un navigateur** (tour 60) : je ne crée pas de réglage dans le dossier de l'assistant pour lancer le serveur (c'est un
  feu orange) : le serveur d'essai est un petit programme du dépôt (`outils/serveur_pages_vues.py`), lancé à la main, sur
  cet ordinateur seulement, avec des fichiers provisoires — surtout pour que le bouton « Réussi » des essais réels n'écrive
  jamais dans le vrai fichier de l'équipe. Deux navigateurs déjà là : le navigateur intégré (pour voir, lire les erreurs,
  appuyer) et Chrome sans fenêtre (pour les images en grand écran et la mesure automatique). La fenêtre de Chrome ne
  descend pas sous 500 points : la mesure met chaque page dans un cadre de 375 points. Tableaux sur petit écran : colonnes
  de largeur égale, mots coupés aux syllabes ; les mots entiers faisaient dépasser le tableau (essayé, mesuré, refusé).
- 12.11.2026, tour 61 (R2) : pour mesurer Apertus, on reprend les 30 demandes et le jugement du banc de l'ossature (`banc_cerveau.mesurer`), sans les changer, plutôt que d'écrire de nouvelles phrases : les chiffres se comparent à ceux du cerveau à règles. Quatre langues seulement (fr, de, it, en), celles de la clinique. Le serveur est lancé par `ServeurModele` de la brique 6, sans la changer. `docs/projet/MESURE_APERTUS.md` garde le dernier essai seulement ; les chiffres retenus sont recopiés dans le suivi et le journal. La première demande (« Bonjour ») met les consignes en mémoire et n'est pas comptée : c'est écrit dans le compte rendu.
- 12.11.2026, tour 62 (T13) : pour le résumé, ce sont les règles qui choisissent les faits (quelles sources, quels chiffres) ; le cerveau ne fait que les écrire, et sa ligne doit porter exactement les chiffres de la version simple. Raison : mesuré avec le vrai Apertus, il ajoutait les rendez-vous de demain, recopiait toute une fiche, ou inventait (« séjour prolongé »). Les questions de la patiente et les désaccords ne lui sont jamais confiés. Le contrôle de la version simple (`garder_les_phrases_sures`) n'est pas changé ; les nouveaux contrôles s'ajoutent. Par défaut la séance garde la version simple ; Apertus seulement si l'équipe lance avec `CLINIQUE_APERTUS=1` (une variable au lancement, pas un réglage de l'ordinateur). Formulaire : les phrases d'abord, « sûr » ensuite — dans l'autre ordre, le modèle répondait « pas sûr » à tout.
- 12.11.2026, tour 63 (H06a) : une vérification de plus dans `proposer_avec_cerveau` (T14) : la date proposée par un cerveau doit avoir la forme d'une date, sinon elle est retirée et le papier n'est pas « sûr ». C'est un ajout ; aucune vérification existante n'est changée. La mesure juge avec le genre du document dans le faux dossier, lu par la porte avec le badge du médecin d'exemple (et celui de l'accueil pour les feuilles sans nom) : le modèle ne le reçoit jamais. « Pas sûr » n'est pas compté comme une faute : un humain choisit. Le cas grave compté à part : « mal rangé et dit sûr ».
- 12.11.2026, tour 64 (H06b) : le tirage compris par Apertus est une commande à part (`tirage-apertus`) ; `tirage` et son option `--apertus` gardent leur comportement et leurs essais. Deux chiffres séparés : ce que le cerveau comprend, et ce que le système répond. Pour l'écran du soignant et le hall, la réponse reste celle des règles de la clinique (c'est ainsi dans la séance) ; pour un ordre au robot, l'action du cerveau va vraiment au gardien. Un geste « parti à tort » est tout geste exécuté sur une demande dont la bonne réponse était de ne rien faire ; « interdit exécuté » seulement si c'est le geste interdit lui-même (saisir, ou aller dans le hall).
- 12.11.2026, tour 65 (H07) : pour la chaîne entière, les phrases sont dites par la voix de synthèse du Mac (des ordres courts), pas prises dans les sons du dépôt (longues phrases lues, sans rapport avec un ordre). Aucun robot dans cette mesure : elle compte le temps et la mémoire. La règle « la mémoire manque » est écrite dans le programme avant la mesure (moins de 1 Go libre, ou plus de 0,5 Go d'échange en plus) et n'a pas été changée après. `docs/projet/MESURE_APERTUS.md` a deux parts : en haut le dernier essai d'Apertus, en bas la dernière mesure de la chaîne ; chaque commande ne réécrit que la sienne.
- 12.11.2026, tour 66 (H08a) : l'ébauche Unitree vise le Go2 et son `SportClient` (se lever, avancer, s'arrêter correspondent mot pour mot à StandUp, Move, StopMove) ; le G1 reste décrit dans sa fiche. « Se lever » est un geste de la carte (`se_lever`), demandé par la prise : jamais à la connexion ni au réarmement (règle de la brique 3). La doublure est une sous-classe du faux kit du projet, pour que le registre de l'ossature la reconnaisse comme fausse sans être modifié. Batterie et cap : rendus « inconnus » plutôt qu'inventés. Limites de la carte : les choix de prudence de la carte M01, acceptés par Hiba (Q10). Aucune brique de l'ossature n'est changée ; le nouveau dossier est celui que l'assistant de la brique 3 crée pour tout robot.
- 12.11.2026, tour 67 (H08b) : l'ébauche ROS 2 est réduite à trois choses (vitesse, arrêt, position) et à deux messages standards relus en ligne (Twist, Odometry). Les canaux inventés de l'ébauche d'origine sont retirés : un canal inventé n'existe sur aucun robot. La doublure est le faux ROS 2 du projet, sans changement ; il garde ses propres canaux inventés, mais notre liaison n'y écrit pas. La carte ne porte rien (charge 0) tant que rien n'est lu. `docs/projet/PREMIERE_HEURE.md` tient en une page et renvoie à `BRANCHER_UN_ROBOT.md` pour le détail ; les commandes du vrai robot y sont à taper par un humain (feu orange). Aucune brique de l'ossature n'est changée.
- 12.11.2026, tour 68 (T21) : après la relecture, la ligne du résumé écrite par un cerveau doit avoir les chiffres de la version simple dans le même ordre, tous ses mots longs, et aucun mot qui ne vienne ni des sources, ni de la version simple, ni d'une courte liste de petits mots ; aucune négation ajoutée. Pour les papiers : le patient est d'accord seulement avec le nom entier (avec ou sans « Madame ») ; l'auteur gardé est celui que la règle lit. Ce sont des ajouts : aucun contrôle existant n'est allégé, aucun essai établi n'est changé. Les phrases du cerveau écartées sont comptées à part des « phrases retirées faute de source ». La fiche de vérité lit les mesures du cerveau dans `journal/clinique/mesures_cerveau/` (jamais envoyé) ; un essai avec un cerveau de test n'y est jamais écrit. Les phrases périmées du suivi et de NON_TESTE.md sont corrigées par un ajout daté, sans effacer l'ancienne phrase.
- 12.11.2026, tour 69 (H09) : le cerveau se sert du badge « assistant » déjà prévu par la porte ; aucun nouveau rôle. Il travaille toujours « pour » la personne dont le badge a ouvert l'écran, et relit par la porte ce qu'il va recevoir : c'est cette lecture-là qui est au journal. Les mesures qui lisent le faux dossier prennent un badge qui a le droit de voir ce qu'elles lisent (soignant de l'étage, accueil), ou celui de l'assistant quand le texte va à un modèle. La porte n'est pas changée.
- 12.11.2026, tour 70 (H01, réponse de Hiba à Q18) : l'accueil ne reçoit plus par la porte le texte d'un papier, ni le programme, ni une liste de soin. La pièce qui range lit le texte par `porte.papiers_a_ranger`, réservée au badge « assistant, au service de l'accueil ». **Vérifications adaptées pour ce changement, et seulement celles-ci** : (1) `briques/clinique/tests/test_papiers.py`, essai `test_la_page_des_papiers_montre_les_propositions_et_un_doigt_valide` : il demandait « Feuille volante » et « Lettera per la signora » (le début du papier) sur la page de l'accueil ; il demande maintenant qu'ils n'y soient PAS, et le titre « Papier à trier » ; le reste de l'essai est inchangé. (2) `briques/clinique/tests/test_cerveau_par_la_porte.py` (écrit au tour 69) : trois essais disaient « sans cerveau, aucune ligne de l'assistant au journal » et comptaient les lignes de l'assistant ; depuis H01 la pièce qui range lit toujours sous ce badge ; ils vérifient maintenant qu'aucun texte n'est « donné au cerveau » sans cerveau. Aucun essai de `test_porte_lecture.py` n'a été touché. Le texte du papier reste dans le carnet (une proposition n'est faite qu'une fois) : limite écrite dans NON_TESTE.md.
- 12.11.2026, tour 71 (H02, réponse de Hiba à Q15) : la tâche créée par une question du soir ne recopie pas la question : elle renvoie à la ligne du carnet (« ligne N du carnet »). Raison : le tableau des tâches est lu par plusieurs métiers ; la question peut parler de santé ; le résumé du médecin la montre déjà avec sa source. La tâche est écrite avec le badge de la patiente (c'est sa question), « validée par un humain : non », par un chemin fermé à tout autre badge. Version la plus petite : pas de bouton « fait » pour le médecin.
- 12.11.2026, tour 72 (H03a, réponse de Hiba à Q19) : toutes les phrases traduites sont dans `traductions_ecrans.yaml`, et la traduction se fait après le dessin de l'écran, sur le texte affiché seulement. Raison : un seul fichier à relire, un seul endroit branché, aucune pièce d'écran réécrite. Les mots allemands déjà dans `ecrans.py` (« Meine Patienten », « Zimmer »…) y restent : ils datent de T03 et des essais établis les lisent. Les données ne sont traduites que si elles commencent par une valeur de la table ; une phrase du résumé n'est jamais touchée. La table du patient n'est pas allumée : deux essais établis disent le contraire, et seule Hiba peut permettre de les adapter (Q25).
- 12.11.2026, tour 74 (J06b-a, réponse de Hiba à Q7) : le fichier des paroles va dans `journal/clinique/`, le dossier qui ne part jamais vers GitHub, et son nom est refusé par `.gitignore` partout : deux protections contre l'oubli. Le modèle est un autre fichier, sans aucune parole. La pièce de lecture ne sait pas écrire. Le filet contre les noms met la ligne de côté sans la montrer, plutôt que d'effacer un mot : c'est à une personne de corriger. La page n'est pas branchée tant que Hiba n'a pas répondu à Q26.
- 12.11.2026, tour 75 (N01b) : la page ne remplace son milieu que s'il a changé, et jamais pendant un appui. Raison : un lien remplacé sous le doigt perdait le clic. Le rafraîchissement toutes les deux secondes reste (c'est le secours demandé par le cahier) ; seule la réécriture inutile disparaît. La vérification « qui clique vraiment » pilote Chrome par sa porte de pilotage, avec le paquet `websockets` déjà dans l'espace du projet : rien n'est installé ; sans Chrome, elle est sautée.
- 12.11.2026, tour 76 (H10a) : pour le mode interprète, le chemin en deux temps (écoute en français, puis Apertus avec les mots fixés) est retenu en attendant l'avis de Hiba : 8 phrases sur 10 sans erreur comptée contre 4 pour le chemin direct, pour 0,8 s de plus. Les contrôles se font contre la phrase vraiment dite quand on la connaît (la mesure), sinon contre le français entendu. Une phrase fausse est affichée telle quelle, avec son erreur : jamais corrigée en cachette. Les nombres ne sont mis en chiffres que s'ils sont dans la phrase française (« no one » n'est pas un nombre). Rien n'est téléchargé.
- 12.11.2026, tour 77 (H10b) : l'écran de régie est une page neuve de la clinique (`/clinique/regie`), pas une page de l'écran de l'ossature (brique 13, pas touchée). Le son est enregistré par la page et envoyé tel quel en fichier simple : rien à installer pour convertir. La traduction se fait hors de la boucle des écrans (un fil à part), une phrase à la fois. La voix sort du haut-parleur du Mac sans faire attendre l'affichage. Sans cerveau, la page ne retombe PAS sur le chemin direct (mesuré mauvais au tour 76) : elle dit qu'elle ne peut pas, et les réponses préparées servent. Les boutons de la régie demandent le code d'équipe depuis un autre ordinateur, comme les autres boutons protégés.
- 12.11.2026, tour 78 (N01c) : le passage des pages dans le navigateur est un programme (`outils/pages_vues_chrome.py`), pas une suite de clics à la main : il se refait à l'identique pour N02, et il presse les boutons par de vrais gestes de souris. Il tourne sur le serveur d'essai, jamais sur la vraie séance. Huit boutons au plus par page, chacun sur une page fraîche. Les images sont gardées dans le dépôt (3,5 Mo pour ce passage).
- 12.11.2026, tour 79 (T24) : la panne et la reprise sont une pièce à part (`panne_reprise.py`) qui appelle le monde des robots, le répartiteur et le tableau des tâches sans les changer ; la version simple de la flotte (T11c) et l'étape 12 restent telles quelles jusqu'à T25. Avec un robot branché, la reprise doit être une vraie livraison : les robots simulés sont écartés (comme dans la séance, K04). Un robot simulé arrivé ne passe jamais la tâche à « livrée » : elle reste « en route », avec une note. L'objet resté avec un robot en panne est seulement noté : le passage de main n'est pas simulé.

- 12.11.2026, tour 80 (T25) : le tableau de flotte est une nouvelle page (`/clinique/tableau-de-flotte`) ; la page simple `/clinique/flotte` et l'étape 12 ne sont pas changées (leurs essais disent « Pas de plan, pas de batterie. »). Le tableau prend le monde et le répartiteur du coursier s'il y en a un, sinon il en crée un. La panne provoquée depuis la page est refusée pour le robot branché. Le temps simulé avance seulement par un bouton, pour que rien ne paraisse bouger tout seul.
- 12.11.2026, tour 81 (T26) : relecture de la tranche 3. Le répartiteur garde l'ordre de ses raisons (panne, occupé, carte au départ ou à l'arrivée, chemin, batterie) et ajoute en dernier « un lieu du trajet interdit par la carte » : un essai établi demandait cet ordre, il n'est pas changé. Avec un robot branché, le tableau de flotte n'attribue rien (la demande part déjà par le coursier). Le tableau n'affiche rien pour la place et la batterie de R1 plutôt qu'un chiffre jamais lu. Les points 2, 4, 6, 7, 9 (feu), 13 du relecteur deviennent H11, H12, H13 au lieu d'être corrigés dans ce tour (un tour, une tâche).
- 12.11.2026, tour 82 (H11) : la carte de rôle est appliquée par le gardien pour tous les lieux du monde (pas seulement ceux du plan de la clinique) et pour les objets. Les nouvelles règles ont d'autres noms (`carte_hors_plan_…`, `carte_objet_…`, `carte_actions`) pour que l'essai établi sur `carte_lieu_…` reste vrai sans être changé. Pour « montrer » et « rejouer un geste », la règle est « demander à un humain », la seule que la brique 7 offre pour une action ; la brique 7 n'est pas touchée.
- 12.11.2026, tour 83 (H12) : la place de R1 dans le monde des robots vient de la prise (`Coursier.placer_dans`), lue avant le choix et après la course. Pour une reprise par le robot branché, l'objet est cherché à son lieu de départ, et la tâche le dit (`note_de_reprise`) : les robots simulés ne prennent rien pour de vrai. L'affichage de la place sur le tableau attend Q28.
- 12.11.2026, tour 84 (H13) : les pannes des robots simulés et les passages à un humain vont dans la boîte noire comme des notes « clinique » (même façon que les pauses : une liste d'attente, écrite par les fonctions qui peuvent attendre). Pour un robot simulé, la page « Pourquoi ? » n'affiche aucune couleur de feu : le gardien n'a rien décidé.
- 12.11.2026, tour 85 (T27) : pour les trois chiffres de la fiche, un essai = une étape de la répétition (1 à 12), rangée dans une seule case d'après les aides et les reprises imprévues arrivées pendant cette étape. L'étiquette est « FAUX ROBOT ET SIMULÉ » parce que les étapes mêlent les deux. Les essais automatiques ne remplacent pas la fiche gardée : seule la vraie commande `repetition` l'écrit.
- 12.11.2026, tour 86 (T28) : « À vous » réutilise le mécanisme des essais comptés (`repetition.variation`) au lieu d'en écrire un autre. Pour l'objet, c'est le vrai tableau des tâches qui décide s'il est absent, flou ou précis : la commande ne garde aucune liste d'objets. L'étape 8 lit « objet_flou » quand il est donné ; sans lui, elle garde son ancien comportement (seul « un coussin » est flou), et ses essais établis passent sans changement.
- 12.11.2026, tour 87 (K07a) : K07 coupée en K07a et K07b. Les boutons de l'invité rejouent les étapes de la répétition à part (comme « À vous »), pour que l'invité ne puisse pas casser la séance ; seule la panne agit sur la séance, parce que c'est la panne J02 elle-même et qu'elle ne fait qu'arrêter le robot. La page « Concours » n'existe pas encore : elle viendra avec K05 ; le lien vers l'écran Invité y sera mis à ce moment-là.
- 12.11.2026, tour 88 (K07b) : le seuil de taille de texte est un nouveau mot, `ecran.taille_texte_min_px: 18`, ajouté à `reglages.exemple.yaml` ; aucun réglage existant n'est changé, et `reglages.yaml` (le fichier de l'équipe) n'est pas touché : sans ce mot, la mesure prend la valeur de l'exemple. 18 px est mon choix, à revoir avec Hiba. Le style plus gros (`STYLE_LISIBLE`) ne s'applique qu'aux écrans Invité et Patient : les autres écrans gardent leur style. Mon essai `test_invite.py` du tour 87 est corrigé (une ligne : un dossier à part pour le faux logiciel) ; ce n'est pas un essai affaibli : il vérifie la même chose sans toucher au dossier de l'équipe.
- 12.11.2026, tour 89 (T29) : le rejeu autonome joue lui-même une répétition, au lieu d'en lire une ancienne : la répétition ne garde que sa fiche, pas ses événements. Pour enregistrer sans toucher aux pièces, la commande remplace `Bus.publier` et `Carnet.ecrire` le temps de la répétition par des versions qui copient puis appellent l'original, et les remet après (un essai le vérifie). Les pages utilisent l'apostrophe typographique (’) pour que le texte reste lisible tel quel dans le fichier.
- 12.11.2026, tour 90 (T30) : les codes QR attendent Hiba (Q29) ; la page écrit les adresses en gros, comme le cahier le permet. Le garde-fou des essais (`conftest.py`, tout réseau coupé sauf cet ordinateur) n'est pas touché : l'essai par le vrai Wi-Fi est une commande à part, `python3 lancer.py telephones`, et l'essai automatique vérifie seulement qu'elle n'annonce pas « réussi » quand le réseau lui est refusé.
- 12.11.2026, tour 91 (T31) : deux fichiers pour le robot à roues à deux bras. La carte d'exemple du FAUX ROBOT porte les chiffres du cahier (5 kg par bras, à vérifier) pour que la conformité et le coussin soient essayés. L'ébauche pour un VRAI robot garde la règle du modèle vide (un chiffre pas lu dans la doc reste 0, le robot refuse de bouger) ; le 5 kg n'y est qu'en note. Pas de nouveau nom de fabricant dans le cerveau.
- 12.11.2026, tour 92 (J07a) : J07 coupée en J07a (la page) et J07b (la commande). Les boutons sont des liens vers des pages qui existent, plus trois pages neuves ; aucune preuve n'est refaite. « Où tourne quoi » ne lit que les mesures gardées par les commandes (`journal/clinique/mesures_cerveau/`) et les réglages ; rien n'est mesuré au moment d'ouvrir la page. Un seul changement dans une pièce existante : un repère `id='attrapees'` sur la ligne des erreurs attrapées de la page des moments.
- 12.11.2026, tour 93 (J07b) : la commande des preuves réutilise les commandes de chaque preuve (essais, répétition enregistrée, panne, reprise, brancher-carte, pages) sans les changer ; ce qu'elles écrivent va dans un dossier à part, pour ne pas changer les fichiers de l'équipe (tableau des essais, chronomètre du branchement). L'option `--court` (trois essais) sert aux vérifications automatiques ; la ligne le dit.
- 12.11.2026, tour 94 (K05) : la liste des capacités est un fichier (`capacites.yaml`) qui dit où regarder, sans aucun résultat ; une vérification interdit d'y écrire un chiffre de réussite. Une ligne n'entre dans la colonne « vrai robot » qu'avec au moins un essai RÉEL réussi (un essai raté est montré, mais ne suffit pas). La page « Concours » de l'avenant 2 (partie 6) aurait dû être créée par la première tâche K finie : elle est créée maintenant ; la commande du concours devient la tâche KC.
- 12.11.2026, tour 95 (K06) : la collecte est allumée selon le oui de Hiba à Q9. Le formulaire n'accepte que le rôle et cinq notes (tout autre champ refusé). Un avis envoyé par le formulaire est RÉEL ; seules les vérifications envoient des avis ESSAI, et toujours dans un fichier à part. Les avis réels et les avis d'essai ne sont jamais mélangés sur la page. Le formulaire ne demande pas le code d'équipe (les personnes servies n'en ont pas) ; il refuse seulement une requête venue d'un autre site.
- 12.11.2026, tour 96 (KC) : la commande du concours réutilise les pièces des tâches K sans les changer ; tout ce qu'elle écrit va dans un dossier à part. Le contrôle 3 réutilise le petit banc Node de l'essai K03b (importé depuis `tests/`), pour jouer le même JavaScript que la page. `--court` sert aux vérifications automatiques (un tirage, dix secondes d'endurance) et chaque ligne le dit.
- 12.11.2026, tour 97 (H05) : changement de la brique 15, avec l'accord de Hiba (Q20, conditions : seulement ajouter, aucune étape existante ne change, toutes les vérifications de l'ossature passent sans être changées, un tour). Ajouté : la sorte d'étape `controle: NOM` dans `scenario.py` ; le paramètre `controles` de `ChefDemo` et la fonction `_etape_controle` dans `chef.py` ; la ligne de résumé dans `verifier.py` ; une ligne du tableau dans `GUIDE.md`. La brique 15 ne connaît aucune pièce de la clinique : c'est la clinique qui lui donne ses contrôles par leur nom. Rien n'est retiré ni changé pour les six sortes d'étapes qui existaient.
- 12.11.2026, tour 98 (N03a) : la séance unique refait les gestes des étapes sur une clinique partagée, dans un module à part (`seance_unique.py`), au lieu de changer les quatorze étapes établies (qui gardent leur clinique neuve pour la grande répétition). Tout passe par les vraies pages et la boucle du faux robot : les appels aux écrans et la course tournent dans la même boucle que le chef. La commande compte ce qui est monté pendant la séance, pour prouver « une seule clinique ». Par défaut, le faux robot va à vitesse normale pour mesurer une vraie durée ; `--vite` sert aux vérifications.
- 12.11.2026, tour 99 (N03b) : la séance unique ouvre la séance de la grande répétition (`repetition.seance()`) autour de tout le jeu du chef, et note chaque étape dedans : ainsi la fiche de vérité (13) et « rien n'est sorti » (14) se calculent sur cette séance, avec la même pièce que la répétition pour l'étape 14. `jouer()` garde par défaut les scènes 1 à 3, pour que les essais de N03a restent vrais sans être changés ; la commande joue les sept.
- 12.11.2026, tour 100 (N02) : la mesure établie en largeur de téléphone (`test_pages_sur_telephone.py`) n'est pas changée ; les pages nouvelles ont leur propre essai, qui réutilise sa fonction de mesure. L'outil de passage reçoit une liste de pages N02 (option `--n02`) ; sa liste N01c reste la même. Les images de N02 sont enregistrées comme celles de N01 (8 Mo).
- 12.11.2026, tour 101 (T32) : les guides par pièce sont dans `briques/clinique/guides/` (un dossier par pièce de la partie 5), à côté du `GUIDE.md` et du `TACHES.md` de toute la clinique, qui restent. Une tâche dont le résultat est une observation (sur un vrai téléphone, sur un autre ordinateur) a pour test une note signée dans `docs/projet/PAGES_VUES.md` ou `NON_TESTE.md`, pas un essai automatique qui passait déjà avant.
- 12.11.2026, tour 103 (H03b) : lignes d'essai adaptées avec l'accord de Hiba (Q25 A, plus un accord à part pour la troisième) : `test_ecrans.py` — `test_le_patient_ne_voit_que_lui_dans_sa_langue` (« fisioterapia » / « visita del medico » au lieu des mots français) et `test_l_ecran_suit_l_horloge_et_montre_temps_accelere` (« visita del medico ») ; `test_traductions_ecrans.py` — l'essai « éteinte en attendant Q25 » devient « allumée depuis Q25 » (italien, allemand, anglais traduits ; français inchangé). Ce que ces essais vérifient (le programme du bon jour) ne change pas.
- 13.11.2026, tour 104 (J06b-b) : lignes d'essai adaptées avec l'accord de Hiba (Q26 A, plus un accord à part pour les deux dernières) : `test_parole_des_soignants.py` — « zéro parole » devient « zéro parole tant que le fichier de l'équipe n'existe pas » ; « la page ne lit aucun fichier » devient « la page ne lit que ce fichier-là, par la pièce de lecture » ; `test_paroles_fichier.py` — « aucun fichier n'existe » devient « sans le fichier, zéro parole » (lu dans un fichier provisoire) ; « la page n'est pas branchée » devient « la page est branchée par la pièce de lecture ». Choix : une parole recueillie ne change pas l'étiquette des listes de soin (HYPOTHÈSE), parce qu'une personne qui parle ne valide pas une liste. Ordre des tâches : à la demande de Hiba (13.11), H15 (les deux Mac) passe avant H14.
- 13.11.2026, tour 105 (H14) : la règle C est placée dans `traiter`, après tous les filtres et juste avant le verrou des chiffres et `_agir` : seules les actions venues d'un cerveau sont touchées ; les ordres d'un humain qui a la main et les gestes du coursier ne passent pas par là et restent permis. La boîte noire note `parole_du_cerveau_refusee` avec le texte proposé. Les réponses de discussion du cerveau ne sont pas touchées (le texte de la règle vise l'action « parler »).
- 13.11.2026, tour 106 (H16a) : seule la personne qui a parlé (`qui_demande`) confirme sa phrase ; la confirmation est une ligne de plus au carnet, la première ligne (« validée : non ») n'est jamais réécrite ; la course du robot part sans attendre (Q23 parle du carnet, pas du départ). Aucun essai établi changé.
- 13.11.2026, tour 107 (H17) : pour ne changer aucun essai établi (H01 : `liste_de_soin` refusée à l'accueil, `listes` absent de sa vue des patients), une nouvelle porte étroite donne à l'accueil seulement les points « pour : accueil » de la liste de sortie, avec nom, chambre, étage et jour de sortie. Seul le badge accueil lui-même coche (pas un assistant à son service). La coche est écrite au carnet avec les mêmes champs qu'une coche au doigt.
- 13.11.2026, tour 108 (H18) : ligne d'essai adaptée avec l'accord de Hiba (Q28 A) : `test_relecture_tranche_3.py`, `test_point_3_avec_le_faux_robot_branche…` — « "pas lue" in ligne and "pas suivie" in ligne » devient « "lue sur le robot" in ligne and "lu sur le robot" in ligne ». Le reste de la ligne (FAUX ROBOT, pas de « 100 % ») est gardé ; d'où pas de chiffre de batterie (Q34). Afficher la page ne déplace pas R1 : `lire_la_place` ne fait que lire.
- 13.11.2026, tour 109 (H19a) : segno installé depuis le fichier téléchargé (`pip install --no-deps --no-index`), après lecture de sa licence ; ajouté à requirements.txt (le contrôle de l'installation le demandera aussi au MacBook). Toujours `make_qr` (jamais un micro code). La vérification ne croit pas segno : CoreImage, déjà sur le Mac, relit le code. La pièce n'est pas branchée sur la page tant que Q35 n'a pas de réponse (un essai établi y demande « Codes QR : pas encore »).
- 13.11.2026, tour 110 (H20) : le modèle se choisit par `--modele` (small par défaut) le temps d'une mesure ; `ecoute.MODELE` et `ecoute.OUTIL` sont remis après, même en cas d'erreur. Medium n'est pas ajouté au catalogue (pour ne changer aucun essai du catalogue) : taille, empreinte et licence sont dans LICENCES.md et le journal. Aucun réglage changé : small reste l'écoute de l'interprète.
