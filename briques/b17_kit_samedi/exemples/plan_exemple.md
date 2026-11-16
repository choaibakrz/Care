# Plan du défi — Défi 2 — « Bienvenue aux bains »

> Fait par le kit du samedi matin (brique 17), hors ligne, en cherchant des mots-clés. **À relire et ajuster par un humain** : le kit repère, il ne comprend pas.
> Tout le projet est testé sur faux robot seulement : rien n'a encore été essayé sur un vrai robot (NON_TESTE.md). Les chiffres sans source sont **à vérifier**.

Sommaire : 1. Résumé · 2. Briques prêtes · 3. Ce qui manque · 4. Plan heure par heure · 5. Équipes · 6. Risques · 7. Scénario · 8. Jury · Annexes

## 1. Résumé du défi

- **Texte écrit en** : français (deviné par le kit).
- **Robot** : humanoïde (mots trouvés : « humanoïde », « deux jambes »). S'entraîner sur le faux robot : `python3 lancer.py --robot humanoide`.
- **Capacités demandées** (la plus importante d'abord ; « prête » = testé sur faux robot) :
  - **prendre et apporter un objet** — en partie (mots : apporter, objet, objets, livraison ; 7 fois, dans 1 critère(s) du jury)
  - **parler et comprendre** — prête (mots : accueillir, parler, répondre, conversation ; 5 fois, dans 1 critère(s) du jury)
  - **plusieurs langues** — prête (mots : dans sa langue, plusieurs langues, langues ; 3 fois, dans 1 critère(s) du jury)
  - **voir et reconnaître** — à construire (mots : reconnaître ; 1 fois)
  - **se déplacer** — prête (mots : accompagner ; 1 fois)
  - **demander de l'aide quand il ne sait pas** — prête (mots : ne sait pas ; 1 fois)
- **Langues** : français, allemand, suisse allemand, italien, anglais (prêtes).
- **Durées repérées** : 48 heures; 6 minutes (démonstration); 4 minutes (démonstration).
- **Horaires repérés** : 9 h — « Le robot fourni est un robot humanoïde à deux jambes. Son kit de programmation sera distribué samedi à 9 h. ».
- **Critères du jury** : 6 repéré(s) → partie 8.
- **Règles de sécurité du défi** : 5 repérée(s) → partie 6.
- **Lieux et objets déjà dans le faux monde** : entree (« entrée »), table (« table »), bouteille (« bouteille »), valise (« valise »). Les autres : à ajouter dans `commun/monde.yaml`.

**Les chantiers du samedi, dans l'ordre :**

1. Les adaptateurs, un par vrai robot (brique 3) — brancher le vrai robot (toujours nécessaire)
2. Les yeux (brique 5) — prendre et apporter un objet ; voir et reconnaître

### Questions à poser aux organisateurs

- [ ] Où sont le kit de programmation du robot et sa documentation, et sous quelle licence ?
- [ ] Vitesse maximale, arrêt d'urgence, chien de garde du robot : où est-ce écrit ? (à vérifier dans le kit du fabricant)
- [ ] À quelle heure passons-nous devant le jury ?

## 2. Briques prêtes

Testées sur faux robot, sur un ordinateur Linux. **Aucune n'a encore été essayée sur un vrai robot, ni sur les Mac** (NON_TESTE.md).

### Brique 1 — La prise universelle · prête
- Sait faire : 10 actions dites pareil pour tous les robots (PRISE.md) ; carte d'identité du robot (capacités, limites, gestes) ; ticket signé du gardien, à usage unique ; suivre et annuler une action longue.
- Commandes : `python3 lancer.py tests briques/b01_prise` · `python3 lancer.py tests briques/b02_faux_robot -k conformite`
- Utile pour ce défi : se déplacer, prendre et apporter un objet.

### Brique 2 — Le faux robot · prête
- Sait faire : trois cartes (humanoïde, chien, bras), chiffres inventés pour la simulation ; pannes d'entraînement (lenteur, refus, perte de liaison, batterie faible, arrêt ignoré) ; chien de garde simulé ; vue de dessus à l'écran.
- Commandes : `python3 lancer.py` · `python3 lancer.py --robot bras` · `python3 lancer.py --robot chien` · `python3 lancer.py demo`

### Brique 3 — Les adaptateurs, un par vrai robot · version minimale
- Sait faire : modèle vide commenté : la mécanique commune (arrêt d'urgence d'abord, chien de garde, vitesse bridée) + une liaison à brancher ; assistant : python3 lancer.py brancher NOM crée le dossier du robot (carte, liaison, adaptateur, test prêt à lancer) ; test de conformité en deux temps : sans mouvement, puis complet (lent) ; vrai robot = phrase tapée au clavier ; deux chemins : kit Python du fabricant (SDK) ou pont ROS 2, chacun avec son faux pour les tests.
- Attention : aucun vrai robot, aucun vrai kit, ROS 2 jamais installé : tout est testé sur faux robot ; aller à un lieu nommé : pas branché (seulement dx, dy) ; position du vrai robot non donnée au gardien.
- Commandes : `python3 lancer.py brancher NOM --genre humanoide --chemin sdk` · `python3 lancer.py brancher NOM --conformite` · `python3 lancer.py brancher NOM --conformite --vrai            (feu orange, à taper par un humain)` · `python3 lancer.py brancher NOM --conformite --vrai --complet  (feu orange, mouvements lents)` · `python3 lancer.py tests briques/b03_adaptateurs`

### Brique 4 — Les oreilles et la voix · prête
- Sait faire : écoute en fr, de, gsw, it, en, zh ; langue reconnue ; réponse dans la même langue ; suisse allemand compris, réponse en allemand ; fin de parole, interruption, mot d'appel, bouton « je parle » ; « stop » prioritaire partout ; confirmation avant saisir et poser.
- Attention : testé sur Linux seulement ; vrai micro et vrai haut-parleur jamais essayés ; la voix du Mac (say) n'a jamais été lancée ; noms des voix à vérifier.
- Commandes : `python3 lancer.py micro` · `python3 lancer.py micro --declenchement bouton` · `python3 lancer.py banc-voix` · `python3 lancer.py enregistrer gsw --prenom …`
- Utile pour ce défi : parler et comprendre, plusieurs langues.

### Brique 6 — Le cerveau · prête
- Sait faire : cascade Apertus 8B → Apertus 4B → cerveau à règles, passage automatique ; formulaire forcé : une action de la carte ou une question, rien d'autre ; filets « cible non nommée » et « verrou des chiffres » ; banc d'essai de 30 demandes × 6 langues.
- Attention : Apertus 8B et 4B jamais lancés (testé ici avec Apertus 0,5B seulement).
- Commandes : `python3 lancer.py cerveau` · `python3 lancer.py cerveau --partager` · `python3 lancer.py banc-cerveau`
- Utile pour ce défi : parler et comprendre, plusieurs langues.

### Brique 7 — Le gardien · prête
- Sait faire : règles en phrases simples (regles.yaml) ; phrase et chiffre doivent aller ensemble, sinon pas de démarrage ; vitesse, force, distance aux personnes (1 m), escalier, zones, valise, poids, objets fragiles ; trois réponses : oui (ticket), non (expliqué dans la langue), « demande à un humain » (main levée) ; seul à fabriquer les tickets ; tout revérifié après l'accord d'un humain.
- Attention : positions et personnes simulées ; jamais avec de vrais yeux.
- Commandes : `python3 lancer.py tests briques/b07_gardien`
- Utile pour ce défi : se déplacer, prendre et apporter un objet.

### Brique 8 — « Je ne suis pas sûr » · prête
- Sait faire : ordre flou, deux lieux ou deux objets → une question, jamais une action (20 demandes floues testées) ; main levée après deux « pas compris » ou deux échecs de suite ; un humain apprend un mot au robot (« frigo » = cuisine), gardé au démarrage suivant.
- Attention : le robot ne comprend pas encore la réponse à sa propre question (« Où ? » → « à la cuisine »).
- Commandes : `python3 lancer.py tests briques/b08_doute`
- Utile pour ce défi : demander de l'aide quand il ne sait pas.

### Brique 12 — La boîte noire et la fiche de vérité · prête
- Sait faire : journal d'événements, une ligne par événement (journal/) ; fiche de vérité calculée depuis les événements (réussites, ratés, refus, part de l'humain, temps) ; mention automatique « faux robot » ou « vrai robot » ; rejeu d'une session.
- Commandes : `python3 lancer.py rejouer` · `python3 lancer.py demo`

