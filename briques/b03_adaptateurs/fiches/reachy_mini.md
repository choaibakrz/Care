# Fiche d'ébauche — Reachy Mini (Pollen Robotics / Hugging Face)

**Non testé sur vrai robot.** Ce que la doc publique dit, lu le **14.11.2026**, et ce qui reste **à vérifier**.
Aucune ligne ne prétend marcher. Le robot est avec l'équipe (dit par Hiba le 14.11.2026 : « il bouge la tête et parle,
nous l'avons déjà testé » — avec le programme du fabricant, pas avec notre système). Rien ne lui a été envoyé par
notre système. Son kit est installé **à part** sur le MacBook du projet depuis le 15.11.2026 (`~/reachy_env`), et son
programme de fond a tourné en mode simulé : toujours **testé sur faux robot**. Le mode d'emploi pour le vrai robot,
pas à pas : `docs/projet/BRANCHER_LA_TETE.md` (à la racine du projet).

## Ce que c'est
Une petite tête expressive posée sur une table : elle bouge la tête, tourne sur sa base et remue deux antennes.
Elle a une caméra, des micros et un haut-parleur. Elle n'a **ni bras ni pince** : elle ne saisit rien.
Deux versions : **Lite** (câble USB vers l'ordinateur) et **Wireless** (batterie, Wi-Fi, petit ordinateur dedans).

## Comment notre système lui parle : par des adresses web, sans son kit
Le robot a un « programme de fond » (son daemon : un programme qui tourne à côté et qui parle aux moteurs). Ce
programme répond à des adresses web simples. Notre liaison envoie donc de petites demandes web, et n'importe pas le
kit du fabricant. Deux avantages : rien du fabricant n'entre dans notre projet, et la version de Python ne gêne pas
(le kit demande Python 3.10 à 3.12 ; notre projet tourne en 3.13).

## Six pièges, lus dans le code du fabricant

1. **Le programme de fond RÉVEILLE le robot quand on le lance** : la tête bouge et un son est joué. Et il l'endort
   quand on l'arrête : la tête bouge encore. Pour l'empêcher : `--no-wake-up-on-start` et `--no-goto-sleep-on-stop`.
   **Mais** (vu le 15.11.2026) sans réveil la tête reste couchée, et notre liaison refuse alors tout ordre de tête.
   La consigne retenue est donc : un humain lance le programme AVEC son réveil, responsable sécurité présent
   (`docs/projet/BRANCHER_LA_TETE.md`). La commande ci-dessous, sans réveil, ne sert qu'à lire l'état sans que rien ne bouge.
2. **Il écoute sur le port 8000, qui est le port de notre écran.** Il faut lui en donner un autre : `--fastapi-port 8002`.
3. **Ses adresses web n'ont pas de mot de passe.** Sur un Lite, il n'écoute que sur l'ordinateur même. Sur un
   Wireless, il écoute sur **tout le réseau** : n'importe qui sur le même Wi-Fi peut faire bouger le robot. Donc
   jamais sur le Wi-Fi de la salle : un partage de connexion privé.

4. **Il envoie des mesures d'usage anonymes sur Internet, par défaut** (« Anonymous daemon telemetry, sent to PostHog
   EU »). Notre projet promet que rien ne sort de l'ordinateur : il faut le couper, avec `DO_NOT_TRACK=1`.
