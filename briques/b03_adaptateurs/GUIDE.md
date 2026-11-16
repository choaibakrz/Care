# Brique 3 — Les adaptateurs, un par vrai robot (guide d'une page)

**Rôle** : traduire les 10 actions de la prise universelle vers UN vrai robot. Un adaptateur ne décide rien : il ne
reçoit que des actions déjà vérifiées par le gardien (ticket) puis par la prise. **Non testé sur vrai robot** ;
tout est **testé sur faux robot** (faux kit SDK, faux ROS 2). Samedi : `BRANCHER_UN_ROBOT.md` (à la racine).

## Les fichiers
| Fichier | Contenu |
|---|---|
| `modele_vide/adaptateur.py` | la mécanique commune (la même pour tous les robots) : chaque méthode du modèle commun, ce qu'elle DOIT faire et ce qu'elle REFUSE |
| `modele_vide/liaison.py` | la **liaison** : les seuls appels propres au fabricant. Vide : tout lève « À BRANCHER » |
| `modele_vide/carte.yaml` | la carte d'identité vide, chiffres « à vérifier » (0 = le robot refuse de bouger) |
| `chemins/sdk/` | chemin (a) : ébauche pour le kit Python du fabricant + `faux_sdk.py` |
| `chemins/ros2/` | chemin (b) : ébauche d'un pont ROS 2 (publie les ordres, lit l'état) + `faux_ros2.py` |
| `conformite_deux_temps.py` | le test de conformité : sans mouvement, puis complet ; feu orange au clavier pour un vrai robot |
| `assistant.py` | `python3 lancer.py brancher …` : crée `robots/NOM/` et lance le test |
| `registre.py` | fabrique l'adaptateur de `robots/NOM/` pour `commun/systeme.py` (branchement proposé au coordinateur) |
| `fiches/` | Unitree G1, Unitree Go2, AGIBOT, Flexiv Rizon, AgileX PiPER, Reachy Mini, main Leadtron DH116 : ce que la doc publique (ou le kit) dit (lien, date), ce qui est à vérifier |
| `robots/` | un dossier par vrai robot, créé par l'assistant |

## La mécanique commune garantit (en plus du gardien et de la prise)
Arrêt d'urgence d'abord (drapeau, boucles coupées, ordre dans un fil **neuf** à chaque tentative, un arrêt normal
mis aussi dans la file habituelle juste derrière l'ordre peut-être en route, jamais d'erreur ; un arrêt coincé ou sauté
est noté et l'état dit « liaison pas sûre ») · chaque ordre revérifié juste avant de partir · tout bloqué jusqu'au
réarmement par un humain (un arrêt pendant le réarmement est renvoyé) · une action longue à la fois · vitesse bridée
(carte ; 0,1 m/s en mode lent ; gestes demandés à mi-vitesse, **vitesse du geste : à vérifier par kit**) · ordres de
vitesse courts répétés toutes les 0,1 s (programme figé = ordres qui cessent = le chien de garde du fabricant arrête
le robot, **à vérifier** par robot) · déplacement arrêté si le robot recule, s'écarte du trajet ou va trop loin ·
notre chien de garde (plus de signe de vie de la prise → arrêt) · capacité non branchée = refus expliqué · état
bizarre = « liaison perdue », jamais une erreur · « vrai » ou « faux » robot décidé par la CLASSE du kit, jamais par
le fichier · fermer le programme = arrêt **normal** (l'arrêt d'urgence du fabricant peut faire tomber un robot à jambes).

## Les commandes
```bash
python3 lancer.py brancher NOM --genre humanoide|chien|bras|roues --chemin sdk|ros2   # crée robots/NOM/
python3 lancer.py brancher NOM --conformite                    # faux kit : testé sur faux robot (*)
python3 lancer.py brancher NOM --conformite --vrai             # FEU ORANGE : vrai robot, sans mouvement
python3 lancer.py brancher NOM --conformite --vrai --complet   # FEU ORANGE : mouvements lents
python3 lancer.py tests briques/b03_adaptateurs
```
(*) Le faux kit essaie la mécanique commune, la carte et l'ÉBAUCHE du chemin — il n'essaie PAS le `liaison.py` du
robot (seul `--vrai` l'essaie).

Avec `--vrai`, le programme rappelle les consignes et attend une phrase **tapée au clavier**, avec un nombre tiré au
hasard (« sans mouvement 4821 », puis « mouvement lent ID-DU-ROBOT 7310 »). Pas d'option pour sauter la question ;
sans clavier, il refuse. **Honnêtement : c'est une protection contre l'oubli, pas contre un agent ou un script** (un
faux clavier se fabrique). La vraie garde est le **feu orange** : le « oui » de Hiba, le responsable sécurité, la main
sur l'arrêt physique. Il refuse aussi si l'écran tourne déjà (une seule liaison avec le robot). Le résultat est gardé
dans `robots/NOM/conformite.yaml`, avec l'empreinte de `carte.yaml`, `liaison.py`, `adaptateur.py` : changer un de
ces fichiers = refaire le test complet avant que le système accepte le vrai robot.

## Brancher un vrai robot, en bref
1. Créer le dossier (assistant). 2. Lire la fiche du robot. 3. Brancher d'abord `ouvrir`, `lire_etat`,
`signe_de_vie`, `arreter_mouvement`, `arret_urgence`, `rearmer`, `fermer` ; `branchees = {"arreter", "etat"}`.
4. Test sans mouvement (feu orange). 5. Brancher une action, l'ajouter à `branchees` ET à la carte. 6. Test complet
(feu orange). Recommencer à l'étape 5.

## Ne pas faire
- Appeler un adaptateur ailleurs que dans la prise ; fabriquer un adaptateur ailleurs que dans `commun/systeme.py`
  (ou le test de conformité).
- Écrire un chiffre, un nom de fonction ou une compatibilité qui n'est pas dans la doc : « à vérifier ».
- Mettre dans la carte un saut, un salto, une course, ou `continous_move=True` (Unitree G1).
- Installer un kit de robot ou ROS 2 sans le « oui » de Hiba (feu orange).