### Brique 13 — L'écran du jury · prête
- Sait faire : écran de l'équipe (vue de dessus, ARRÊT, Réarmer, tablette) et écran du jury /jury ; entendu / compris / va faire / refuse parce que / question / aide, en direct ; sous-titres dans la langue parlée et dans une 2e langue ; fiche de vérité en grand ; bouton « Internet coupé » (vraie coupure du programme), mode silence, flux pour le motion design.
- Attention : jamais sur le grand écran du Carnival, ni Safari, ni iPad, ni Mac.
- Commandes : `python3 lancer.py   (puis http://<cet-ordinateur>:8000/jury)`
- Utile pour ce défi : demander de l'aide quand il ne sait pas.

### Brique 14 — La porte des agents (MCP) · version minimale
- Sait faire : serveur MCP sur stdio (paquet officiel mcp 2.3.0, MIT) ; cinq outils : dire_au_robot, voir_carte, voir_etat, voir_fiche, arreter ; chaque ordre d'un agent passe par la chaîne de la voix (cerveau, gardien, ticket, prise), source « agent:nom » ; accord d'un humain pour chaque action d'un agent (allumé par défaut) ; ordres par minute limités ; « stop » et arrêt toujours permis ; fiche de vérité et boîte noire : demandes des agents, ordres refusés par la porte.
- Il manque : version HTTP dans le même programme que l'écran principal (nécessaire avant un vrai robot).
- Attention : jamais essayée dans une vraie session de l'assistant de code ; l'enregistrement dans l'assistant de code est un réglage de Hiba (feu orange) ; la commande crée son propre système : faux robot seulement.
- Commandes : `python3 lancer.py porte-agents --agent assistant` · `python3 lancer.py tests briques/b14_porte_agents`

### Brique 15 — Le chef de démonstration · prête
- Sait faire : jouer un scénario YAML vérifié avant de jouer (toute clé inconnue refusée) ; plans B dans l'ordre (tablette, mode local, main humaine, sauter), notés dans la boîte noire ; répétition avec pannes provoquées ou tirées au hasard, accélération ; compte rendu de la démonstration ; essai de 3 minutes mesuré à 174,81 s (faux robot, cerveau à règles).
- Attention : jamais joué avec Apertus ni avec la vraie voix.
- Commandes : `python3 lancer.py scenario essai_3_minutes.yaml` · `python3 lancer.py scenario essai_3_minutes.yaml --repetition --panne robot@7 --acceleration 20` · `python3 -m briques.b15_chef_demo.verifier MON_SCENARIO.yaml`

