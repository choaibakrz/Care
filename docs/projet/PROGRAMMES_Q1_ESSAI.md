# Le Q1 — essai de 30 secondes : paroles, gestes, et une danse à la fin

*Écrit le 15.11.2026 par l'outil `briques/clinique/programmes_q1.py`. À coller à la main dans l'application du Q1 :
notre système n'envoie rien au robot. **Rien de ce qui suit n'est essayé sur le robot.***

**D'où viennent les numéros des gestes.** Du kit public du fabricant (fichier `McPresetMotion.msg`, partie « Q », lu le
15.11.2026). Le 3003 y est « fist bump » : c'est bien le numéro que l'équipe a exporté et vu marcher. Les autres
numéros viennent de la même liste, mais **personne ne les a encore vus marcher dans l'application** : c'est ce
que cet essai va dire.

**Avant de lancer** : le robot debout, au milieu d'un espace vide d'un mètre autour de lui, loin du bord de la table,
personne à portée de ses bras. La danse fait bouger tout le corps.

## 1. D'abord, la danse seule (dix secondes pour savoir si le numéro marche)

```json
{"schemaVersion":1,"type":"qy_blockly_canvas","canvas":{"name":"essai_danse_a","robotTarget":"q1","updatedAt":1794768936292,"workspace":{"blocks":{"languageVersion":0,"blocks":[{"type":"q1_action","id":"act1","x":150,"y":150,"fields":{"ACTION_CODE":"3046"}}]}}}}
```

Si le robot danse : le numéro 3046 marche dans l'application. S'il ne fait rien ou affiche une erreur : me le dire,
et exporter depuis l'application un programme qui contient une danse, comme pour le poing contre poing.

Les deux autres danses de la liste du fabricant :

```json
{"schemaVersion":1,"type":"qy_blockly_canvas","canvas":{"name":"essai_danse_b","robotTarget":"q1","updatedAt":1794768936292,"workspace":{"blocks":{"languageVersion":0,"blocks":[{"type":"q1_action","id":"act1","x":150,"y":150,"fields":{"ACTION_CODE":"3047"}}]}}}}
```

```json
{"schemaVersion":1,"type":"qy_blockly_canvas","canvas":{"name":"essai_danse_c","robotTarget":"q1","updatedAt":1794768936292,"workspace":{"blocks":{"languageVersion":0,"blocks":[{"type":"q1_action","id":"act1","x":150,"y":150,"fields":{"ACTION_CODE":"3048"}}]}}}}
```

## 2. L'essai de 30 secondes

Dans l'ordre : il salue de la main · « Hello! I am Q one. I work with Iris. » · un geste de quelqu'un qui parle ·
« Iris keeps watch. I bring what the nurse is missing. » · un cœur avec les mains ·
« Before I move, I ask Iris. If she says no, I stop. » · le geste « non » · « And now, we dance! » · la danse A · « Thank you! »

```json
{"schemaVersion":1,"type":"qy_blockly_canvas","canvas":{"name":"essai_30_secondes","robotTarget":"q1","updatedAt":1794768936292,"workspace":{"blocks":{"languageVersion":0,"blocks":[{"type":"q1_action","id":"act1","x":150,"y":150,"fields":{"ACTION_CODE":"3004"},"next":{"block":{"type":"q1_tts","id":"tts1","inputs":{"TEXT":{"shadow":{"type":"text","id":"txt1","fields":{"TEXT":"Hello! I am Q one. I work with Iris."}}}},"next":{"block":{"type":"q1_action","id":"act2","fields":{"ACTION_CODE":"3012"},"next":{"block":{"type":"q1_tts","id":"tts2","inputs":{"TEXT":{"shadow":{"type":"text","id":"txt2","fields":{"TEXT":"Iris keeps watch. I bring what the nurse is missing."}}}},"next":{"block":{"type":"q1_action","id":"act3","fields":{"ACTION_CODE":"3007"},"next":{"block":{"type":"q1_tts","id":"tts3","inputs":{"TEXT":{"shadow":{"type":"text","id":"txt3","fields":{"TEXT":"Before I move, I ask Iris. If she says no, I stop."}}}},"next":{"block":{"type":"q1_action","id":"act4","fields":{"ACTION_CODE":"3021"},"next":{"block":{"type":"q1_tts","id":"tts4","inputs":{"TEXT":{"shadow":{"type":"text","id":"txt4","fields":{"TEXT":"And now, we dance!"}}}},"next":{"block":{"type":"q1_action","id":"act5","fields":{"ACTION_CODE":"3046"},"next":{"block":{"type":"q1_tts","id":"tts5","inputs":{"TEXT":{"shadow":{"type":"text","id":"txt5","fields":{"TEXT":"Thank you!"}}}}}}}}}}}}}}}}}}}}}}}]}}}}
```

## 2 bis. Après le premier essai (15.11 au soir) : la même scène en cinq petits programmes

Vu par l'équipe sur le robot : il danse dès le début, en même temps qu'il parle. Les blocs d'un programme ne
s'attendent donc pas les uns les autres. Tant que nous n'avons pas un bloc « attendre », le plus sûr est de
**couper la scène en petits programmes d'un geste et d'une phrase**, que le pilote lance l'un après l'autre.
Le geste se fait alors pendant la phrase, et c'est le pilote qui donne le rythme.

**`pas_1_bonjour`** — il salue de la main en disant bonjour

```json
{"schemaVersion":1,"type":"qy_blockly_canvas","canvas":{"name":"pas_1_bonjour","robotTarget":"q1","updatedAt":1794768936292,"workspace":{"blocks":{"languageVersion":0,"blocks":[{"type":"q1_action","id":"act1","x":150,"y":150,"fields":{"ACTION_CODE":"3004"},"next":{"block":{"type":"q1_tts","id":"tts1","inputs":{"TEXT":{"shadow":{"type":"text","id":"txt1","fields":{"TEXT":"Hello! I am Q one. I work with Iris."}}}}}}}]}}}}
```

