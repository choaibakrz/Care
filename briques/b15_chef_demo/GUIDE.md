# Brique 15 — Le chef de démonstration (guide d'une page)

**Rôle** : jouer une démonstration comme une partition. Un scénario = une liste d'étapes. Chaque étape a son plan B.
Tout ordre passe par la chaîne : cerveau → gardien (ticket) → prise → robot. Le chef ne touche jamais le robot.
**Testé sur faux robot** (faux humanoïde, cerveau à règles), sur Linux.

## Commandes
```bash
python3 lancer.py scenario essai_3_minutes.yaml                       # jouer (un nom seul est cherché dans scenarios/)
python3 lancer.py scenario essai_3_minutes.yaml --repetition --panne robot@7 --panne voix@salut_gsw --acceleration 20
python3 lancer.py scenario essai_3_minutes.yaml --repetition --pagaille --graine 7    # pannes au hasard, mêmes à chaque fois
python3 -m briques.b15_chef_demo.verifier --tous                       # vérifier les scénarios, sans robot
```
Options : `--rapport DOSSIER` (compte rendu ; par défaut `mesures/`), `--operateur auto|clavier` (main humaine simulée,
ou attendre la touche Entrée), `--robot humanoide|chien|bras` (sinon la carte écrite dans le scénario).

## Le format d'un scénario (YAML) — modèle commenté : `scenarios/modele.yaml`
Toute clé inconnue est refusée à la lecture : une faute de frappe se voit avant la démonstration.

| En haut du fichier | Sens |
|---|---|
| `titre` | obligatoire |
| `description`, `robot` | facultatifs ; `robot` = carte du faux robot visée (humanoide, chien, bras) |
| `duree_visee_s` | durée souhaitée à vitesse normale (comparée dans le compte rendu) |
| `langue` | langue des phrases du chef (« Je passe à la tablette »…) ; `fr` par défaut |
| `duree_max_s` | limite par défaut d'une étape `dire` (20 s) |
| `plan_b` | plan B par défaut des étapes `dire`, ex. `[tablette, mode_local, main_humaine, sauter]` |
| `etapes` | la liste des étapes |

Une étape = `nom` (unique) + **une seule** chose à faire :

| Chose | Exemple | Ce qui se passe |
|---|---|---|
| `dire` | `dire: {texte: "Va à la table", langue: fr}` ou `dire: "Va"` | la phrase va à la chaîne comme si elle était entendue |
| `annonce` | `annonce: {texte: "Bonjour !", langue: fr}` | affichée et dite par la voix ; pas un ordre au robot |
| `attendre_s` | `attendre_s: 3` | pause |
| `provoquer_panne` | `provoquer_panne: robot` | répétition seulement ; dure jusqu'à `reparer` ou la fin |
| `reparer` | `reparer: true` | répétition seulement |
| `fiche` | `fiche: fr` ou `fiche: true` | dit la fiche de vérité de cette démonstration |
| `controle` | `controle: point_oublie` | appelle un contrôle donné au chef (`ChefDemo(..., controles={nom: fonction})`) : réussie ou ratée, avec un détail. Ajouté le 12.11.2026 (clinique, H05). |

