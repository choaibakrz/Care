# Brancher un robot en 30 minutes — samedi matin

Le pas à pas pour faire parler notre ossature à un robot qu'on découvre le jour même (Unitree, AGIBOT, Flexiv, ou autre).
**Rien de ceci n'a encore été essayé sur un vrai robot** : l'assistant et le test de conformité sont **testés sur faux
robot** seulement (`NON_TESTE.md`). Les 30 minutes sont un but, pas une mesure.

Rappel : tout ordre au robot passe par cerveau → gardien (ticket) → prise → adaptateur. L'adaptateur ne fait que
traduire. Le chemin : `briques/b03_adaptateurs/` (guide : `briques/b03_adaptateurs/GUIDE.md`).

## Avant le vrai robot : une carte, le faux robot, le chronomètre (clinique en boîte, J04)
Pour s'entraîner, et pour montrer « combien de temps pour brancher un robot qu'on n'a jamais vu ». **Aucun vrai robot
n'est touché** : la commande fait tourner le faux robot avec la carte donnée. Elle refuse une carte « vrai_robot: true ».
1. Écrire la carte d'identité du robot : un fichier dans `briques/b02_faux_robot/cartes/` (modèle : `plateau.yaml`, un
   robot à roues sans bras). Ce que le robot ne fait pas n'est pas dans `capacites`. Chaque chiffre : « à vérifier ».
   Trois cartes sont prêtes d'avance, marquées « PRÉPARÉE SANS LE ROBOT » : `unitree_g1`, `unitree_go2`, `unitree_g1d`.
   Pour un robot que personne n'a prévu : imprimer `docs/projet/CARTE_A_REMPLIR.md`, la remplir avec la personne du fabricant, puis la recopier.
2. Dire « je commence » : `python3 lancer.py brancher-carte plateau --je-commence` (le chronomètre part).
3. Lancer le test : `python3 lancer.py brancher-carte plateau`. Il affiche « contrôles réussis : tant sur tant ».
   Un contrôle raté porte une ligne ✘ et « à corriger : … », en une phrase. Corriger, relancer.
4. Quand tous les contrôles réussissent, le chronomètre s'arrête seul. La durée va dans la fiche de vérité, ligne
   « Brancher un robot inconnu — FAUX ROBOT ». La ligne « RÉEL » reste « à mesurer avec le vrai robot » : c'est
   l'équipe qui la mesurera, avec les étapes 0 à 6 ci-dessous, montre en main.
Le cerveau ne change pas : il lit la carte. Un robot sans bras porte l'objet sur son plateau et demande à un humain de
le poser, puis de le prendre (`briques/clinique/coursier.py`).

## 0. La sécurité d'abord (avant de toucher au clavier)
- [ ] **Accord de Hiba** pour brancher ce robot. Tout ce qui envoie un ordre au vrai robot est **feu orange**.
- [ ] Le **responsable sécurité** est là, à côté du robot, et le reste pendant tous les essais.
- [ ] Le **bouton d'arrêt PHYSIQUE** (ou la télécommande d'arrêt) est trouvé, montré à tous, **essayé robot immobile**.
      Pendant chaque essai, une main est dessus. L'arrêt logiciel ne le remplace **jamais**.
- [ ] Robot à jambes : **suspendu** (portique, harnais) ou posé de façon stable, comme le dit sa fiche.
      Certains « arrêts » du fabricant coupent les moteurs : le robot **tombe** (fiches Unitree).
- [ ] Zone vide autour du robot (distance : règles du lieu, à demander aux organisateurs).
- [ ] Le **premier mouvement sera lent** : 0,1 m/s, quelques centimètres, gestes demandés à mi-vitesse (mode « lent » ;
      **vitesse du geste : à vérifier par kit**, certains kits jouent le geste à la vitesse du fabricant).
- [ ] Sans odomètre, le programme ne voit pas un robot parti à l'envers : à la fin du test complet, un humain confirme à l'œil.