**`pas_2_travail`** — un geste de quelqu'un qui parle, avec sa phrase

```json
{"schemaVersion":1,"type":"qy_blockly_canvas","canvas":{"name":"pas_2_travail","robotTarget":"q1","updatedAt":1794768936292,"workspace":{"blocks":{"languageVersion":0,"blocks":[{"type":"q1_action","id":"act1","x":150,"y":150,"fields":{"ACTION_CODE":"3012"},"next":{"block":{"type":"q1_tts","id":"tts1","inputs":{"TEXT":{"shadow":{"type":"text","id":"txt1","fields":{"TEXT":"Iris keeps watch. I bring what the nurse is missing."}}}}}}}]}}}}
```

**`pas_3_coeur`** — un cœur avec les mains

```json
{"schemaVersion":1,"type":"qy_blockly_canvas","canvas":{"name":"pas_3_coeur","robotTarget":"q1","updatedAt":1794768936292,"workspace":{"blocks":{"languageVersion":0,"blocks":[{"type":"q1_action","id":"act1","x":150,"y":150,"fields":{"ACTION_CODE":"3007"},"next":{"block":{"type":"q1_tts","id":"tts1","inputs":{"TEXT":{"shadow":{"type":"text","id":"txt1","fields":{"TEXT":"I do it for the people who care."}}}}}}}]}}}}
```

**`pas_4_non`** — le geste « non », avec la phrase sur Iris

```json
{"schemaVersion":1,"type":"qy_blockly_canvas","canvas":{"name":"pas_4_non","robotTarget":"q1","updatedAt":1794768936292,"workspace":{"blocks":{"languageVersion":0,"blocks":[{"type":"q1_action","id":"act1","x":150,"y":150,"fields":{"ACTION_CODE":"3021"},"next":{"block":{"type":"q1_tts","id":"tts1","inputs":{"TEXT":{"shadow":{"type":"text","id":"txt1","fields":{"TEXT":"Before I move, I ask Iris. If she says no, I stop."}}}}}}}]}}}}
```

**`pas_5_danse`** — la danse

```json
{"schemaVersion":1,"type":"qy_blockly_canvas","canvas":{"name":"pas_5_danse","robotTarget":"q1","updatedAt":1794768936292,"workspace":{"blocks":{"languageVersion":0,"blocks":[{"type":"q1_action","id":"act1","x":150,"y":150,"fields":{"ACTION_CODE":"3046"},"next":{"block":{"type":"q1_tts","id":"tts1","inputs":{"TEXT":{"shadow":{"type":"text","id":"txt1","fields":{"TEXT":"And now, we dance!"}}}}}}}]}}}}
```

**Un essai pour comprendre l'ordre** : huit mots, puis la danse. Regarder si la danse part dès le premier mot, ou après le huitième.

```json
{"schemaVersion":1,"type":"qy_blockly_canvas","canvas":{"name":"essai_parole_puis_danse","robotTarget":"q1","updatedAt":1794768936292,"workspace":{"blocks":{"languageVersion":0,"blocks":[{"type":"q1_tts","id":"tts1","x":90,"y":130,"inputs":{"TEXT":{"shadow":{"type":"text","id":"txt1","fields":{"TEXT":"One. Two. Three. Four. Five. Six. Seven. Eight."}}}},"next":{"block":{"type":"q1_action","id":"act1","fields":{"ACTION_CODE":"3046"}}}}]}}}}
```

## 3. Ce qu'il faut me dire après l'essai

1. **La danse seule marche-t-elle ?** (oui / non / erreur affichée)
2. **Les dix blocs s'enchaînent-ils**, ou le robot s'arrête-t-il après le premier ?
3. **Parle-t-il pendant le geste, ou après ?** (pour savoir si un geste « qui parle » peut accompagner une phrase)
4. **Combien de secondes dure le tout ?** (je l'ai calculé à environ 30 secondes, sans rien mesurer)
5. **Combien de secondes dure la danse ?**

## 4. Les seize gestes de la liste du fabricant

| Nom dans l'outil | Numéro | Ce que dit le fabricant | Vu marcher dans l'application ? |
|---|---|---|---|
| `faire_signe` | 3001 | beckon / wave | pas encore |
| `serrer_la_main` | 3002 | shake hands | pas encore |
| `fist_bump` | 3003 | fist bump | **oui** (exporté par l’équipe) |
| `saluer` | 3004 | wave | pas encore |
| `content` | 3005 | emotion — happy | pas encore |
| `coeur` | 3007 | heart with both hands | pas encore |
| `encourager` | 3008 | come on | pas encore |
| `s_etirer` | 3010 | stretch | pas encore |
| `parler_a` | 3012 | speaking action A | pas encore |
| `parler_b` | 3013 | speaking action B | pas encore |
| `parler_c` | 3014 | speaking action C | pas encore |
| `embrasser` | 3018 | embrace | pas encore |
| `refuser` | 3021 | reject | pas encore |
| `danse_a` | 3046 | dance moves A | pas encore |
| `danse_b` | 3047 | dance moves B | pas encore |
| `danse_c` | 3048 | dance moves C | pas encore |

Pour écrire un autre programme :

```bash
python3 -m briques.clinique.programmes_q1 --nom mon_essai geste:saluer "Hello." geste:danse_b
```

**La marche** n'est pas dans cette liste : c'est un autre bloc de l'application, dont je ne connais pas le nom.
Pour que le robot marche dans un programme, exporter depuis l'application un petit programme qui le fait avancer.
