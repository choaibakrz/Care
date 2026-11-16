# Fiche d'ébauche — AgileX PiPER (bras 6 axes)

**Non testé sur vrai robot.** Ce que la doc publique dit, lu le **14.11.2026**, et ce qui reste **à vérifier**.
Aucune ligne ne prétend marcher. Chemin conseillé : **sdk** (le kit Python `piper_sdk` d'AgileX).
Le bras est sur la table de l'équipe (photos de Hiba, 14.11.2026 : étiquettes « AGILEX » et « PiPER »). Rien ne lui a
été envoyé. Le kit du fabricant n'est **pas installé** (l'installer est un feu orange).
Relue par un relecteur neuf le 14.11.2026 (3 défauts graves et 9 moyens corrigés).

## Attention : deux « Piper » dans le projet
`requirements-piper-gpl.txt` parle de **Piper, la voix** (un programme de synthèse vocale, GPL). Le bras utilise
**`piper_sdk`** (AgileX, MIT). Ce sont deux choses sans rapport : ne pas confondre les deux paquets.

## Attention : ne lancer aucun exemple du fabricant tel quel
**Un exemple dont le nom dit « read » ÉCRIT un réglage** : `piper_read_crash_protection.py` appelle
`CrashProtectionConfig(0,0,0,0,0,0)`, c'est-à-dire « aucune détection de choc » sur les six articulations.
Sur les 8 exemples « ctrl » lus, 5 mettent le bras sous tension (`EnablePiper()`) juste après la connexion.

## Ce que la doc publique dit vraiment (lu le 14.11.2026)
Dépôt : https://github.com/agilexrobotics/piper_sdk, branche `master`. Les commentaires du fabricant sont souvent en
chinois : les phrases marquées « (traduit) » sont nos traductions, pas des citations.

