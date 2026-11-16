# Brique 11 — La main humaine (guide d'une page)

**Rôle** : quand le robot ne peut pas (ou ne doit pas) agir seul, un humain **prend la main** depuis l'écran de
l'équipe, donne des ordres simples, puis **la rend**. Le jury le voit. Tout est **testé sur faux robot**.

## Sur l'écran de l'équipe (`http://<cet-ordinateur>:8000`, colonne de droite)
- **« Je prends la main »** (écrire d'abord son prénom ou un rôle : il est noté dans la boîte noire).
  Un seul humain à la fois. Un **arrêt normal part toujours**, par le gardien : ce que le robot faisait seul s'arrête,
  et une action de la voix en train de partir est refusée par la prise (ticket d'avant l'arrêt) ou arrêtée.
  Les **demandes à un humain** faites avant (voix, agents) sont **oubliées** : elles ne partiront pas pendant la main
  humaine. Cette tablette reçoit un **jeton** (gardé dans son navigateur) : seule elle donne des ordres et rend la main.
  Une autre tablette voit seulement **« Libérer la main »** (deux clics, noté `force` dans la boîte noire), pour le cas
  où la tablette du pilote est perdue ou éteinte.
- Pendant la main humaine :
  - la **voix**, la **tablette** (champ texte) et les **agents d'IA** ne commandent plus le robot. Ils reçoivent une
    réponse polie dans leur langue : « Un humain pilote le robot en ce moment : je ne prends pas cet ordre. Dites
    « stop » pour m'arrêter. » Rien ne va au cerveau, ni au gardien, ni au robot ;
  - **« stop » passe toujours**, et le bouton **ARRÊT** reste ouvert à tous (sans code) ;
  - l'humain donne des **ordres par boutons** : les actions de la carte d'identité, avec leurs précisions (lieu,
    objet, cible, geste, dx/dy en mètres, vitesse, force…). Chaque ordre suit le **même chemin** que la voix :
    formulaire (au lieu du cerveau) → **gardien** (ticket) → prise → robot. Un refus est **expliqué** à l'écran
    (ex. « C'est trop : vitesse 2.0 m/s, la limite de sécurité est 0.3 m/s. »). Si le gardien demande un humain
    (la tasse fragile), la demande s'affiche dans « Demandes à un humain ». Pas de « vous confirmez ? » pour un
    bouton (un bouton ne s'entend pas de travers).
- **« Je rends la main »** : tout redevient comme avant (la voix et les agents commandent de nouveau ; un « vous
  confirmez ? » d'avant la main humaine est oublié ; les demandes à un humain faites par le pilote aussi).
  Un numéro de main augmente à chaque changement : un ordre parti avant le changement ne part jamais après.
- Le chef de démonstration demande la main (plan B) : sa **consigne** s'affiche ; on rend la main avec
  **« Fait »** ou **« Pas pu »** (le chef note l'étape rattrapée ou non). Le chef attend au plus 2 minutes qu'on la
  prenne, puis 5 minutes qu'on la rende ; ensuite il passe à la suite (l'humain garde la main : on ne la lui retire
  jamais). Une deuxième demande du chef pendant la première est refusée.

## « Demandes à un humain » (même écran)
La liste des actions qui attendent un humain (verdict « humain » du gardien) : l'action, les raisons, qui l'a
demandée, le **temps restant** (2 minutes). **Accepter** (le gardien **revérifie tout** avant le ticket : un « non »
reste un « non ») ou **Refuser**. En dessous : **apprendre un mot** (« frigo » = cuisine) et le **vote du public**
(seulement si `reglages.yaml → interrupteurs → vote_public → actif: true`). Utilise les routes de la brique 13
(`/api/aide/repondre`, `/api/aide/apprendre`, `/api/gardien/vote`).

**Code d'équipe** : tous les boutons le demandent depuis le Wi-Fi (sur l'ordinateur-cerveau lui-même : pas de code).
Sauf ARRÊT. Lire l'état (`GET /api/main_humaine`) est ouvert, comme `/api/aides`.

## Sur l'écran du jury (`/jury`)
Un bandeau jaune **« UN HUMAIN PILOTE »** + qui + depuis quand ; les ordres de l'humain apparaissent comme
« Ordre de l'humain qui pilote (Hiba) : aller à : table » (pas une phrase, pas de cerveau). Une main humaine
**simulée** par le chef (répétition) s'affiche « MAIN HUMAINE SIMULÉE — personne ne pilote vraiment ».
Fiche de vérité : **part de l'humain** (temps entre reprise et rendu), **ordres de l'humain**, « Réussites : **dont N
par l'humain** ». L'arrêt envoyé en prenant la main n'est pas une réussite du robot. La main **simulée** du chef
(répétition) est comptée **à part** (`part_humain_simulee_pct`), jamais comme un vrai humain.

## Ce qui est noté (boîte noire)
`pilotage_humain`, champ `quoi` : `reprise` (qui ; sa conversation = celle de l'arrêt envoyé ; `demandes_oubliees`),
`ordre` (qui, action ; même conversation que le gardien et le robot), `rendu` (qui, durée, nombre d'ordres, fait,
`force` si « Libérer la main »), `demande` / `demande_retiree` (chef de démonstration). Le jeton n'y est jamais.

## Fichiers
| Fichier | Rôle |
|---|---|
| `main_humaine.py` | qui a la main, les ordres (vers `Chaine.ordre_humain`), la demande du chef |
| `routes.py` | `/api/main_humaine` (lire), `/prendre`, `/rendre`, `/ordre` (protégés) ; sert `static/` |
| `static/main_humaine.js`, `.css` | les deux encadrés de l'écran de l'équipe (chargés par `index.html`) |
| `tests/` | API, voix ignorée sauf stop, gardien, code, fiche, chef ; un test dans Chromium (saute s'il manque) |

Dans la chaîne (`commun/chaine.py`) : `pilote_humain`, numéro de main, `changer_de_main(qui)`, `ordre_humain(...)`.
Dans le gardien : `oublier_demandes(lesquelles)` (les demandes de l'autre camp, au changement de main).
Dans le chef (`briques/b15_chef_demo/chef.py`) : `OperateurEcran(app.state.main_humaine)`.

## Tester
`python3 lancer.py tests briques/b11_main_humaine`. **Non testé** : vraie tablette, Safari/iPad, vrai robot.
