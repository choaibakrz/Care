# Brique 13 — Notes pour le coordinateur (étape 4 : l'écran du jury)

Tout est **testé sur faux robot**, sur Linux (Python 3.13, Chromium 153 sans écran). Jamais sur un Mac, jamais sur un vrai robot.
Suite complète : **143 réussis, 11 sautés** (avant : 129 réussis, 11 sautés). Aucun nouveau paquet installé.

## Ce qui est fait
- `/jury` : sous-titres (langue parlée + 2e langue au choix), six encadrés (entendu, compris, va faire, refuse parce que,
  question, aide), fiche de vérité en grand, mention « testé sur faux / vrai robot » toujours visible, pictogrammes SVG
  intégrés, clair et sombre, sans défilement (1920×1080 et 1280×720 vérifiés), téléphone accepté (390 px, sans défilement de côté).
- 2e langue : les réponses du robot sont redites exactement (`Chaine.redire`, à partir de `cle` + `valeurs` dans `reponse_dite`).
  Ce que dit la personne : « traduction indisponible hors ligne » ; endroit prévu pour Apertus : `traduction.py`
  (`app.state.jury.traducteur`).
- « Internet coupé » (`internet.py`) : remplace `socket.connect`, `connect_ex`, `sendto` et `socket.getaddrinfo` ;
  cet ordinateur et le réseau local restent permis ; les mandataires (« proxy ») déclarés sont refusés aussi ; l'étage
  « Apertus par Internet » de la cascade est mis de côté puis rendu. Événement `internet_coupe`. Protégé par le code.
- Mode silence : la voix de la conversation devient `VoixTexte` (sous-titres seulement) et le haut-parleur se tait ;
  pictogrammes en grand. Événement `mode_silence`. Protégé par le code. Suit `interrupteurs.mode_silence.actif`.
- Motion design : `FLUX_POUR_MOTION_DESIGN.md` (un exemple par type, 22 vrais sur faux robot, 6 écrits à la main et marqués),
  `/api/flux_simple` et `/ws_simple` (filtres `types`, `sans`, `historique`, `max`, `direct`, `complet`).
