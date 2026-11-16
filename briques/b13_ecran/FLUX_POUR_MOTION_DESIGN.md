# Le flux d'événements, pour le motion design (brique 13)

Tout ce que le robot entend, comprend, décide et fait arrive **en direct**, une ligne par événement.
Tout passe par le **réseau local** (le Wi-Fi de l'équipe) : aucun besoin d'Internet. Quand on appuie sur
« Internet coupé », le flux continue.

`<mac>` = l'adresse de l'ordinateur-cerveau sur le Wi-Fi (par exemple `192.168.1.20` ; sur le Mac :
Réglages Système → Wi-Fi → Détails). Sur l'ordinateur-cerveau lui-même : `localhost`.

**Lecture seule.** Ce flux ne peut rien commander au robot. (Les boutons de l'écran sont protégés par le code d'équipe.)

## Quatre adresses

| Adresse | Ce qui arrive | Pour quoi |
|---|---|---|
| `ws://<mac>:8000/ws_simple` | WebSocket ; un message = **une ligne simple** (heure, type, langue, texte court, pictogramme). À la connexion : les 50 derniers. | le plus simple pour l'animation |
| `http://<mac>:8000/api/flux_simple` | une ligne simple par événement (JSON, une ligne de texte chacune) | depuis un script, `curl` |
| `ws://<mac>:8000/ws` | WebSocket ; un message = **l'événement complet**. À la connexion : les 200 derniers. | tout le détail |
| `http://<mac>:8000/api/flux` | l'événement complet, une ligne JSON chacun, en direct | idem, en HTTP |

Réglages du flux simple (à mettre après `?`, séparés par `&`) :

| Réglage | Exemple | Effet |
|---|---|---|
| `types` | `types=parole_entendue,reponse_dite` | seulement ces types |
| `sans` | `sans=action_progression,note` | tous les types sauf ceux-là |
| `historique` | `historique=100` | d'abord les 100 derniers événements (WebSocket : 50 par défaut) |
| `max` | `max=10` | s'arrête après 10 lignes (`/api/flux_simple`) |
| `direct` | `direct=0` | seulement l'historique, puis s'arrête : une photo du moment (`/api/flux_simple`) |
| `complet` | `complet=1` | (`/ws_simple`) l'événement complet, avec la ligne simple dans `simple` — c'est ce qu'utilise `/jury` |

## La ligne simple

```json
{"numero": 5, "heure": "2026-11-14T10:02:03.120+00:00", "heure_locale": "11:02:03", "type": "reponse_dite", "langue": "fr", "texte": "Je vais à : cuisine.", "picto": "aller", "conversation": "ec24c9ea6f", "robot": "faux-humanoide", "id": "39458832feab"}
```

- `heure` : l'heure exacte, en temps universel (UTC). `heure_locale` : l'heure de l'ordinateur-cerveau, déjà lisible.
- `type` : le genre d'événement (liste plus bas). `langue` : fr, de, gsw (suisse allemand), it, en, zh, ou vide.
- `texte` : un texte court (160 caractères au plus) : la phrase dite, la réponse, ou un résumé.
- `picto` : le nom du pictogramme (vide si aucun). Les dessins sont dans la page `/jury` (SVG intégré) :
  `<symbol id="p-NOM">`. On peut les copier.
- `conversation` : le même numéro relie une phrase à toutes ses suites (compris, gardien, action, réponse).
- `numero` : augmente de 1 à chaque événement (pour l'ordre).

| Picto | Veut dire |
|---|---|
| `aller` | le robot se déplace |
| `prendre` | le robot prend un objet |
| `regarder` | le robot regarde |
| `refus` | le robot refuse (et dit pourquoi) |
| `question` | le robot pose une question |
| `arret` | arrêt (« stop » ou arrêt d'urgence) |
| `aide` | le robot a besoin d'un humain |
| `poser` | le robot pose un objet |
| `montrer` | le robot montre quelque chose |
| `geste` | le robot fait un geste |
| `etat` | le robot dit son état (batterie) |
| `entendu` | le robot a entendu une personne |
| `compris` | le robot a compris |
| `parle` | le robot parle |
| `fait` | c'est fait, réussi |
| `rate` | raté |
| `panne` | panne |
| `internet` | Internet coupé (tout continue) |
| `silence` | mode silence (sous-titres seulement) |

## L'événement complet

```json
{"type": "parole_entendue", "source": "clavier", "donnees": {"texte": "Va à la cuisine", "langue": "fr", "confiance": 1.0, "personne": null}, "id": "a1b2c3d4e5f6", "numero": 2, "heure": "2026-11-14T10:02:03.090+00:00", "t": 6274.01, "robot": "faux-humanoide", "conversation": "ec24c9ea6f"}
```

- `type`, `source` (qui l'envoie : chaine, gardien, prise, oreilles, voix, ecran…), `donnees` (le détail, propre à
  chaque type : voir plus bas), `id`, `numero`, `heure`, `robot`, `conversation`.
- `t` : une horloge interne en secondes, pour mesurer des durées entre deux événements (pas une heure).

## Une demande, du début à la fin

Même `conversation` du début à la fin :

1. `parole_entendue` (la phrase) → `demande_comprise` (ce que le cerveau a compris) → `gardien_decision` (oui / non)
2. si oui : `reponse_dite` (l'annonce : « Je vais à : cuisine. ») → `action_demarree` → `action_progression`…
   → `action_terminee` → `reponse_dite` (« C'est fait. »)
3. si non : `reponse_dite` avec `genre` = `refus` (le robot dit pourquoi)
4. pas clair : `question_posee` puis `reponse_dite` avec `genre` = `question`
5. action à risque (prendre, poser) : `confirmation_demandee` ; le « oui » est une nouvelle `conversation`
   (`demande_comprise` avec `genre` = `confirmation`)

Avec le micro, avant `parole_entendue` : `parole_finie` puis `transcription` ; après chaque réponse : `voix_debut`.
À tout moment : `arret_urgence` (à montrer en grand, passe avant tout).

## Exemples pour brancher

Dans un terminal (`-N` : afficher au fur et à mesure) :

```
curl -N "http://<mac>:8000/api/flux_simple?sans=action_progression"
curl "http://<mac>:8000/api/flux_simple?historique=500&direct=0" > seance.ndjson
```

Dans une page web (JavaScript) :

```
const ws = new WebSocket("ws://<mac>:8000/ws_simple?sans=action_progression");
ws.onmessage = (m) => { const e = JSON.parse(m.data); console.log(e.heure_locale, e.picto, e.texte); };
```

En Python, sans rien installer :

```
import json, urllib.request
with urllib.request.urlopen("http://<mac>:8000/api/flux_simple?types=parole_entendue,reponse_dite") as r:
    for ligne in r:
        e = json.loads(ligne)
        print(e["heure_locale"], e["picto"], e["langue"], e["texte"])
```

Après coup : la boîte noire (`journal/*.jsonl`) garde les mêmes événements complets, une ligne chacun.
La fonction `ligne_simple` de `briques/b13_ecran/flux_simple.py` les transforme en lignes simples.

## Un exemple par type d'événement

Exemples fabriqués par `python -m briques.b13_ecran.exemples_flux --ecrire` : une petite séance sur le **faux robot**
(cerveau à règles, sans Internet). Les types qu'aucune brique n'émet encore sont écrits à la main et marqués comme tels.
La `carte` de `session_debut` est raccourcie.

<!-- EXEMPLES:DEBUT -->

### `session_debut`

Le programme démarre ; on note le robot et les réglages. — *vrai événement, testé sur faux robot.*

Champs utiles : `mention` (testé sur faux / vrai robot), `cerveau`, `vrai_robot`. `carte` : la carte d'identité (raccourcie ici).

```json
{"type": "session_debut", "source": "systeme", "donnees": {"carte": {"…": "la carte d'identité complète (voir /api/carte)"}, "vrai_robot": false, "cerveau": "regles", "machine": "(nom de l'ordinateur)", "mention": "testé sur faux robot", "regles": [{"id": "vitesse_max", "phrase": "Le robot ne va jamais plus vite que 0,3 mètre par seconde.", "active": true, "sorte": "vitesse_max", "en_direct": true, "valeurs": {"m_s": 0.3}}, {"id": "force_max", "phrase": "Le robot ne serre jamais plus fort que 15 newtons.", "active": true, "sorte": "force_max", "en_direct": true, "valeurs": {"n": 15}}, {"id": "distance_personnes", "phrase": "Le robot reste toujours à 1 mètre des personnes, quand il se déplace, prend, pose ou fait un geste.", "active": true, "sorte": "distance_personnes", "en_direct": false, "valeurs": {"m": 1, "actions": ["se_deplacer", "saisir", "poser", "rejouer_geste"], "si_personnes_inconnues": "humain"}}, {"id": "escalier", "phrase": "Le robot ne va jamais dans l'escalier, et ne passe jamais par l'escalier.", "active": true, "sorte": "zone_interdite", "en_direct": false, "valeurs": {"lieu": "escalier", "rectangle": {"x_min": 8.6, "y_min": 0.0, "x_max": 10.0, "y_max": 1.6}}}, {"id": "cuisine_pendant_le_service", "phrase": "Le robot ne va jamais dans la cuisine pendant le service.", "active": false, "sorte": "zone_interdite", "en_direct": true, "valeurs": {"lieu": "cuisine", "rayon_m": 1.0}}, {"id": "rester_dans_la_halle", "phrase": "Le robot reste toujours dans la halle.", "active": true, "sorte": "zone_permise", "en_direct": false, "valeurs": {"rectangle": "halle"}}, {"id": "valise", "phrase": "Le robot ne touche jamais la valise.", "active": true, "sorte": "objets_interdits", "en_direct": false, "valeurs": {"objets": ["valise"]}}, {"id": "poids_max", "phrase": "Le robot ne prend jamais un objet plus lourd que ce que permet sa carte d'identité.", "active": true, "sorte": "poids_max", "en_direct": false, "valeurs": {"kg": "carte"}}, {"id": "objets_fragiles", "phrase": "Pour prendre un objet fragile (la tasse), le robot demande d'abord à un humain.", "active": true, "sorte": "objets_fragiles", "en_direct": false, "valeurs": {"objets": ["tasse"]}}, {"id": "verser", "phrase": "Pour verser à boire, le robot demande d'abord à un humain.", "active": true, "sorte": "demander_humain", "en_direct": false, "valeurs": {"gestes": ["verser"]}}]}, "id": "d064e1914ccc", "numero": 1, "heure": "2026-11-11T19:12:05.558+00:00", "t": 20535.801281815, "robot": "faux-humanoide", "conversation": null}
```

Ligne simple :

```json
{"numero": 1, "heure": "2026-11-11T19:12:05.558+00:00", "heure_locale": "19:12:05", "type": "session_debut", "langue": null, "texte": "début : faux-humanoide — testé sur faux robot", "picto": "", "conversation": null, "robot": "faux-humanoide", "id": "d064e1914ccc"}
```

### `session_fin`

Le programme s'arrête proprement. — *vrai événement, testé sur faux robot.*

Champs utiles : rien de plus : le programme s'arrête.

```json
{"type": "session_fin", "source": "systeme", "donnees": {}, "id": "8fb1006d95d5", "numero": 53, "heure": "2026-11-11T19:12:07.038+00:00", "t": 20537.280518504, "robot": "faux-humanoide", "conversation": null}
```

Ligne simple :

```json
{"numero": 53, "heure": "2026-11-11T19:12:07.038+00:00", "heure_locale": "19:12:07", "type": "session_fin", "langue": null, "texte": "fin de la session", "picto": "", "conversation": null, "robot": "faux-humanoide", "id": "8fb1006d95d5"}
```

### `parole_entendue`

Une personne a dit quelque chose (texte, langue, confiance). — *vrai événement, testé sur faux robot.*

Champs utiles : `texte`, `langue` (fr, de, gsw, it, en, zh ; vide = devinée plus tard), `confiance` de l'écoute.

```json
{"type": "parole_entendue", "source": "clavier", "donnees": {"texte": "Va à la cuisine", "langue": "fr", "confiance": 1.0, "personne": null}, "id": "beb56e38ba9b", "numero": 2, "heure": "2026-11-11T19:12:05.562+00:00", "t": 20535.804563554, "robot": "faux-humanoide", "conversation": "fb3adbf2e8"}
```

Ligne simple :

```json
{"numero": 2, "heure": "2026-11-11T19:12:05.562+00:00", "heure_locale": "19:12:05", "type": "parole_entendue", "langue": "fr", "texte": "Va à la cuisine", "picto": "entendu", "conversation": "fb3adbf2e8", "robot": "faux-humanoide", "id": "beb56e38ba9b"}
```

### `demande_comprise`

Le cerveau a choisi quoi faire (action, question ou discussion). — *vrai événement, testé sur faux robot.*

Champs utiles : `genre` (action, question, inconnu, hors_carte, discussion, confirmation), `action.nom`, `action.parametres`, `confiance`, `langue`, `duree_ms` (temps du cerveau). `source` = le cerveau.

```json
{"type": "demande_comprise", "source": "regles", "donnees": {"genre": "action", "action": {"nom": "se_deplacer", "parametres": {"lieu": "cuisine"}}, "options": [], "confiance": 0.9, "confiance_ecoute": 1.0, "confiance_basse": false, "langue": "fr", "duree_ms": 10.3}, "id": "f75b1c7361e9", "numero": 3, "heure": "2026-11-11T19:12:05.572+00:00", "t": 20535.815147501, "robot": "faux-humanoide", "conversation": "fb3adbf2e8"}
```

Ligne simple :

```json
{"numero": 3, "heure": "2026-11-11T19:12:05.572+00:00", "heure_locale": "19:12:05", "type": "demande_comprise", "langue": "fr", "texte": "compris : action — se_deplacer (lieu=cuisine)", "picto": "aller", "conversation": "fb3adbf2e8", "robot": "faux-humanoide", "id": "f75b1c7361e9"}
```

### `question_posee`

Le robot pose une question au lieu d'agir (brique 8). — *vrai événement, testé sur faux robot.*

Champs utiles : `question` (le texte dit), `options`, `langue`.

```json
{"type": "question_posee", "source": "chaine", "donnees": {"question": "Où dois-je aller ?", "options": [], "langue": "fr"}, "id": "53bfa56f9268", "numero": 19, "heure": "2026-11-11T19:12:06.994+00:00", "t": 20537.236606815, "robot": "faux-humanoide", "conversation": "e389ac440b"}
```

Ligne simple :

```json
{"numero": 19, "heure": "2026-11-11T19:12:06.994+00:00", "heure_locale": "19:12:06", "type": "question_posee", "langue": "fr", "texte": "Où dois-je aller ?", "picto": "question", "conversation": "e389ac440b", "robot": "faux-humanoide", "id": "53bfa56f9268"}
```

### `aide_demandee`

Le robot lève la main : il a besoin d'un humain. — *émis par le gardien (brique 7) et par le doute (brique 8) — forme relevée dans le code, valeurs d'exemple.*

Champs utiles : `raison` (gardien, pas compris, échecs), `texte` ou `action` + `raisons`, `numero` (pour répondre). Le robot lève la main.

```json
{"type": "aide_demandee", "source": "exemple", "donnees": {"raison": "gardien", "numero": "a1b2c3", "action": {"nom": "rejouer_geste", "parametres": {"nom": "verser"}}, "raisons": [{"code": "demander_humain", "details": {"regle": "verser"}}], "demandeur": "chaine"}, "id": "024c0287f4e5", "numero": 80, "heure": "2026-11-11T19:12:07.968+00:00", "t": 20538.211086486, "robot": "faux-humanoide", "conversation": null}
```

Ligne simple :

```json
{"numero": 80, "heure": "2026-11-11T19:12:07.968+00:00", "heure_locale": "19:12:07", "type": "aide_demandee", "langue": null, "texte": "gardien", "picto": "aide", "conversation": null, "robot": "faux-humanoide", "id": "024c0287f4e5"}
```

### `gardien_decision`

Le gardien a dit oui, non ou « demande à un humain ». — *vrai événement, testé sur faux robot.*

Champs utiles : `verdict` (oui, non, humain), `action` (complétée : vitesse, force), `raisons[].code`.

```json
{"type": "gardien_decision", "source": "gardien", "donnees": {"verdict": "oui", "action": {"nom": "se_deplacer", "parametres": {"lieu": "cuisine", "vitesse": 0.3}}, "raisons": [], "demandeur": "cerveau", "numero_demande": null, "non_verifie": []}, "id": "3853863119c2", "numero": 4, "heure": "2026-11-11T19:12:05.574+00:00", "t": 20535.816821232, "robot": "faux-humanoide", "conversation": "fb3adbf2e8"}
```

Ligne simple :

```json
{"numero": 4, "heure": "2026-11-11T19:12:05.574+00:00", "heure_locale": "19:12:05", "type": "gardien_decision", "langue": null, "texte": "gardien : oui", "picto": "aller", "conversation": "fb3adbf2e8", "robot": "faux-humanoide", "id": "3853863119c2"}
```

### `action_demarree`

Une action est partie vers le robot. — *vrai événement, testé sur faux robot.*

Champs utiles : `action.nom`, `action.parametres`, `id_action`, `longue`.

```json
{"type": "action_demarree", "source": "prise", "donnees": {"id_action": "132df5bd", "action": {"nom": "se_deplacer", "parametres": {"lieu": "cuisine", "vitesse": 0.3}}, "longue": true}, "id": "dcda9e82df6b", "numero": 6, "heure": "2026-11-11T19:12:05.593+00:00", "t": 20535.835680467, "robot": "faux-humanoide", "conversation": "fb3adbf2e8"}
```

Ligne simple :

```json
{"numero": 6, "heure": "2026-11-11T19:12:05.593+00:00", "heure_locale": "19:12:05", "type": "action_demarree", "langue": null, "texte": "démarre : se_deplacer (lieu=cuisine, vitesse=0.3)", "picto": "aller", "conversation": "fb3adbf2e8", "robot": "faux-humanoide", "id": "dcda9e82df6b"}
```

### `action_progression`

Une action longue avance (0 à 100 %). — *vrai événement, testé sur faux robot.*

Champs utiles : `progression` de 0 à 1, `id_action`. Beaucoup de lignes : à filtrer si inutile.

```json
{"type": "action_progression", "source": "prise", "donnees": {"id_action": "132df5bd", "progression": 0.0}, "id": "9948ec12d812", "numero": 7, "heure": "2026-11-11T19:12:05.593+00:00", "t": 20535.835935881, "robot": "faux-humanoide", "conversation": "fb3adbf2e8"}
```

Ligne simple :

```json
{"numero": 7, "heure": "2026-11-11T19:12:05.593+00:00", "heure_locale": "19:12:05", "type": "action_progression", "langue": null, "texte": "0 %", "picto": "", "conversation": "fb3adbf2e8", "robot": "faux-humanoide", "id": "9948ec12d812"}
```

### `action_terminee`

Une action est finie : réussie, ratée ou annulée. — *vrai événement, testé sur faux robot.*

Champs utiles : `statut` (reussie, ratee, annulee), `message`, `duree_ms`.

```json
{"type": "action_terminee", "source": "prise", "donnees": {"id_action": "132df5bd", "action": {"nom": "se_deplacer", "parametres": {"lieu": "cuisine", "vitesse": 0.3}}, "statut": "reussie", "message": "fait", "code_erreur": null, "duree_ms": 1371}, "id": "53fcbaaaa59c", "numero": 11, "heure": "2026-11-11T19:12:06.964+00:00", "t": 20537.207366412, "robot": "faux-humanoide", "conversation": "fb3adbf2e8"}
```

Ligne simple :

```json
{"numero": 11, "heure": "2026-11-11T19:12:06.964+00:00", "heure_locale": "19:12:06", "type": "action_terminee", "langue": null, "texte": "reussie : fait", "picto": "fait", "conversation": "fb3adbf2e8", "robot": "faux-humanoide", "id": "53fcbaaaa59c"}
```

### `action_refusee`

La prise a refusé une action (absente de la carte, hors limites, sans ticket). — *vrai événement, testé sur faux robot.*

Champs utiles : `raisons[].code` (ex. robot_occupe), `action`.

```json
{"type": "action_refusee", "source": "prise", "donnees": {"action": {"nom": "se_deplacer", "parametres": {"lieu": "table", "vitesse": 0.3}}, "raisons": [{"code": "robot_occupe", "details": {"en_cours": "se_deplacer"}}]}, "id": "5fff2aa8e0bf", "numero": 43, "heure": "2026-11-11T19:12:07.017+00:00", "t": 20537.260345897, "robot": "faux-humanoide", "conversation": "fdc0f11a23"}
```

Ligne simple :

```json
{"numero": 43, "heure": "2026-11-11T19:12:07.017+00:00", "heure_locale": "19:12:07", "type": "action_refusee", "langue": null, "texte": "la prise refuse (robot_occupe)", "picto": "refus", "conversation": "fdc0f11a23", "robot": "faux-humanoide", "id": "5fff2aa8e0bf"}
```

### `reponse_dite`

Le robot répond à la personne (texte, langue). — *vrai événement, testé sur faux robot.*

Champs utiles : `texte`, `langue` (langue de la réponse), `langue_entendue`, `genre` (annonce, fin, refus, question, inconnu…), `cle` + `valeurs` (phrase connue : l'écran la redit dans une autre langue).

```json
{"type": "reponse_dite", "source": "chaine", "donnees": {"texte": "Je vais à : cuisine.", "langue": "fr", "langue_entendue": "fr", "genre": "annonce", "temps_ms": 30.9, "cle": "annonce.se_deplacer", "valeurs": {"distance": "", "sens": "", "lieu": {"monde": "cuisine"}, "objet": {"monde": null}, "cible": {"monde": null}, "geste": ""}}, "id": "8fdc22df5d60", "numero": 5, "heure": "2026-11-11T19:12:05.593+00:00", "t": 20535.835439974, "robot": "faux-humanoide", "conversation": "fb3adbf2e8"}
```

Ligne simple :

```json
{"numero": 5, "heure": "2026-11-11T19:12:05.593+00:00", "heure_locale": "19:12:05", "type": "reponse_dite", "langue": "fr", "texte": "Je vais à : cuisine.", "picto": "aller", "conversation": "fb3adbf2e8", "robot": "faux-humanoide", "id": "8fdc22df5d60"}
```

### `arret_urgence`

Arrêt d'urgence demandé. Passe avant tout. — *vrai événement, testé sur faux robot.*

Champs utiles : `raison`, `qui`. Passe avant tout : à montrer en grand.

```json
{"type": "arret_urgence", "source": "prise", "donnees": {"raison": "bouton_ecran", "qui": "humain", "erreur": null}, "id": "a6156278f346", "numero": 47, "heure": "2026-11-11T19:12:07.025+00:00", "t": 20537.267561674, "robot": "faux-humanoide", "conversation": null}
```

Ligne simple :

```json
{"numero": 47, "heure": "2026-11-11T19:12:07.025+00:00", "heure_locale": "19:12:07", "type": "arret_urgence", "langue": null, "texte": "ARRÊT D'URGENCE (bouton_ecran)", "picto": "arret", "conversation": null, "robot": "faux-humanoide", "id": "a6156278f346"}
```

### `panne`

Une panne a été provoquée ou constatée. — *vrai événement, testé sur faux robot.*

Champs utiles : `quoi`, `provoquee` (vrai = panne d'entraînement).

```json
{"type": "panne", "source": "ecran", "donnees": {"quoi": "lenteur", "provoquee": true}, "id": "36778e94e94f", "numero": 45, "heure": "2026-11-11T19:12:07.021+00:00", "t": 20537.263448574, "robot": "faux-humanoide", "conversation": null}
```

Ligne simple :

```json
{"numero": 45, "heure": "2026-11-11T19:12:07.021+00:00", "heure_locale": "19:12:07", "type": "panne", "langue": null, "texte": "panne : lenteur (entraînement)", "picto": "panne", "conversation": null, "robot": "faux-humanoide", "id": "36778e94e94f"}
```

### `reparation`

La panne est réparée. — *vrai événement, testé sur faux robot.*

Champs utiles : `quoi` (tout, liaison, rearmement).

```json
{"type": "reparation", "source": "ecran", "donnees": {"quoi": "tout"}, "id": "cde1664deeb2", "numero": 46, "heure": "2026-11-11T19:12:07.023+00:00", "t": 20537.265721939, "robot": "faux-humanoide", "conversation": null}
```

Ligne simple :

```json
{"numero": 46, "heure": "2026-11-11T19:12:07.023+00:00", "heure_locale": "19:12:07", "type": "reparation", "langue": null, "texte": "réparé : tout", "picto": "fait", "conversation": null, "robot": "faux-humanoide", "id": "cde1664deeb2"}
```

### `etat_robot`

Le robot donne son état (batterie, erreurs, position). — *pas encore émis — forme à vérifier.*

Champs utiles : pas encore émis par une brique. Prévoir : `batterie_pct`, `erreurs`, `position`.

```json
{"type": "etat_robot", "source": "exemple", "donnees": {"batterie_pct": 87.0, "erreurs": [], "position": {"x": 1.0, "y": 1.0}}, "id": "0557ff7cc347", "numero": 87, "heure": "2026-11-11T19:12:07.968+00:00", "t": 20538.211252296, "robot": "faux-humanoide", "conversation": null}
```

Ligne simple :

```json
{"numero": 87, "heure": "2026-11-11T19:12:07.968+00:00", "heure_locale": "19:12:07", "type": "etat_robot", "langue": null, "texte": "batterie 87.0 %", "picto": "", "conversation": null, "robot": "faux-humanoide", "id": "0557ff7cc347"}
```

### `pilotage_humain`

Un humain reprend ou rend la main (brique 11). — *émis par la main humaine (brique 11) — forme relevée dans le code, valeurs d'exemple.*

Champs utiles : `quoi` : reprise, ordre, rendu, demande, demande_retiree (brique 11) ; `qui` (prénom ou rôle) ; ordre : `action` (même `conversation` que la suite : gardien, robot) ; rendu : `duree_s`, `ordres`, `fait`. La fiche compte la part de l'humain (reprise → rendu) et `ordres_humains`. Source « main_humaine » = l'écran ; « chef_demo » = main humaine annoncée par le chef (opérateur simulé).

```json
{"type": "pilotage_humain", "source": "exemple", "donnees": {"quoi": "ordre", "qui": "Hiba", "action": {"nom": "se_deplacer", "parametres": {"lieu": "table"}}, "envoye_par": "Hiba"}, "id": "c3136d3334f6", "numero": 89, "heure": "2026-11-11T19:12:07.968+00:00", "t": 20538.211281107, "robot": "faux-humanoide", "conversation": null}
```

Ligne simple :

```json
{"numero": 89, "heure": "2026-11-11T19:12:07.968+00:00", "heure_locale": "19:12:07", "type": "pilotage_humain", "langue": null, "texte": "ordre de l'humain (Hiba) : se_deplacer (lieu=table)", "picto": "aide", "conversation": null, "robot": "faux-humanoide", "id": "c3136d3334f6"}
```

### `regle_changee`

Une règle du gardien a été changée en direct. — *émis par le gardien (brique 7) — forme relevée dans le code, valeurs d'exemple.*

Champs utiles : `regle`, `avant`, `apres` (la règle : `phrase`, `valeurs`…), `qui`, `comment` (vote du public, fichier relu), `vote`.

```json
{"type": "regle_changee", "source": "exemple", "donnees": {"regle": "vitesse_max", "avant": {"id": "vitesse_max", "phrase": "Le robot ne va jamais plus vite que 0,3 mètre par seconde.", "active": true, "sorte": "vitesse_max", "en_direct": true, "valeurs": {"m_s": 0.3}}, "apres": {"id": "vitesse_max", "phrase": "Le robot ne va jamais plus vite que 0,2 mètre par seconde.", "active": true, "sorte": "vitesse_max", "en_direct": true, "valeurs": {"m_s": 0.2}}, "qui": "vote", "comment": "vote du public"}, "id": "d69e5a1bab7f", "numero": 88, "heure": "2026-11-11T19:12:07.968+00:00", "t": 20538.211264406, "robot": "faux-humanoide", "conversation": null}
```

Ligne simple :

```json
{"numero": 88, "heure": "2026-11-11T19:12:07.968+00:00", "heure_locale": "19:12:07", "type": "regle_changee", "langue": null, "texte": "règle changée : vitesse_max", "picto": "", "conversation": null, "robot": "faux-humanoide", "id": "d69e5a1bab7f"}
```

### `note`

Remarque libre (répétition, test, commentaire). — *vrai événement, testé sur faux robot.*

Champs utiles : `texte` : une remarque (chiffres recopiés, décision annulée par un stop…).

```json
{"type": "note", "source": "oreilles", "donnees": {"texte": "écho de la voix du robot ignoré : Ich gehe zu: Küche."}, "id": "4d47e2fbd9ff", "numero": 77, "heure": "2026-11-11T19:12:07.615+00:00", "t": 20537.857925423, "robot": null, "conversation": null}
```

Ligne simple :

```json
{"numero": 77, "heure": "2026-11-11T19:12:07.615+00:00", "heure_locale": "19:12:07", "type": "note", "langue": null, "texte": "écho de la voix du robot ignoré : Ich gehe zu: Küche.", "picto": "", "conversation": null, "robot": null, "id": "4d47e2fbd9ff"}
```

### `parole_finie`

Les oreilles ont détecté la fin d'une phrase (durée, attente du silence). — *vrai événement, testé sur faux robot.*

Champs utiles : `duree_s` de la phrase, `attente_fin_ms`, `bouton`.

```json
{"type": "parole_finie", "source": "oreilles", "donnees": {"duree_s": 1.0, "attente_fin_ms": 0, "coupee": false, "bouton": true}, "id": "638f9d76ce83", "numero": 66, "heure": "2026-11-11T19:12:07.263+00:00", "t": 20537.505895969, "robot": null, "conversation": null}
```

Ligne simple :

```json
{"numero": 66, "heure": "2026-11-11T19:12:07.263+00:00", "heure_locale": "19:12:07", "type": "parole_finie", "langue": null, "texte": "fin de phrase (1.0 s)", "picto": "entendu", "conversation": null, "robot": null, "id": "638f9d76ce83"}
```

### `transcription`

L'écoute a transformé la phrase en texte (langue, confiance, temps de calcul). — *vrai événement, testé sur faux robot.*

Champs utiles : `texte`, `langue`, `confiance`, `calcul_ms` (temps de l'écoute), `moteur`.

```json
{"type": "transcription", "source": "oreilles", "donnees": {"texte": "Geh in die Küche", "langue": "de", "langue_proba": 0.98, "confiance": 0.91, "calcul_ms": 412.0, "moteur": "écoute factice", "langue_moteur": "", "langue_verifiee": true}, "id": "b353ad6033e2", "numero": 67, "heure": "2026-11-11T19:12:07.263+00:00", "t": 20537.506295165, "robot": null, "conversation": null}
```

Ligne simple :

```json
{"numero": 67, "heure": "2026-11-11T19:12:07.263+00:00", "heure_locale": "19:12:07", "type": "transcription", "langue": "de", "texte": "Geh in die Küche", "picto": "entendu", "conversation": null, "robot": null, "id": "b353ad6033e2"}
```

### `mot_d_appel`

Le mot d'appel a été entendu : le robot écoute pendant un moment. — *émis par conversation.py avec un vrai micro — forme relevée dans le code, valeurs d'exemple.*

Champs utiles : `texte`, `langue` : le robot écoute pendant un moment.

```json
{"type": "mot_d_appel", "source": "exemple", "donnees": {"texte": "Robot, va à la cuisine", "langue": "fr"}, "id": "9e6e17e0ff92", "numero": 90, "heure": "2026-11-11T19:12:07.968+00:00", "t": 20538.211292809, "robot": "faux-humanoide", "conversation": null}
```

Ligne simple :

```json
{"numero": 90, "heure": "2026-11-11T19:12:07.968+00:00", "heure_locale": "19:12:07", "type": "mot_d_appel", "langue": "fr", "texte": "Robot, va à la cuisine", "picto": "entendu", "conversation": null, "robot": "faux-humanoide", "id": "9e6e17e0ff92"}
```

### `interruption`

La personne a parlé pendant que le robot parlait : le robot se tait. — *émis par conversation.py avec un vrai micro — forme relevée dans le code, valeurs d'exemple.*

Champs utiles : `parle_depuis_ms` : la personne a coupé la parole au robot.

```json
{"type": "interruption", "source": "exemple", "donnees": {"parle_depuis_ms": 340}, "id": "3b953aa30056", "numero": 91, "heure": "2026-11-11T19:12:07.968+00:00", "t": 20538.211302036, "robot": "faux-humanoide", "conversation": null}
```

Ligne simple :

```json
{"numero": 91, "heure": "2026-11-11T19:12:07.968+00:00", "heure_locale": "19:12:07", "type": "interruption", "langue": null, "texte": "interruption : le robot se tait", "picto": "entendu", "conversation": null, "robot": "faux-humanoide", "id": "3b953aa30056"}
```

### `voix_debut`

Le robot commence à dire sa réponse (temps depuis la fin de la phrase). — *vrai événement, testé sur faux robot.*

Champs utiles : `texte`, `langue`, `latence_ms` (fin de la phrase → début du son), `sous_titres_seulement`.

```json
{"type": "voix_debut", "source": "voix", "donnees": {"texte": "Ich gehe zu: Küche.", "langue": "de", "latence_ms": 3, "calcul_voix_ms": 35.0, "moteur": "voix d'essai", "sous_titres_seulement": false}, "id": "a2a37202d27c", "numero": 74, "heure": "2026-11-11T19:12:07.266+00:00", "t": 20537.50849625, "robot": null, "conversation": "a17f28d25a"}
```

Ligne simple :

```json
{"numero": 74, "heure": "2026-11-11T19:12:07.266+00:00", "heure_locale": "19:12:07", "type": "voix_debut", "langue": "de", "texte": "voix : 3 ms après la fin de la phrase", "picto": "parle", "conversation": "a17f28d25a", "robot": null, "id": "a2a37202d27c"}
```

### `cerveau_secours`

Le cerveau est trop lent, éteint ou hors formulaire : on passe au cerveau suivant. — *vrai événement, testé sur faux robot.*

Champs utiles : `de`, `vers`, `raison`, `attente_ms`.

```json
{"type": "cerveau_secours", "source": "cerveau", "donnees": {"de": "apertus_8b", "vers": "regles", "raison": "CerveauIndisponible: apertus_8b : ConnectError: All connection attempts failed", "delai_s": 2.0, "attente_ms": 23, "mis_de_cote": true}, "id": "89c3c36f16f6", "numero": 56, "heure": "2026-11-11T19:12:07.100+00:00", "t": 20537.343354911, "robot": null, "conversation": null}
```

Ligne simple :

```json
{"numero": 56, "heure": "2026-11-11T19:12:07.100+00:00", "heure_locale": "19:12:07", "type": "cerveau_secours", "langue": null, "texte": "cerveau : apertus_8b → regles (CerveauIndisponible: apertus_8b : ConnectError: All connection attempts failed)", "picto": "", "conversation": null, "robot": null, "id": "89c3c36f16f6"}
```

### `cerveau_serveur`

Un cerveau de secours est lancé ou arrêté sur cet ordinateur (pas une panne). — *émis par la cascade du cerveau (brique 6) avec les vrais serveurs Apertus — forme relevée dans le code, valeurs d'exemple.*

Champs utiles : `quoi` (lance, arrete), `de`, `vers`, `raison` : un cerveau de secours lancé ou arrêté (pas une panne).

```json
{"type": "cerveau_serveur", "source": "exemple", "donnees": {"de": "apertus_8b", "vers": "apertus_4b", "quoi": "lance", "raison": "secours lancé au besoin"}, "id": "05c2a47c6b7c", "numero": 81, "heure": "2026-11-11T19:12:07.968+00:00", "t": 20538.211121368, "robot": "faux-humanoide", "conversation": null}
```

Ligne simple :

```json
{"numero": 81, "heure": "2026-11-11T19:12:07.968+00:00", "heure_locale": "19:12:07", "type": "cerveau_serveur", "langue": null, "texte": "cerveau de secours lancé (secours lancé au besoin)", "picto": "", "conversation": null, "robot": "faux-humanoide", "id": "05c2a47c6b7c"}
```

### `confirmation_demandee`

Avant une action à risque, le robot répète l'ordre et attend un « oui ». — *vrai événement, testé sur faux robot.*

Champs utiles : `question`, `action`, `langue` : avant une action à risque, le robot attend « oui ».

```json
{"type": "confirmation_demandee", "source": "chaine", "donnees": {"action": {"nom": "saisir", "parametres": {"objet": "bouteille", "force": 15.0}}, "langue": "fr", "question": "Je prends : bouteille. Vous confirmez ?"}, "id": "7ad44127d4c5", "numero": 24, "heure": "2026-11-11T19:12:06.999+00:00", "t": 20537.241701656, "robot": "faux-humanoide", "conversation": "d447c0e45b"}
```

Ligne simple :

```json
{"numero": 24, "heure": "2026-11-11T19:12:06.999+00:00", "heure_locale": "19:12:06", "type": "confirmation_demandee", "langue": "fr", "texte": "Je prends : bouteille. Vous confirmez ?", "picto": "question", "conversation": "d447c0e45b", "robot": "faux-humanoide", "id": "7ad44127d4c5"}
```

### `scenario_debut`

Le chef de démonstration commence un scénario (titre, étapes, répétition, pannes prévues). — *émis par le chef de démonstration (brique 15) — forme relevée dans le code, valeurs d'exemple.*

Champs utiles : `titre`, `etapes`, `repetition`, `acceleration`, `pannes` prévues, `duree_visee_s`, `mention`.

```json
{"type": "scenario_debut", "source": "exemple", "donnees": {"titre": "Essai de trois minutes", "fichier": "essai_3_minutes.yaml", "etapes": 21, "repetition": false, "acceleration": 1.0, "pannes": {}, "graine": null, "duree_visee_s": 180, "mention": "testé sur faux robot"}, "id": "2300377041e4", "numero": 83, "heure": "2026-11-11T19:12:07.968+00:00", "t": 20538.211203303, "robot": "faux-humanoide", "conversation": null}
```

Ligne simple :

```json
{"numero": 83, "heure": "2026-11-11T19:12:07.968+00:00", "heure_locale": "19:12:07", "type": "scenario_debut", "langue": null, "texte": "", "picto": "", "conversation": null, "robot": "faux-humanoide", "id": "2300377041e4"}
```

### `scenario_etape`

Une étape du scénario commence ou finit (nom, résultat, cause d'un raté, durée). — *émis par le chef de démonstration (brique 15) — forme relevée dans le code, valeurs d'exemple.*

Champs utiles : `quoi` (debut, fin), `numero`, `nom`, `genre` ; à la fin : `resultat`, `cause`, `detail`, `duree_s`, `plans_b`.

```json
{"type": "scenario_etape", "source": "exemple", "donnees": {"quoi": "fin", "numero": 7, "nom": "aller_table", "genre": "dire", "resultat": "reussie", "cause": null, "detail": "", "duree_s": 15.2, "limite_s": 30.0, "plans_b": []}, "id": "7d09b35cf83e", "numero": 84, "heure": "2026-11-11T19:12:07.968+00:00", "t": 20538.211218188, "robot": "faux-humanoide", "conversation": null}
```

Ligne simple :

```json
{"numero": 84, "heure": "2026-11-11T19:12:07.968+00:00", "heure_locale": "19:12:07", "type": "scenario_etape", "langue": null, "texte": "", "picto": "", "conversation": null, "robot": "faux-humanoide", "id": "7d09b35cf83e"}
```

### `plan_b`

Une étape a raté : le chef essaie un moyen de secours (tablette, main humaine, mode local, sauter). — *émis par le chef de démonstration (brique 15) — forme relevée dans le code, valeurs d'exemple.*

Champs utiles : `etat` (essai, reussi, rate, inutile), `moyen` (tablette, mode_local, main_humaine, sauter), `cause`, `etape`.

```json
{"type": "plan_b", "source": "exemple", "donnees": {"etat": "essai", "moyen": "tablette", "cause": "voix", "etape": "salut_fr", "numero": 2}, "id": "651b977d3783", "numero": 85, "heure": "2026-11-11T19:12:07.968+00:00", "t": 20538.211230353, "robot": "faux-humanoide", "conversation": null}
```

Ligne simple :

```json
{"numero": 85, "heure": "2026-11-11T19:12:07.968+00:00", "heure_locale": "19:12:07", "type": "plan_b", "langue": null, "texte": "", "picto": "", "conversation": null, "robot": "faux-humanoide", "id": "651b977d3783"}
```

### `scenario_fin`

Le scénario est fini ou interrompu (durée, étapes réussies, rattrapées, ratées). — *émis par le chef de démonstration (brique 15) — forme relevée dans le code, valeurs d'exemple.*

Champs utiles : `titre`, `duree_s`, `reussies`, `rattrapees`, `ratees`, `sautees`, `jouees`, `interrompu`, `raison`.

```json
{"type": "scenario_fin", "source": "exemple", "donnees": {"titre": "Essai de trois minutes", "duree_s": 174.8, "reussies": 21, "rattrapees": 0, "ratees": 0, "sautees": 0, "jouees": 21, "etapes": 21, "interrompu": false, "raison": null}, "id": "0c82bfa817a7", "numero": 86, "heure": "2026-11-11T19:12:07.968+00:00", "t": 20538.211241369, "robot": "faux-humanoide", "conversation": null}
```

Ligne simple :

```json
{"numero": 86, "heure": "2026-11-11T19:12:07.968+00:00", "heure_locale": "19:12:07", "type": "scenario_fin", "langue": null, "texte": "", "picto": "", "conversation": null, "robot": "faux-humanoide", "id": "0c82bfa817a7"}
```

### `aide_recue`

Un humain a aidé le robot : demande acceptée ou refusée, ou mot appris (brique 8). — *émis par le gardien et le doute (briques 7, 8) — forme relevée dans le code, valeurs d'exemple.*

Champs utiles : `sorte` (demande_du_gardien, mot_appris), `accepte`, `qui` ; pour un mot : `mot`, `sens`, `langue`.

```json
{"type": "aide_recue", "source": "exemple", "donnees": {"sorte": "demande_du_gardien", "numero": "a1b2c3", "accepte": true, "qui": "ecran"}, "id": "92126139e970", "numero": 82, "heure": "2026-11-11T19:12:07.968+00:00", "t": 20538.211186176, "robot": "faux-humanoide", "conversation": null}
```

Ligne simple :

```json
{"numero": 82, "heure": "2026-11-11T19:12:07.968+00:00", "heure_locale": "19:12:07", "type": "aide_recue", "langue": null, "texte": "", "picto": "", "conversation": null, "robot": "faux-humanoide", "id": "92126139e970"}
```

### `internet_coupe`

Bouton « Internet coupé » de l'écran : sorties vers Internet coupées, ou rétablies (brique 13). — *vrai événement, testé sur faux robot.*

Champs utiles : `coupe` (vrai / faux), `preuve`, `etages_eteints` (Apertus par Internet), `connexions_refusees`.

```json
{"type": "internet_coupe", "source": "ecran", "donnees": {"coupe": true, "preuve": "essai : connexion vers 1.1.1.1:443 refusée avant de partir", "etages_eteints": [], "limites": []}, "id": "716eeb0f57d0", "numero": 49, "heure": "2026-11-11T19:12:07.030+00:00", "t": 20537.272676924, "robot": "faux-humanoide", "conversation": null}
```

Ligne simple :

```json
{"numero": 49, "heure": "2026-11-11T19:12:07.030+00:00", "heure_locale": "19:12:07", "type": "internet_coupe", "langue": null, "texte": "Internet coupé — tout continue", "picto": "internet", "conversation": null, "robot": "faux-humanoide", "id": "716eeb0f57d0"}
```

### `mode_silence`

Mode silence de l'écran : la voix passe en sous-titres seulement, ou revient (brique 13). — *vrai événement, testé sur faux robot.*

Champs utiles : `actif` : la voix passe en sous-titres seulement, pictogrammes en grand.

```json
{"type": "mode_silence", "source": "ecran", "donnees": {"actif": true, "voix": "sous-titres seulement", "micro": false}, "id": "a811c83d889f", "numero": 51, "heure": "2026-11-11T19:12:07.034+00:00", "t": 20537.277336859, "robot": "faux-humanoide", "conversation": null}
```

Ligne simple :

```json
{"numero": 51, "heure": "2026-11-11T19:12:07.034+00:00", "heure_locale": "19:12:07", "type": "mode_silence", "langue": null, "texte": "mode silence : sous-titres seulement", "picto": "silence", "conversation": null, "robot": "faux-humanoide", "id": "a811c83d889f"}
```

### `porte_agents`

Porte des agents (brique 14) : un agent d'IA se branche, ou son ordre est refusé avant le cerveau. — *émis par la porte des agents (brique 14) — forme relevée dans le code, valeurs d'exemple.*

Champs utiles : `quoi` (ouverte, ordre_refuse), `agent` (agent:nom) ; ouverte : `ordres_par_minute`, `accord_humain` ; ordre_refuse : `raison` (trop_d_ordres, ordre_invalide), `texte`. Les ordres acceptés, eux, sont des `parole_entendue` de source « agent:nom » (brique 14).

```json
{"type": "porte_agents", "source": "exemple", "donnees": {"quoi": "ordre_refuse", "agent": "agent:assistant", "raison": "trop_d_ordres", "texte": "Va à la table", "n": 10, "attendre_s": 12.5}, "id": "40893de08ddd", "numero": 92, "heure": "2026-11-11T19:12:07.968+00:00", "t": 20538.21131183, "robot": "faux-humanoide", "conversation": null}
```

Ligne simple :

```json
{"numero": 92, "heure": "2026-11-11T19:12:07.968+00:00", "heure_locale": "19:12:07", "type": "porte_agents", "langue": null, "texte": "", "picto": "", "conversation": null, "robot": "faux-humanoide", "id": "40893de08ddd"}
```

### `yeux`

Les yeux (brique 5) : démarrage, caméra en panne ou revenue, personnes données ou non au gardien, objet cherché vu ou pas. — *émis par les yeux (brique 5), éteints par défaut — forme relevée dans le code, valeurs d'exemple.*

Champs utiles : `quoi` (demarrage, camera, gardien, branchement:NOM, objet_vu, objet_pas_vu, objet_non_cherche, erreur), `valeur`, `raison` ; demarrage : `mention` (testé sur caméra simulée / vraie caméra), `absents` ; objet_vu : `objet`, `direction_deg`, `distance_max_m`. Seulement quand quelque chose change (brique 5).

```json
{"type": "yeux", "source": "exemple", "donnees": {"quoi": "objet_pas_vu", "objet": "bouteille", "depuis_s": 3.0}, "id": "08b6d1604057", "numero": 93, "heure": "2026-11-11T19:12:07.968+00:00", "t": 20538.211321597, "robot": "faux-humanoide", "conversation": null}
```

Ligne simple :

```json
{"numero": 93, "heure": "2026-11-11T19:12:07.968+00:00", "heure_locale": "19:12:07", "type": "yeux", "langue": null, "texte": "", "picto": "", "conversation": null, "robot": "faux-humanoide", "id": "08b6d1604057"}
```

<!-- EXEMPLES:FIN -->