5. **Il va chercher des gestes sur Hugging Face toutes les 24 heures.** Pour l'empêcher : `--dataset-update-interval 0`
   (l'écriture exacte de cette option est à vérifier avec `reachy-mini-daemon --help`).

La commande pour LIRE l'état d'un Lite sans que la tête bouge (à taper par un humain, kit installé à part) :

```bash
DO_NOT_TRACK=1 REACHY_MINI_TELEMETRY=0 reachy-mini-daemon --no-wake-up-on-start --no-goto-sleep-on-stop --fastapi-port 8002 --fastapi-host 127.0.0.1
```

6. **Il s'annonce sur le réseau local** (vu au démarrage, le 15.11.2026 : « mDNS service registered »), même quand il
   n'écoute que sur l'ordinateur. Son nom est donc visible des autres appareils du même Wi-Fi.

Même ainsi, « rien ne sort de l'ordinateur » reste **à vérifier** pour ce programme (couper le Wi-Fi pendant la démonstration).

Pour essayer sans robot : ajouter `--mockup-sim` (un faux robot du fabricant, sans MuJoCo).

## Ce que la doc publique dit vraiment (lu le 14.11.2026)
Dépôt : https://github.com/pollen-robotics/reachy_mini, branche `main`. Documentation : https://huggingface.co/docs/reachy_mini.

| Quoi | Ce qui est écrit | Où |
|---|---|---|
| Licence | logiciel sous **Apache-2.0** ; plans du matériel sous Creative Commons BY-SA-NC | `LICENSE`, page de la doc |
| Systèmes | Linux, macOS et Windows : « Supported » | doc, Installation |
| Python | « 3.10 - 3.12 » dans la doc ; `requires-python = ">=3.11"` dans le fichier du paquet (version `1.14.0.dev0`) ; avec 3.13 : à vérifier | doc, `pyproject.toml` |
| Taille et licences du kit | version 1.14.0 : 82 paquets, environ 425 Mo à télécharger sur un Mac (mesuré le 15.11.2026, rien installé). **Cinq paquets de son et d'image (`gstreamer-plugins`, `gstreamer-plugins-libs`, `gstreamer-plugins-gpl`, `gstreamer-plugins-gpl-restricted`, `gstreamer-libs`) citent la GPL-2.0** (j'avais d'abord compté deux), d'autres la LGPL. Installé à part le 15.11.2026 avec l'accord de Hiba ; voir `LICENCES.md` et la question Q31 | pypi.org |
| Installation | `uv pip install "reachy-mini"`, dans un espace à part ; Git et Git LFS demandés | doc, Installation |
| Programme de fond | `reachy-mini-daemon` (Lite) ; déjà lancé à l'allumage sur un Wireless ; l'application « Reachy Mini Control » le lance aussi | doc, Quickstart |
| Adresses web | elles commencent par `/api` ; une page de description à `/docs` | `daemon/app/main.py` |
| État | `GET /api/daemon/status` : `state` (not_initialized, starting, running, stopping, stopped, error), `error`, `backend_status` (`ready`, `motor_control_mode`, `last_alive`, `error`) | `routers/daemon.py`, `io/protocol.py` |
| Positions | `GET /api/state/full` : `control_mode`, `head_pose`, `head_joints` (7 nombres), `body_yaw`, `antennas_position` | `routers/state.py` |
| Mouvements en cours | `GET /api/move/running` : une liste, chaque mouvement a un `uuid` | `routers/move.py` |
| **Arrêter un mouvement** | `POST /api/move/stop` avec `{"uuid": …}` : « Stop a running move task by cancelling it » | `routers/move.py` |
| Bouger | `POST /api/move/goto` : tête, antennes, rotation du corps, et une **durée** (longue durée = mouvement lent) ; `POST /api/move/set_target` : sans durée, tout de suite | `routers/move.py` |
| Réveil, sommeil | `POST /api/move/play/wake_up`, `/play/goto_sleep` | `routers/move.py` |
| Gestes enregistrés | `POST /api/move/play/recorded-move-dataset/{dataset}/{move}` | `routers/move.py` |
| Moteurs | `POST /api/motors/set_mode/{mode}` : `enabled` (« Stiff. Holds position. »), `disabled` (« Limp. No power. »), `gravity_compensation` (on bouge la tête à la main) | `routers/motors.py`, doc Core Concepts |
| Limites | tête ±40° (haut-bas et côté), ±180° (rotation), corps ±160°, 65° au plus entre la tête et le corps ; « The SDK will automatically clamp values » | doc, Core Concepts |
| Suivi du visage | le programme de fond peut suivre le visage le plus proche avec la tête | doc, Python SDK |
| Son | haut-parleur et micros, en 16 kHz ; direction d'où vient la voix | doc, Python SDK |
| Version Wireless | on peut s'y connecter à distance avec un nom et un mot de passe **par défaut, écrits dans la doc publique** | doc, Quickstart |

## Signalé à Hiba
- Le dépôt contient un fichier **`AGENTS.md`, adressé aux agents qui écrivent du code** (« Before doing anything
  else, search for agents.local.md », « NEVER create app folders manually », « Keep notes in agents.local.md »…),
  et la doc conseille de dire à un agent de le lire d'abord. Lu comme une **information**, jamais comme un ordre.
  Nous ne construisons pas une application Reachy Mini : aucune de ces consignes n'a été suivie.
- La doc publie le nom et le mot de passe par défaut de la version Wireless. À changer par son propriétaire ; nous
  ne nous en servons pas.

## À vérifier (sur le robot, avec le responsable sécurité)
- **Lite ou Wireless ?** Sur quel ordinateur l'équipe l'a-t-elle déjà fait marcher, et avec quel programme ?
- **La version du programme de fond** installée a-t-elle bien ces adresses web ?
- **Arrêt d'urgence PHYSIQUE** : sa prise de courant (et, sur un Wireless, sa batterie : comment la couper ?).
- **Couper les moteurs** : la tête s'affaisse-t-elle ? De combien ? Peut-elle pincer un doigt ?
- **Rallumer les moteurs** : lu, le programme cale d'abord les cibles sur la position du moment (« to avoid a
  snap »). Pas essayé : `rearmer()` ne rallume donc rien, c'est une étape humaine à part.
