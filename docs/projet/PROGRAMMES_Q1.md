# Les programmes du petit robot Q1 — à coller à la main dans son application

*Écrits le 15.11.2026 par l'outil `briques/clinique/programmes_q1.py`. **Notre système n'envoie rien au robot** : une
personne copie le texte et le colle dans l'application, comme pour « boulangerie ». Non testé sur vrai robot par notre
système. Nous connaissons deux blocs : « dire un texte » (`q1_tts`) et « faire un geste » (`q1_action`), avec un seul
geste : le poing contre poing (code 3003, exporté par l'équipe). Rien d'autre n'est écrit.*

Pour en fabriquer un autre :

```bash
python3 -m briques.clinique.programmes_q1 --nom mon_programme "La phrase à dire." geste:fist_bump
```

Le fichier arrive dans `mesures/q1/`. Une phrase : 200 caractères au plus. Dix étapes au plus.

## `essai_enchainement`

ESSAI 1 — à coller en premier. Si le robot dit « One », « Two », « Three » : plusieurs blocs à la suite marchent. S'il ne dit que « One », ou rien : ils ne marchent pas, et on reste à un seul bloc par programme.

Le robot dit « One. », puis dit « Two. », puis dit « Three. ».

```json
{"schemaVersion":1,"type":"qy_blockly_canvas","canvas":{"name":"essai_enchainement","robotTarget":"q1","updatedAt":1794768936292,"workspace":{"blocks":{"languageVersion":0,"blocks":[{"type":"q1_tts","id":"tts1","inputs":{"TEXT":{"shadow":{"type":"text","id":"txt1","fields":{"TEXT":"One."}}}},"next":{"block":{"type":"q1_tts","id":"tts2","inputs":{"TEXT":{"shadow":{"type":"text","id":"txt2","fields":{"TEXT":"Two."}}}},"next":{"block":{"type":"q1_tts","id":"tts3","inputs":{"TEXT":{"shadow":{"type":"text","id":"txt3","fields":{"TEXT":"Three."}}}}}}}},"x":90,"y":130}]}}}}
```

## `essai_parole_puis_geste`

ESSAI 2 — une phrase, puis le poing contre poing, dans le même programme. S'il dit « Hello. » puis tend le poing : on peut mettre la parole et le geste ensemble.

Le robot dit « Hello. », puis fait le geste : poing contre poing (fist bump).

```json
{"schemaVersion":1,"type":"qy_blockly_canvas","canvas":{"name":"essai_parole_puis_geste","robotTarget":"q1","updatedAt":1794768936292,"workspace":{"blocks":{"languageVersion":0,"blocks":[{"type":"q1_tts","id":"tts1","x":90,"y":130,"inputs":{"TEXT":{"shadow":{"type":"text","id":"txt1","fields":{"TEXT":"Hello."}}}},"next":{"block":{"type":"q1_action","id":"act1","fields":{"ACTION_CODE":"3003"}}}}]}}}}
```

## `essai_italien`

ESSAI 3 — la voix du robot sait-elle dire de l'italien ? À écouter par la personne italienne.

Le robot dit « Buongiorno. ».

```json
{"schemaVersion":1,"type":"qy_blockly_canvas","canvas":{"name":"essai_italien","robotTarget":"q1","updatedAt":1794768936292,"workspace":{"blocks":{"languageVersion":0,"blocks":[{"type":"q1_tts","id":"tts1","inputs":{"TEXT":{"shadow":{"type":"text","id":"txt1","fields":{"TEXT":"Buongiorno."}}}},"x":90,"y":130}]}}}}
```

## `essai_espagnol`

ESSAI 4 — et de l'espagnol ? À écouter par un hispanophone.

Le robot dit « Buenos días. Iris significa: mira. ».

```json
{"schemaVersion":1,"type":"qy_blockly_canvas","canvas":{"name":"essai_espagnol","robotTarget":"q1","updatedAt":1794768936292,"workspace":{"blocks":{"languageVersion":0,"blocks":[{"type":"q1_tts","id":"tts1","inputs":{"TEXT":{"shadow":{"type":"text","id":"txt1","fields":{"TEXT":"Buenos días. Iris significa: mira."}}}},"x":90,"y":130}]}}}}
```

## `essai_francais`

ESSAI 5 — et du français ?

Le robot dit « Bonjour. Je suis le petit robot. ».

```json
{"schemaVersion":1,"type":"qy_blockly_canvas","canvas":{"name":"essai_francais","robotTarget":"q1","updatedAt":1794768936292,"workspace":{"blocks":{"languageVersion":0,"blocks":[{"type":"q1_tts","id":"tts1","inputs":{"TEXT":{"shadow":{"type":"text","id":"txt1","fields":{"TEXT":"Bonjour. Je suis le petit robot."}}}},"x":90,"y":130}]}}}}
```

## `scene_2_giulia_it`

SCÈNE — le bonjour du matin, en italien. PHRASE À FAIRE RELIRE par la personne italienne avant de la jouer.

Le robot dit « Buongiorno, signora Giulia. Sono le sette. Le parlo da destra, il suo orecchio buono. L'infermiera arriva con il tè. ».

```json
{"schemaVersion":1,"type":"qy_blockly_canvas","canvas":{"name":"scene_2_giulia_it","robotTarget":"q1","updatedAt":1794768936292,"workspace":{"blocks":{"languageVersion":0,"blocks":[{"type":"q1_tts","id":"tts1","inputs":{"TEXT":{"shadow":{"type":"text","id":"txt1","fields":{"TEXT":"Buongiorno, signora Giulia. Sono le sette. Le parlo da destra, il suo orecchio buono. L'infermiera arriva con il tè."}}}},"x":90,"y":130}]}}}}
```

## `scene_2_giulia_en`

SCÈNE — le même bonjour, en anglais : à prendre si l'italien sort mal de la voix du robot.

Le robot dit « Good morning, Mrs Giulia. It is seven o'clock. I am speaking on your right side, your good ear. The nurse is coming with your tea. ».

```json
{"schemaVersion":1,"type":"qy_blockly_canvas","canvas":{"name":"scene_2_giulia_en","robotTarget":"q1","updatedAt":1794768936292,"workspace":{"blocks":{"languageVersion":0,"blocks":[{"type":"q1_tts","id":"tts1","inputs":{"TEXT":{"shadow":{"type":"text","id":"txt1","fields":{"TEXT":"Good morning, Mrs Giulia. It is seven o'clock. I am speaking on your right side, your good ear. The nurse is coming with your tea."}}}},"x":90,"y":130}]}}}}
```

## `scene_poing`

SCÈNE — le poing contre poing, seul. C'est le programme exporté par l'équipe, réécrit par l'outil (un seul bloc : la forme vue marcher).

Le robot fait le geste : poing contre poing (fist bump).

```json
{"schemaVersion":1,"type":"qy_blockly_canvas","canvas":{"name":"scene_poing","robotTarget":"q1","updatedAt":1794768936292,"workspace":{"blocks":{"languageVersion":0,"blocks":[{"type":"q1_action","id":"act1","x":150,"y":150,"fields":{"ACTION_CODE":"3003"}}]}}}}
```

## `scene_2_giulia_it_et_poing`

SCÈNE — le bonjour en italien PUIS le poing contre poing, en un seul programme. **Seulement si l'essai 2 a marché.**

Le robot dit « Buongiorno, signora Giulia. Sono le sette. Le parlo da destra, il suo orecchio buono. L'infermiera arriva con il tè. », puis fait le geste : poing contre poing (fist bump).

```json
{"schemaVersion":1,"type":"qy_blockly_canvas","canvas":{"name":"scene_2_giulia_it_et_poing","robotTarget":"q1","updatedAt":1794768936292,"workspace":{"blocks":{"languageVersion":0,"blocks":[{"type":"q1_tts","id":"tts1","x":90,"y":130,"inputs":{"TEXT":{"shadow":{"type":"text","id":"txt1","fields":{"TEXT":"Buongiorno, signora Giulia. Sono le sette. Le parlo da destra, il suo orecchio buono. L'infermiera arriva con il tè."}}}},"next":{"block":{"type":"q1_action","id":"act1","fields":{"ACTION_CODE":"3003"}}}}]}}}}
```

## `scene_1_bonjour_en`

EN RÉSERVE — le robot se présente, et dit lui-même la vérité sur ce qu'il sait faire (anglais).

Le robot dit « Hello. I am the small robot. Iris prepared my words. A human pasted them into my app. I cannot hear you yet. ».

```json
{"schemaVersion":1,"type":"qy_blockly_canvas","canvas":{"name":"scene_1_bonjour_en","robotTarget":"q1","updatedAt":1794768936292,"workspace":{"blocks":{"languageVersion":0,"blocks":[{"type":"q1_tts","id":"tts1","x":90,"y":130,"inputs":{"TEXT":{"shadow":{"type":"text","id":"txt1","fields":{"TEXT":"Hello. I am the small robot. Iris prepared my words. A human pasted them into my app. I cannot hear you yet."}}}}}]}}}}
```

## `scene_3_fin_en`

EN RÉSERVE — une dernière phrase (seulement si on choisit de finir par le petit robot).

Le robot dit « Thank you. One day, I hope my maker opens a door for Iris. ».

```json
{"schemaVersion":1,"type":"qy_blockly_canvas","canvas":{"name":"scene_3_fin_en","robotTarget":"q1","updatedAt":1794768936292,"workspace":{"blocks":{"languageVersion":0,"blocks":[{"type":"q1_tts","id":"tts1","x":90,"y":130,"inputs":{"TEXT":{"shadow":{"type":"text","id":"txt1","fields":{"TEXT":"Thank you. One day, I hope my maker opens a door for Iris."}}}}}]}}}}
```

## Pour un autre geste

Comme pour le poing contre poing : dans l'application, fabriquer un programme avec ce geste (ou une marche, une attente,
un tour de tête…), l'**exporter** en texte, et me le donner. J'ajoute alors son code à l'outil. Je n'invente aucun code.