| Quoi | Ce qui est écrit | Où |
|---|---|---|
| Kit | `piper_sdk`, licence **MIT** (« Copyright (c) 2024 Agilex Robotics Co., Ltd. ») ; `setup.py` dit la version `0.7.0a1` (une version d'essai) et Python ≥ 3.6 | `LICENSE`, `setup.py` |
| **Trois familles** | kit `0.0.x` pour un bras d'avant la version V1.5-2 ; classe `C_PiperInterface_V2` ensuite ; « Use `C_PiperInterface_V3` for firmware version `1.8-8` and later ». La doc de V3 (`assets/V3/INTERFACE_V3.MD`) **n'a pas été lue** | `README.MD` |
| Systèmes | Ubuntu 18.04, 20.04, 22.04 ; `setup.py` ne déclare que Linux ; le type de câble « socketcan » (celui de Linux) est écrit en dur. Mac et Windows : pas cités | page du dépôt, `setup.py`, `piper_interface_v2.py` |
| Liaison | par **CAN** (un câble de données de robot), avec le boîtier USB → CAN **du bras** (« only supports the robot arm's built-in CAN module ») ; débit 1000000 | page du dépôt |
| Mise en route du câble | `sudo apt install can-utils ethtool` ; `piper-can activate can0 1000000` (commande installée avec le kit, Linux seulement) | `assets/can_config.MD` |
| Installation | `pip3 install python-can` (≥ 3.3.4) ; `pip3 install piper_sdk` (≥ 0.1.9 pour les exemples V2) | `piper_sdk/demo/V2/README.MD` |
| Connexion | `C_PiperInterface_V2(can_name="can0")` ouvre le câble ; `ConnectPort()` lance un « fil » (un petit programme qui tourne à côté) qui lit le câble. Avec `piper_init=True` (le réglage d'origine), il **écrit aussi 13 messages de question** au bras (vitesses max, accélérations max, version) ; avec `piper_init=False`, il n'écrit **rien** (écoute seule). Dans les deux cas : aucune mise sous tension, aucun mouvement | `piper_interface_v2.py` (`ConnectPort`, `PiperInit`) |
| Premier message | « the first frame of all messages is the default value » : avant le premier message reçu, l'état rendu vaut 0 partout, ce qui se lit « normal, arrivé ». `time_stamp` et `Hz` valent alors 0 | `README.MD`, `piper_interface_v2.py` |
| Bras « maître » | « reading joint feedback requires the robot to be in slave mode. If it is in master mode, the robot will not respond » | `README.MD` |
| Le bras répond-il ? | `isOk()` est **vrai dès le départ** ; il ne devient faux qu'après 5 mesures de suite sans **aucun** message sur le câble (une mesure toutes les 0,05 s). `get_connect_status()` rend un drapeau du programme, mis à vrai **même si l'ouverture du câble a échoué**. `DisconnectPort()` n'arrête pas la surveillance : juste après une reconnexion, `isOk()` peut encore être faux | `piper_interface_v2.py` |
| État | `GetArmStatus()` : `time_stamp`, `Hz`, et `.arm_status` avec `ctrl_mode` (0 attente, 1 commandé par CAN, 2 apprentissage à la main, 3 Ethernet, 4 Wi-Fi, 5 télécommande, 6 apprentissage lié, 7 trajet hors ligne, 0xFF inconnu), `arm_status` (0 normal, 1 arrêt d'urgence, 2 pas de solution, 3 point singulier — une position où le bras ne sait plus comment bouger —, 4 angle hors limite, 5 communication d'une articulation, 6 frein d'articulation non ouvert, 7 collision, 8 survitesse en apprentissage, 9 articulation anormale, 0x0A autre, 0x0B–0x0D apprentissage, 0x0E et 0x0F surchauffe, 0xFF inconnu), `motion_status` (0 arrivé, 1 pas arrivé), `err_status` (une panne possible par articulation) | `piper_interface_v2.py`, `arm_feedback_status.py` |
| Vitesse des moteurs | `GetArmHighSpdInfoMsgs()` : `motor_1` … `motor_6`, chacun avec `motor_speed` en 0,001 rad/s | `piper_interface_v2.py` |
| Autres lectures | `GetArmJointMsgs()` (angles, en 0,001 degré), `GetArmGripperMsgs()` (pince : course en 0,001 mm, couple — la force de rotation — en 0,001 N·m), `GetArmEndPoseMsgs()`, `GetArmLowSpdInfoMsgs()` (tension en 0,1 V, températures, état de chaque moteur), `GetArmEnableStatus()` (moteurs sous tension ou non), `GetPiperFirmwareVersion()` | même fichier |
| Mettre sous tension | `EnablePiper()` (répété jusqu'à « vrai ») ; impossible en mode bras maître (traduit) | `demo/V2/piper_ctrl_enable.py` |
| Couper la tension | `DisablePiper()` | `demo/V2/piper_ctrl_disable.py` |
| Bouger | `MotionCtrl_2(0x01, 0x01, <vitesse en %>, 0x00)` puis `JointCtrl(j1…j6)` (angles en 0,001 degré) ; `EndPoseCtrl(X, Y, Z, RX, RY, RZ)` ; modes MOVE P / J / L / C | `demo/V2/piper_ctrl_moveJ.py`, `piper_interface_v2.py` |
| Pince | `GripperCtrl(course, couple, code, 0)` : course en 0,001 mm, couple 0 à 5000 (= 0 à 5 N·m), code 0x01 = sous tension | `demo/V2/piper_ctrl_gripper.py`, `piper_interface_v2.py` |
| **Arrêt « rapide »** | `MotionCtrl_1(0x01, 0, 0)` ou `EmergencyStop(0x01)` : « Stop the robotic arm and allow it to **descend slowly**. After use, reset and re-enable twice before resuming normal control » | `demo/V2/README.MD`, `piper_ctrl_stop.py` |
| **Remise à zéro** | `MotionCtrl_1(0x02, 0, 0)`, `ResetPiper()` ou `EmergencyStop(0x02)` (que le kit appelle « Resume ») : c'est **le même ordre**. « The robot will **immediately lose power and fall down**, clearing all errors and internal flags ». À faire aussi après le mode apprentissage, dit le fabricant | `piper_interface_v2.py`, `demo/V2/README.MD` |
| Pause du trajet | `MotionCtrl_1(0, 0x01, 0)` : « Pause current plan » | `piper_interface_v2.py` |
| Protection contre les chocs | `CrashProtectionConfig(…)` : un niveau par articulation ; 0 = aucune détection | `piper_interface_v2.py` |
| Vitesse max du bout du bras | `GetCurrentEndVelAndAccParam()` rend `end_max_linear_vel` en 0,001 m/s, après `ArmParamEnquiryAndConfig(param_enquiry=0x01)` — qui est aussi une fonction de **réglage** : prudence | `piper_interface_v2.py` |
| Plusieurs fils | le kit garde un message d'envoi par fil (prévu pour des envois venus de plusieurs fils) | `piper_interface_v2.py` |
| Mode « MIT » | commande directe de chaque moteur : « misuse of this protocol can damage the robot arm » | page du dépôt |
| Autre kit | un kit plus récent existe : `pyAgxArm` (non lu) | page du dépôt |

## Ce que dit le guide du fabricant (lu le 14.11.2026)
« PiPER Robotic Arm — Quick start user manual V1.0, 2024.09 », AgileX Robotics, 10 pages, PDF donné par Hiba
(https://cdn.robotshop.com/rbm/815d1a40-62cd-43a6-8dad-e05323e8953a/8/8c19397c-f1ab-4891-97e7-50fc64a8ef24/ac127c74_piper-quick-start-user-manual-en(1).pdf).

| Quoi | Ce qui est écrit | Page |
|---|---|---|
| Charge | « The maximum payload of the robotic arm is 1.5KG » (outil compris : la main pèse déjà 545 g) | 1 |
| Pas de capteur d'obstacle | « the robotic arm does not come with any automatic obstacle-avoidance sensors » : choisir un endroit dégagé | 1 |
| Fixation | « Ensure that the robotic arm and tools/end effectors are always correctly and securely fixed in place » | 1 |
| Distance | garder la tête, le visage et le corps hors de la zone que le bras peut atteindre ; pas de vêtements amples, cheveux attachés ; lunettes de protection si on doit entrer dans la zone | 1–2 |
| Chaleur | le bras chauffe : ne pas le toucher pendant qu'il marche ni juste après (« wait for one hour ») | 2 |
| Plusieurs machines | relier des machines ensemble ajoute des risques ; garder le niveau d'arrêt d'urgence le plus exigeant | 2 |
| Dans la boîte | bras, boîtier « USB to CAN », bloc d'alimentation, câble MicroUSB, câble courant + données, 4 vis de base, clé | 4 |
| Prise du bras | **une seule prise**, 4 broches : courant +, courant −, CAN-H, CAN-L ; un voyant d'état. Aucune prise pour un outil n'est décrite au bout du bras | 5 |
| Alimentation | avec un autre bloc que celui fourni : « the power input must not exceed 26V, and the current must be no less than 10A » | 5 |
| Bouton d'apprentissage | entre les articulations 5 et 6. Un clic : enregistrer (voyant vert fixe), un clic : arrêter ; double clic : **rejouer** le dernier trajet (voyant vert clignotant). Trajet de 3 minutes au plus ; un nouvel enregistrement efface l'ancien | 5–6 |
| Pendant le rejeu | « the user must keep a safe distance from the robotic arm to avoid injury » | 6 |
| Avant de commander par programme | voyant éteint (apprentissage arrêté), puis passer en mode attente, puis en mode CAN | 6 |
| Base | 4 trous filetés M5, écartés de 70 mm ; plaque de 80 × 95 mm sur le dessin | 6–7 |
| Bout du bras | « The end can be equipped with other tools via a flange » ; le dessin montre un disque (la bride) entre le bras et la pince. **Aucune cote** de cette bride dans ce guide | 7 |
| Logiciel du fabricant | « ArmRobotUA », pour Windows 7 ou plus : boutons « Enable » et « Emergency Stop », réglage de vitesse en % | 7–8 |
| Programmation | kit Python `piper_sdk` et paquet ROS1 `piper_ros` | 9 |

**Ce que ce guide ne dit pas** : aucun bouton d'arrêt d'urgence PHYSIQUE (seulement un bouton dans le logiciel Windows,
et « immediately perform an emergency stop » si le logiciel montre une erreur) ; rien sur des freins ni sur ce que
fait le bras quand on coupe le courant ; ni la portée, ni les vitesses, ni comment lire la version du logiciel du bras.
La carte garde 0 pour la charge tant qu'aucune action « saisir » n'est branchée ; le chiffre du fabricant (1,5 kg,
outil compris) est maintenant lu et pourra y être écrit à ce moment-là.

## Signalé à Hiba
Aucun texte adressé à un agent n'a été vu dans les fichiers lus (vérifié aussi par le relecteur).

## À vérifier (sur le bras, avec le manuel et le responsable sécurité)
- **D'abord : la version du logiciel du bras**, AVANT de choisir la classe V2 ou V3. L'ébauche utilise V2 : c'est un
  choix provisoire. **En écoute seule, le kit ne demande jamais cette version** (`GetPiperFirmwareVersion()` ne rend
  alors rien d'utile) : la lire sur la plaque du bras ou dans l'application du fabricant, ou par une question écrite
  au bras (`SearchPiperFirmwareVersion()`, un message : feu orange).
  La version du kit installée par `pip3` a-t-elle bien toutes les fonctions lues ici ?
- **Variante** : PiPER, PiPER-H, PiPER-L ou PiPER-X ? À lire sur la plaque du bras.
- **Chiffres du bras** : 4,2 kg, charge 1,5 kg, portée 626 mm, répétabilité (l'écart quand il refait le même geste)
  ±0,1 mm, alimentation 24 V ; PiPER-H : 2 kg, 636 mm. Ils viennent d'un **résumé de recherche** (page
  https://global.agilex.ai/products/piper et revendeurs) : la page du fabricant n'a pas pu être relue (elle a refusé
  deux fois). Les mêmes chiffres (4,2 kg, 1,5 kg, 626 mm, DC 24 V, base 70 mm × 70 mm, 4 vis M5) ont été lus
  directement sur la page d'un distributeur (https://westonrobot.github.io/docs-legacy/robot_user_guide/agilex/piper.html,
  14.11.2026), pas chez le fabricant. Le manuel du bras (PDF) n'a pas pu être téléchargé.
  **La carte garde donc 0 partout.**
- **Le bras envoie-t-il son état sans qu'on lui demande rien** (écoute seule) ? Est-il en mode « bras maître » ?
- **Arrêt d'urgence PHYSIQUE** : aucun bouton vu dans la doc lue. Couper l'alimentation arrête-t-il le bras sans qu'il
  tombe ? L'état « frein d'articulation non ouvert » laisse penser qu'il y a des freins : **à vérifier, ne pas le supposer**.
- **Arrêt normal** (le bras s'arrête et reste en place) : aucun appel lu ne le dit clairement. « Pause current plan »
  existe, mais on ne sait pas s'il vaut pour un mouvement lancé par `JointCtrl`.
- **Arrêt d'urgence logiciel** : `EmergencyStop(0x01)` fait **descendre** le bras lentement : ce n'est pas un arrêt
  « sans mouvement ». Que tient la main pendant la descente ? Où descend le bras ? Choix avec le responsable sécurité.
- **Réarmer** : la doc dit « reset and re-enable twice ». Or la remise à zéro fait **tomber** le bras : elle ne peut
  pas être dans `rearmer()` (qui ne doit jamais faire bouger le robot). Proposition : une étape humaine à part.
- **Chien de garde du fabricant** : que fait le bras si l'ordinateur se tait ou si le câble est débranché ? Rien lu.
- **« En mouvement »** : la logique de l'ébauche (modes, « pas arrivé », vitesse des moteurs au-dessus de 0,02 rad/s)
  est un choix de l'équipe. Dans le doute elle dit « en mouvement ». Seuil et bruit des capteurs : à vérifier.
  Le rythme des messages (`Hz`) est une moyenne des six moteurs : un seul moteur muet ne se verrait pas. La pince
  ou la main ne sont pas regardées. `Hz` retombe-t-il bien à 0 quand le bras se tait ? À vérifier sur le bras.
- **Vitesse** : le kit commande en pourcentage (0 à 100), pas en m/s. La carte garde 0.
- **Force de la pince** : le kit donne un couple (N·m), pas une force (N). La carte garde 0.
- **Le bout du bras** : une main est sur la table. Étiquettes vues sur les photos de Hiba (14.11.2026) : « Leadtron »,
  « Dexterous Hand », « DH116 CANFDCABLE », et un boîtier USB « Mini CANFD-I ». Lu le 14.11.2026 dans le manuel du
  fabricant (« Leadtron DH116 Series Dexterous User Manual »,
  https://store.leadshine.com/cdn/shop/files/DH116_DH116P_Series_Dexterous_User_Manual.pdf, 9 pages) :
  11 articulations dont 6 avec moteur ; 545 g ±10 g ; alimentation « 12~48V@2.5A » ; CANFD (fils : rouge VDC, vert GND,
  jaune CANH, noir CANL) ; force de pincement sur le côté ≤ 50 N ; ouverture ou fermeture en 0,5 s au plus vite ;
  « Windows 10 and above / Linux / ROS2, C++ / Python » ; kit `LHandProLib` et paquet ROS 2 `lhandpro_ws` (à télécharger
  chez le fabricant : non lus, **licence non écrite dans le manuel**).
  **Attention (lu)** : couper le courant avant tout montage ; et « it will automatically reset when powered on » :
  la main **bouge toute seule quand on la met sous tension**. Doigts dégagés, rien dans la main à ce moment-là.
  Le manuel ne montre **aucun plan de la bride** : la main va-t-elle sur le bout du bras, avec ou sans plaque ? À
  vérifier en les posant l'un contre l'autre, sans courant. C'est un deuxième appareil, avec son câble, son
  alimentation et ses propres arrêts : une étape à part, après le bras.
- **Fixation** : sur les photos, le bras est posé sur la table, pas vissé. À fixer avant toute mise sous tension.
- **Depuis un Mac** : Linux seulement d'après le kit. Chemin possible : une machine virtuelle Ubuntu 22.04 (à créer :
  feu orange), en lui passant le boîtier USB → CAN. À vérifier.
- **Reconnexion** : `DisconnectPort()` attend-il la fin de la lecture ? Une reconnexion rapide relance-t-elle bien
  la lecture ? Le kit accepte-t-il un arrêt pendant un autre appel ? À vérifier sur le bras.

## Correspondance proposée (prise → PiPER), à vérifier une par une
| Action de la prise | Appel proposé | Remarque |
|---|---|---|
| connexion | `C_PiperInterface_V2(can_name)` + `ConnectPort(piper_init=False)` dans `creer_kit()` ; `ouvrir()` attend un vrai état du bras | **écrit** dans `robots/agilex_piper/liaison.py` ; écoute seule, pas d'`EnablePiper()` |
| `etat` | `GetArmStatus()` + `GetArmHighSpdInfoMsgs()` | **écrit** ; batterie : à vérifier (le kit donne une tension) |
| `arreter` | à choisir (pause du trajet ? rester sur place ?) | **pas écrit** : rien de clair dans la doc |
| arrêt d'urgence logiciel | `EmergencyStop(0x01)` (descente lente) | **pas écrit** : choix avec le responsable sécurité |
| `rearmer` | rien côté bras ? (la remise à zéro fait tomber le bras) | **pas écrit** : étape humaine à décider |
| `montrer` | `MotionCtrl_2` + `JointCtrl` vers une pose enregistrée, vitesse en % bridée | poses à enregistrer avec le bras |
| `saisir`, `poser` | `GripperCtrl` (pince du bras) ou la main DH116 (autre kit) | pas lu pour la main |
| `rejouer_geste` | apprentissage à la main : `MotionCtrl_1(0, 0, 0x03)` (rejouer le trajet appris, traduit) | non essayé, vitesse inconnue |
| `se_deplacer` | — | un bras ne se déplace pas : `position_fixe` dans la carte |

## Où en est l'ébauche
- Le test de conformité « faux kit » (`python3 lancer.py brancher agilex_piper --conformite`) essaie la mécanique
  commune et la carte, **pas** `liaison.py` : `adaptateur.py` y met encore le faux kit du projet. À passer sur la
  doublure quand les trois arrêts seront choisis (comme pour le Go2).
- `liaison.py` est essayée à part, avec la doublure (`tests/test_ebauche_agilex_piper.py`) : testé sur faux robot.
- Avec `--vrai` aujourd'hui : sans le kit installé, le programme s'arrête et dit pourquoi, rien n'est envoyé. Avec le
  kit : la connexion se ferait en écoute seule, puis le test échouerait du bon côté (aucune action branchée, les trois
  arrêts disent « À BRANCHER », le système refuse le vrai robot).

## Premier essai (feu orange)
Bras **fixé** à la table, zone vide autour de lui (distance décidée avec le responsable sécurité), responsable
sécurité présent, une main sur la prise d'alimentation. D'abord le test **sans mouvement**, en écoute seule (sans
`EnablePiper()`) : lire l'état. Puis, après le « oui » de Hiba et le choix des arrêts, un seul petit mouvement lent.