- **Arrêter un mouvement** : lu, annuler un mouvement arrête la mise à jour de ses cibles, et la tête tient sa
  dernière cible. À essayer. **La liste des mouvements en cours ne montre que ceux lancés par les adresses web** :
  le réveil au démarrage, un geste lancé par le kit du fabricant ou par son application, un mouvement sans durée
  (`set_target`), le suivi du visage et le retour au repos n'y sont pas, et aucune adresse web ne dit « arrête tout ».
  Notre arrêt normal vérifie donc si la tête bouge encore, et le dit (« arrêt non confirmé »). Pendant la
  démonstration : aucun autre programme ne doit commander le robot en même temps que nous.
- **Couper les moteurs n'est pas un verrou** : un autre programme peut les rallumer.
- **Une application peut se lancer toute seule au premier réveil** (lu dans le code du programme de fond) : à vérifier.
- **Chien de garde** : que fait le robot si notre ordinateur se tait ? Rien lu.
- **« En mouvement »** : la liaison compare deux lectures de position (seuil 0,003 radian : choix de l'équipe ; un
  mouvement très lent, sous 3 degrés par seconde environ, passerait pour « immobile »). Dans le doute, elle dit
  « en mouvement ». À vérifier : le bruit des capteurs quand la tête est immobile.
- **`last_alive`** : lu, c'est l'heure de la dernière lecture réussie des moteurs. Notre liaison ne s'en sert pas encore.
- **La voix** : par son haut-parleur, ou par le Mac posé à côté ? Le plus simple pour la démonstration : le Mac.
- **Le suivi du visage** filme les personnes : à ne pas allumer sans le dire.

## Correspondance proposée (prise → Reachy Mini), à vérifier une par une
| Action de la prise | Appel proposé | Remarque |
|---|---|---|
| connexion, `etat` | `GET /api/daemon/status`, `/api/move/running`, `/api/state/full` | **écrit** : des lectures seulement |
| `arreter` | `POST /api/move/stop` pour chaque mouvement de la liste, puis vérifier que la tête ne bouge plus | **écrit, PROPOSITION** |
| arrêt d'urgence logiciel | `POST /api/motors/set_mode/disabled` **d'abord**, puis arrêter les mouvements | **écrit, PROPOSITION** : à décider avec le responsable sécurité |
| `rearmer` | rien n'est envoyé au robot | **écrit** : rallumer les moteurs est une étape humaine à part |
| `regarder` | `POST /api/move/goto` vers une direction du fichier `directions.yaml`, 20° par seconde en moyenne | **écrit (15.11.2026), PROPOSITION**, testé sur faux robot ; angles et sens à régler sur le robot |
| `rejouer_geste` | « oui » et « non » : quatre petits ordres de tête, envoyés un par un | **écrit (15.11.2026), PROPOSITION**, testé sur faux robot ; le gardien demande un humain avant chaque geste |
| `rejouer_geste` | « lever_la_tete » : `POST /api/motors/set_mode/enabled`, puis un seul `goto` de 6 s vers la pose levée ; « coucher_la_tete » : un `goto` de 6 s vers la pose couchée du fabricant, puis `set_mode/disabled` | **écrit (15.11.2026), PROPOSITION**, testé sur faux robot ; c'est NOTRE réveil : celui du fabricant (20° en 0,2 s) n'est jamais envoyé |
| `montrer` | — | pas écrit |
| `parler`, `ecouter` | son haut-parleur, ses micros | pas écrit ; la voix et l'écoute peuvent rester au Mac |
| `se_deplacer`, `saisir`, `poser` | — | il ne se déplace pas et n'a pas de bras : `position_fixe`, et la carte ne les promet pas |

