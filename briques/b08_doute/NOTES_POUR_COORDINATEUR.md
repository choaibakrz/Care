# Notes pour le coordinateur — briques 7 (gardien) et 8 (« je ne suis pas sûr »)

Étape 4, 11.11.2026. Tout est **testé sur faux robot**, sur Linux, Internet coupé. Aucun nouveau paquet.
Suite complète : 215 réussis, 11 sautés (modèle d'écoute et voix chinoise absents ici). Au départ : 128 réussis,
12 sautés. Le test « vrai petit Apertus » a tourné cette fois, car un serveur Apertus 0,5B (lancé avant moi, pas par
moi) écoute sur le port 8091 de cette machine.

## Cinq lignes pour Hiba
1. Le gardien lit `briques/b07_gardien/regles.yaml` : 10 règles en phrases simples (vitesse, force, 1 m des personnes,
   escalier, cuisine pendant le service, rester dans la halle, valise, poids, tasse fragile, verser).
2. Trois réponses : oui, non (expliqué dans la langue), ou « humain » : le robot lève la main, l'écran montre la demande,
   un humain accepte ou refuse, et le gardien revérifie tout avant d'agir.
3. Les 10 ordres dangereux d'essai sont tous refusés, avec l'explication dans la langue (par la chaîne et en direct).
4. Brique 8 : 20 demandes floues → 20 questions, aucune action ; deux « pas compris » ou deux échecs de suite → main
   levée ; un humain peut apprendre un mot (« frigo » = cuisine), compris tout de suite et au démarrage suivant.
5. À décider : la distance aux personnes (1 m), et « vrai robot sans les yeux = un humain avant chaque mouvement ».

## Ce que j'ai fait
**Brique 7** (`briques/b07_gardien/`)
- `regles.yaml` : une règle = phrase + sorte + valeurs. 9 sortes (`GUIDE.md`). La phrase doit dire le même chiffre et
  les mêmes noms que les valeurs, sinon le gardien refuse de démarrer et dit quoi corriger. `active`, `en_direct`.
- `regles.py` : lecture, vérification, changement en direct (jamais au-dessus de `reglages.yaml → securite` ; la
  phrase prend le nouveau chiffre). `geometrie.py` : segment, cercle, rectangle (ligne droite départ → arrivée).
- `perception.py` : position du robot (état lu par la prise) + personnes. Faux robot : simulées (`monde.yaml →
  personnes`). Vrai robot : `annoncer_personnes()` (brique 5) ; sans nouvelles depuis 2 s → verdict « humain ».
- `gardien.py` : `valider` (limites : la plus stricte entre reglages et règles) puis les règles. Verdict `humain` :
  demande gardée 2 min (copie de l'action), événement `aide_demandee`. `reponse_humaine` : revérifie TOUT ; seules
  les raisons « humain » vues par l'humain sont levées. « arreter » ou arrêt d'urgence effacent les demandes.
  `changer_regle`, `recharger` → événement `regle_changee` (avant, après, qui). `vote.py` : idée 9 (égalité = rien).
- `ordres_dangereux.yaml` : les 10 ordres (6 langues), avec ce qu'il faut préparer et l'explication attendue.
- Chien de garde : celui du faux robot existait (0,6 s sans signe de vie de la prise → arrêt). Vérifié et documenté ;
  nouveau test : le programme principal « figé » (plus de signes de vie, plus de suivi) → le robot s'arrête seul en
  moins d'1 s et ne repart pas. Simulé : la boucle des signes de vie est coupée, le faux robot tourne à part.

**Brique 8** (`briques/b08_doute/`)
- `doute.py` : `Doute` (deux « pas compris » de suite pour la même personne ; deux échecs de suite, dont « le robot
  refuse / ne répond plus » → `aide_demandee` + « Je lève la main : j'ai besoin d'aide. » dans la langue).
  `filet_plusieurs_choix` : deux lieux / objets / gestes nommés pour une action → question, pour TOUS les cerveaux.
- `aides_apprises.py` + `aides_apprises.yaml` (vide au départ, dans le dépôt : seulement des mots, `qui` va dans la
  boîte noire, pas dans le fichier). Mots refusés : stop, mots d'action, oui/non, négations, nom d'autre chose,
  moins de 3 lettres, un seul caractère chinois. Événement `aide_recue`.
- `demandes_floues.yaml` : les 20 demandes. Interrupteur `main_levee` lu par le programme.

## Changements dans les fichiers partagés (petits, expliqués dans le code)
- `commun/chaine.py` : verdict « humain » → `_attendre_un_humain` (main levée, n° de demande gardé) ;
  `reponse_humaine` (suite après l'écran ; pas de 2e « vous confirmez ? » : l'humain vient de dire oui) ; la fin de
  `_agir` déplacée telle quelle dans `_lancer` (pour servir aux deux) ; `Doute` appelé après la décision et après
  chaque fin d'action ; `filet_plusieurs_choix` après le filet « négation » ; « stop » et l'arrêt d'urgence vident les
  demandes à un humain ; options des questions dites dans la langue (`_nommer`). **Intacts** : stop prioritaire,
  confirmation, verrou des chiffres, négation, annulation par stop (tous leurs tests passent).
- `briques/b13_ecran/serveur.py` : **3 lignes** (un import, un appel, une ligne de docstring). Les 7 routes sont dans
  un fichier à part, `briques/b13_ecran/routes_confiance.py`, pour ne pas gêner la personne qui fait l'écran du jury :
  `GET /api/gardien/regles`, `POST /api/gardien/regle`, `/api/gardien/recharger`, `/api/gardien/vote`,
  `GET /api/aides`, `POST /api/aide/repondre`, `/api/aide/apprendre` (POST protégés par le code d'équipe).
  `static/ecran.js` : 3 cas d'événements (main levée, aide reçue, règle changée) + « Aides reçues » dans la fiche.
  Pas de boutons ajoutés à la page : à faire par la personne de l'écran (voir `b07/TACHES.md`, `b08/TACHES.md`).
- `commun/phrases.yaml` : `main_levee` + 14 codes de refus, en fr, de, it, en, zh (gsw → de). `commun/phrases.py` :
  `expliquer_refus(..., intro=)` et noms des lieux / objets dans la langue (`zone_noms`, `objet_noms`).
- `commun/evenements.py` : un type de plus, `aide_recue`. (`aide_demandee`, `regle_changee` existaient.)
- `commun/monde.yaml` / `monde.py` : lieu `escalier` (toujours interdit), objet `caisse` (5 kg, trop lourde), section
  `personnes` (un visiteur simulé, loin des chemins des tests). Le suisse allemand « Stäge » n'est PAS mis : sans
  accent il devient « stage » (la scène, en anglais) — un test vérifie maintenant qu'aucun nom ne veut dire deux choses.
- `briques/b01_prise/raisons.py` : 14 codes + `CODES_HUMAIN`. `validation.py`, `prise.py`, `ticket.py` : **non touchés**.
- `commun/systeme.py` : règles, perception, aides apprises, doute ; les règles notées dans `session_debut`.
- `briques/b12_boite_noire/fiche.py` : compteur `aides_recues`.
- `reglages.exemple.yaml` : sections `gardien` et `doute` (facultatives) ; `main_levee` actif/socle, `vote_public` socle.
- **Deux tests d'autres briques adaptés** (la valise est maintenant refusée par le gardien, avant le robot) :
  `b02 test_trop_lourd_et_hors_de_portee` (vérifie le refus du gardien, puis « hors de portée » avec l'objet de test)
  et `b12 DEMO` (« prends la bouteille » au lieu de « la valise » : même raté « hors de portée »). Même intention.

## À faire par quelqu'un d'autre
- **Relecture sécurité indépendante** (AGENTS.md : obligatoire pour b07). Je n'ai pas pu la faire faire par un autre.
- Sur chaque Mac, `reglages.yaml` (hors dépôt, copié de l'ancien exemple) dit sans doute encore
  `main_levee: actif: false` (**à vérifier**, je ne l'ai pas ouvert) : la main levée « il bute » y serait éteinte
  (le verdict « humain » du gardien, lui, marche toujours). `vote_public` éteint : le vote est refusé (400).
  Les nouvelles sections `gardien` et `doute` sont facultatives : sans elles, les valeurs par défaut s'appliquent.
- Écran du jury : boutons accepter / refuser, apprendre un mot, résultat du vote, grande main levée.
- Brique 5 : appeler `systeme.gardien.perception.annoncer_personnes(...)`.

## Lignes à ajouter (je n'ai pas touché ces fichiers)
**LICENCES.md** : « Étape 4 (briques 7 et 8) : aucun paquet ajouté, aucun code copié. Idées seulement (de mémoire,
pages non relues : à vérifier) : RoboGuard et ASIMOV (règles en langue simple vérifiées hors du modèle), KnowNo
(demander quand plus d'un choix reste possible). »

**DECISIONS.md** (« Prises pendant l'étape 4, à relire par Hiba ») :
- Règles du gardien dans `regles.yaml`, en phrases ; phrase et valeurs doivent dire la même chose, sinon pas de démarrage.
- La plus stricte gagne entre `reglages.yaml → securite` et les règles ; en direct, jamais au-dessus de `securite`.
- Chemin = ligne droite ; un robot dans une zone interdite peut en sortir. Distance aux personnes : 1 m, aussi pour
  prendre, poser et les gestes (à confirmer : tendre un objet à quelqu'un devient impossible).
- Vrai robot sans les yeux, ou position inconnue : verdict « humain » avant chaque mouvement.
- Verdict « humain » : demande valable 2 min ; après l'accord, tout est revérifié ; pas de 2e question à la personne.
- Changement en direct : seulement allumer / éteindre / le chiffre ; dure jusqu'à l'arrêt ; certaines règles
  verrouillées (`en_direct: false` : personnes, escalier, halle, valise, poids). Vote : égalité = rien ne change.
- Main levée : 2 « pas compris » de suite (même personne ; une question entre deux ne remet pas à zéro), 2 échecs de
  suite. Mots appris : dans le dépôt (seulement des mots), lieux et objets seulement.

**NON_TESTE.md** :
- Gardien : position du robot et personnes simulées seulement ; jamais avec de vraies positions ni de vrais yeux.
- Chemin en ligne droite : un vrai robot qui contourne les obstacles peut passer ailleurs (à vérifier par robot).
- Chien de garde « programme figé » : simulé (boucle des signes de vie coupée), le faux robot tourne dans le même
  programme ; sur un vrai robot, le chien de garde est celui du fabricant (à vérifier dans chaque kit).
- Boutons de l'écran pour la main levée et les règles : API testée, pas de page web encore.
- Phrases nouvelles en de, it, zh : écrites par moi, à faire relire.

## Ce qui reste (voir les deux TACHES.md)
Comprendre la réponse à une question (« Où ? » → « à la cuisine ») ; apprendre des gestes et des verbes ; zones avec
horaires ; vrai calcul du doute du modèle (KnowNo) ; idée 5 (demander à la salle) ; porte des agents (étape 5).
