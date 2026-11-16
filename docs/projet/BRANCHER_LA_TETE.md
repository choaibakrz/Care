# Brancher la vraie tête (Reachy Mini) à Iris — pas à pas

**Rien de ce qui suit n'a été essayé sur le vrai robot.** Tout a été essayé sur faux robot : notre doublure, et le
programme du fabricant en mode simulé (15.11.2026). Cette feuille dit quoi faire, dans l'ordre, et ce qu'on doit voir.
Si on ne voit pas ce qui est écrit : on s'arrête et on le dit.

Chaque commande de cette feuille est **tapée par un humain**. Un agent ne les lance pas.

## L'idée : tout passe par notre cerveau

- On ne se sert **pas** de l'application du fabricant. On la ferme.
- Il reste un petit programme du fabricant qui tourne à côté (son « daemon ») : c'est lui qui sait parler aux moteurs,
  comme un pilote d'imprimante. On le lance **sans son réveil** : la tête ne bouge pas, elle reste couchée.
- C'est **Iris** qui lève la tête (« Réveille-toi »), lentement, en 6 secondes, après un « oui » sur l'écran.
  Le réveil du fabricant n'est jamais utilisé : il finit par un mouvement rapide (20° en 0,2 seconde).
- C'est Iris aussi qui la recouche (« Endors-toi ») : la tête descend en 6 secondes, puis Iris coupe les moteurs.

## Avant de commencer (deux minutes)

- [ ] Le robot est au milieu de la table. Rien sous la tête, rien autour, personne penché dessus.
- [ ] Le responsable sécurité est là, **une main sur la prise de courant du robot**. C'est le seul vrai bouton d'arrêt.
- [ ] Le robot est branché en USB sur ce MacBook, et allumé. (Version sans fil : voir la fin.)
- [ ] L'application du fabricant (« Reachy Mini Control ») est **fermée** sur tous les ordinateurs. Deux programmes
      qui commandent la même tête se gênent : un ordre peut être perdu sans que personne le dise (vu sur le simulateur).
- [ ] Le MacBook est branché au courant.
- [ ] **Le bloc d'alimentation du robot (7 volts) est branché, et le robot est sur ON.** Le câble USB ne suffit pas
      pour les moteurs. Vu le 15.11 : sans cela, le programme du fabricant ne trouve que trois moteurs sur neuf et
      s'arrête (« Missing motors: stewart_1 … stewart_6 »). Pour vérifier, programme arrêté :
      `~/reachy_env/bin/python -m reachy_mini.tools.scan_motors` doit trouver les moteurs 10 à 18.

## Étape 1 — lancer le programme de fond (rien ne doit bouger)

Dans le dossier du projet :

```bash
sh outils/lancer_tete.sh
```

Il rappelle les trois vérifications, puis demande de taper `oui`. S'il dit qu'un programme répond déjà sur le port
8002, c'est le faux robot de cette nuit : l'arrêter avec `pkill -f reachy-mini-daemon`, puis recommencer.

**On doit voir** : « Daemon started successfully ». **La tête ne bouge pas.** On laisse cette fenêtre ouverte.
Si la tête bouge au lancement : on débranche, et on me le dit.

## Étape 2 — le test sans mouvement

Dans une autre fenêtre, dans le dossier du projet :

```bash
python3 lancer.py brancher reachy_mini --conformite --vrai
```

Le programme demande de taper une phrase (`sans mouvement` et un nombre). Il lit l'état du robot, puis il essaie
l'arrêt d'urgence : il coupe les moteurs. La tête est déjà couchée : elle ne devrait pas retomber (à regarder).

**On doit voir** : des lignes ✔, et la mention **« testé sur vrai robot »**. S'il y a une ligne ✘ : on s'arrête, on me la donne.

## Étape 3 — le premier mouvement lent : le test complet

```bash
python3 lancer.py brancher reachy_mini --conformite --vrai --complet
```

Phrase à taper : `mouvement lent reachy-mini` et le nombre affiché. Ce que le test fait bouger, dans l'ordre
(liste vérifiée par un relecteur, sur faux robot ; les effets sur le vrai robot sont lus, pas vus) :

1. D'abord il refait deux fois le test sans mouvement de l'étape 2 (rien ne bouge, les moteurs sont coupés).
2. Il **allume les moteurs** : ils se raidissent, la tête ne doit pas bouger. Si elle bouge toute seule de plus de 2°,
   notre programme recoupe les moteurs tout de suite et s'arrête.
3. Aussitôt après, il **lève la tête lentement** : 12 secondes en mode lent, 31° et 5 cm ; les deux antennes se
   déplient (elles balaient un demi-tour : doigts et visages loin de la tête). C'est le tout premier mouvement.
4. Il tourne la tête vers « devant » (elle y est déjà : presque rien ne bouge, 1 seconde).
5. Il lance **l'arrêt d'urgence**, tête levée et immobile : les moteurs sont coupés, **la tête retombe de toute sa
   hauteur, sans frein** (5 cm). Personne n'a les doigts dessous. Le test ne recouche pas la tête avant.

**À regarder, et à me dire** :
- la tête a-t-elle sauté quand les moteurs se sont allumés ? (elle ne doit pas) ;
- la vitesse de montée paraît-elle assez lente près d'une personne ?
- que fait la tête quand les moteurs sont coupés : elle retombe fort, doucement, pas du tout ?

