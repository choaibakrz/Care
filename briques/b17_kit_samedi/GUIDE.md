# Brique 17 — Le kit du samedi matin (guide d'une page)

**Rôle** : passer du texte du défi à un plan en une heure. Hors ligne, sans modèle de langue : le kit cherche des
mots-clés (français, allemand, anglais). Même défi → même plan. **Le kit repère, un humain relit.**

## Lancer
```bash
python3 lancer.py kit-samedi defi.md                     # le plan s'affiche dans le terminal
python3 lancer.py kit-samedi defi.md --sortie plan.md    # plan.md + plan_scenario.yaml
python3 lancer.py kit-samedi defi.txt --scenario demo.yaml
```
Exemple tout fait : `exemples/defi_exemple.md` (faux défi inventé) → `exemples/plan_exemple.md`.
Un faux défi en allemand : `exemples/defi_exemple_de.md`. Avec l'assistant : la skill `savoir-faire/lire-le-defi`.

## Ce que le plan contient
1. Résumé : robot, capacités demandées, langues, durées, critères, règles de sécurité, questions aux organisateurs.
2. Briques prêtes, avec leurs commandes (testé sur faux robot ; rien sur un vrai robot).
3. Ce qui manque : par capacité, quelle brique, quelles tâches de son `TACHES.md`. L'adaptateur (brique 3) toujours en premier.
4. Plan heure par heure, samedi 9 h → lundi 9 h : repas, sommeil par rotation, gels du code, répétitions, démonstration.
5. Les 35 personnes : rôles fixes et équipes d'`AGENTS.md`, puis des renforts pour les briques qui manquent.
6. Risques : ceux du défi, nos règles, ceux de tout défi, et un extrait de `NON_TESTE.md`.
7. Brouillon de scénario : étapes avec un plan B chacune (voix → tablette, robot → main humaine, réseau → mode local).
8. Critères du jury → ce que l'on montre → preuve (fiche de vérité, boîte noire).

## Les fichiers
| Fichier | Contenu | Qui le change |
|---|---|---|
| `mots_cles.yaml` | les mots qui font repérer robot, capacités, langues, critères, sécurité, durées | tout le monde |
| `connaissances.yaml` | par capacité : briques, risque, parade, preuve ; étapes du scénario ; plans B | relecteur |
| `programme_48h.yaml` | les 48 heures (heures officielles **à vérifier**) | Hiba |
| `equipes.yaml` | rôles fixes, équipes de base, nombre de renforts | Hiba |
| `../etat_des_briques.yaml` | l'état des 17 briques (lu par le kit) | à chaque fusion |
| `analyseur.py` / `plan.py` / `kit.py` | lire le défi / écrire le plan et le scénario / la commande | — |

## Règles
- Les phrases du scénario sont **essayées sur le faux robot** (humanoïde, chien, bras) par un test : elles font ce
  que le plan annonce. Lieux et objets : ceux de `commun/monde.yaml`, à remplacer par ceux du défi.
- Le plan n'écrit jamais « testé sur vrai robot » (un garde-fou le retire, même recopié du défi).
- Le scénario passe par la chaîne normale (cerveau → gardien → prise) : le kit ne commande aucun robot.
- Le format YAML du scénario est simple ; il doit être aligné sur celui de la brique 15 (chef de démonstration).

## Tester
```bash
python3 lancer.py tests briques/b17_kit_samedi
```
