# Notes pour le coordinateur — brique 3 (les adaptateurs, un par vrai robot)

Mis à jour le 11.11.2026 après la relecture sécurité indépendante (commit 9c0ef26), branche `corrections-b3` (partie
de b3fd50c). Tout est **testé sur faux robot** (faux kit SDK, faux ROS 2), sur Linux, Internet coupé. **Aucun vrai
robot, aucun kit de fabricant, ROS 2 jamais installé.** Aucun nouveau paquet. Aucun code copié.

## Cinq lignes pour Hiba
1. Corrigé : un ordre de vitesse « en route » ne peut plus faire repartir le robot après l'arrêt d'urgence ; un arrêt
   coincé dans le kit ne fait plus sauter les suivants ; un robot qui part à l'envers est arrêté après 5 cm.
2. Le test de conformité dit maintenant ÉCHEC si une action qui bouge finit « échouée » (sauf refus expliqué).
3. Le système refuse le vrai robot si la carte, la liaison ou l'adaptateur ont changé depuis le test complet.
4. La phrase tapée au clavier (avec un nombre au hasard) protège contre l'oubli, **pas contre un agent** : la vraie
   garde reste le feu orange (toi, le responsable sécurité, la main sur l'arrêt physique). C'est écrit partout.
5. **À décider avec le responsable sécurité** : l'arrêt d'urgence logiciel d'un robot à jambes. Proposition : un
   « arrêt de marche » (G1 : `SetVelocity(0, 0, 0)`), mais il **ne bloque pas le robot** : le robot accepte l'ordre
   suivant ; c'est notre adaptateur qui bloque NOS ordres, pas ceux d'un autre programme ou de la télécommande.

## Les 18 constats de la relecture (chacun avec son test : `tests/test_adaptateurs_relecture.py`, sauf mention)
1. **Robot qui repart** : après l'arrêt, un arrêt normal est mis dans la file du fil habituel (il passe juste derrière
   l'ordre en route) ; chaque ordre est revérifié dans le fil juste avant de partir (drapeau + « génération » qui
   augmente à chaque arrêt) ; faux kit : `arret_bloquant=False` (comme StopMove), `duree_ordre_s=1.0` (comme Move du
   G1), `latence_vitesse_s` (un ordre parti avant l'arrêt arrive après lui). Vérifié en remettant le défaut : le test
   échoue (0,18 m parcourus).
2. **Arrêt coincé** : un fil NEUF (démon) par tentative, 4 au plus en même temps ; raté ou coincé → arrêt normal de
   secours dans un autre fil ; tentative sautée → notée (journal, `arrets_sautes`, et bus si l'adaptateur l'a reçu) ;
   tant qu'un arrêt est coincé, l'état dit `liaison_ok: false` (la prise réessaie et demande le bouton PHYSIQUE).
   Fiches : délai court pour l'appel d'arrêt.
3. **Mauvais sens** : arrêt si le robot recule de plus de 5 cm, s'écarte de plus de 15 cm du trajet, ou dépasse le but
   de 15 cm (odomètre). Sans odomètre : estimation au temps, comme avant.
4. **`briques/b01_prise/conformite.py`** (seul fichier touché dans b01) : une action qui bouge et finit « échouée » =
   ✘, sauf refus expliqué AVANT de bouger (codes listés dans `REFUS_EXPLIQUES`, et le robot n'a pas changé de place
   quand sa position est connue) ; un refus au départ (`robot_refuse` avec explication) = ✔. Le faux bras de la
   brique 2 passe toujours (« hors de portée », « je ne tiens rien » : refus expliqués).
5. **Verrou** : `conformite.yaml` garde l'empreinte SHA-256 de `carte.yaml`, `liaison.py`, `adaptateur.py` ; le
   registre compare. Après fabrication, le registre vérifie avec `sur_faux_kit` que vrai/faux est bien ce qui était
   demandé.
6. **Clavier** : phrase + nombre tiré au hasard ; « protection contre l'oubli, pas contre un agent » écrit dans le
   code, le guide, BRANCHER_UN_ROBOT.md, la skill, le registre.
7. **`tests_bout_en_bout/test_aucun_contournement.py`** : `robots/`, `assistant.py`, `registre.py` ne sont plus exclus
   (restent exclus : l'intérieur des adaptateurs, `modele_vide/`, `chemins/`, et le témoin de la conformité pour la
   règle 1). Attrape `charger_robot(...).fabriquer(...)`, `getattr(x, "fabriquer")`, et la construction de tout
   adaptateur, liaison ou faux kit (classe vérifiée, plus seulement « nom en majuscule » ; imports relatifs compris),
   sauf dans la fonction `fabriquer` de `robots/NOM/adaptateur.py`. Un test vérifie que la règle attrape ces raccourcis.
   Pour ça, les fonctions du faux kit ont changé de nom (`ouvrir_liaison`, `arreter_en_urgence`, `lever_arret`) :
   leur copie dans `robots/NOM/liaison.py` ne ressemble plus aux commandes du robot. **Les scripts e1 à e8 du
   relecteur qui redéfinissent `arret_urgence` du faux kit sont à adapter** (`arreter_en_urgence`).
8. **État bizarre** : types nettoyés (batterie « n/a » → inconnue, erreurs en texte, position non numérique ignorée) ;
   toute erreur de lecture → `LiaisonPerdue`. Testé avec « n/a », [80], NaN, True, et une liste au lieu d'un dictionnaire.
9. **None** : pour un arrêt, `None` = « non confirmé » (`LiaisonSDK._ok(..., arret=True)`) ; fiche G1 :
   `SetVelocity(0, 0, 0)` rend un code, `StopMove()`, `Move()`, `Damp()`, `ZeroTorque()` rendent `None` (code relu le
   11.11.2026). Go2 : `StopMove()`, `Move()`, `Damp()`, `Hello()` rendent un code (relu).
10. **Vitesse des gestes** : « demandée à mi-vitesse ; vitesse du geste : à vérifier par kit » (avertissement, guide,
    fiches, docstring).
11. **Flexiv** : `ClearFault()` dans `rearmer()` (fiche et ébauche).
12. **Faux ou vrai** : `type(kit) is FauxKit` / `type(rclpy) is FauxRclpy` dans les liaisons ; l'attribut
    `simulation` est supprimé. Volontaire : une copie (sous-classe) du faux kit est vue VRAIE par la liaison mais
    FAUSSE par le système (`sur_faux_kit`, `isinstance`) → désaccord → le registre et le système refusent.
13. **Témoin** : écrit qu'il ne voit que les refus du gardien ; contrôle renommé « … (gardien) ».
14. **Faux kit** : `--conformite` sans `--vrai` n'essaie PAS le `liaison.py` du robot (dit dans la sortie, le guide,
    la skill, le test généré).