## 3. Ce qui manque

Par capacité demandée : quelle brique, quelle tâche (prise dans son TACHES.md). Une tâche = une personne, moins d'une heure, avec son test.

### Toujours : brancher le vrai robot (brique 3, version minimale)
Un **adaptateur** est le petit programme qui traduit les 10 actions de la prise universelle en ordres pour CE robot. Le modèle et l'assistant existent (`python3 lancer.py brancher`, BRANCHER_UN_ROBOT.md) ; la liaison de CE robot reste à écrire samedi.

- [ ] Samedi, suivre BRANCHER_UN_ROBOT.md (skill brancher-un-robot) avec le robot du défi.
- [ ] Chronomètre « robot inconnu » à l'écran du jury (idée 12), avec la personne de l'écran (brique 13).

### Prendre et apporter un objet — en partie
- Briques : 1 (prête), 7 (prête), 5 (à faire).
- Mots du défi : apporter, objet, objets, livraison.
- Dans le texte : « Apporter un objet demandé (une bouteille d'eau, une serviette) depuis la table d'accueil jusqu'au visiteur. »
- Brique 5 — premières tâches (dossier à créer) :
  - [ ] Simuler une caméra dans le faux robot (petite image du monde) — tâche de la brique 2.
  - [ ] Trouver un objet nommé dans une image (MediaPipe, décidé par Hiba).
  - [ ] Repérer les personnes (pour la règle « distance aux personnes » du gardien).

### Voir et reconnaître — à construire
- Briques : 5 (à faire).
- Mots du défi : reconnaître.
- Dans le texte : « Reconnaître l'objet demandé parmi plusieurs objets posés sur la table. »
- Brique 5 : mêmes tâches que pour « prendre et apporter un objet », plus haut.

**Déjà prêt pour ce défi** (testé sur faux robot) : parler et comprendre, plusieurs langues, se déplacer, demander de l'aide quand il ne sait pas.

## 4. Plan heure par heure (samedi 9 h → lundi 9 h)

Heures officielles du Carnival (repas, passage devant le jury) : **à vérifier**. Si la démonstration est plus tôt, avancer d'autant les gels et les répétitions.
Un **gel du code** est un moment après lequel on n'ajoute plus rien : on corrige seulement. **Feu orange** = tout ce qui touche le vrai robot attend le « oui » de Hiba.
Sommeil par rotation, nuit 1 : R1 dort samedi 22 h – dimanche 4 h ; R2 dort dimanche 1 h – 7 h ; R3 dort dimanche 4 h – 10 h. Nuit 2 : tout le monde dort 23 h – 5 h.

### Samedi 14 novembre

| Heure | Ce qu'on fait | Qui |
|---|---|---|
| 09 h | Arrivée. Liste docs/projet/SAMEDI_MATIN.md : réseau local, les deux Mac, python3 lancer.py tests. | tous |
| 10 h | Lire le défi avec le kit (python3 lancer.py kit-samedi). Réunion de 20 minutes : ce plan, les équipes, les feux. | tous |
| 11 h | Brancher le vrai robot (humanoïde) — feu orange. Test de conformité sans mouvement. Arrêt d'urgence physique ET logiciel. | Adaptateurs + Sécurité ; les autres : leurs tâches, sur faux robot |
| 12 h | Repas, en deux services : deux personnes restent toujours près du robot. | tous |
| 13 h | Construire : les adaptateurs, un par vrai robot (brique 3) et les yeux (brique 5). Tout sur faux robot d'abord. | équipes |
| 14 h | Construire. Adaptateur : premières actions sans mouvement (état, regarder, parler). | équipes |
| 15 h | Point de 15 minutes : chaque chef dit « fait / bloqué / besoin d'aide ». | chefs d'équipe + Hiba |
| 16 h | Construire. Premier mouvement du vrai robot : lent, bouton physique en main — feu orange. | Adaptateurs + Sécurité ; les autres : construire |
| 17 h | Premier essai de bout en bout sur faux robot : phrase → gardien → action → fiche de vérité. | Tests + Démonstration |
| 18 h | Construire : les tâches des TACHES.md. Premier scénario de démonstration écrit (brouillon du kit). | équipes ; Démonstration |
| 19 h | Repas. | tous |
| 20 h | Point de 15 minutes. Relecture sécurité des changements du jour (gardien, prise, adaptateur). | chefs + Relecteurs |
| 21 h | Construire. Sauvegarde : commit, journaux copiés sur le second Mac. | équipes |
| 22 h | R1 va dormir. Les autres : petites tâches des TACHES.md, sur faux robot. | R2, R3 |
| 23 h | Construire. Vrai robot : seulement si le responsable sécurité ou son adjoint est réveillé. | R2, R3 |

### Dimanche 15 novembre

| Heure | Ce qu'on fait | Qui |
|---|---|---|
| 00 h | Construire. Lancer tous les tests (python3 lancer.py tests). | R2, R3 |
| 01 h | R2 va dormir. R3 : tests, guides, phrases dans les langues du défi. Robot éteint. | R3 |
| 02 h | Petites tâches sans vrai robot. | R3 |
| 03 h | Répétition « à blanc » du scénario sur faux robot ; noter ce qui casse. | R3 |
| 04 h | R1 se lève, R3 va dormir. R1 relit ce que R3 a fait (celui qui écrit n'est pas celui qui vérifie). | R1 |
| 05 h | Construire. | R1 |
| 06 h | Construire. Préparer la zone de démonstration (vide, marquée au sol). | R1 |
| 07 h | R2 se lève. Petit-déjeuner. | R1, R2 |
| 08 h | Construire. Vrai robot : essais lents — feu orange. | R1, R2 |
| 09 h | Construire. | R1, R2 |
| 10 h | R3 se lève. Point de 20 minutes avec tout le monde : ce qui marche, ce qu'on abandonne. | tous |
| 11 h | Construire : finir les adaptateurs, un par vrai robot (brique 3) et les yeux (brique 5). | équipes |
| 12 h | **Repas. GEL DES FONCTIONS après le repas : plus de nouvelle fonction, on finit et on corrige.** | tous |
| 13 h | Finir, corriger, tester. Plans B prêts : tablette, main humaine, mode local. | équipes |
| 14 h | Répétition 1 : le scénario entier sur faux robot, chronométré. | Démonstration + tous |
| 15 h | Corriger ce que la répétition 1 a montré. | équipes |
| 16 h | Répétition 2 : avec le vrai robot — feu orange. Provoquer exprès chaque plan B. | Démonstration + Sécurité + Adaptateurs |
| 17 h | Corriger. Relire la fiche de vérité et la boîte noire des répétitions. | équipes |
| 18 h | Répétition 3 : devant trois personnes qui jouent le jury ; préparer les réponses aux questions. | tous |
| 19 h | Repas. | tous |
| 20 h | **GEL DU CODE : plus aucun changement, sauf correction acceptée par Hiba et un relecteur. Version finale gardée sur les deux Mac.** | Architecte + Relecteurs |
| 21 h | Pitch : textes, chiffres de la fiche de vérité, réponses au jury. | Démonstration + Rédacteur |
| 22 h | Matériel : batteries, câbles, Mac, micros. Charger seulement sous surveillance. | Sécurité + Adaptateurs |
| 23 h – 05 h | Tout le monde dort (code gelé, robot éteint). | tous |

### Lundi 16 novembre

| Heure | Ce qu'on fait | Qui |
|---|---|---|
| 05 h | Lever, petit-déjeuner. | tous |
| 06 h | Liste docs/projet/SAMEDI_MATIN.md une seconde fois : tests, robot, arrêt d'urgence physique et logiciel. | Sécurité + Adaptateurs + Tests |
| 07 h | Répétition générale, la dernière. Rien ne change après. | tous |
| 08 h | **DÉMONSTRATION devant le jury (heure exacte à vérifier dans le programme officiel).** | Démonstration + Sécurité ; les autres : public |

## 5. Répartition des 35 personnes

35 personnes, chacune dans **une seule** équipe. La première personne de la liste est le chef. « Vérifié par » : celui qui écrit n'est pas celui qui vérifie. Les prénoms : annexe A.
Le **responsable sécurité** (équipe Sécurité) peut tout arrêter, à tout moment, sans discussion.

| Équipe | Personnes | Mission | Briques | Vérifié par |
|---|---|---|---|---|
| Responsable | P01 (Hiba) | Décide ; dit « oui » ou « non » à chaque feu orange ; parle au jury. | — | — |
| Sécurité | P02, P03 | Responsable sécurité et son adjoint : la main sur le bouton d'arrêt PHYSIQUE à chaque mouvement du vrai robot ; peuvent tout arrêter, sans discussion. | 7 | Responsable |
| Relecteurs sécurité | P04, P05 | Relisent chaque changement du gardien, de la prise et des adaptateurs, avant la fusion. | 1, 3, 7 | — |
| Architecte | P06 | Garde la prise universelle stable ; rassemble le code ; tient les gels du code. | 1 | Relecteurs sécurité |
| Tests | P07, P08 + renforts P34, P35 | Les six preuves, Internet coupé ; lance les tests avant chaque fusion. | 12 | Architecte |
| Rédacteur des guides | P09 | Guides d'une page, TACHES.md à jour, textes du pitch en mots simples. | — | Responsable |
| Démonstration | P10, P11 | Le scénario, les répétitions, le chronomètre, les plans B, le pitch (brique 15). | 15 | Responsable |
| Adaptateurs | P12, P13, P14, P15 + renforts P26, P27, P28, P29 | Brancher le vrai robot : adaptateur, carte d'identité, test de conformité. Pour ce défi : brancher le vrai robot (toujours nécessaire). | 3 | Tests + relecteurs sécurité |
| Gardien | P16, P17 | Les règles du défi dans le gardien ; refus expliqués. | 7 | Relecteurs sécurité (obligatoire) |
| Cerveau | P18, P19 | Apertus sur les Mac ; les mots du défi dans le cerveau à règles. | 6 | Tests + relecteurs sécurité |
| Voix | P20, P21 | Écoute et voix dans les langues du défi ; micro de la salle. | 4 | Tests |
| Yeux | P22, P23 + renforts P30, P31, P32, P33 | Trouver les objets et les personnes du défi. Pour ce défi : prendre et apporter un objet ; voir et reconnaître. | 5 | Tests |
| Écran | P24, P25 | Écran du jury, sous-titres, fiche de vérité en grand. | 13 | Tests |

## 6. Risques

### Les risques de ce défi

- **Prendre et apporter un objet** : Objet trop lourd ou qui glisse : la règle « poids » du gardien lit la carte et le monde, pas le vrai poids. → Objets légers choisis d'avance ; force limitée à 15 N par défaut ; le robot demande « oui » avant de saisir.
- **Parler et comprendre** : Bruit de la salle : l'écoute se trompe ou n'entend pas. → Micro-cravate ou casque ; bouton « je parle » ; la tablette (taper la phrase à l'écran).
- **Plusieurs langues** : Langue demandée sans voix sur ce Mac : la réponse ne s'affiche qu'en sous-titres. → Vérifier les voix du Mac samedi matin (say -v '?') ; sinon sous-titres à l'écran, et le dire au jury.
- **Voir et reconnaître** : Aucune brique « yeux » n'existe encore : le robot ne trouve pas un objet tout seul. → Objets à des places connues (commun/monde.yaml) ; un humain nomme l'objet au robot.
- **Se déplacer** : Collision avec une personne : le gardien garde 1 m, mais seulement au départ de l'action, et sans vrais yeux il demande un humain. → Vitesse limitée à 0,3 m/s par défaut ; zone de démonstration vide ; bouton d'arrêt physique en main.
- **Demander de l'aide quand il ne sait pas** : La main levée (brique 8) n'est essayée que sur le faux robot ; les boutons de l'écran pour répondre manquent. → Montrer l'ordre flou → la question (preuve 3, déjà prête).

### Les règles de sécurité du défi (à respecter, à mettre dans le gardien)

- Le bouton d'arrêt d'urgence du robot doit rester accessible à tout moment.
- Vitesse maximale du robot : 0,5 m/s dans la zone de démonstration.
- Le robot ne doit pas toucher les visiteurs.
- Il est interdit de faire porter au robot des objets de plus de 1 kg.
- Des enfants peuvent être présents dans le public : garder une distance de sécurité de 1 mètre.

### Nos règles, toujours

- L'arrêt d'urgence passe avant tout. Le bouton d'arrêt **physique** du robot reste à portée de main.
- Vitesse 0,3 m/s et force 15 N par défaut (`reglages.yaml` → `securite`), même si le robot peut plus.
- Tout ordre au robot passe par le cerveau, le **gardien** (qui vérifie et délivre un ticket), la prise, puis l'adaptateur. Rien d'autre.
- Démonstration de soin : sur un mannequin seulement, jamais de diagnostic.

### Les risques de tout défi

- **Robot inconnu jusqu'à samedi : aucun adaptateur n'existe encore (brique 3).** → Équipe adaptateurs dès 10 h ; test de conformité sans mouvement d'abord.
- **Rien n'a jamais été essayé sur un vrai robot.** → Premier mouvement lent, responsable sécurité présent, main sur le bouton d'arrêt physique.
- **Les Mac n'ont jamais lancé le projet (preparer_mac.sh non essayé sur Mac).** → Samedi 9 h : python3 lancer.py tests sur les deux Mac ; chaque Mac peut tout faire seul.
- **Wi-Fi de la salle saturé ou coupé.** → Mode local : tout tourne sur l'ordinateur-cerveau, sans Internet.
- **Fatigue : les erreurs arrivent la nuit.** → Sommeil par rotation ; gels du code le dimanche ; celui qui écrit n'est pas celui qui vérifie.
- **Batteries du robot vides ou qui chauffent.** → Charger seulement sous surveillance (règle du lieu : à vérifier) ; demander « batterie ? » au robot.

### Jamais essayé (extrait de NON_TESTE.md)

Ne jamais promettre au jury ce qui suit : ce n'est pas encore essayé.

**Jamais essayé sur un vrai robot**
- Toute la prise universelle, le gardien, la chaîne : uniquement avec le faux robot.
- Le chien de garde : simulé dans le faux robot. Un vrai robot doit avoir le sien (à vérifier dans chaque kit fabricant).
- L'arrêt d'urgence logiciel : il ne remplace **jamais** le bouton d'arrêt physique du robot. Sur le faux robot, une liaison coupée empêche l'ordre d'arrivée (comme en vrai) ; c'est son chien de garde qui l'arrête.
- Le code d'équipe de l'écran : une protection simple contre les erreurs sur le Wi-Fi, pas contre une attaque sérieuse.
- Les limites de vitesse et de force : vérifiées dans le code, pas mesurées sur un moteur.

**Jamais essayé sur les Mac**
- `preparer_mac.sh` : seulement lancé sur Linux, en mode essai (les parties Mac sont sautées).
- `outils/mesurer.py` : mesures llama.cpp, MLX, whisper.cpp, mlx-whisper, sherpa-onnx jamais lancées.
- `requirements-mac.txt` : versions relevées sur PyPI, jamais installées sur Mac.
- Installation de llama.cpp par Homebrew ou par GitHub : jamais essayée.
- Les sons d'essai par la commande `say` : les noms de voix macOS sont **à vérifier**.
- Voix Piper hors chinois : sherpa-onnx 2.x n'inclut plus espeak-ng ; il faudrait l'ajouter (GPL-3.0, décision de Hiba).

**Voix (étape 2) : testé sur Linux seulement**
- Écoute mlx-whisper et whisper.cpp : écrites d'après leur documentation, jamais lancées.
- Voix du Mac (`say`) : jamais lancée ; noms des voix **à vérifier** sur chaque Mac.
- Vrai micro et vrai haut-parleur (`sounddevice`) : jamais essayés. `python3 lancer.py micro` testé seulement avec `--fichier`.
- Bouton « 🎙 Je parle » de la page web : jamais essayé dans un navigateur (le serveur `/api/je_parle` est testé).
- Filtre d'écho (le robot ignore sa propre voix) : testé avec une écoute factice, pas avec un vrai haut-parleur.
- Interruption avec un vrai haut-parleur : le robot peut s'entendre lui-même ; **à mesurer** (casque conseillé).
- Ordres courts : testés avec une voix SYNTHÉTIQUE chinoise ; les vraies voix (FLEURS) sont des phrases longues. Les ordres dits par de vraies personnes : à enregistrer (`python3 lancer.py enregistrer`).
- Suisse allemand : aucune vraie voix testée.

**Cerveau (étape 3) : testé sur Linux seulement, avec Apertus 0,5B**
- Apertus 8B et 4B : jamais lancés (ni ici, ni sur Mac). `outils/banc_cerveaux_mac.py` jamais lancé.
- llama.cpp sur Mac (`llama-server`), mlx-lm (`mlx_lm.server`, formulaire vérifié) : jamais lancés.
- Apertus par Internet (CSCS) : jamais appelé depuis ce projet (pas de clé ici).
- Lancement « au besoin » du 4B, et son arrêt quand le 8B revient : testés avec un faux serveur (objet qui joue le serveur), pas avec deux vrais modèles.
- Deux Mac (cerveau sur l'iMac) : jamais essayé.

**Voix : ce qui ne marche que sur Mac**
- **La voix du Mac (`say`) ne marche que sur un Mac.** Sur un autre ordinateur, seules les réponses en chinois sont dites (Piper) ; les autres s'affichent en sous-titres. L'option Piper GPL (éteinte) marcherait partout.
- Option Piper GPL (`requirements-piper-gpl.txt`, `voix_piper_gpl.py`) : jamais installée ni lancée.
- Essai suisse allemand Flix-AI (`outils/essai_suisse_allemand.py`) : jamais lancé (Mac seulement).

**Chef de démonstration (brique 15) : testé sur faux robot seulement**
- Jamais avec un vrai robot, ni sur les Mac, ni avec la vraie cascade Apertus (panne réseau testée avec un cerveau « en ligne » factice).
- La voix est simulée (phrase donnée à la chaîne) ; `lancer.py scenario` n'a ni écran ni voix : annonces au terminal.
- Main humaine : opérateur simulé ; la brique 11 n'existe pas encore.
- Durée du scénario de trois minutes : mesurée une seule fois à ×1 (174,81 s), sur Linux, faux robot, cerveau à règles.

**Kit du samedi matin (brique 17) : hors ligne, jamais sur un vrai défi**
- Mots-clés essayés sur trois faux défis inventés (fr, de, en) ; un défi écrit en italien serait mal lu.
- Phrases du brouillon de scénario : jouées par le chef sur le faux robot, cerveau à règles seulement (ni Apertus, ni la voix).
- Skill `lire-le-defi` : jamais lancée dans une session de l'assistant de code (seul son format est testé).
- Heures du programme de 48 h : proposition, heures officielles du Carnival **à vérifier**.

**Gardien, doute (briques 7, 8) : testé sur faux robot seulement**
- Position du robot et personnes simulées ; jamais avec de vraies positions ni de vrais yeux.
- Chemin en ligne droite : un vrai robot qui contourne les obstacles peut passer ailleurs (à vérifier par robot).
- Chien de garde « programme figé » : simulé ; sur un vrai robot, c'est celui du fabricant (à vérifier dans chaque kit).
- Boutons de l'écran pour la main levée et les règles : API testée, page web pas encore faite.
- Phrases nouvelles en de, it, zh : écrites par l'agent, à faire relire.
- Distance aux personnes : vérifiée seulement AU DÉPART d'une action, pas pendant. Une personne qui s'approche pendant un trajet ou un geste n'arrête pas le robot ; seuls « stop », l'arrêt d'urgence et le chien de garde l'arrêtent.
- Zones et personnes : mesurées depuis le corps du robot (sa position x, y), pas depuis la main ni l'objet tenu. Un bras qui se tend peut aller plus près d'une personne, ou plus loin dans une zone, que ce que dit la règle.
- Code d'équipe : il reste gardé dans le navigateur du grand écran (`localStorage`). Quelqu'un qui touche cet écran peut appuyer sur « Réarmer » sans le retaper. À faire : redemander le code pour Réarmer.

**Écran du jury (brique 13) : testé avec Chromium sur Linux seulement**
- Jamais sur le grand écran ou le projecteur du Carnival, ni sur Safari, ni sur iPad, ni sur un Mac. « Lisible de loin » : non mesuré.
- « Internet coupé » : ne coupe que ce programme Python (pas le navigateur ni le reste du Mac) ; testé sur Linux.
- Mode silence avec un vrai haut-parleur : jamais essayé.
- Exemples du flux `etat_robot`, `pilotage_humain`, `mot_d_appel`, `interruption` et ceux des briques 7, 8, 15 : forme relevée dans le code, valeurs d'exemple.

**Adaptateurs (brique 3) : testé sur faux robot seulement**
- Aucun vrai robot, aucun vrai kit (Unitree, AGIBOT, Flexiv), ROS 2 jamais installé : liaisons essayées avec le faux kit et le faux ROS 2 seulement. Tous les appels des ébauches sont « à brancher ».
- Chien de garde du fabricant : simulé. Unitree G1 : `Move()` envoie 1 s (lu dans le code, jamais essayé) ; Go2, AGIBOT, Flexiv : inconnu. Fil réservé à l'arrêt d'urgence : un vrai kit accepte-t-il deux appels en même temps ? À vérifier.
- Kits sur Mac : jamais essayés. Pages officielles non lues (support.unitree.com, docs.nvidia.com) : à vérifier.
- Skill `brancher-un-robot` : jamais lancée dans une session de l'assistant de code. Chronomètre « robot inconnu » : terminal seulement.

**Porte des agents (brique 14) : testé sur faux robot seulement**
- Jamais dans une vraie session de l'assistant de code : client essayé = celui du SDK `mcp` 2.3.0. Enregistrement dans l'assistant de code : pas fait (feu orange, réglage de Hiba). Jamais sur Mac, jamais avec Apertus ; plusieurs agents à la fois : non testé.

**Pas encore construit**
- Briques 5, 9 à 11, 16.

## 7. Brouillon de scénario de démonstration

À répéter, chronométrer et couper. Chaque phrase passe par le cerveau, le gardien puis la prise : rien ne contourne le gardien. Phrases essayées sur le faux robot « humanoïde » : testé sur faux robot seulement. Lieux et objets : la table, la bouteille, l'entrée et la cuisine du faux monde (`commun/monde.yaml`), à remplacer par ceux du défi. Le défi parle aussi de : valise (« valise »).

1. **Accueil : le robot salue et répond dans la langue du visiteur** — 30 s au plus
   - Dire (français) : « Salue » → le robot agit et le dit.
   - Plan B : voix en panne → la tablette ; robot en panne → la main humaine.
   - Montre au jury : « Qualité de l'accueil et de la conversation dans plusieurs langues (25 points) »
2. **Trouver : le robot regarde la table** — 30 s au plus
   - Dire (allemand) : « Schau zum Tisch » → le robot agit et le dit.
   - Plan B : yeux en panne → un humain nomme l'objet ; voix en panne → la tablette.
3. **Aller : le robot va à la table** — 60 s au plus
   - Dire (italien) : « Vai al tavolo » → le robot agit et le dit.
   - Plan B : voix en panne → la tablette ; robot en panne → la main humaine.
4. **Prendre : le robot répète l'ordre, attend « oui », prend la bouteille** — 45 s au plus
   - Dire (anglais) : « Take the bottle », puis « yes » → le robot répète l'ordre et attend « oui » ; après le « oui », il agit.
   - Plan B : voix en panne → la tablette ; robot en panne → la main humaine.
   - Montre au jury : « Livraison de l'objet demandé, sans le faire tomber (20 points) »
5. **Apporter : le robot va à l'entrée avec l'objet** — 60 s au plus
   - Dire (français) : « Va à l'entrée » → le robot agit et le dit.
   - Plan B : voix en panne → la tablette ; robot en panne → la main humaine.
   - Montre au jury : « Livraison de l'objet demandé, sans le faire tomber (20 points) »
6. **Poser : le robot pose l'objet, après un « oui »** — 45 s au plus
   - Dire (allemand) : « Stell die Flasche hin », puis « ja » → le robot répète l'ordre et attend « oui » ; après le « oui », il agit.
   - Plan B : voix en panne → la tablette ; robot en panne → la main humaine.
   - Montre au jury : « Livraison de l'objet demandé, sans le faire tomber (20 points) »
7. **Ordre flou : le robot pose une question au lieu de deviner** — 20 s au plus
   - Dire (italien) : « Vai » → le robot pose une question au lieu de deviner.
   - Plan B : voix en panne → la tablette.
   - Montre au jury : « Sécurité : respect des règles, arrêt d'urgence, comportement prudent (20 points) »
8. **Ordre dangereux : le robot refuse et explique pourquoi** — 30 s au plus
   - Dire (anglais) : « Go to the kitchen at 5 meters per second » → le robot refuse et explique pourquoi, dans la même langue.
   - Plan B : voix en panne → la tablette.
   - Montre au jury : « Sécurité : respect des règles, arrêt d'urgence, comportement prudent (20 points) »
9. **Arrêt d'urgence : bouton ARRÊT, le robot s'arrête et reste bloqué jusqu'au réarmement** — 30 s au plus
   - À l'écran : appuyer sur ARRÊT pendant un mouvement lent ; montrer qu'il reste bloqué ; un humain réarme.
   - Plan B : arrêt logiciel sans effet → le bouton d'arrêt PHYSIQUE.
   - Montre au jury : « Sécurité : respect des règles, arrêt d'urgence, comportement prudent (20 points) »
10. **La vérité en chiffres : la fiche de vérité à l'écran** — 45 s au plus
   - À l'écran : montrer la fiche de vérité (réussites, refus, questions, part de l'humain, mention faux ou vrai robot).
   - Plan B : réseau en panne → le mode local.
   - Montre au jury : « Fiabilité : que se passe-t-il quand quelque chose ne marche pas ? (15 points) »

**Durée totale proposée : 6 min 35 s.** Le défi donne 6 min pour la démonstration.
Trop long : garder 20 % de marge pour les imprévus. Raccourcir d'abord les étapes « à construire », puis celles qui ne montrent aucun critère du jury.
Étapes sans critère du jury : 2, 3 (à raccourcir ou à regrouper).

### Les plans B de toute la démonstration

- Voix en panne → la tablette : taper la phrase dans le champ texte de l'écran ; la réponse s'affiche en sous-titres.
- Robot en panne → la main humaine : bouton ARRÊT d'abord, puis un membre de l'équipe fait le geste et le dit au jury.
- Réseau en panne → le mode local : tout tourne sur l'ordinateur-cerveau, sans Internet ; écran sur http://localhost:8000 ; cerveau à règles si Apertus tombe.

Le même brouillon en YAML : `plan_exemple_scenario.yaml`, au format du chef de démonstration (brique 15) : `python3 lancer.py scenario plan_exemple_scenario.yaml --repetition`.

## 8. Critères du jury → ce que l'on montre → preuve

La **fiche de vérité** compte tout depuis la boîte noire (réussites, refus, part de l'humain, temps) et dit d'elle-même « faux robot » ou « vrai robot ». La **boîte noire** garde chaque événement (`journal/`) et se rejoue : `python3 lancer.py rejouer`.

| Critère du jury | Ce que l'on montre | Preuve |
|---|---|---|
| Qualité de l'accueil et de la conversation dans plusieurs langues (25 points) | Une personne parle au robot ; il répond dans la même langue. La même demande dans deux langues donne la même action. | Boîte noire (phrases entendues et réponses, avec l'heure) ; fiche de vérité (« non compris » par langue). Boîte noire (langue reconnue pour chaque phrase) ; fiche de vérité (« non compris » par langue). |
| Livraison de l'objet demandé, sans le faire tomber (20 points) | Le robot répète l'ordre, attend « oui », prend l'objet et l'apporte. | Boîte noire (confirmation demandée, puis action) ; fiche de vérité (réussites et ratés). |
| Sécurité : respect des règles, arrêt d'urgence, comportement prudent (20 points) | Un ordre dangereux refusé et expliqué ; le bouton ARRÊT. | Fiche de vérité (refus du gardien, arrêts d'urgence) ; boîte noire (chaque décision du gardien). |
| Fiabilité : que se passe-t-il quand quelque chose ne marche pas ? (15 points) | Une panne d'entraînement pendant la démonstration, et le plan B. | Fiche de vérité (réussites, ratés, pannes) ; boîte noire (rejeu). |
| Autonomie du robot pendant la démonstration (10 points) | Le robot agit seul ; quand un humain aide, on le dit. | Fiche de vérité (part de l'humain) — seulement si le pilotage humain est noté (brique 11, à faire). |
| Originalité de la solution (10 points) | Une idée en plus parmi les interrupteurs (docs/projet/IDEES.md), choisie par l'équipe. | Aucune preuve automatique : à préparer pour le pitch. |

Total des points repérés : 100.

## Annexe A — La liste des 35 personnes (à remplir samedi)

| Personne | Prénom | Équipe | Sommeil, nuit 1 |
|---|---|---|---|
| P01 | Hiba | Responsable | R1 |
| P02 |  | Sécurité | R2 |
| P03 |  | Sécurité | R3 |
| P04 |  | Relecteurs sécurité | R3 |
| P05 |  | Relecteurs sécurité | R1 |
| P06 |  | Architecte | R1 |
| P07 |  | Tests | R2 |
| P08 |  | Tests | R3 |
| P09 |  | Rédacteur des guides | R3 |
| P10 |  | Démonstration | R1 |
| P11 |  | Démonstration | R2 |
| P12 |  | Adaptateurs | R2 |
| P13 |  | Adaptateurs | R3 |
| P14 |  | Adaptateurs | R1 |
| P15 |  | Adaptateurs | R2 |
| P16 |  | Gardien | R3 |
| P17 |  | Gardien | R1 |
| P18 |  | Cerveau | R1 |
| P19 |  | Cerveau | R2 |
| P20 |  | Voix | R2 |
| P21 |  | Voix | R3 |
| P22 |  | Yeux | R3 |
| P23 |  | Yeux | R1 |
| P24 |  | Écran | R1 |
| P25 |  | Écran | R2 |
| P26 |  | Adaptateurs | R3 |
| P27 |  | Adaptateurs | R1 |
| P28 |  | Adaptateurs | R2 |
| P29 |  | Adaptateurs | R3 |
| P30 |  | Yeux | R2 |
| P31 |  | Yeux | R3 |
| P32 |  | Yeux | R1 |
| P33 |  | Yeux | R2 |
| P34 |  | Tests | R1 |
| P35 |  | Tests | R2 |

## Annexe B — Les mots du plan

- **Adaptateur** : le petit programme qui traduit nos 10 actions en ordres pour un robot précis.
- **Prise universelle** : la courte liste de 10 actions, dite pareil pour tous les robots (briques/b01_prise/PRISE.md).
- **Carte d'identité** : le fichier qui dit ce qu'un robot sait faire et ses limites (vitesse, force, portée).
- **Gardien** : le programme qui vérifie chaque action avant qu'elle parte ; seul lui délivre le ticket.
- **Ticket** : l'autorisation signée du gardien, pour une seule action, valable 5 secondes.
- **Test de conformité** : l'essai qu'un adaptateur doit réussir avant de servir (briques/b01_prise/conformite.py).
- **Faux robot** : le robot imaginaire de l'ordinateur, pour s'entraîner sans matériel.
- **Boîte noire** : le journal où chaque événement est écrit, avec l'heure (dossier journal/).
- **Fiche de vérité** : les chiffres calculés depuis la boîte noire : réussites, refus, temps, part de l'humain.
- **Gel du code** : le moment après lequel on n'ajoute plus rien : on corrige seulement.
- **Rotation** : un groupe qui dort pendant que les autres travaillent (R1, R2, R3).
- **Feu orange** : une action qui attend le « oui » de Hiba (vrai robot, installation, gros téléchargement).
- **Plan B** : ce qu'on fait si une partie tombe en panne pendant la démonstration.
- **Mode local** : tout tourne sur un seul Mac, sans Internet.
- **Tablette** : le champ texte de l'écran : on tape la phrase au lieu de la dire.
