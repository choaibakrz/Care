# Fiche d'ébauche — Unitree G1 (humanoïde)

**Non testé sur vrai robot.** Aucune ligne de cette fiche ne prétend marcher : c'est ce que la doc publique dit,
lue le **11.11.2026**, et la liste de ce qui reste **à vérifier** sur le robot lui-même.
Chemin conseillé : **sdk** (kit Python du fabricant) ; ROS 2 possible (voir plus bas).

## Ce que la doc publique dit vraiment (lu le 11.11.2026)

| Quoi | Ce qui est écrit | Où |
|---|---|---|
| Kit Python | `unitree_sdk2_python`, licence **BSD-3-Clause**, © Unitree Robotics (fichier LICENSE lu) | https://github.com/unitreerobotics/unitree_sdk2_python |
| Installation | Python ≥ 3.8, `cyclonedds == 0.10.2`, numpy, opencv-python ; `pip3 install -e .` depuis le dépôt | README du même dépôt |
| Messages G1 | « idl/unitree_hg is used for Unitree G1/H1-2 robots » | `example/g1/readme.md` |
| Démarrer | `ChannelFactoryInitialize(0, <carte réseau>)` ; `LocoClient()` ; `SetTimeout(10.0)` ; `Init()` | `example/g1/high_level/g1_loco_client_example.py` |
| Avertissement du fabricant | « WARNING: Please ensure there are no obstacles around the robot while running this example. » puis « Press Enter to continue... » | même exemple |
| Marcher | `Move(vx, vy, vyaw, continous_move=False)` → `SetVelocity(vx, vy, omega, duration)` avec **duration = 1.0 s** ; si `continous_move=True` : **864000 s** | `unitree_sdk2py/g1/loco/g1_loco_client.py` |
| S'arrêter | `StopMove()` = `SetVelocity(0, 0, 0)` ; **`StopMove()`, `Move()`, `Damp()`, `ZeroTorque()` ne rendent rien (`None`)**, alors que `SetVelocity()` et `SetFsmId()` rendent un code (relu le 11.11.2026) | même fichier |
| Modes | `Damp()` = FSM 1 ; `ZeroTorque()` = FSM 0 ; `Start()` = FSM 500 ; `Sit()` = FSM 3 ; `Squat2StandUp()` et `StandUp2Squat()` = FSM 706 ; `Lie2StandUp()` = FSM 702 | même fichier |
| Hauteur | `HighStand()`, `LowStand()` (`SetStandHeight`) | même fichier |
| Gestes du bras | `G1ArmActionClient()` ; `ExecuteAction(action_map.get("high wave"))` (sans réglage de vitesse : **vitesse du geste : à vérifier par kit**) ; noms vus : release arm, shake hand, high five, hug, high wave, clap, face wave, left kiss, heart, right heart, hands up, x-ray, right hand up, reject, right kiss, two-hand kiss | `example/g1/high_level/g1_arm_action_example.py` |
| Autres gestes | `WaveHand()`, `ShakeHand()` (par `SetTaskId`) | `g1_loco_client.py` |
| Se relever couché | commentaire : « ensure that the robot faces up and the ground is hard, flat and rough » | `g1_loco_client_example.py` |
| ROS 2 | `unitree_ros2`, **BSD-3-Clause** ; foxy (Ubuntu 20.04) ou humble (22.04, « recommend ») ; CycloneDDS 0.10.2 ; l'introduction dit « Supports Unitree Go2, B2, and H1 » (le G1 n'apparaît que dans des exemples) | https://github.com/unitreerobotics/unitree_ros2 |
| Réseau (ROS 2) | carte réseau en IPv4 manuelle **192.168.123.99**, masque 255.255.255.0 | README de `unitree_ros2` |

## À vérifier (sur le robot, avec la doc officielle)
- **Doc officielle** support.unitree.com : **non lue** (adresse non autorisée dans la session de préparation).
- **Arrêt d'urgence PHYSIQUE** : vu seulement dans des **résumés de recherche** (pages non lues) : la télécommande,
  touches L2 + B, mettrait le robot en mode amorti, et le robot **perd l'équilibre et tombe** ; une page de NVIDIA dirait
  que le G1 n'a pas de bouton d'arrêt sur le corps. **Tout est à vérifier** avec le robot et le fabricant.
- **Chien de garde du fabricant** : `Move()` envoie une durée de 1 s ; le robot s'arrête-t-il vraiment seul si l'ordre
  n'est pas répété ? À vérifier, robot **suspendu** (portique). Ne jamais utiliser `continous_move=True`.
- **Arrêt d'urgence logiciel** : `Damp()` ou `ZeroTorque()` peuvent faire **tomber** le robot. Proposition :
  `arret_urgence()` = `SetVelocity(0, 0, 0)` (il rend un code ; `StopMove()` fait la même chose mais ne rend rien :
  un arrêt sans code = « non confirmé ») ; le reste à la main. Cet « arrêt de marche » **ne bloque pas** le robot (il
  accepte l'ordre suivant). **Décision de Hiba et du responsable sécurité.**
- **Délai de l'appel d'arrêt** : les exemples règlent `SetTimeout(10.0)` ; pour l'arrêt, un délai court (un client à
  part réglé à 0,5 s par exemple ; à vérifier) : un arrêt qui attend 10 s sa réponse ne sert à rien.
- Le kit marche-t-il depuis un Mac (macOS, puce Apple) ? CycloneDDS 0.10.2 sur Mac : à vérifier. Sinon : un ordinateur
  Linux sur le réseau du robot.
- Version « EDU » nécessaire pour le kit ? Version du logiciel du robot ↔ version du kit : à vérifier.
- Vitesse maximale : **aucune limite lue**. Les exemples utilisent `Move(0.3, 0, 0)` : c'est un exemple, pas une limite.
- Lire l'état (batterie, position) en Python pour le G1 : pas lu (à vérifier dans `unitree_sdk2py`).
- Parler : un dossier `example/g1/audio` existe (non lu). Mains (saisir) : non lu.
- Le kit accepte-t-il deux appels en même temps (le fil de l'arrêt d'urgence) ? À vérifier.

## Correspondance proposée (prise → G1), à vérifier une par une
| Action de la prise | Appel proposé | Remarque |
|---|---|---|
| `se_deplacer` (dx, dy) | `Move(vx, vy, 0)` répété toutes les 0,1 s | l'adaptateur bride à 0,1 m/s en mode lent |
| `arreter` | `SetVelocity(0, 0, 0)` | rend un code (`StopMove()` rend `None`) |
| arrêt d'urgence logiciel | `SetVelocity(0, 0, 0)` (proposition) | ne bloque pas le robot ; `Damp()` = chute possible |
| `rejouer_geste` | `G1ArmActionClient.ExecuteAction(action_map.get(nom))` | noms exacts dans la carte ; vitesse du geste : à vérifier par kit |
| `etat` | à vérifier | |
| `parler`, `ecouter` | voix et micro du Mac (brique 4), ou `audio` (à vérifier) | |
| `saisir`, `poser` | pas dans la carte tant que non vérifié | |

## Premier essai (feu orange)
Robot **suspendu** au portique, responsable sécurité présent, main sur l'arrêt physique (télécommande ?). Test sans
mouvement, puis `Move` à 0,1 m/s pendant une seconde. Jamais de saut, de course ni de geste rapide dans la carte.