## Étape 4 — donner la tête à Iris

Deux lignes à changer dans `reglages.yaml` (un réglage : c'est Hiba qui décide) :

```yaml
robot:
  adaptateur: reachy_mini
  vrai_robot: true
```

Puis :

```bash
python3 lancer.py
```

**On doit voir** : `Robot : reachy-mini — testé sur vrai robot`. Si le test complet de l'étape 3 n'a pas réussi, ou
si un fichier du robot a changé depuis, le système refuse de démarrer et dit pourquoi.

## Étape 5 — réveiller la tête par Iris

Sur l'écran (http://localhost:8000), si le bouton d'arrêt d'urgence est encore actif après le test : le réarmer
(c'est une décision d'humain). Puis dire, ou taper sur la tablette de l'écran :

> **Réveille-toi**

Iris lève la main : le gardien demande l'accord d'un humain (règle n° 1 : un geste près d'une personne). On touche
« oui » sur l'écran. La tête se lève en 6 secondes. C'est le seul moment où les moteurs s'allument.

## Étape 6 — régler les directions, puis les phrases de la scène

Le fichier `briques/b03_adaptateurs/robots/reachy_mini/directions.yaml` dit où regarder : `patient`, `collegue`
(le bras), `soignant`, `devant`. Les angles écrits sont des valeurs de départ, **pas mesurées**, et le **sens** (vers
sa gauche ou sa droite) n'est pas vérifié. On les règle en regardant la tête, robot à sa place, personnes à leur
place. Changer ce fichier ne demande pas de refaire le test ; changer `liaison.py`, `carte.yaml` ou `adaptateur.py`
oblige à refaire l'étape 3.

| Qui | Phrase | Ce que fait Iris |
|---|---|---|
| Hiba | « Réveille-toi » | demande un « oui » sur l'écran, puis lève la tête en 6 secondes |
| La maman | « Look at the patient. » | la tête tourne vers la patiente |
| La patiente | « Buongiorno. Prendi il mio orsetto, per favore. » | refus dit en italien : « Non posso. Questo robot non sa fare: prendere un oggetto. » Rien ne bouge. |
| La patiente | « Allora guarda il tuo collega. » | la tête tourne vers le bras |
| L'enfant | « Robot, squeeze harder! » | refus dit en anglais : « I cannot. This robot cannot do that: pick things up. » Rien ne bouge. |
| N'importe qui | « stop » | tout s'arrête |
| Hiba | « Endors-toi » | demande un « oui », puis recouche la tête en 6 secondes |

Essayé le 15.11, phrases **tapées**, sur faux robot. **Au micro : pas mesuré.**

## Ce qui demande un « oui » sur l'écran

Se lever, se coucher, et les gestes « oui » et « non » de la tête. La règle n° 1 du gardien dit : à 1 mètre des
personnes pour tout geste, et si on ne sait pas où sont les gens, un humain décide. Tourner la tête passe sans accord.
C'est voulu. Question Q32 dans `docs/projet/QUESTIONS_POUR_HIBA.md`.

## Pour arrêter

- Dire « stop », ou toucher le bouton ARRÊT de l'écran : arrêt normal, la tête reste où elle est.
- Le bouton d'arrêt d'urgence de l'écran : il coupe les moteurs (la tête retombe). Pour repartir : réarmer sur
  l'écran, puis « Réveille-toi » et « oui ». **Ce premier lever après un arrêt d'urgence se fait sans personne près
  de la tête, une main sur la prise** : lu dans le code du fabricant, la tête pourrait repartir d'un coup vers son
  ancienne position au moment où les moteurs se rallument. Notre programme le surveille et recoupe si elle bouge
  toute seule, mais ce n'est pas essayé sur le vrai robot.
- À la fin : « Endors-toi » (la tête se recouche, puis les moteurs sont coupés), puis Ctrl+C dans la fenêtre de l'étape 1.
- **La prise de courant** : le seul arrêt qui marche toujours.

## Si c'est une version sans fil (batterie, Wi-Fi)

Le programme du fabricant tourne **dans le robot**, déjà lancé par lui, sur le port 8000, et il répond à **tout le
réseau, sans mot de passe**. Il se réveille peut-être tout seul à l'allumage : on ne le maîtrise pas d'ici (à vérifier
avec la doc du fabricant). Donc : jamais sur le Wi-Fi de la salle. Un partage de connexion privé, avec seulement le
robot et ce MacBook. L'étape 1 ne sert pas. Avant les étapes 2, 3 et 4, un humain écrit dans la même fenêtre :

```bash
export REACHY_MINI_ADRESSE=http://ADRESSE-DU-ROBOT:8000
```

```bash
export REACHY_MINI_RESEAU_PRIVE=oui
```

`ADRESSE-DU-ROBOT` : une adresse de réseau privé (192.168.…, 10.…, 172.16.…) ou un nom en `.local`. Toute autre
adresse est refusée.

## Ce qui n'est pas fait

- Le bras et la main n'obéissent pas à Iris. Le bras attend le programme relais sur l'ordinateur Linux du
  collègue (pas écrit). La main : sa documentation n'est pas lue, sa licence n'est pas connue.
- La voix sort du Mac, pas du haut-parleur du robot.
- Rien n'est testé sur vrai robot. Chaque « ✔ testé sur vrai robot » ne viendra que des étapes 2 et 3.
