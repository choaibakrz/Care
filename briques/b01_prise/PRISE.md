# La prise universelle — la liste des actions

C'est la courte liste de choses que tout robot peut savoir faire, dite de la même façon pour tous.
Le cerveau, les agents et les humains ne demandent **que** ces actions. Jamais un ordre direct aux moteurs.

| Action | Ce qu'elle fait | Longue ? | Précisions |
|---|---|---|---|
| `se_deplacer` | Aller à un lieu nommé, ou avancer de quelques mètres | oui | `lieu` **ou** `dx`/`dy` (m) ; `vitesse` (m/s, ≤ carte) |
| `regarder` | Tourner la tête ou la caméra vers une cible | non | `cible` (obligatoire) |
| `ecouter` | Écouter avec les micros du robot | non | `duree_s` |
| `parler` | Dire un texte par le haut-parleur du robot | non | `texte` (obligatoire), `langue` |
| `saisir` | Prendre un objet nommé | oui | `objet` (obligatoire), `force` (N, ≤ carte) |
| `poser` | Poser l'objet tenu à un lieu, ou ici | oui | `lieu` |
| `montrer` | Montrer du doigt (ou du corps) une cible | non | `cible` (obligatoire) |
| `rejouer_geste` | Rejouer un geste enregistré, par son nom | oui | `nom` (obligatoire, dans la carte), `vitesse_relative` (≤ 1) |
| `arreter` | S'arrêter tout de suite. Toujours permis | non | — |
| `etat` | Dire son état : batterie, erreurs, position, objet tenu | non | — |

« Longue » : l'action peut être **suivie** (0 à 100 %) et **annulée** en cours de route.

## La carte d'identité

Chaque robot fournit une carte (fichier YAML) : ce qu'il sait faire (`capacites`), ses limites
(`vitesse_max_m_s`, `portee_max_m`, `charge_max_kg`, `force_max_n`), ses gestes enregistrés, et s'il s'agit
d'un vrai robot (`vrai_robot`). `arreter` et `etat` sont obligatoires. Exemples : `briques/b02_faux_robot/cartes/`.

## Les trois verrous

1. **Le gardien** vérifie l'action et délivre un ticket signé, pour **un** robot, à usage unique, valable 5 secondes.
2. **La prise** refuse toute action sans ticket valide, travaille sur une **copie** de l'action (la modifier après coup
   ne sert à rien), et revérifie la carte, les limites et les plafonds de sécurité (0,3 m/s, 15 N, 5 m par défaut).
3. **Le robot** (adaptateur) s'arrête seul s'il ne reçoit plus de signe de vie (chien de garde).

Règles en plus :
- Un nombre doit être un vrai nombre ; vitesse, force et durée doivent être plus grandes que zéro.
- **Une seule action longue à la fois.** Une deuxième est refusée (« je suis occupé ») ; « arreter » passe toujours.
- **« arreter » n'est jamais refusé** : ses précisions éventuelles sont ignorées, et le robot arrête tout.
- Si la prise **perd le fil** d'une action pendant plus d'1 seconde, elle déclenche l'arrêt d'urgence.
  Une coupure plus courte (Wi-Fi) est tolérée : on patiente, l'action continue.
- Un adaptateur ne se fabrique que dans `commun/systeme.py`, et il est donné directement à la prise.

L'**arrêt d'urgence** ne demande aucun ticket. La prise vérifie ensuite que le robot s'est arrêté, réessaie toutes
les 0,1 s pendant 3 s, et affiche « utiliser le bouton PHYSIQUE » si l'arrêt n'est pas confirmé.
Après lui, un humain doit réarmer le robot ; un nouvel arrêt pendant le réarmement annule le réarmement.

## Hors de la liste

`arret_urgence`, `rearmer`, `suivre`, `annuler` et `etat_robot` sont des commandes de la prise, pas des actions.
Ajouter une action à la liste : décision d'équipe (voir `DECISIONS.md`), puis `actions.py` **et** ce fichier.
Un test vérifie que les deux listes sont identiques.
