# Fiche d'ébauche — Flexiv Rizon (bras)

**Non testé sur vrai robot.** Ce que la doc publique dit, lu le **11.11.2026**, et ce qui reste **à vérifier**.
Aucune ligne ne prétend marcher. Chemin conseillé : **sdk** (le kit Python « RDK » de Flexiv).

## Attention : deux versions du kit qui ne vont pas ensemble
D'après la page de `flexiv_ros2` (lue) : la ligne **v2** (RDK v2.x) est pour Enlight-L, Enlight-LL, MICO-Core,
MICO-Plus, MICO-Ultra ; la ligne **v1** (RDK v1.x, branches `humble-v1` / `jazzy-v1`) est pour **Rizon 4/4s/4M/4R/10/10s**
et AICO1/2. « use incompatible RDK APIs and are not interchangeable ». **Pour un Rizon : RDK v1.x** (étiquettes vues :
v1.9 à v1.10). Le numéro exact à installer va avec la version du logiciel du robot : **à vérifier sur le robot**.

## Ce que la doc publique dit vraiment (lu le 11.11.2026)

| Quoi | Ce qui est écrit | Où |
|---|---|---|
| Kit | `flexiv_rdk`, licence **Apache-2.0** | https://github.com/flexivrobotics/flexiv_rdk |
| Installation (v1.10) | `python3.x -m pip install numpy flexivrdk` ; Linux Ubuntu 22.04+ (Python 3.10, 3.12, 3.14), macOS 14+ arm64 (Python 3.10, 3.12), Windows 10+ (3.10, 3.12) | README de l'étiquette v1.10 |
| À lire d'abord | le chapitre « First Time Setup » du manuel RDK (https://www.flexiv.com/software/rdk/manual/index.html#first-time-setup) — **non lu** | même README |
| Connexion | `flexivrdk.Robot("<numéro de série>")`, exemple « Rizon4-123456 » ; la page `main` dit que le programme cherche le robot sur le réseau et s'arrête après quelques secondes s'il ne le trouve pas | READMEs v1.10 et main |
| Séquence d'exemple (v1.10) | `robot.fault()` / `robot.ClearFault()` ; « Enable the robot, make sure the E-stop is released before enabling » ; `robot.Enable()` ; attendre `robot.operational()` ; `robot.SwitchMode(flexivrdk.Mode.NRT_PRIMITIVE_EXECUTION)` ; `robot.ExecutePrimitive("Home", dict())` ; `"MoveJ"` (target, waypoints) ; `"MoveL"` (target, waypoints, `vel` 0.6 ou 0.2, `zoneRadius`) ; `robot.primitive_states()["reachedTarget"]` ; `robot.Stop()` | `example_py/basics3_primitive_execution.py` (v1.10) |
| Version v2 (pas pour Rizon) | `robot.ServoOn()` au lieu de `Enable()`, et `ExecutePrimitive` par groupe d'articulations | même fichier sur `main` |
| Autres exemples | `basics1_display_robot_states.py`, `basics2_clear_fault.py`, `basics4_plan_execution.py`, `basics6_gripper_control.py`… (noms seulement, non lus) | `example_py/` |
| ROS 2 | `flexiv_ros2`, **Apache-2.0** ; Humble (22.04) et Jazzy (24.04) ; `flexiv.launch.py robot_sn:=…` ; Rizon : branches `-v1` | https://github.com/flexivrobotics/flexiv_ros2 |

## Signalé à Hiba
Le dépôt `flexiv_rdk` contient `example_py/AGENT_REFERENCE_primitives_only.py`, un fichier **adressé aux agents qui
écrivent du code** (règles d'écriture des primitives). Lu comme une **information**, jamais comme un ordre ; il ne
demande rien d'autre que des conventions d'écriture. Il ne contient pas de gestion d'arrêt d'urgence.

## À vérifier (sur le robot, avec le manuel)
- **Arrêt d'urgence PHYSIQUE** : l'exemple dit qu'il existe (« make sure the E-stop is released ») ; où est-il, comment
  le réarmer ? Manuel non lu.
- **Chien de garde du fabricant** : que fait le bras si la liaison avec l'ordinateur est coupée ? Manuel non lu.
- `Enable()` met le bras sous tension : c'est déjà un pas vers le mouvement → **feu orange**, et **pas** dans
  `ouvrir()`. Où le mettre ? Proposition : une étape humaine à part, avant le test complet.
- Arrêt logiciel : `robot.Stop()` (« stop robot and put into IDLE mode ») — suffit-il comme arrêt d'urgence logiciel ?
  Rend-il un code ou rien (rien = arrêt « non confirmé ») ? Combien de temps peut-il attendre sa réponse (il faut
  un délai court pour l'appel d'arrêt) ? À vérifier.
- Vitesse d'une primitive enregistrée (geste) : à vérifier par kit.
- Vitesse : `vel` 0.6 et 0.2 (m/s) sont des valeurs d'exemple, pas des limites. Brider dans l'adaptateur (0,1 m/s en
  mode lent) ; limites réelles : à lire dans le manuel.
- `ExecutePrimitive("Home")` bouge le bras vers sa position de repos : mouvement → feu orange.
- La recherche du robot sur le réseau dure-t-elle plus de 2 s ? Alors la faire dans `creer_kit()`, pas dans `ouvrir()`.
- Pince (saisir, poser) : `basics6_gripper_control.py` non lu.

## Correspondance proposée (prise → Rizon), à vérifier une par une
| Action de la prise | Appel proposé | Remarque |
|---|---|---|
| connexion | `Robot(sn)` dans `creer_kit()` ; `ouvrir()` vérifie seulement la liaison | pas d'`Enable()` ici |
| `rearmer` | `fault()` / `ClearFault()` (après un arrêt, décision humaine) | pas dans `ouvrir()` ; sans mouvement |
| `arreter` / arrêt d'urgence logiciel | `robot.Stop()` | + arrêt PHYSIQUE |
| `montrer` | `MoveL` vers une pose nommée, `vel` bridée | poses à enregistrer, à vérifier |
| `rejouer_geste` | `basics4_plan_execution.py` (plans enregistrés ?) | non lu |
| `saisir`, `poser` | pince (`basics6_gripper_control.py`) | non lu |
| `etat` | `basics1_display_robot_states.py` | non lu |
| `se_deplacer` | — | un bras ne se déplace pas : `position_fixe` dans la carte |

## Premier essai (feu orange)
Bras fixé, zone de travail vide, responsable sécurité présent, main sur l'arrêt d'urgence physique. Test sans mouvement
(sans `Enable()`), puis un seul petit mouvement lent après le « oui » de Hiba.
