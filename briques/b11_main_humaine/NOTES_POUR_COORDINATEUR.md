# Brique 11 — Notes pour le coordinateur (la main humaine)

Tout est **testé sur faux robot**, sur Linux (Python 3.13, Chromium sans écran). Jamais sur un vrai robot, jamais sur
une vraie tablette, ni Safari, ni iPad, ni Mac. Aucun paquet installé, rien téléchargé, rien publié.
Branche `brique-11` (partie de `9c0ef26`). Suite complète : **623 réussis, 11 sautés** (avant : 607 réussis, 11 sautés ;
les 16 nouveaux sont ceux de la brique 11, dont celui de Chromium). Refaire `python3 lancer.py tests` après la fusion.

## Corrections après la relecture sécurité (branche `corrections-b11`, partie de `fe3565a`)
Suite complète : **717 réussis, 12 sautés** (7 tests neufs dans `tests/test_main_humaine.py`). Testé sur faux robot.
- **2 (moyen)** — Prendre la main envoie **toujours** « arreter » (chaîne → gardien → ticket → prise), plus seulement si
  `action_longue_en_cours()`. Course de la relecture (panne « lenteur », clic pendant que la prise attend le robot) :
  le déplacement de la voix finit « annulée » (ou la prise refuse `ticket_avant_stop`). Scripts du relecteur relancés :
  `course_prendre.py`, `prendre_nominal.py` → l'action de la voix est annulée, plus rien en cours.
- **3 (moyen)** — À chaque changement de main, `Chaine.changer_de_main` vide ses demandes en attente et demande au
  gardien d'oublier celles de **l'autre camp** (`humain:…` contre voix/agents) ; `reponse_humaine` refuse une demande
  faite pour une autre main (numéro de main dans le contexte, revérifié après le gardien). `demande_pendant_main.py` :
  la demande de l'agent disparaît du panneau, l'accepter ne fait rien partir.
- **7 (petit)** — Numéro de main (`_main`) : lu au départ (après la porte dans `traiter`, au début de `ordre_humain`),
  comparé dans `_agir` après le gardien. Test : la main prise puis rendue PENDANT la vérification → rien ne part.
  Si l'ordre oublié avait créé une demande à un humain, elle est oubliée chez le gardien aussi.
- **8 (petit)** — Jeton (`secrets.token_urlsafe`) remis par `prendre` à la tablette, exigé pour `ordre` et `rendre`
  (comparaison `hmac.compare_digest`) ; jamais dans l'état lu par tous ni dans la boîte noire. Une autre tablette (avec
  le code d'équipe) n'a que **« Libérer la main »** (`forcer`, deux clics, événement `rendu` avec `force: true`) : sinon
  une tablette éteinte bloquerait la voix jusqu'au redémarrage. Réponse 409 (pas 403 : la page redemande le code sur 403).
