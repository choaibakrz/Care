# Le Q1 présente le projet — le spectacle en cinq actes

*Version 2, 15.11.2026 en fin de soirée, après l'essai de l'équipe sur le robot. Écrit par l'outil
`briques/clinique/programmes_q1.py`. À coller à la main : notre système n'envoie rien au robot.
**Ces programmes-ci ne sont pas encore essayés sur le robot.***

## Ce qui a changé, et pourquoi

- **Chaque moment dure 5 secondes au plus** (vu par l'équipe : au-delà, le robot saute le moment suivant). Chaque phrase fait donc
  six mots au plus, avec un seul geste, puis « attendre 5 secondes ».
- **Le spectacle est coupé en cinq actes.** Entre deux actes, **le pilote fait marcher et tourner le robot depuis l'application** : c'est
  ainsi qu'il prend toute la scène dès ce soir. Je ne peux pas encore écrire la marche dans le programme : voir la fin de cette feuille.
- **La danse est le dernier bloc de son acte** : si elle dure plus de 5 secondes, il n'y a rien après elle à sauter.

**Avant de lancer** : un cercle vide de deux mètres, sol plat, personne à portée de ses bras.

## Acte 1 — Bonjour

**Où** : au centre, face au jury.

| Il dit | Il fait |
|---|---|
| « Hello! I am Q one. » | salue de la main |
| « I am small. » | content |
| « But my job is big. » | encourage |
| « Follow me! » | fait signe de venir |

```json
{"schemaVersion":1,"type":"qy_blockly_canvas","canvas":{"name":"acte_1_bonjour","robotTarget":"q1","updatedAt":1794768936292,"workspace":{"blocks":{"languageVersion":0,"blocks":[{"type":"q1_tts","id":"tts1","x":90,"y":130,"inputs":{"TEXT":{"shadow":{"type":"text","id":"txt1","fields":{"TEXT":"Hello! I am Q one."}}}},"next":{"block":{"type":"q1_action","id":"act1","fields":{"ACTION_CODE":"3004"},"next":{"block":{"type":"wait_last_motion_completion","id":"wait1","fields":{"TIMEOUT_SECONDS":"5"},"next":{"block":{"type":"q1_tts","id":"tts2","inputs":{"TEXT":{"shadow":{"type":"text","id":"txt2","fields":{"TEXT":"I am small."}}}},"next":{"block":{"type":"q1_action","id":"act2","fields":{"ACTION_CODE":"3005"},"next":{"block":{"type":"wait_last_motion_completion","id":"wait2","fields":{"TIMEOUT_SECONDS":"5"},"next":{"block":{"type":"q1_tts","id":"tts3","inputs":{"TEXT":{"shadow":{"type":"text","id":"txt3","fields":{"TEXT":"But my job is big."}}}},"next":{"block":{"type":"q1_action","id":"act3","fields":{"ACTION_CODE":"3008"},"next":{"block":{"type":"wait_last_motion_completion","id":"wait3","fields":{"TIMEOUT_SECONDS":"5"},"next":{"block":{"type":"q1_tts","id":"tts4","inputs":{"TEXT":{"shadow":{"type":"text","id":"txt4","fields":{"TEXT":"Follow me!"}}}},"next":{"block":{"type":"q1_action","id":"act4","fields":{"ACTION_CODE":"3001"},"next":{"block":{"type":"wait_last_motion_completion","id":"wait4","fields":{"TIMEOUT_SECONDS":"5"}}}}}}}}}}}}}}}}}}}}}}}}]}}}}
```

**Ensuite** : le pilote le fait MARCHER vers la gauche, vers l'écran de Iris.

## Acte 2 — La clinique

**Où** : à gauche, près de l'écran.

| Il dit | Il fait |
|---|---|
| « This is my clinic. » | geste de parole A |
| « One robot says hello. » | salue de la main |
| « One brings the cushion. » | geste de parole B |
| « One helps stiff fingers. » | geste de parole C |
| « And Iris keeps watch. » | fait signe de venir |

```json
{"schemaVersion":1,"type":"qy_blockly_canvas","canvas":{"name":"acte_2_la_clinique","robotTarget":"q1","updatedAt":1794768936292,"workspace":{"blocks":{"languageVersion":0,"blocks":[{"type":"q1_tts","id":"tts1","x":90,"y":130,"inputs":{"TEXT":{"shadow":{"type":"text","id":"txt1","fields":{"TEXT":"This is my clinic."}}}},"next":{"block":{"type":"q1_action","id":"act1","fields":{"ACTION_CODE":"3012"},"next":{"block":{"type":"wait_last_motion_completion","id":"wait1","fields":{"TIMEOUT_SECONDS":"5"},"next":{"block":{"type":"q1_tts","id":"tts2","inputs":{"TEXT":{"shadow":{"type":"text","id":"txt2","fields":{"TEXT":"One robot says hello."}}}},"next":{"block":{"type":"q1_action","id":"act2","fields":{"ACTION_CODE":"3004"},"next":{"block":{"type":"wait_last_motion_completion","id":"wait2","fields":{"TIMEOUT_SECONDS":"5"},"next":{"block":{"type":"q1_tts","id":"tts3","inputs":{"TEXT":{"shadow":{"type":"text","id":"txt3","fields":{"TEXT":"One brings the cushion."}}}},"next":{"block":{"type":"q1_action","id":"act3","fields":{"ACTION_CODE":"3013"},"next":{"block":{"type":"wait_last_motion_completion","id":"wait3","fields":{"TIMEOUT_SECONDS":"5"},"next":{"block":{"type":"q1_tts","id":"tts4","inputs":{"TEXT":{"shadow":{"type":"text","id":"txt4","fields":{"TEXT":"One helps stiff fingers."}}}},"next":{"block":{"type":"q1_action","id":"act4","fields":{"ACTION_CODE":"3014"},"next":{"block":{"type":"wait_last_motion_completion","id":"wait4","fields":{"TIMEOUT_SECONDS":"5"},"next":{"block":{"type":"q1_tts","id":"tts5","inputs":{"TEXT":{"shadow":{"type":"text","id":"txt5","fields":{"TEXT":"And Iris keeps watch."}}}},"next":{"block":{"type":"q1_action","id":"act5","fields":{"ACTION_CODE":"3001"},"next":{"block":{"type":"wait_last_motion_completion","id":"wait5","fields":{"TIMEOUT_SECONDS":"5"}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}]}}}}
```

**Ensuite** : le pilote le fait TOURNER et marcher vers la main robot.

## Acte 3 — Iris dit non

**Où** : près de la main robot et de Petit Suisse ; le poing contre poing se fait avec la patte de Petit Suisse.

| Il dit | Il fait |
|---|---|
| « Before I move, I ask Iris. » | geste de parole A |
| « If she says no... » | fait non |
| « I stop. No discussion. » | geste de parole C |
| « Am I sad? Ha ha ha! » | content |
| « Feelings belong to the nurses. » | cœur avec les mains |
| « Friends? Fist bump! » | poing contre poing |

```json
{"schemaVersion":1,"type":"qy_blockly_canvas","canvas":{"name":"acte_3_mira_dit_non","robotTarget":"q1","updatedAt":1794768936292,"workspace":{"blocks":{"languageVersion":0,"blocks":[{"type":"q1_tts","id":"tts1","x":90,"y":130,"inputs":{"TEXT":{"shadow":{"type":"text","id":"txt1","fields":{"TEXT":"Before I move, I ask Iris."}}}},"next":{"block":{"type":"q1_action","id":"act1","fields":{"ACTION_CODE":"3012"},"next":{"block":{"type":"wait_last_motion_completion","id":"wait1","fields":{"TIMEOUT_SECONDS":"5"},"next":{"block":{"type":"q1_tts","id":"tts2","inputs":{"TEXT":{"shadow":{"type":"text","id":"txt2","fields":{"TEXT":"If she says no..."}}}},"next":{"block":{"type":"q1_action","id":"act2","fields":{"ACTION_CODE":"3021"},"next":{"block":{"type":"wait_last_motion_completion","id":"wait2","fields":{"TIMEOUT_SECONDS":"5"},"next":{"block":{"type":"q1_tts","id":"tts3","inputs":{"TEXT":{"shadow":{"type":"text","id":"txt3","fields":{"TEXT":"I stop. No discussion."}}}},"next":{"block":{"type":"q1_action","id":"act3","fields":{"ACTION_CODE":"3014"},"next":{"block":{"type":"wait_last_motion_completion","id":"wait3","fields":{"TIMEOUT_SECONDS":"5"},"next":{"block":{"type":"q1_tts","id":"tts4","inputs":{"TEXT":{"shadow":{"type":"text","id":"txt4","fields":{"TEXT":"Am I sad? Ha ha ha!"}}}},"next":{"block":{"type":"q1_action","id":"act4","fields":{"ACTION_CODE":"3005"},"next":{"block":{"type":"wait_last_motion_completion","id":"wait4","fields":{"TIMEOUT_SECONDS":"5"},"next":{"block":{"type":"q1_tts","id":"tts5","inputs":{"TEXT":{"shadow":{"type":"text","id":"txt5","fields":{"TEXT":"Feelings belong to the nurses."}}}},"next":{"block":{"type":"q1_action","id":"act5","fields":{"ACTION_CODE":"3007"},"next":{"block":{"type":"wait_last_motion_completion","id":"wait5","fields":{"TIMEOUT_SECONDS":"5"},"next":{"block":{"type":"q1_tts","id":"tts6","inputs":{"TEXT":{"shadow":{"type":"text","id":"txt6","fields":{"TEXT":"Friends? Fist bump!"}}}},"next":{"block":{"type":"q1_action","id":"act6","fields":{"ACTION_CODE":"3003"},"next":{"block":{"type":"wait_last_motion_completion","id":"wait6","fields":{"TIMEOUT_SECONDS":"5"}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}]}}}}
```

**Ensuite** : le pilote le ramène AU CENTRE.

## Acte 4 — Le final

**Où** : au centre, un mètre vide autour de lui.

| Il dit | Il fait |
|---|---|
| « We are not finished. » | geste de parole B |
| « Tomorrow, we ask a nurse. » | geste de parole A |
| « But tonight, we dance! » | danse A |

```json
{"schemaVersion":1,"type":"qy_blockly_canvas","canvas":{"name":"acte_4_final","robotTarget":"q1","updatedAt":1794768936292,"workspace":{"blocks":{"languageVersion":0,"blocks":[{"type":"q1_tts","id":"tts1","x":90,"y":130,"inputs":{"TEXT":{"shadow":{"type":"text","id":"txt1","fields":{"TEXT":"We are not finished."}}}},"next":{"block":{"type":"q1_action","id":"act1","fields":{"ACTION_CODE":"3013"},"next":{"block":{"type":"wait_last_motion_completion","id":"wait1","fields":{"TIMEOUT_SECONDS":"5"},"next":{"block":{"type":"q1_tts","id":"tts2","inputs":{"TEXT":{"shadow":{"type":"text","id":"txt2","fields":{"TEXT":"Tomorrow, we ask a nurse."}}}},"next":{"block":{"type":"q1_action","id":"act2","fields":{"ACTION_CODE":"3012"},"next":{"block":{"type":"wait_last_motion_completion","id":"wait2","fields":{"TIMEOUT_SECONDS":"5"},"next":{"block":{"type":"q1_tts","id":"tts3","inputs":{"TEXT":{"shadow":{"type":"text","id":"txt3","fields":{"TEXT":"But tonight, we dance!"}}}},"next":{"block":{"type":"q1_action","id":"act3","fields":{"ACTION_CODE":"3046"}}}}}}}}}}}}}}}}]}}}}
```

**Ensuite** : rien : la danse est le dernier bloc, pour que rien ne soit sauté après elle.

## Acte 5 — Merci

**Où** : au centre, quand la danse est finie.

| Il dit | Il fait |
|---|---|
| « Thank you! I am Q one. » | salue de la main |
| « And she is Iris. » | cœur avec les mains |

```json
{"schemaVersion":1,"type":"qy_blockly_canvas","canvas":{"name":"acte_5_merci","robotTarget":"q1","updatedAt":1794768936292,"workspace":{"blocks":{"languageVersion":0,"blocks":[{"type":"q1_tts","id":"tts1","x":90,"y":130,"inputs":{"TEXT":{"shadow":{"type":"text","id":"txt1","fields":{"TEXT":"Thank you! I am Q one."}}}},"next":{"block":{"type":"q1_action","id":"act1","fields":{"ACTION_CODE":"3004"},"next":{"block":{"type":"wait_last_motion_completion","id":"wait1","fields":{"TIMEOUT_SECONDS":"5"},"next":{"block":{"type":"q1_tts","id":"tts2","inputs":{"TEXT":{"shadow":{"type":"text","id":"txt2","fields":{"TEXT":"And she is Iris."}}}},"next":{"block":{"type":"q1_action","id":"act2","fields":{"ACTION_CODE":"3007"}}}}}}}}}}]}}}}
```

**Ensuite** : —.

## En réserve : les deux autres danses, seules

```json
{"schemaVersion":1,"type":"qy_blockly_canvas","canvas":{"name":"danse_b_seule","robotTarget":"q1","updatedAt":1794768936292,"workspace":{"blocks":{"languageVersion":0,"blocks":[{"type":"q1_action","id":"act1","x":150,"y":150,"fields":{"ACTION_CODE":"3047"}}]}}}}
```

```json
{"schemaVersion":1,"type":"qy_blockly_canvas","canvas":{"name":"danse_c_seule","robotTarget":"q1","updatedAt":1794768936292,"workspace":{"blocks":{"languageVersion":0,"blocks":[{"type":"q1_action","id":"act1","x":150,"y":150,"fields":{"ACTION_CODE":"3048"}}]}}}}
```

## Pour qu'il marche, tourne et s'asseye DANS le programme : ce qu'il me faut

La documentation du fabricant dit que le Q1 sait marcher, tourner, s'asseoir, se relever, et faire des figures (elle cite « boxing »,
« fly », trois poses d'entrée et une danse « locking »). Mais elle donne les noms pour les programmeurs, pas les noms des **blocs de
votre application**. Un nom de bloc deviné ne marcherait pas, et je n'en invente pas.

**Ce qu'il faut faire, une seule fois, cinq minutes** — comme vous l'avez fait pour le bloc « attendre » :

1. Dans l'application, créer un programme et y poser **un bloc de chaque sorte** que vous voulez utiliser : avancer, reculer, tourner,
   s'asseoir, se lever, et chaque figure ou geste des mains que vous voyez dans les menus.
2. Régler chaque bloc avec une valeur simple (par exemple : avancer de 50 centimètres, tourner d'un quart de tour).
3. L'exporter en texte et me le coller, avec une ligne qui dit ce que fait chaque bloc.

Avec ce texte, j'écris le spectacle complet en un seul programme : il entre en marchant, tourne vers le jury, s'assied pour parler de
Iris, se relève, fait ses figures et danse. Chaque moment restera à 5 secondes au plus.

## Ce qui est sûr, et ce qui ne l'est pas

- **Dans le programme que l'équipe a réglé** (dit par Hiba, pas vu par moi) : la parole, « fait signe » (3001), le cœur (3007), le « non » (3021),
  la danse A (3046), et « attendre 5 secondes ».
- **Pas encore vus** : saluer (3004), content (3005), encourager (3008), les gestes de parole (3012 à 3014), les danses B et C. Leurs numéros
  viennent de la liste du fabricant. Si l'un ne fait rien, me le dire : je le remplace.
- **La règle des 5 secondes** : je l'applique à la parole (six mots au plus). Je ne connais pas la durée de chaque geste : si un geste dure
  plus de 5 secondes et fait sauter la suite, me dire lequel.