## 1. Connaître le robot (5 min)
- [ ] Fabricant, modèle exact, version du logiciel du robot (sur le robot ou dans son appli) : les noter.
- [ ] Ouvrir sa fiche : `briques/b03_adaptateurs/fiches/` (`unitree_g1.md`, `unitree_go2.md`, `agibot.md`,
      `flexiv_rizon.md`). Pas de fiche : partir de la doc du fabricant, et tout chiffre non écrit = « à vérifier ».
- [ ] Choisir le chemin : **sdk** (le fabricant donne des fonctions Python) ou **ros2** (le robot parle ROS 2 : des
      programmes qui s'envoient des messages sur des « sujets »). Dans le doute : sdk.
- [ ] Le kit du fabricant est-il installé, et sur quel ordinateur ? **Installer un kit ou ROS 2 = feu orange** (taille,
      licence, accord de Hiba).

## 2. Créer le dossier du robot (2 min, rien n'est envoyé au robot)
```bash
python3 lancer.py brancher unitree_g1 --genre humanoide --chemin sdk
python3 lancer.py brancher unitree_g1 --conformite        # faux kit : doit dire RÉUSSI, « testé sur faux robot »
```
Attention : ce test sur le faux kit n'essaie PAS le `liaison.py` du robot (il essaie la mécanique commune, la carte
et l'ébauche du chemin). Seul le test `--vrai` (étape 4) essaie les appels écrits pour le vrai robot.
Le dossier `briques/b03_adaptateurs/robots/unitree_g1/` contient : `carte.yaml` (la carte d'identité), `liaison.py`
(les appels au robot, lignes « À BRANCHER »), `adaptateur.py`, `tests/test_conformite_unitree_g1.py`.

## 3. Brancher l'arrêt et l'état D'ABORD (10 min)
Dans `liaison.py`, remplacer les lignes « À BRANCHER » de ces méthodes seulement, avec la doc du fabricant :
- [ ] `creer_kit()` (sdk) ou `creer_ros2()` + `SUJETS` (ros2) : se connecter au kit, sans rien faire bouger.
- [ ] `ouvrir()`, `fermer()`, `signe_de_vie()`, `lire_etat()` (batterie, odomètre, en mouvement, erreurs).
- [ ] `arreter_mouvement()` : vitesse nulle, le robot reste stable.
- [ ] `arret_urgence()` : l'arrêt logiciel **le plus sûr**, choisi **avec le responsable sécurité** (pas forcément le
      plus « fort » : sur un robot à jambes, couper les moteurs = chute). Le noter dans la fiche. Un « arrêt de marche »
      (vitesse nulle) ne BLOQUE PAS le robot : il accepte l'ordre suivant ; notre adaptateur bloque nos ordres à nous.
      Un appel qui rend un code (ex. `SetVelocity(0, 0, 0)` du G1) plutôt que rien (`StopMove()` du G1 rend `None` :
      arrêt « non confirmé »). Délai court pour l'appel d'arrêt (un client à part, si le kit le permet).
- [ ] `rearmer()` : lever le blocage, **sans** mouvement (ne jamais relever le robot par programme).
- [ ] Puis écrire `branchees = frozenset({"arreter", "etat"})`. La carte garde `capacites: [arreter, etat]`.
- [ ] Remplir l'en-tête de `carte.yaml` (fabricant, modèle) ; chaque chiffre avec son lien et sa date, sinon 0.

## 4. Test sans mouvement sur le vrai robot (3 min) — FEU ORANGE
- [ ] « Oui » de Hiba. Responsable sécurité présent. Main sur l'arrêt PHYSIQUE. L'écran (`python3 lancer.py`) **arrêté**.
- [ ] Un humain tape, dans un terminal :
```bash
python3 lancer.py brancher unitree_g1 --conformite --vrai
```
Le programme rappelle les consignes et attend la phrase `sans mouvement` suivie du nombre affiché, tapée au
clavier. Cette phrase protège contre l'oubli, pas contre un agent ou un script : la vraie garde est ce feu orange.
Il vérifie : connexion,
carte, état, arrêt d'urgence logiciel, blocage jusqu'au réarmement, refus de tout ce qui dépasse les limites (le
« témoin » vérifie que les refus du gardien n'ont rien envoyé au robot), et qu'aucune tentative d'arrêt n'a été sautée. Il note le résultat dans `conformite.yaml`.
Il affiche aussi le **chronomètre** (minutes depuis l'étape 2).
- [ ] Échec : lire la ligne ✘ et « Reste à brancher », corriger, recommencer. Ne jamais passer à l'étape 5 sur un échec.

## 5. Le premier mouvement, lent (10 min) — FEU ORANGE
- [ ] Brancher **une** action (par exemple `vitesse()` pour `se_deplacer`, ou `geste()`), l'ajouter à `branchees`
      **et** à `capacites` dans la carte, avec la vitesse maximale lue dans la doc (sinon : 0 = refus).
- [ ] `python3 lancer.py brancher unitree_g1 --conformite` (faux kit) passe toujours.
- [ ] « Oui » de Hiba, responsable sécurité, main sur l'arrêt physique, robot suspendu ou zone vide. Un humain tape :
```bash
python3 lancer.py brancher unitree_g1 --conformite --vrai --complet
```
Phrase à taper : `mouvement lent <id du robot> <nombre affiché>` (ex. `mouvement lent unitree-g1 7310`).
Le robot avance de 20 cm à 0,1 m/s, joue chaque capacité de la carte (gestes demandés à mi-vitesse : **vitesse du
geste à vérifier par kit**, beaucoup n'ont pas de réglage), puis **deux déplacements de 2 m** sont demandés et coupés
après 0,2 s (une annulation, un arrêt d'urgence). Un déplacement qui recule ou s'écarte du trajet est arrêté, et compte
comme un échec.
- [ ] Mesurer et noter dans la fiche : le robot s'arrête-t-il seul quand nos ordres cessent (chien de garde du fabricant) ?

## 6. Brancher dans le système
- [ ] Dans `reglages.yaml` : `robot.adaptateur: unitree_g1` et `robot.vrai_robot: true`. Le système
      (`commun/systeme.py`, par `briques/b03_adaptateurs/registre.py`) refuse un vrai robot dont le test complet n'a pas
      réussi, ou dont la carte, la liaison ou l'adaptateur ont changé depuis (`conformite.yaml`). C'est une protection
      contre l'oubli, pas contre quelqu'un qui réécrirait ce fichier.
- [ ] `python3 lancer.py tests` passe. La fiche de vérité dira « vrai robot » d'elle-même ; ne jamais écrire
      « testé sur vrai robot » pour ce qui n'a tourné que sur le faux kit.

## Si ça coince
| Symptôme | Piste |
|---|---|
| « À BRANCHER : … » | la méthode citée n'est pas encore écrite dans `liaison.py` |
| « liaison perdue », « n'a pas répondu en 1 s » | câble, Wi-Fi, adresse IP (Unitree : carte réseau en 192.168.123.99/24 d'après `unitree_ros2`), kit pas lancé |
| « la carte ne promet que ce qui est branché » ✘ | une capacité de la carte n'est pas dans `branchees` : la brancher ou l'enlever |
| « vitesse nulle » | `vitesse_max_m_s` vaut 0 dans la carte : écrire le chiffre de la doc (lien, date) |
| « REFUSÉ : pas de clavier » | la commande `--vrai` doit être tapée par un humain dans un terminal (pas par un agent) |
| « l'écran tourne déjà » | arrêter `python3 lancer.py` : une seule liaison avec le robot |
| Le robot bouge à la connexion | **arrêt physique**, puis corriger `ouvrir()` : il ne doit jamais faire bouger le robot |