- **9 (petit)** — Fiche : l'arrêt de la reprise (conversation de l'événement `reprise`, `arret_envoye`) ne compte pas
  comme réussite ; nouveau `part_humain_simulee_pct` (opérateur automatique du chef : `simulee: true` dans ses
  événements ; un vieux journal sans ce drapeau est reconnu par l'opérateur « simulé »). Jury : tuile « Réussites » →
  « dont N par l'humain » ; « part de l'humain » → « + X % simulée (répétition) ». Écran de l'équipe et compte rendu
  du chef aussi.
- **10** — Tests : `test_prendre_la_main_arrete_l_action_en_cours` (cas normal) et
  `test_la_course_du_clic_pendant_qu_une_action_de_la_voix_demarre` (panne « lenteur ») ; plus un test par point.
- **12 (petit)** — `OperateurEcran(main, attente_s, attente_rendu_s)` : rendu attendu au plus 5 min (choix, pas une
  mesure), puis `demande_retiree` et plan B suivant ; **l'humain garde la main** (jamais retirée). Une deuxième demande
  du chef pendant la première : refusée (`False`, une `note`).

Fichiers partagés touchés par ces corrections : `commun/chaine.py` (`_main`, `changer_de_main` rend un nombre et
oublie les demandes, `ordre_humain` sans la main → note, `_agir(main_base=…)`, contexte `main` dans
`_attendre_un_humain` / `reponse_humaine`), `briques/b07_gardien/gardien.py` (`oublier_demandes(lesquelles=None)` :
sans argument, inchangé), `briques/b12_boite_noire/fiche.py` (arrêt de reprise, part simulée). Autres :
`briques/b15_chef_demo/chef.py` (`simulee`, `attente_rendu_s`), `compte_rendu.py` (part simulée),
`tests/test_chef_demo.py` (une ligne : la main de l'opérateur automatique est maintenant « simulée », plus « humaine »),
`briques/b13_ecran/static/jury.html`, `jury.js`, `ecran.js`. **À relire par le relecteur sécurité** : chaîne et gardien.
Non touchés : `briques/b01_prise/`, `briques/b05_yeux/`, `perception.py`, `lancer.py`, `serveur.py`, `evenements.py`.

## Ce qui est fait
- Écran de l'équipe : encadré **« La main humaine »** (prénom, « Je prends la main » / « Je rends la main », ordres par
  boutons construits depuis la carte d'identité, réponse du gardien à l'écran) et encadré **« Demandes à un humain »**
  (liste du gardien avec action, raisons, demandeur, temps restant ; Accepter / Refuser ; apprendre un mot ; vote du
  public si l'interrupteur est allumé). Fichiers servis par la brique 11 (`/main_humaine/…`), chargés par `index.html`.
- Pendant la main humaine : la chaîne répond poliment aux phrases (voix, tablette, agents, chef) — clé
  `humain_pilote`, 5 langues — et rien ne part ; **« stop » passe avant** (bloc existant, inchangé) ; ARRÊT ouvert.
- Ordres de l'humain : `Chaine.ordre_humain` = formulaire → `_agir` (gardien, ticket, prise) avec la source
  `humain:qui`. Le gardien voit `demandeur = humain:qui` (aucune règle du gardien changée). Pas de « vous confirmez ? ».
- Prendre la main arrête une action longue en cours (« arreter », par la même chaîne). Rendre la main ne change rien
  d'autre que rouvrir la porte aux phrases.
- Écran du jury : bandeau jaune « UN HUMAIN PILOTE » + qui + depuis ; « MAIN HUMAINE SIMULÉE » pour l'opérateur
  automatique du chef ; un ordre de l'humain s'affiche « Ordre de l'humain qui pilote (…) » ; fiche : ordres de l'humain.
- Fiche de vérité : la part de l'humain était déjà comptée (reprise → rendu) — **vérifié** par un test (en direct, par
  `calculer`, et depuis le fichier de la boîte noire). Ajouté : `ordres_humains`, `reussites_pilotees`.
- Chef de démonstration : `OperateurEcran(app.state.main_humaine)` ; la consigne s'affiche ; « Fait » / « Pas pu » ;
  sans réponse en 2 minutes : `demande_retiree`, plan B suivant. **Pas branché à `lancer.py scenario`** (cette commande
  n'a pas d'écran) : noté dans TACHES.md (brique 11 et brique 15).
- Porte des agents : statut `humain_pilote` (avec une explication pour l'agent) quand un humain a la main.
- Tests : `briques/b11_main_humaine/tests/` (15 + 1 dans Chromium, qui saute si Node/Playwright/Chromium manquent).

## Fichiers partagés modifiés (exactement)
- `commun/chaine.py` : constante `SOURCE_HUMAIN` ; attribut `pilote_humain` dans `__init__` ; dans `traiter`, un bloc de
  7 lignes **juste après le bloc « stop »** (réponse `humain_pilote`, retour) ; dans `_agir`, `demandeur` accepte aussi
  `humain:…`, et un contrôle de 6 lignes **après** celui du « stop » (la main a changé pendant la vérification du gardien :
  l'ordre est oublié, sauf « arreter ») ; deux méthodes neuves `changer_de_main(qui)` et `ordre_humain(...)`, placées après
  `oublier_la_decision_en_cours`. Une seule ligne existante modifiée (`demandeur = …` dans `_agir`), aucune supprimée.
  **À relire par le relecteur sécurité.**
- `commun/phrases.yaml` : une clé `humain_pilote` par langue (fr, de, it, en, zh), juste après `main_levee`.
- `briques/b12_boite_noire/fiche.py` : deux champs à la fin du bloc brique 14 (`ordres_humains`, `reussites_pilotees`),
  un dictionnaire `_conv_pilotees` (1000 au plus), 2 lignes dans `action_terminee`, une branche `quoi == "ordre"`.
- `briques/b13_ecran/serveur.py` : une ligne dans l'en-tête, 2 lignes après `ajouter_routes_confiance(...)`.
- **Non modifiés** : `commun/evenements.py` (le type `pilotage_humain` existait), `lancer.py`, `briques/b01_prise/`,
  `briques/b07_gardien/`.

## Autres fichiers d'autres briques (petits changements)
- Brique 13 : `static/index.html` (2 lignes), `static/ecran.js` (journal + 1 ligne de fiche), `static/ecran.css`
  (`form` : `flex-wrap: wrap` — **sans cela, l'écran de l'équipe débordait déjà sur un téléphone** : 517 px pour 390 ; le
  test existant ne le voyait pas, car la page se dézoome), `static/jury.html` (bandeau + détail de la tuile « part de
  l'humain »), `static/jury.css` (2 lignes), `static/jury.js` (étiquette, `surPilotage`, `montrerPilote`, fiche, état lu
  toutes les 2 s), `flux_simple.py` (texte court de `pilotage_humain`), `exemples_flux.py` + `FLUX_POUR_MOTION_DESIGN.md`
  (exemple de `pilotage_humain`, écrit à la main comme les autres exemples des briques 7, 8, 15), `GUIDE.md` (2 lignes).
- Brique 14 : `porte.py` (statut `humain_pilote` + son explication).
- Brique 15 : `chef.py` (classe `OperateurEcran` ; `_main_humaine` ne note pas reprise/rendu si l'opérateur le fait),
  `GUIDE.md`, `TACHES.md`.
- Brique 17 : `connaissances.yaml` (3 phrases : « Rien n'existe encore (brique 11) » n'était plus vrai).
- `briques/etat_des_briques.yaml` : entrée 11 (`socle`, faux robot : oui, vrai robot : jamais).

## À vérifier (honnêteté)
- Phrase `humain_pilote` en de, it, en, zh et étiquette « pilote » du jury : traduites par l'agent, **à relire**.
- Prendre la main **arrête toujours** le robot : choix prudent (relecture), **à confirmer par Hiba**.
- La course du clic est corrigée sur le faux robot (le robot simulé arrête tout, la prise refuse un ticket d'avant
  l'arrêt). Sur un vrai robot, cela suppose que son « arreter » arrête AUSSI une action qu'il est en train de
  démarrer : **à vérifier dans chaque kit** (test de conformité).
- « Libérer la main » : n'importe quelle tablette qui a le code d'équipe peut le faire (noté). Choix pour ne jamais
  bloquer la voix ; **à confirmer par Hiba**.
- `qui` n'est toujours pas vérifié (texte libre) : le jeton dit QUELLE tablette pilote, pas QUI la tient. Lire l'état
  (`GET /api/main_humaine`) est ouvert sans code, comme `/api/aides` : il montre le prénom de la personne qui pilote.
- Aucun texte lu dans le dépôt n'a demandé quoi que ce soit : rien à signaler à Hiba de ce côté.

## Lignes proposées (je n'ai pas modifié ces fichiers)

**LICENCES.md**
- Brique 11 : aucun nouveau paquet, aucun code repris. Test du navigateur : Playwright pour Node et Chromium **déjà
  installés** sur l'ordinateur de test (comme pour la brique 13), utilisés tels quels ; le test saute s'ils manquent.

**DECISIONS.md** (à relire par Hiba)
- Main humaine : un seul humain à la fois ; pendant ce temps, toutes les phrases (voix, tablette, agents, chef) reçoivent
  « un humain pilote » et ne vont ni au cerveau ni au gardien ; « stop » et ARRÊT passent toujours.
- Les ordres de l'humain sont des boutons (actions de la carte), jamais du texte libre ; chacun passe par le gardien
  (source `humain:qui`) ; pas de « vous confirmez ? » pour un bouton.
- Prendre la main arrête ce que le robot faisait seul (arrêt normal, par le gardien). Rendre la main ne l'arrête pas.
- La fiche compte à part les ordres de l'humain et leurs réussites (`ordres_humains`, `reussites_pilotees`) ; les
  réussites pilotées restent aussi dans « réussites ».
- Une main humaine simulée (répétition du chef) est affichée au jury comme « MAIN HUMAINE SIMULÉE ».

**NON_TESTE.md**
- Main humaine : jamais sur une vraie tablette, ni Safari, ni iPad, ni Mac ; testé dans Chromium sans écran (Linux,
  1280×900 et 390×844). Jamais avec un vrai robot. Jamais avec la vraie voix (phrases données à la chaîne).
- `OperateurEcran` du chef : testé seulement dans un test (chef et écran dans le même programme) ; pas de commande.
- Visite à distance (idée 13) : rien par Internet ; Wi-Fi local seulement.

**À ajouter après les corrections (lot D, relecture sécurité)**
- DECISIONS.md, à la ligne « Main humaine » : « Prendre la main envoie **toujours** un arrêt normal (par le gardien),
  qui ne compte pas comme réussite du robot. À chaque changement de main, les demandes à un humain de l'autre camp
  sont oubliées. Un jeton remis à la tablette qui a pris la main est exigé pour les ordres et le rendu ; une autre
  tablette peut seulement « Libérer la main » (noté). La main simulée du chef est comptée à part dans la fiche. Le chef
  attend au plus 5 minutes le rendu, puis passe à la suite (l'humain garde la main). »
- NON_TESTE.md, ligne 49 (« Main humaine : opérateur simulé ; la brique 11 n'existe pas encore ») n'est plus vraie :
  « Main humaine : opérateur simulé (répétition, compté à part) ou écran (brique 11, seulement dans un test). »
- NON_TESTE.md, section brique 11 : « Arrêt envoyé en prenant la main : sur un vrai robot, qu'il arrête aussi une action
  en train de démarrer est à vérifier dans chaque kit. Jeton gardé dans le navigateur de la tablette (localStorage) :
  jamais essayé sur Safari / iPad. »

## Pour Hiba (interrupteur)
`reglages.exemple.yaml → interrupteurs → visite_a_distance` dit `etat: a_faire` (brique 11). Je ne l'ai pas changé
(feu orange : un réglage). Le pilotage local est fait ; la visite à distance, non : il peut rester `a_faire`.