- Tests : `tests/test_jury.py` (13, TestClient) et `tests/test_navigateur_jury.py` (Chromium par Playwright pour Node,
  saute proprement s'il manque). Capture : `capture_jury.png` (1600×900, deviceScaleFactor 2).

## Changements dans les fichiers partagés (à fusionner avec soin)
- `commun/chaine.py` : `repondre(..., cle=None, valeurs=None, **extra)` ajoute `cle` et `valeurs` à `reponse_dite`
  (rien d'autre ne change). Nouveaux : `redire()`, `_valeur()`, `_annonce_cle()`, `_nommer_cle()`. Chaque appel de
  `repondre` reçoit sa clé. `_annonce()` passe maintenant par `redire()` (même texte : un test compare, pour toutes
  les réponses de 23 phrases en 6 langues, le texte dit et le texte redit). **Fusion avec la brique 8** : si une
  nouvelle branche (verdict « humain ») appelle `repondre`, lui donner aussi `cle=` (sinon l'écran affichera
  « traduction indisponible hors ligne » pour cette phrase en 2e langue).
- `commun/evenements.py` : deux types **à la fin** de `TYPES` : `internet_coupe`, `mode_silence`. Si l'autre branche
  ajoute aussi des types à la fin : garder les deux ajouts.
- `briques/b13_ecran/serveur.py` : une ligne dans le texte d'en-tête, et 3 lignes juste après `app.mount("/static", …)`
  (import + `brancher_jury(app, systeme, protege, abonnes, conversation)`). Aucune route existante changée.
  Toutes les routes du jury sont dans `jury.py` : l'API « demander à un humain » peut s'ajouter ailleurs dans `serveur.py`.
- `briques/b04_oreilles_voix/conversation.py` : 1 ligne (`cle="je_vous_ecoute"`).
- `static/index.html` + `static/ecran.css` : un lien « écran du jury » (1 ligne chacun).

## À signaler (honnêteté)
- **conftest.py** laisse passer les connexions vers 127.0.0.1. Dans l'environnement de test en ligne, un mandataire
  (« proxy ») est déclaré sur 127.0.0.1 (`HTTPS_PROXY`) : une requête `httpx` (qui lit cette variable) pourrait donc
  sortir vers Internet pendant les tests, malgré « Internet coupé pour TOUS les tests ». **Non essayé** (pour ne rien
  envoyer dehors) : à vérifier par le rôle « Tests ». Le bouton de l'écran, lui, refuse ces mandataires (testé).
- Aucun texte lu dans le dépôt n'a demandé quoi que ce soit : rien à signaler à Hiba de ce côté.
- `reglages.exemple.yaml → interrupteurs.bouton_internet_coupe` dit encore `etat: a_faire` (je n'ai pas changé les
  réglages) : à passer à `socle` si Hiba est d'accord. Le bouton s'affiche quel que soit cet interrupteur.

## Ce qui reste
Voir `TACHES.md` : traduction de la personne (Apertus, décision de Hiba), essai sur le vrai grand écran / Safari / iPad,
champs de `aide_demandee` à vérifier avec la brique 8, relecture des étiquettes traduites (de, it, en, zh), exemples
réels de `mot_d_appel` et `interruption` avec le micro.

## Lignes proposées (je n'ai pas modifié ces fichiers)

**LICENCES.md**
- Brique 13 : aucun nouveau paquet. Pictogrammes SVG dessinés pour le projet (aucun copié). Polices du système seulement.
- Test du navigateur et capture : Playwright pour Node 1.63.0 (Apache-2.0, Microsoft) et Chromium (licence de type BSD,
  projet Chromium), **déjà installés** sur l'ordinateur de test, utilisés tels quels ; le projet ne les installe pas et
  ne les distribue pas. Le test saute s'ils manquent.

**DECISIONS.md** (à relire par Hiba)
- Écran du jury : page séparée `/jury`, mêmes événements que l'écran de l'équipe (`/ws_simple?complet=1`), mise en page
  fixe sans défilement, polices du système, clair et sombre.
- 2e langue : les réponses du robot sont redites à partir de `phrases.yaml` (exact, sans modèle). Ce que dit la personne
  n'est pas traduit tant qu'aucun modèle n'est branché : l'écran le dit (« traduction indisponible hors ligne »).
- « Internet coupé » coupe les sorties du programme (connexions, recherches de noms, mandataires), garde le réseau local,
  met de côté l'étage Apertus par Internet. Une seule coupure à la fois pour tout le programme.
- Mode silence = la voix `VoixTexte` (déjà dans la brique 4) à la place de la voix normale, le temps du mode.
- Étiquettes de la page traduites (de, it, en, zh) par l'agent : à relire par l'équipe.

**NON_TESTE.md**
- `/jury` : jamais ouvert sur le grand écran / projecteur du carnaval, ni sur Safari, ni sur iPad, ni sur un Mac.
  Testé avec Chromium sans écran sur Linux (1920×1080, 1280×720, 390×844). « Lisible de loin » : non mesuré.
- « Internet coupé » : testé sur Linux seulement. Ne coupe que ce programme Python (pas le navigateur, pas les autres
  programmes du Mac ; une connexion ouverte avant le clic reste ouverte, sauf celle du cerveau par Internet).
  Non couvert si `uvloop` est installé un jour (la page le signale). Adresses IPv6 publiques du réseau local : refusées.
- Mode silence avec un vrai haut-parleur : jamais essayé (haut-parleur factice).
- Exemples du flux `aide_demandee`, `etat_robot`, `regle_changee`, `pilotage_humain`, `mot_d_appel`, `interruption` :
  écrits à la main (aucune brique ne les émet encore, ou seulement avec un vrai micro).