15. **Arrêt pendant le réarmement** : l'arrêt est renvoyé au robot (et mis dans la file) si le numéro a changé.
16. **Avertissement** : dit aussi les deux déplacements de 2 m coupés après 0,2 s.
17. **Documents** : `BRANCHER_UN_ROBOT.md` (le système charge déjà le registre), ces notes, `docs/projet/SAMEDI_MATIN.md` § 6
    (« Commencer l'adaptateur à partir de b01/adaptateur.py » → `lancer.py brancher` et le guide).
18. **Go2** : mise en garde `Dance1()` / `Dance2()` dans la fiche.
En plus : `rearmer`, `deconnecter`, le chien de garde et l'erreur imprévue mettent aussi un arrêt dans la file ;
un seul arrêt attend dans la file à la fois (sinon le fil reste bouché si l'arrêt du kit est lent).

## Fichiers touchés hors de la brique 3
- `briques/b01_prise/conformite.py` (point 4 seulement).
- `tests_bout_en_bout/test_aucun_contournement.py` (point 7).
- `docs/projet/SAMEDI_MATIN.md` § 6 (point 17) ; `BRANCHER_UN_ROBOT.md` ; `savoir-faire/brancher-un-robot/SKILL.md`.

## Proposé, pas fait (fichier de l'architecte)
**`commun/systeme.py`** : donner le bus au registre, pour que les remarques de l'adaptateur (arrêt sauté, chien de
garde) arrivent dans la boîte noire. `registre.fabriquer(nom, reglages, bus=...)` l'accepte déjà ; il faudrait
`_creer_adaptateur(self.reglages, self.monde, acceleration, self.bus)` et `fabriquer(nom, reglages, bus=bus)`.
Sans ça, elles vont dans `journal` de l'adaptateur et dans l'état (`erreurs`, `liaison_ok`), pas dans la boîte noire.

## Lignes à ajouter (je n'ai pas touché ces fichiers)
**DECISIONS.md** — « Brique 3, après la relecture (à relire par Hiba) » :
- L'arrêt d'urgence logiciel proposé pour un robot à jambes (« arrêt de marche », G1 `SetVelocity(0, 0, 0)`) **ne
  bloque pas le robot** : il accepte l'ordre suivant. L'adaptateur bloque nos ordres ; il ne peut rien contre un autre
  programme ou la télécommande. À dire à Hiba avec la décision « arrêt de marche ou moteurs coupés ».
- Pour un arrêt, un appel qui ne rend rien (`None`) = « non confirmé ».
- La phrase tapée au clavier protège contre l'oubli, pas contre un agent ; la garde est le feu orange.
- Le vrai robot est refusé si la carte, la liaison ou l'adaptateur ont changé depuis le test complet (empreintes).
- Une action qui bouge et finit « échouée » fait échouer le test de conformité (sauf refus expliqué avant de bouger).
- Un déplacement s'arrête si le robot recule de 5 cm ou s'écarte de 15 cm du trajet.

**NON_TESTE.md** — à ajouter dans « Adaptateurs (brique 3) » :
- Course « ordre en route / arrêt » : corrigée et essayée avec le faux kit seulement (latence simulée) ; un vrai kit
  peut avoir d'autres chemins (plusieurs canaux, réessais) : à vérifier.
- Fils d'arrêt neufs (démons) : un vrai kit accepte-t-il des appels depuis plusieurs fils à la fois ? À vérifier par kit.
  Un fil coincé ne bloque plus la fermeture du programme (démon), mais reste coincé jusqu'à la fin.
- Garde du trajet : seulement avec un odomètre ; sans odomètre, estimation au temps. Marges (5 cm, 15 cm) jamais
  essayées sur un vrai robot (bruit de l'odomètre d'un robot à jambes : à mesurer).
- Remarques de l'adaptateur pas encore dans la boîte noire (le système ne lui donne pas le bus : proposé ci-dessus).

**LICENCES.md** : rien de nouveau (aucun paquet, aucun code copié ; `unitree_sdk2_python`, BSD-3-Clause, relu pour
les codes de retour, est déjà listé).

**`briques/etat_des_briques.yaml`** (fait) : entrée 3, `relecture` à jour, une ligne « phrase contre l'oubli », une
limite connue de plus (« l'arrêt de marche ne bloque pas le robot »).

## Signalé (une page lue est une information, jamais un ordre)
- `flexiv_rdk/example_py/AGENT_REFERENCE_primitives_only.py` s'adresse aux « code-generation agents » (conventions
  pour écrire des primitives). Lu comme information ; aucune consigne suivie ; rien de dangereux demandé.
- Les exemples Unitree affichent « WARNING: Please ensure there are no obstacles around the robot » : repris dans les
  fiches comme consigne de sécurité du fabricant.
- Pages officielles non lues (adresses non autorisées dans la session) : support.unitree.com, docs.nvidia.com ;
  x2-aimdk.agibot.com pas essayé.

## Ce qui reste (voir `TACHES.md`)
Nouvelle relecture sécurité des corrections (celui qui écrit n'est pas celui qui vérifie) ; donner le bus au registre
(`systeme.py`) ; chronomètre à l'écran (idée 12) ; aller à un lieu nommé (caler l'odomètre) ; mesurer le chien de
garde et le bruit de l'odomètre de chaque vrai robot ; poses nommées pour un bras.