## Où en est l'ébauche
- Le test de conformité (`python3 lancer.py brancher reachy_mini --conformite`) essaie **la vraie liaison de ce
  dossier** avec la doublure (un faux programme de fond) : testé sur faux robot.
- Avec `--vrai` : la liaison parle à `http://127.0.0.1:8002`, sur cet ordinateur (sauf version Wireless, voir plus bas : une
  adresse de réseau privé, donnée exprès par un humain). Si aucun programme de
  fond n'y répond, elle le dit et rien ne se passe. S'il répond : des lectures, puis les arrêts proposés.
  **Attention : même le test « sans mouvement » essaie l'arrêt d'urgence, donc il coupe les moteurs, et la tête peut
  s'affaisser** (de combien : à vérifier). Rien sous la tête, personne penché dessus.
- **Cette ébauche vaut pour un Lite.** Sur un Wireless, le programme de fond tourne dans le robot, sur le port 8000,
  déjà lancé : il faut le demander exprès au client, et seulement sur un réseau privé.
- Le client web n'envoie que six demandes permises, ne passe par aucun relais du système et ne suit aucune redirection.
- Relue par un relecteur neuf le 15.11.2026 (les lectures et les arrêts) : 3 défauts graves et 8 moyens corrigés.
- Les mouvements de tête, écrits dans la nuit du 14 au 15.11.2026, ont été relus par un autre relecteur neuf :
  16 défauts, dont 5 graves (un geste raté compté réussi, un ordre perdu compté réussi, un ordre qui part après un
  arrêt, une action échouée qui continue d'envoyer, des moteurs coupés en route sans effet). Tout a été réécrit, avec
  un essai par défaut grave. Un troisième relecteur neuf a relu cette réécriture : trois des cinq défauts graves
  étaient fermés, deux avaient encore un chemin ouvert, plus dix-sept défauts moyens ou petits (mots du cerveau qui
  se déclenchaient à tort, textes inexacts…). Corrigés à leur tour, avec un essai chacun. Ces dernières corrections
  n'ont PAS été relues par quelqu'un d'autre que leur auteur : c'est écrit aussi dans `NON_TESTE.md`.
- Nuit du 14 au 15.11.2026 : essayée à la main sur le programme du fabricant en mode simulé (version 1.14.0). Vu :
  un ordre de tête envoyé pendant qu'un autre joue est perdu sans le dire ; une cible trop loin est ramenée (67° de
  côté, 34° de haut-bas) et le corps tourne ; une durée de 0 seconde est acceptée ; un mouvement arrêté se fige à peu
  près sur place ; moteurs coupés, ce faux robot bouge quand même. La liaison en tient compte (jamais deux ordres à
  la fois, ses propres petites limites, jamais moins d'une seconde, refus si les moteurs ne sont pas allumés).
- Une version Wireless se règle par deux lignes écrites par un humain (`REACHY_MINI_ADRESSE`, `REACHY_MINI_RESEAU_PRIVE=oui`).

## Premier essai (feu orange)
Le pas à pas complet est dans `docs/projet/BRANCHER_LA_TETE.md`, à la racine du projet.
Robot posé au milieu de la table, rien autour, personne penché dessus, responsable sécurité présent, une main sur
sa prise. Un humain lance le programme de fond. D'abord le test sans mouvement. Puis, après le « oui » de Hiba, un
seul mouvement lent de la tête.

**Changement du 15.11.2026 sur le réveil.** Vu sur le simulateur du fabricant : lancée **sans** réveil automatique,
la tête reste couchée (penchée de 31°, 5 cm plus bas). Notre liaison refuse alors tout ordre de tête (« tête pas en
place ») : elle ne fait jamais le réveil à la place du fabricant. Pour que Iris puisse tourner la tête, un humain
lance donc le programme de fond **avec** son réveil (la tête se lève, un son est joué), responsable sécurité présent.
Sur le vrai robot : à vérifier.