Facultatif sur une étape : `attendu` (seulement avec `dire`), `duree_max_s`, `plan_b` (remplace celui du scénario ;
`[]` = aucun), `attendre_fin: false` (ne pas attendre la fin de l'action), `pause_apres_s`, `remarque` (pour les humains).

**`attendu`** (lu dans les événements du bus, conversation de la phrase) :
`{action: se_deplacer, parametres: {lieu: table}}` (terminée et réussie ; `statut: demarree` = démarrée suffit) ·
`refus` (le gardien dit non, le robot explique, rien ne bouge) · `question` · `{genre: confirmation, action: saisir}` ·
`{genre: reponse, contient: "Schweizerdeutsch"}` · `rien`. Langues : fr, de, gsw, it, en, zh.
Pannes : `robot` (le faux robot refuse tout), `voix` (phrase brouillée), `reseau` (cerveaux par le réseau muets),
ou une panne du faux robot (`lenteur`, `refus`, `perte_liaison`, `batterie_faible`, `arret_ignore`).

## Le plan B
Raté, ou pas fini à temps (limite = `duree_max_s`) → les moyens de `plan_b`, **dans l'ordre**, jusqu'au premier qui marche.
Pas fini à temps et le robot bouge encore : le chef dit d'abord « stop » (par la chaîne). Si l'attendu arrive quand même
(en retard), l'étape est réussie, notée « après la limite » ; on ne rejoue jamais une étape dont l'attendu est là.
Le chef devine la cause (dans les événements) et passe les moyens qui ne peuvent pas aider (notés « inutile ») :

| Cause | Vue dans… | Moyens passés |
|---|---|---|
| robot | refus de la prise, action ratée, panne de liaison | tablette, mode_local |
| gardien / le robot a fait autre chose | gardien « non », action inattendue | tablette, mode_local (rejouer ferait agir encore) |
| voix | « je n'ai pas compris », écoute peu sûre | mode_local |
| réseau | `cerveau_secours`, cerveau muet jusqu'à la limite | tablette |

- `tablette` : la même phrase, tapée (source « clavier ») ; **jusqu'à la fin du scénario**. Pour un « oui », l'ordre
  d'origine est redemandé d'abord (la chaîne n'accepte le « oui » que de la même source que l'ordre).
- `mode_local` : met de côté, jusqu'à la fin, les cerveaux par le réseau et ceux qui ont échoué ; la phrase est rejouée.
  Si le cerveau est passé au secours pendant une étape **réussie**, le chef y passe tout de suite (« préventif »).
- `main_humaine` : `pilotage_humain` {quoi: reprise} + consigne à l'opérateur, puis {quoi: rendu}. L'opérateur est simulé
  (faux robot) ou tape Entrée (`--operateur clavier`, défaut sur vrai robot). Brique 11 : `OperateurEcran` — un humain
  prend la main par l'écran de l'équipe (consigne affichée, ordres par boutons via le gardien, « Fait » / « Pas pu ») ;
  c'est l'écran qui note reprise et rendu. Seulement si le chef tourne dans le même programme que l'écran.
- `sauter` : « On passe à la suite. », étape suivante.

## L'arrêt d'urgence passe avant tout
Dès l'événement `arret_urgence` (bouton, écran, prise), l'étape en cours est coupée, le chef dit « Arrêt d'urgence :
la démonstration s'arrête », et s'arrête. Il ne réarme **jamais** : un humain le fait. Déjà actif au départ : rien ne commence.

## Répétition
Chronomètre par étape et total, compte rendu Markdown (réussies, rattrapées, ratées, plan B, temps, fiche de vérité).
`--panne NOM@ÉTAPE` (numéro ou nom) : la panne dure le temps de cette étape. `--acceleration N` (faux robot seulement) :
faux robot et pauses N fois plus vite ; les limites aussi, jamais sous 2 s (le cerveau ne va pas plus vite).
Les temps accélérés ne sont pas des temps réels : répéter à ×1 pour les connaître.

## Événements (boîte noire, écran)
`scenario_debut`, `scenario_etape` (debut / fin), `plan_b` (essai, puis reussi / rate / saute / inutile), `scenario_fin`,
et `panne` / `reparation` (provoquee: true), `pilotage_humain`, `reponse_dite` (genre « annonce »). La fiche de vérité
compte `plans_b` et `plans_b_reussis`.

## Limites (à savoir avant samedi)
- La **voix est simulée** : le chef donne la phrase à la chaîne comme si les oreilles l'avaient entendue (source « micro »).
- `lancer.py scenario` lance **son propre système** : terminal et boîte noire, mais ni l'écran ni la voix en même temps.
  Les annonces sont dites seulement si la voix (brique 4) écoute le même bus (à faire : lancer un scénario depuis l'écran).
- **Vrai robot : `lancer.py scenario` refuse** pour l'instant (ni bouton ARRÊT de l'écran, ni « stop » à la voix ici).
- Un **« stop » dit par une personne** (micro, tablette, agent) ou l'arrêt d'urgence **arrête tout le scénario** ; le
  chef ne réarme jamais. Après un refus du gardien, seul « sauter » est permis (jamais la main humaine).
- Le chef n'annule jamais une phrase en route : trop long → « stop » par la chaîne, puis il attend la fin.
- La **main humaine** est simulée sur faux robot (on attend 5 s, divisées par l'accélération) : le chef ne peut pas
  vérifier ce que l'humain a fait. Avec l'écran (brique 11, `OperateurEcran`), l'humain dit « Fait » ou « Pas pu ».

## Fichiers
| Fichier | Rôle |
|---|---|
| `scenario.py` | le format, lu et vérifié (pydantic) |
| `chef.py` | le chef d'orchestre, les plans B, les pannes de répétition |
| `compte_rendu.py` | le compte rendu Markdown |
| `commande.py`, `verifier.py` | la commande `lancer.py scenario`, la vérification sans robot |
| `phrases_chef.yaml` | les phrases du chef (fr, de, it, en, zh) |
| `scenarios/` | `essai_3_minutes.yaml`, `modele.yaml` |
