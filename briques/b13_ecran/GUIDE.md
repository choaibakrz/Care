# Brique 13 — L'écran (équipe et jury)

`python3 lancer.py`, puis dans un navigateur :
- `http://localhost:8000` : **l'écran de l'équipe** (vue du faux robot, ARRÊT, pannes d'entraînement, journal ; brique 11 :
  « La main humaine » et « Demandes à un humain », voir `briques/b11_main_humaine/GUIDE.md`).
- `http://localhost:8000/jury` : **l'écran du jury**, pour le grand écran. Depuis le Wi-Fi : `http://<adresse-du-mac>:8000/jury`.

Tout est servi par l'ordinateur-cerveau : aucune police, aucune bibliothèque venue d'Internet. L'écran marche Internet coupé.

## L'écran du jury
- **En haut, les sous-titres** : ce que la personne a dit, et la réponse du robot, dans la langue parlée ET dans une
  deuxième langue (sélecteur « 2e langue », gardé dans ce navigateur).
  - Les réponses du robot sont **redites exactement** dans l'autre langue (phrases de `commun/phrases.yaml`).
  - Ce que dit la personne demanderait un modèle de traduction : aucun n'est branché, l'écran affiche
    « traduction indisponible hors ligne ». L'endroit pour brancher Apertus plus tard : `traduction.py`.
- **Au milieu, six encadrés** : J'ai entendu · J'ai compris · Je vais faire · Je refuse parce que… ·
  Je pose une question · J'ai besoin d'aide. Ceux de la demande en cours sont allumés, les autres pâles.
- **En bas, la fiche de vérité en grand** : demandes, réussites, ratés, refus, questions, aides, part de l'humain,
  temps de réponse. La mention **testé sur faux robot / testé sur vrai robot** est toujours visible (en haut et en bas).
- **Un humain pilote** (brique 11) : bandeau jaune « UN HUMAIN PILOTE » + qui, tant qu'un humain a la main.
- **Pictogrammes** (SVG dans la page) : le grand, à droite des sous-titres, montre la situation du moment
  (aller, prendre, regarder, refus, question, arrêt, aide…).
- **Boutons** : 2e langue · Mode silence · Internet coupé · clair/sombre (◐) · **ARRÊT** (ouvert à tous, toujours).
  En bas : écrire une phrase au robot (en attendant le micro).
- Mode silence, Internet coupé, écrire une phrase et Réarmer demandent le **code d'équipe** depuis le Wi-Fi
  (sur l'ordinateur-cerveau lui-même : pas de code).
- Sur un téléphone : tout est l'un sous l'autre.

## Le bouton « Internet coupé » (idée 8)
Il coupe **vraiment** les sorties vers Internet de ce programme (`internet.py`) : les connexions vers Internet, et
les recherches de nom par `getaddrinfo`, `gethostbyname`, `gethostbyname_ex` et `gethostbyaddr`, sont refusées avant
de partir ; les « proxy » aussi. Pas vu : `getnameinfo`, et ce qui ne passe pas par Python (autre programme,
bibliothèque en C qui fait sa propre recherche). Cet ordinateur et le réseau local restent permis (192.168…, 10…,
172.16 à 31…, 100.64 à 100.127… comme Tailscale, noms en .local, .lan, .home, .home.arpa, .fritz.box, nom sans point) :
l'autre Mac, les tablettes et l'écran continuent. En plus, `reglages.yaml → ecran → internet_coupe → toujours_permis`
(noms ou adresses du robot et de l'autre Mac). ARRÊT et Réarmer marchent pendant la coupure (testé sur faux robot).
Il éteint l'étage « Apertus par Internet » de la cascade s'il existe.
La page affiche en grand « Internet coupé — tout continue », avec la preuve (connexion d'essai refusée, demandes traitées
depuis la coupure). Un second clic rétablit. Tout est noté dans la boîte noire (événement `internet_coupe`).
Limite : seul ce programme est coupé (pas le reste du Mac). Pour tout couper : débrancher aussi la box d'Internet.

## Le mode silence (idée 14)
La voix du robot passe en **sous-titres seulement** (s'il parlait, il se tait), les pictogrammes passent en grand.
Noté dans la boîte noire (`mode_silence`). Allumé dès le départ si `reglages.yaml → interrupteurs.mode_silence.actif: true`.

## Pour le motion design
Voir `FLUX_POUR_MOTION_DESIGN.md` : `ws://<mac>:8000/ws_simple` ou `http://<mac>:8000/api/flux_simple`
(une ligne courte par événement : heure, type, langue, texte, pictogramme), et un exemple de chaque type d'événement.

## Vérifier
- `python3 lancer.py tests` : pages, API, deuxième langue, Internet coupé (vraie connexion refusée, localhost permis),
  flux, mode silence ; et un test dans Chromium (saute proprement s'il n'est pas là ; on n'installe rien).
- `python -m briques.b13_ecran.capture` : refait `capture_jury.png` (faux robot). Testé sur faux robot seulement.
- `python -m briques.b13_ecran.exemples_flux --ecrire` : refait les exemples du flux.

Fichiers : `serveur.py` (routes de base), `jury.py` (routes du jury), `internet.py`, `flux_simple.py`, `traduction.py`,
`static/jury.*`, `capture.py` + `navigateur_jury.js`, `exemples_flux.py`, `tests/`.
