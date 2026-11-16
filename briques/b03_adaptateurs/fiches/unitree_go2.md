# Fiche d'ébauche — Unitree Go2 (chien)

**Non testé sur vrai robot.** Ce que la doc publique dit, lu le **11.11.2026**, et ce qui reste **à vérifier**.
Aucune ligne ne prétend marcher. Chemin conseillé : **sdk** ; ROS 2 possible (`unitree_ros2` dit supporter le Go2).

## Ce que la doc publique dit vraiment (lu le 11.11.2026)

| Quoi | Ce qui est écrit | Où |
|---|---|---|
| Kit Python | `unitree_sdk2_python`, **BSD-3-Clause**, © Unitree Robotics | https://github.com/unitreerobotics/unitree_sdk2_python |
| Installation | Python ≥ 3.8, `cyclonedds == 0.10.2` ; si CycloneDDS introuvable : le construire (branche `releases/0.10.x`) et régler `CYCLONEDDS_HOME` | README du dépôt |
| Avant le contrôle bas niveau | couper le service `sport_mode` dans l'appli « to prevent conflicting instructions » | README du dépôt |
| Démarrer | `ChannelFactoryInitialize(0, <carte réseau>)` ; `SportClient()` ; `SetTimeout(10.0)` ; `Init()` | `example/go2/high_level/go2_sport_client.py` |
| Avertissement du fabricant | « WARNING: Please ensure there are no obstacles around the robot while running this example. » | même exemple |
| Bouger, s'arrêter | `Move(vx, vy, vyaw)` (envoyé sans attendre de réponse) ; `StopMove()` ; `StandUp()`, `StandDown()`, `BalanceStand()`, `RecoveryStand()`, `Damp()` | `unitree_sdk2py/go2/sport/sport_client.py` |
| Gestes | `Hello()`, `Stretch()`, `Sit()`, `RiseSit()`, `Heart()`, `Content()`, `Dance1()`, `Dance2()`, `Scrape()` ; ils rendent un code (relu le 11.11.2026) | même fichier |
| Mouvements **dangereux** (jamais dans la carte) | `FrontFlip()`, `BackFlip()`, `LeftFlip()`, `FrontJump()`, `FrontPounce()`, `HandStand()`, `FreeJump()`, `FreeBound()` | même fichier |
| Autres | `SpeedLevel(level)`, `SwitchJoystick(on)`, `AutoRecoverySet(enabled)`, `FreeAvoid(flag)` | même fichier |
| Dossiers du kit Go2 | `obstacles_avoid`, `robot_state`, `sport`, `video`, `vui` | `unitree_sdk2py/go2/` |
| ROS 2 | `unitree_ros2` (**BSD-3-Clause**) : « Supports Unitree Go2, B2, and H1 » ; foxy ou humble ; sujets `/sportmodestate`, `/lowstate`, `/wirelesscontroller`, `/lowcmd`, `/api/sport/request` (messages `unitree_api::msg::Request`), `/utlidar/cloud` | https://github.com/unitreerobotics/unitree_ros2 |
| Réseau | carte réseau en IPv4 manuelle **192.168.123.99**/24 (exemple d'interface : enp3s0) | README de `unitree_ros2` |

## À vérifier (sur le robot, avec la doc officielle)
- **Doc officielle** support.unitree.com : **non lue** (adresse non autorisée dans la session de préparation).
- **Arrêt d'urgence PHYSIQUE** : où est-il ? (télécommande ? bouton ? couper la batterie ?) — rien lu.
- **Chien de garde du fabricant** : `Move()` n'a **pas** de durée dans le kit Python (le G1 en a une). Si les ordres
  cessent, le chien s'arrête-t-il seul, et en combien de temps ? **À mesurer**, chien posé sur un support, pattes dans le vide.
- **Arrêt d'urgence logiciel** : `StopMove()` (il reste debout) ou `Damp()` (il s'affaisse, à vérifier) ? Décision
  de Hiba et du responsable sécurité. Proposition : `StopMove()`.
- **Mise en garde `Dance1()` / `Dance2()`** : des danses de tout le corps, longues et sans doute rapides (rien lu
  sur leur vitesse ni leur durée) : pas dans la carte sans un essai à part, chien suspendu, feu orange.
  Vitesse d'un geste enregistré : à vérifier par kit (aucun réglage lu).
- L'arrêt de marche `StopMove()` **ne bloque pas** le chien : il accepte l'ordre suivant.
- **Délai de l'appel d'arrêt** : l'exemple règle `SetTimeout(10.0)` ; pour l'arrêt, un délai court (un client à part,
  réglé à 0,5 s par exemple ; à vérifier) : un arrêt qui attend 10 s sa réponse ne sert à rien.
- Version « EDU » nécessaire pour le kit ? Version du logiciel du chien ↔ version du kit : à vérifier.
- Vitesse maximale : **aucune limite lue** ; `Move(0.3, 0, 0)` dans l'exemple n'est pas une limite.
- Lire l'état (batterie, odomètre) : dossier `robot_state` et sujet `/sportmodestate` vus, contenu non lu.
- `AutoRecoverySet` (se relever seul après une chute) : bouge sans ordre ? À vérifier, et sans doute à couper.
- Le kit marche-t-il depuis un Mac ? À vérifier (sinon un ordinateur Linux sur le réseau du robot).

## Correspondance proposée (prise → Go2), à vérifier une par une
| Action de la prise | Appel proposé | Remarque |
|---|---|---|
| `se_deplacer` (dx, dy) | `Move(vx, vy, 0)` répété toutes les 0,1 s, puis `StopMove()` | 0,1 m/s en mode lent |
| `arreter` / arrêt d'urgence logiciel | `StopMove()` | `Damp()` à décider |
| `rejouer_geste` | `Hello()`, `Stretch()`, `Sit()`… selon le nom de la carte | **jamais** saut, salto, appui renversé |
| `etat` | à vérifier (`robot_state`) | |
| `parler`, `ecouter` | voix et micro du Mac (brique 4) ; `vui` à vérifier | |

## Premier essai (feu orange)
Chien couché ; le mettre debout avec la télécommande ou l'appli du fabricant (à vérifier), feu orange ; zone vide,
responsable sécurité présent. Test sans mouvement, puis `Move` à 0,1 m/s pendant une seconde, main sur l'arrêt physique.
Notre adaptateur ne relève jamais le robot tout seul (ni à la connexion, ni au réarmement).
