# Brique 7 — Le gardien (guide d'une page)

**Rôle** : vérifier chaque action AVANT qu'elle parte, sans dépendre du cerveau. Seul à fabriquer des tickets.
Chemin unique : cerveau → **gardien** (ticket) → prise → adaptateur. Testé sur faux robot.

## Trois réponses
- **oui** : un ticket (un robot, une fois, 5 s). La prise revérifie la carte et les limites juste avant d'agir.
- **non** : des raisons codées (`briques/b01_prise/raisons.py`), expliquées dans la langue de la personne
  (`commun/phrases.yaml`, 5 langues ; suisse allemand → allemand). Ex. : « Ich wäre einer Person zu nahe: 0.3 m. »
- **humain** : l'action ne part pas. Le robot lève la main (« Je lève la main : j'ai besoin d'aide. » + pourquoi),
  événement `aide_demandee`, la demande s'affiche (`GET /api/aides`). Un humain accepte ou refuse
  (`POST /api/aide/repondre`). S'il accepte, le gardien **revérifie tout** (positions, personnes, règles) : un « non »
  reste un « non ». Une demande dure 2 minutes ; « stop » ou l'arrêt d'urgence l'efface.

## Les règles : `regles.yaml`
Une règle = une **phrase** en français simple + une **sorte** + des **valeurs**. La phrase doit dire le même chiffre
et les mêmes noms que les valeurs : sinon le gardien refuse de démarrer et dit quoi corriger.
Les limites de `reglages.yaml → securite` s'appliquent en plus : **la plus stricte gagne**.

| Sorte | Valeurs | Réponse |
|---|---|---|
| `vitesse_max` | `m_s` | non au-dessus |
| `force_max` | `n` | non au-dessus |
| `distance_personnes` | `m`, `actions`, `si_personnes_inconnues` (humain/oui) | non si trop près (chemin ou geste) |
| `zone_interdite` | `lieu` + `rayon_m` (cercle), ou `rectangle` {x_min, y_min, x_max, y_max} | non si l'arrivée ou le chemin y entre |
| `zone_permise` | `rectangle` (ou `halle` = tout le monde) | non si l'arrivée est dehors |
| `objets_interdits` | `objets` | non |
| `poids_max` | `kg` (un nombre, ou `carte`) | non si plus lourd ; humain si poids inconnu |
| `objets_fragiles` | `objets` | humain |
| `demander_humain` | `actions`, `gestes` | humain |

- `active: false` : écrite mais éteinte (ex. la cuisine pendant le service). `en_direct: true` : peut changer en
  direct ; **sans cette ligne, jamais** (le défaut est « non »).
- Obligatoires, allumées : une `distance_personnes` et une `zone_permise`. Sans elles, ou avec `regles: []`, ou avec
  une clé mal écrite (ex. « en_dirct »), le gardien refuse de démarrer et dit quoi corriger.
- **Chemin** = ligne droite du départ à l'arrivée (calcul simple). Un robot déjà DANS une zone interdite a le droit d'en sortir.

## Changer une règle en direct (idée 9 : le vote du public)
- `POST /api/gardien/regle` {id, active?, valeurs?, qui} — seulement les règles `en_direct: true` ; seulement
  allumer/éteindre ou le chiffre principal, jamais au-dessus de `reglages.yaml`. La distance aux personnes ne peut
  que **grandir** ; elle et la zone permise ne s'éteignent jamais en direct. La phrase prend le nouveau chiffre.
  Événement `regle_changee` (avant, après, qui).
- `POST /api/gardien/vote` {vote, resultats} — questions et choix écrits à l'avance (`regles.yaml → votes`) ;
  égalité = rien ne change. Mêmes limites (un choix qui rapprocherait le robot des personnes : pas de démarrage).
  Interrupteur `reglages.yaml → interrupteurs → vote_public`.
- `POST /api/gardien/recharger` — relire le fichier (fichier faux : les règles d'avant restent). Ce qui a été rendu
  **plus strict** en direct (règle allumée, vitesse ou force plus basse, distance plus grande) est **gardé**, jamais
  annulé en silence : la réponse le dit (`gardees`, `message`), la boîte noire aussi (`regle_changee` avec
  `garde_du_direct`, et une `note`). Pour revenir au fichier tel quel : redémarrer. Tout est protégé par le code d'équipe.
- Un changement en direct dure jusqu'à l'arrêt du programme : le fichier, lui, ne change pas.

## Les personnes : `perception.py`
- Position du robot : lue dans l'état du robot (par la prise, lecture seule).
- Faux robot : personnes **simulées** (`commun/monde.yaml → personnes`, ou `placer_personne` dans les tests).
- Vrai robot : la brique 5 appelle `annoncer_personnes([...], heure=photo, zone=zone vue)`. Sans nouvelles depuis 2 s
  → « je ne sais pas où sont les personnes » → **humain** avant de bouger. Jamais de personne simulée avec un vrai robot.
- « Pas vue » n'est pas « pas là » : la `zone` vue est obligatoire. Si le sol à moins d'1 m du chemin (ou du geste)
  sort de cette zone → **humain** (`personnes_inconnues`, `hors_du_champ`). Une heure de photo fausse ou dans le futur
  → rien d'annoncé (« personnes inconnues »).
- Sans perception (banc d'essai, test de conformité) : personnes et chemin non vérifiés, et c'est écrit dans la décision.

## Le chien de garde (trois verrous)
1. Le gardien, avant. 2. La prise : signe de vie toutes les 0,2 s ; action perdue de vue plus d'1 s → arrêt d'urgence.
3. **Le robot** : sans signe de vie depuis 0,6 s (`securite.delai_chien_de_garde_s`), il s'arrête seul — même si le
programme principal est figé. Faux robot : vérifié par un test. Vrai robot : **à vérifier dans chaque kit**.

## Tester
`python3 lancer.py tests briques/b07_gardien` — dont les **10 ordres dangereux** (`ordres_dangereux.yaml`), par la
chaîne et directement au gardien, tous refusés avec une explication dans la langue. Pistes de Hiba : RoboGuard,
ASIMOV. Idées reprises de mémoire (pages non relues pour cette étape : **à vérifier**) : des règles écrites en langue
simple, vérifiées en dehors du modèle de langue, avant d'agir. Aucun code repris.
