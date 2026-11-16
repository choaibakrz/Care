---
name: lancer-une-repetition
description: Lancer une répétition de la démonstration du Leukerbad Robot Carnival avec le chef de démonstration (brique 15), sur le faux robot, avec ou sans pannes provoquées, puis lire le compte rendu et dire ce qu'il faut corriger. À utiliser quand Hiba ou l'équipe demande « on répète », « on essaie le scénario », « et si la voix tombe ? », ou avant chaque répétition prévue dans le plan de 48 heures.
---

# Lancer une répétition

Le chef de démonstration joue un scénario YAML étape par étape. Chaque phrase passe par la même chaîne qu'une
personne (cerveau → gardien → prise) : il ne contourne rien. En répétition, il peut provoquer des pannes
(robot, voix, réseau…) pour entraîner les plans B (tablette, mode local, main humaine, sauter).

## Étapes

1. **Vérifier le scénario sans robot** : `python3 -m briques.b15_chef_demo.verifier MON_SCENARIO.yaml`
   (les scénarios sont dans `briques/b15_chef_demo/scenarios/` ; le kit du samedi en écrit un brouillon,
   `plan_scenario.yaml`, au même format). Une faute de frappe doit se voir ici, pas devant le jury.
2. **Répéter sur le faux robot, sans panne**, vite : `python3 lancer.py scenario MON_SCENARIO.yaml --repetition --acceleration 20`
   (choisir le faux robot qui ressemble au vrai : `--robot humanoide|chien|bras`).
3. **Répéter avec des pannes** : `--panne robot@3` (le robot refuse à l'étape 3), `--panne voix@5`, `--panne reseau@2`,
   ou des pannes au hasard, les mêmes à chaque fois : `--pagaille --graine 7`. Chaque plan B doit rattraper l'étape.
4. **Répéter à vitesse normale** (sans `--acceleration`) au moins une fois : mesurer la vraie durée, la comparer à la
   durée de la démonstration (garder 20 % de marge).
5. **Lire le compte rendu** (le chemin s'affiche à la fin) et la fiche de vérité. Pour chaque étape ratée : la cause
   (robot, voix, réseau, gardien, temps), le plan B essayé, et la correction à faire (phrase, limite de temps, plan B).
6. **Sur un vrai robot : feu orange.** Montrer à Hiba en deux lignes ce qui va bouger, attendre son « oui », le
   responsable sécurité présent, la main sur le bouton d'arrêt PHYSIQUE. Jamais de panne provoquée sur un vrai robot
   (le chef les ignore hors répétition, et elles ne visent que le faux robot).
7. **Rester honnête** : écrire « testé sur faux robot » ou « testé sur vrai robot » selon la mention de la fiche ;
   une démonstration de soin se fait avec un mannequin seulement, jamais de diagnostic.
8. **Rendre à Hiba cinq lignes** : scénario et robot, durée mesurée, étapes réussies / rattrapées / ratées,
   les trois corrections les plus utiles, le chemin du compte rendu.

## Ce que cette skill ne fait pas
- Elle ne fait pas bouger un vrai robot sans le « oui » de Hiba.
- Elle ne change pas les règles du gardien ni les limites de sécurité pour « faire passer » une étape.
