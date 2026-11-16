---
name: ajouter-une-langue
description: Ajouter une langue au robot du Leukerbad Robot Carnival (par exemple le romanche ou l'espagnol), ou compléter une langue existante. À utiliser quand Hiba ou l'équipe demande « le robot doit aussi parler … », quand un visiteur parle une langue que le robot ne connaît pas, ou quand le contrôle des langues signale un manque. Ajoute les phrases, les « oui » et « non », les mots du cerveau à règles, les noms des lieux et des objets, puis vérifie avec outils/verifier_langues.py et les tests.
---

# Ajouter une langue

Une langue = un code de 2 ou 3 lettres (`rm` pour le romanche, `es` pour l'espagnol, `gsw` pour le suisse allemand).
Le robot doit, dans cette langue : comprendre un ordre, comprendre « stop », comprendre « oui » et « non »,
répondre, expliquer un refus, poser une question. Le contrôle des langues dit ce qui manque.

## Étapes

1. **Voir ce qui manque** (hors ligne, ne change rien) : `python3 outils/verifier_langues.py CODE`
2. **Déclarer la langue** dans `commun/langues.yaml` : `nom`, `reponse` (la langue dans laquelle le robot répond :
   la même s'il a une voix pour elle, sinon la plus proche, et il le dit une fois — comme le suisse allemand → allemand),
   `code_ecoute` (le code que connaît l'écoute Whisper ; s'il n'existe pas : **à vérifier**, écrire la langue la plus proche).
3. **Remplir, dans cet ordre** (le plus important d'abord) :
   - `briques/b06_cerveau/branchements/regles_lexique.yaml` → `verbes.arreter` : **« stop » d'abord**. Sans lui,
     l'arrêt à la voix ne marche pas dans cette langue (le bouton ARRÊT de l'écran, lui, marche toujours).
   - `commun/oui_non.yaml` : « oui » et « non ». Aucun mot qui apparaît dans les questions du robot (un test le vérifie).
   - `commun/chaine.py` → `NEGATIONS` : « ne … pas » (sinon « ne va pas à la cuisine » ferait partir le robot).
   - `commun/phrases.yaml` : copier le bloc `fr`, traduire, garder les `{lieu}`, `{objet}`… tels quels.
   - le reste de `regles_lexique.yaml` (verbes, gestes), puis les noms dans `commun/monde.yaml`.
   - `briques/b15_chef_demo/phrases_chef.yaml` ; les phrases du banc d'essai `briques/b06_cerveau/banc_demandes.yaml`.
4. **Relancer le contrôle** jusqu'à « ok », puis `python3 lancer.py tests`. Faire aussi la liste « à faire à la main »
   qu'il affiche (nombres en lettres, vitesse, voix, écran du jury).
5. **Essayer sur le faux robot** : `python3 lancer.py`, puis dans la tablette de l'écran, une phrase par sorte :
   un ordre, « stop », un ordre dangereux (refus expliqué dans la langue), un ordre flou (question).
   Puis `python3 lancer.py banc-cerveau --langues CODE` pour mesurer.
6. **Rester honnête** : chaque phrase écrite sans locuteur est « à faire relire » (le noter dans `NON_TESTE.md`) ;
   « testé sur faux robot » seulement ; une voix ou un modèle d'écoute pour cette langue : vérifier la licence
   (`LICENCES.md`) et la taille avant de télécharger (feu orange au-delà de 500 Mo, ou si GPL).
7. **Rendre à Hiba cinq lignes** : la langue, ce qui marche (testé sur faux robot), ce qui manque, qui doit relire, le résultat des tests.

## Ce que cette skill ne fait pas
- Elle ne télécharge ni voix ni modèle sans le feu vert prévu par `docs/projet/REGLES_DES_AGENTS.md`.
- Elle n'invente pas de traduction « sûre » : sans locuteur, elle écrit « à faire relire ».
