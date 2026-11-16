# Fiche d'ébauche — main Leadtron DH116 (main gauche, 6 moteurs)

**Non testé sur vrai robot** : c'est vrai de la version d'aujourd'hui de l'ébauche (`robots/leadtron_dh116/`), qui n'a
tourné qu'avec une doublure (une fausse main) : **testé sur faux robot**. Une version **d'avant** a été essayée sur la
vraie main le 15.11.2026 (voir « Le premier essai réel » et « Le deuxième essai réel », plus bas) ; les limites et
les gestes ont été changés **après**, et ne sont **pas essayés sur la vraie main**. Le test de conformité sur la vraie
main est **à refaire**.
Cette fiche dit ce qui a été lu dans le kit du fabricant le **15.11.2026**, ce qui a été vu, et ce qui reste **à vérifier**.

## Ce que c'est
Une main robotique seule (pas de bras), main gauche, avec **6 moteurs** : pouce (écartement), pouce (flexion), index,
majeur, annulaire, auriculaire. Elle est reliée au MacBook par un boîtier USB appelé « CANFD Analyser » (il traduit
l'USB vers le câble de données de la main). Elle est posée ou fixée sur une table : elle ne se déplace pas.

## Ce que l'essai humain du 15.11.2026 a montré
(Rapporté à l'auteur de cette ébauche dans la demande du 15.11.2026. Il ne l'a pas vu lui-même.)
- **La main répond au logiciel du fabricant sur ce MacBook** : elle a bougé, conduite par un humain. C'est le logiciel
  du fabricant qui a parlé à la main, pas notre système. Cela ne dit rien de notre liaison.
- **Alimentation : l'étiquette de la boîte dit 12 à 24 V.** Un manuel en ligne disait 12 à 48 V. **C'est l'étiquette
  qui compte** : jamais plus de 24 V.
- **Le boîtier USB ne se déclare à l'ordinateur qu'avec un câble à grande fiche (USB-A).** Avec un autre câble,
  l'ordinateur ne le voit pas.

## Le premier essai réel (15.11.2026) : ce qui s'est passé sur la vraie main
Rapporté par le coordinateur à l'auteur de cette fiche, qui ne l'a pas vu. Main VIDE, commandes tapées par Hiba, avec
la version de l'ébauche de ce moment-là (limites : vitesse 2500, courant 200).

- **Réussi** : les deux commandes du test de conformité (`--vrai`, puis `--vrai --complet`). « preparer_la_main » a
  ouvert la main. Puis, par le système entier, « prépare la main » : réussi en 2 secondes.
- **Raté, et dit raté** : « tiens doucement », avec des cibles de 800 et 600 et un courant de **150 pour mille**. Le
  pouce (flexion) s'est arrêté à 536 positions de sa cible de 600 (il n'avait avancé que de 64). L'auriculaire a dit
  « couple atteint » sans avoir avancé (à 784 de sa cible de 800). Les quatre autres moteurs sont arrivés.
- **Ensuite, la main est restée inutilisable** : « prépare la main » a raté (« la mise en position de départ n'est pas
  finie après 12 s ») ; redemandé, il a été refusé (« la main bouge déjà ») ; « tiens doucement » a été refusé (« main
  pas préparée »). Il a fallu redémarrer.
- **Hypothèse, pas prouvée** : 150 pour mille ne suffit pas au pouce et à l'auriculaire ; et cette petite limite de
  courant est restée dans la main, si bien que la mise en position de départ suivante n'a pas pu finir.

**Décision de Hiba (responsable du projet), le 15.11.2026 : « personne ne s'approche de la main, seuls des objets
seront à son contact ; ne pas être trop prudent ».** Ce qui a été changé ensuite (rien de cela n'est essayé sur la vraie main) :
1. les limites sont relevées : courant 600 pour mille (au lieu de 200), vitesse 5000 (au lieu de 2500) ; la position
   reste à 6000 ; « ouvrir_la_main » utilise 500 ; « tenir_doucement » : courant 400, positions 3000, 2500, 3500 ×4 ;
2. avant chaque mise en position de départ, la liaison écrit pour chaque moteur sa vitesse et son courant les plus
   grands (5000 et 600), et demande au kit de les envoyer tout de suite (`apply_motion_params`) ; le délai passe de
   12 à 20 secondes ;
3. si la main est dite en mouvement quand on demande « prépare la main », la liaison envoie d'abord un arrêt, attend
   au plus une demi-seconde et relit. Elle ne refuse que si les doigts changent encore de place ;
4. un nouveau geste, « bouger_les_doigts » (voir la table plus bas).

## Le deuxième essai réel (15.11.2026), et ce qui a changé ensuite
Rapporté par le coordinateur ; l'auteur de cette fiche ne l'a pas vu. Avec les limites 5000 et 600 : **les gestes
marchent**, mais « les doigts n'ont pas assez de force pour tenir le doudou et les doigts ne bougent pas très bien ».

**Décision de Hiba (responsable du projet) : « je te laisse faire le max de ton intelligence, je veux vraiment que tu
me sortes des commandes qui sortent de l'ordinaire, je veux que ça fasse un effet waouh de suite ».** Son cadre reste
le même : personne ne s'approche de la main, seuls des objets la touchent.

Ce qui a été changé (**rien de cela n'est essayé sur la vraie main**) :
1. **Les limites sont maintenant les valeurs des exemples du fabricant**, choisies par Hiba pour une main qui ne touche
   que des objets : courant 1000 pour mille (toute la force), vitesse 20000 (toute la course en une demi-seconde),
   position 10000 (toute la course). Le logiciel du fabricant s'en sert ; **notre système ne les a jamais essayées sur
   la vraie main**. À ces valeurs, **jamais un doigt de personne dans la main**.
2. **Les gestes sont décrits dans un fichier**, `robots/leadtron_dh116/gestes.yaml`, que l'équipe règle sans refaire le
   test de conformité : une suite d'étapes (six positions, une vitesse, un courant, une pause). La liaison relit le
   fichier à chaque geste et refuse tout ce qui sort des limites (rien ne part). `postures.yaml` n'est plus lu.
3. **Quatorze gestes** (table ci-dessous). Toutes les positions sont des valeurs de départ, **pas mesurées, à régler
   sur la vraie main**, surtout celles du pouce.

| Geste | Ce qu'il fait | Étapes | Durée ESTIMÉE (calculée, pas mesurée) |
|---|---|---|---|
| `preparer_la_main` | allume, règle, mise en position de départ : la main s'ouvre (écrit dans liaison.py) | — | 2 s vues au premier essai réel |
| `ouvrir_la_main` | tout à 0 | 1 | moins d'1 s (0,8 s depuis le poing) |
| `tenir_doucement` | prise douce : pouce 5000/5000, doigts 6000, vitesse 6000, courant 600 | 1 | 1,1 s |
| `attraper` | tenir FORT le doudou : les doigts à 8500, puis le pouce à 7000 ; courant 1000 | 2 | 1,8 s |
| `bouger_les_doigts` | fermer à 7000 (pouce à 3000), rouvrir, trois fois | 6 | 6,2 s |
| `poing` | les quatre doigts à fond, puis le pouce par-dessus | 2 | 1,8 s |
| `victoire` | annulaire et auriculaire repliés, pouce par-dessus, index et majeur tendus | 2 | 1,8 s |
| `pouce_leve` | les quatre doigts à fond, pouce tendu | 1 | 1,0 s |
| `pointer` | index tendu, les autres repliés, pouce par-dessus | 2 | 1,8 s |
| `rock` | index et auriculaire tendus, majeur et annulaire repliés, pouce par-dessus | 2 | 1,8 s |
| `je_t_aime` | majeur et annulaire repliés ; pouce, index, auriculaire tendus | 1 | 1,0 s |
| `compter` | à l'européenne : le pouce tendu d'abord (« un »), puis un doigt de plus toutes les 0,6 s ; le pouce n'est jamais par-dessus les doigts (réglé le 15.11 au soir : sur la vraie main, le pouce gênait l'index) | 5 | 7,9 s (nouvelle forme : fausse main seulement) |
| `vague` | les doigts se ferment l'un après l'autre, se rouvrent de même ; deux fois | 16 | 6,9 s |
| `pierre_feuille_ciseaux` | trois battements, puis une forme tirée au hasard : poing, main ouverte ou victoire | 7 ou 8 | 2,5 s (feuille) à 4,2 s |

Les durées sont calculées main ouverte au départ, à pleine vitesse du geste. En mode lent (moitié de la vitesse), les
mouvements durent deux fois plus, les pauses ne changent pas. Sur la vraie main elles dépendront de ce que la main
tient vraiment comme vitesse.

Le tirage de `pierre_feuille_ciseaux` se lit après coup dans l'état rendu par la liaison (clé `dernier_tirage`).
À savoir : l'adaptateur commun ne recopie pas encore cette clé vers l'écran (à brancher par le coordinateur).

## Le kit du fabricant : lu, jamais lancé, jamais copié
Le kit s'appelle `LHandProLib` (version du 31.10.2026 pour Mac). Il est **hors du projet**, dans
`~/Downloads/lhandprolib-20261031-mac/contenu/arm64/`. D'où il vient et sa taille : voir `LICENCES.md`.
**Sa licence n'est pas indiquée** → aucun code n'est copié dans notre projet, seulement des NOMS de fonctions, cités
ici avec le fichier où ils ont été lus. (Un morceau du kit, `gsusb-canfd`, a une licence MIT ; nous n'en copions rien non plus.)
Pendant l'écriture de l'ébauche : le kit a été **lu comme du texte**, jamais importé ni lancé ; aucune prise USB touchée.

Le kit a besoin de deux choses sur l'ordinateur :
- `pyusb` (un paquet Python pour parler à l'USB) : il est dans `.venv` depuis le 15.11.2026 (voir `LICENCES.md`) ;
- `libusb` (une bibliothèque du système pour l'USB ; le `README.md` du fabricant demande `brew install libusb` sur Mac).
  **Elle n'est pas installée sur ce Mac**, et rien n'a été installé. Le kit en livre une copie :
  `arm64/lib/libusb-1.0.0.dylib`. Le coordinateur a créé à côté un lien `libusb-1.0.dylib` vers elle, et a vérifié le
  15.11.2026 sur ce Mac, sans toucher à l'USB, que pyusb la trouve quand la variable d'environnement
  `DYLD_FALLBACK_LIBRARY_PATH` contient ce dossier (et ne trouve rien sans elle). Notre classe `KitDeLaMain` ajoute
  donc ce dossier à la variable avant de charger le kit. **Pas essayé avec le boîtier USB** : si la connexion rate,
  le message d'erreur cite aussi cette cause.

## Quatre pièges, lus dans le kit

1. **Se connecter fait BOUGER la main, par défaut.** La fonction `connect()` du fabricant a deux options,
   `enable_motors` et `home_motors`, toutes deux à « oui » par défaut : elle allume les moteurs, puis lance la « mise
   en position de départ » (le « home » : la main s'ouvre pour retrouver son zéro). Notre classe `KitDeLaMain` appelle
   donc toujours `connect(enable_motors=False, home_motors=False, …)`. Un essai le vérifie.
2. **Les exemples du fabricant vont très vite et à pleine force** : 20000 positions par seconde (toute la course en
   une demi-seconde) et 1000 pour mille du courant. Depuis la décision de Hiba du 15.11.2026, nos limites SONT ces valeurs-là (plus bas).
3. **Sans mise en position de départ, la main refuse de bouger** (erreur `LER_NOT_HOME`). Le kit a une fonction pour
   passer outre (`set_move_no_home`) : nous ne l'appelons **jamais**. Et la mise en position de départ se fait à la
   vitesse et au courant **du fabricant**, pas aux nôtres (à vérifier) : main vide, personne ne la touche.
4. **La mise en position de départ et l'arrêt d'urgence de la main remettent peut-être sa vitesse et son courant à
   leurs valeurs d'origine** (une phrase du manuel, à `play_gesture` : « parameters reset by homing/e-stop »). Le kit
   dit renvoyer nos réglages au mouvement suivant, mais ce n'est pas lisible (bibliothèque fermée). **À vérifier.**
   Notre filet : la liaison mesure la vitesse des doigts, et si un doigt va plus de deux fois plus vite que demandé,
   elle arrête les moteurs et dit le geste raté. C'est un filet, pas une garantie : à pleine vitesse, la main serait
   déjà arrivée.
   Ce que le manuel écrit là-dessus (lu, pas vérifié sur la main) : lignes 1317 à 1327, la vitesse et le courant ne
   sont envoyés à la main qu'au `move_motors` qui suit un `set_position_velocity` ou un `set_max_current` (la position,
   elle, part à chaque fois) ; ligne 2160 (version v1.8), ils sont renvoyés d'office après `home_motors`, `stop_motors`
   et `play_gesture`. Notre liaison règle la vitesse et le courant des six moteurs avant CHAQUE mouvement.
   Autre conséquence des lignes 1317 à 1327 : un `move_motors` envoie plusieurs messages. S'il est refusé en route,
   une partie a pu partir : après tout refus (sauf « mise en position de départ pas faite »), la liaison envoie l'arrêt.

## Ce qui a été lu, et où (15.11.2026)
Tous les chemins partent de `arm64/`. `ex/` veut dire `share/LHandProLib/examples/CANFD_python/`.

| Quoi | Ce qui est écrit | Où |
|---|---|---|
| Le contrôleur | `LHandProController(communication_mode="CANFD", canfd_node_id=1)` | `ex/lhandprolib_python_sdk/controller.py`, `ex/main.py` |
| Se connecter | `connect(enable_motors=True, home_motors=True, home_wait_time=5.0, …, canfd_nom_baudrate=1000000, canfd_dat_baudrate=5000000)` ; rend False (sans erreur) si ça rate ; après l'allumage il attend 1 s, après la mise en position de départ il attend 5 s | `ex/lhandprolib_python_sdk/controller_base.py` |
| Le boîtier USB | cherche les boîtiers, prend **le premier** sans demander, puis appelle `initial_ex` | `ex/lhandprolib_python_sdk/controller_canfd.py` |
| Fermer | `disconnect()` | `controller_base.py` |
| La poignée | `sdk_handle` (les fonctions ci-dessous) ; `is_connected` (un drapeau du programme) | `controller_base.py` |
| Nombre de moteurs | `get_dof()` rend (total, actifs) | `ex/lhandprolib_python_sdk/lhandprolib_wrapper.py` |
| Lire | `get_now_position(n)`, `get_now_status(n)`, `get_now_alarm(n)`, `get_enable(n)`, `get_position_reached(n)`, `get_torque_reached(n)` ; n de 1 à 6 | `lhandprolib_wrapper.py`, manuel |
| Allumer, couper | `set_enable(0, True)`, `set_enable(0, False)` ; 0 = tous les moteurs | `lhandprolib_wrapper.py`, manuel |
| Mise en position de départ | `home_motors(0)` | `lhandprolib_wrapper.py`, manuel |
| Régler un moteur | `set_target_position(n, position)`, `set_position_velocity(n, vitesse)`, `set_max_current(n, courant)` | `lhandprolib_wrapper.py`, manuel |
| Bouger, arrêter | `move_motors(0)`, `stop_motors(0)` (« Stop motor movement ») | `lhandprolib_wrapper.py`, manuel |
| Unités | position de 0 (« start position ») à 10000 (« full stroke ») ; vitesse en positions par seconde ; courant en pour mille (« ‰ ») | `docs/LHandProLib_SDK_Manual.md` (en tête : « Version 1.7 » ; au pied du fichier : « Document version: v1.8 », 16.09.2026) |
| États d'un moteur | `LST_STOPPED` 0, `LST_RUNNING` 1, `LST_ALARM` 2, `LST_POS_LIMIT` 3, `LST_NEG_LIMIT` 4, `LST_BOTH_LIMIT` 5, `LST_EMG_STOP` 6, `LST_HOMING` 7 | `ex/lhandprolib_python_sdk/lhandprolib_loader.py`, manuel |
| Alarmes | `LAM_*` de 0 (aucune) à 9 : position, vitesse, courant, surcharge, tension haute, tension basse, capteur, blocage, autre | `lhandprolib_loader.py`, manuel |
| Erreurs du kit | une exception avec un `error_code` ; `LER_NOT_HOME` = 11 ; 5 à 8 = communication | `lhandprolib_wrapper.py`, `lhandprolib_loader.py` |
| Où il cherche sa bibliothèque | d'abord la variable `LHANDPRO_LIB_PATH`, puis des dossiers voisins, en remontant jusqu'à `arm64/lib/` | `lhandprolib_loader.py` |
| Ordre des moteurs | pouce (écartement), pouce (flexion), index, majeur, annulaire, auriculaire | manuel, « 6-DOF Hand Joint Enumeration » |
| Un mode « à blanc » | `set_dry_run_mode` : les ordres sont préparés mais pas envoyés. **Pas utilisé, pas essayé** | manuel |

## Nos limites : celles des exemples du fabricant (décision de Hiba, pas essayées sur la vraie main par notre système)
Écrites dans `robots/leadtron_dh116/liaison.py`. Un ordre au-delà est **refusé** : rien ne part.

| Limite | Valeur | Avant |
|---|---|---|
| Vitesse d'un doigt | au plus 20000 positions par seconde (toute la course en une demi-seconde) | 2500, puis 5000 |
| Courant | au plus 1000 pour mille (toute la force) | 200, puis 600 |
| Position | au plus 10000 (toute la course : la main se ferme à fond) | 6000 |
| Étapes d'un geste | au plus 30 ; pause après une étape : 3 s au plus ; durée estimée du geste : 25 s au plus | — |
| Vitesse demandée pour un geste | elle ne fait que ralentir ; sous un quart, le geste est refusé | — |

Ces valeurs sont celles des exemples du fabricant (`main.py` : 20000 et 1000). Hiba les a choisies pour une main qui ne
touche que des objets. **Notre système ne les a pas essayées sur la vraie main.**

**Le filet « trop vite »** (un doigt allé plus de deux fois plus vite que la vitesse demandée pour l'étape → tout est
arrêté, geste dit raté) est gardé. Il est proportionnel à la vitesse demandée : pour une étape à 10000 ou plus, il ne
se déclencherait qu'au-delà de 20000, donc en pratique il ne protège plus de rien ; pour une étape lente (6000) il
arrête encore une main qui partirait à 20000. Sur la fausse main, il ne se déclenche pas à tort à 20000.

Les formes des gestes sont dans `robots/leadtron_dh116/gestes.yaml` : des valeurs de départ, **pas mesurées**. On ne
sait pas combien de **newtons** fait un courant de 1000 pour mille : c'est pour cela que la carte ne promet ni `saisir`
ni `poser`, et que ses limites restent à 0.

## À vérifier (sur la main, avec le responsable sécurité)
- **Couper les moteurs** : les doigts deviennent-ils mous ? La main **lâche-t-elle l'objet, ou le garde-t-elle
  serré** ? Un doigt de personne pris dans la main est-il libéré ? **On ne le sait pas.** C'est la première chose à
  essayer, main vide, puis avec l'ours en peluche. Notre arrêt d'urgence proposé coupe les moteurs.
- **Arrêt d'urgence PHYSIQUE** : débrancher l'alimentation de la main. Où est la prise ? Et que fait la main alors ?
- **L'ordre de notre arrêt d'urgence** : arrêter, puis couper. Si l'arrêt reste coincé dans le kit, la coupure attend.
  Faut-il couper d'abord ? Choix humain.
- **`stop_motors`** : arrête-t-il aussi une mise en position de départ en cours ? La main tient-elle sa place après ?
  Notre arrêt normal vérifie que les positions ne changent plus, et dit « arrêt non confirmé » sinon.
- **Allumer les moteurs** : la main saute-t-elle vers une ancienne cible ? La liaison compare les positions avant et
  1 s après, et recoupe si un doigt a bougé de plus de 300 positions.
- **La mise en position de départ** : à quelle vitesse, avec quelle force ? Combien de temps ? La main dit-elle
  « en cours » (`LST_HOMING`) pendant ce temps ? Si elle ne le dit jamais, la liaison attend 5 s comme le fabricant.
  Le kit a un réglage de courant pour elle (`set_home_current`) : pas utilisé, valeur d'origine inconnue.
- **Ce que rendent vraiment** `get_now_status`, `get_position_reached` et `get_torque_reached` : pendant un
  mouvement, à l'arrivée, quand un doigt pousse sur un objet. La liaison dit un doigt « arrivé » si la main le dit ET
  s'il est à moins de 300 positions de sa cible ; « arrêté sur l'objet » si la main dit « couple atteint », s'il a AVANCÉ de plus de 300 positions depuis son départ, ET s'il ne
  bouge plus depuis 0,3 s. Si la vraie main ne parle pas ainsi, les gestes seront dits ratés (le sens sûr).
- **Les lectures sont-elles fraîches ?** Le kit a un fil de fond qui lit la main. Si la main est débranchée, nos
  lectures rendent-elles une erreur, ou la dernière valeur connue ? Dans le second cas, notre signe de vie ne prouve rien.
- **Le chien de garde** : que fait la main si notre ordinateur se tait pendant un mouvement ? Rien lu.
- **Deux appels en même temps** : notre arrêt d'urgence part dans un autre fil. Le kit le supporte-t-il ? Rien lu.
- **Ce que la bibliothèque envoie quand on se connecte** (`initial_ex`) : pas lisible. La main bouge-t-elle ? À regarder.
- **Le numéro de la main** (`canfd_node_id`) : 1 dans les exemples. Celui de notre main ?
- **Un seul boîtier branché** : le kit prend le premier qu'il trouve, sans demander.
- **Le sens des moteurs** (plus = plus fermé ?) et leur ordre (1 = pouce, écartement ?) : lus dans le manuel, pas vus.
- **Le pouce et l'index se touchent-ils** en se fermant ensemble ? Les positions de `gestes.yaml` sont à régler (le pouce surtout).
- **Fermer la liaison** (décision du 15.11.2026, après relecture) : si c'est notre système qui a allumé les moteurs,
  il les **coupe** avant de fermer (sinon un Ctrl+C laissait la main sous force). **On ne sait pas si la main lâche
  alors l'objet.** Des moteurs allumés par le logiciel du fabricant ne sont pas coupés.
- **Un doigt qui touche l'objet tout de suite** (avant d'avoir avancé de 300 positions) est dit « pas arrivé », et le
  geste raté, même s'il tient vraiment l'objet. De même, redemander « tenir_doucement » à une main déjà fermée sur
  l'ours donne « raté ». C'est le sens sûr (une main qui n'a pas bougé n'a rien pris) ; le seuil est à régler.
- **Le logiciel du fabricant doit être fermé** quand notre système parle à la main : un seul programme sur le boîtier.
- **Reconnexion** : le test de conformité ferme et rouvre le boîtier USB plusieurs fois de suite. Notre kit attend
  0,3 s entre fermer et rouvrir (le fabricant : 0,2 s, `controller_canfd.py` lignes 128 à 131). Tout cela doit tenir
  en moins de 1,8 s, sinon la prise dit « liaison perdue ». Combien de temps prend une connexion ? Pas mesuré.
- **L'accord d'un humain** : aujourd'hui le gardien ne demande pas l'accord d'un humain avant « preparer_la_main »
  (qui allume les moteurs et ouvre la main). À décider par Hiba (règle « demander_humain » du gardien).

## Correspondance proposée (prise → main), à vérifier une par une
| Action de la prise | Appel proposé | Remarque |
|---|---|---|
| connexion, `etat` | `connect(enable_motors=False, home_motors=False, …)`, puis des lectures | **écrit** : rien n'est allumé, rien ne bouge (à vérifier pour `initial_ex`) |
| `arreter` | `stop_motors(0)`, puis vérifier que les positions ne changent plus | **écrit, PROPOSITION** |
| arrêt d'urgence logiciel | `stop_motors(0)` puis `set_enable(0, False)` | **écrit, PROPOSITION** : à décider avec le responsable sécurité ; on ne sait pas si la main lâche l'objet |
| fermer la liaison | `set_enable(0, False)` si c'est nous qui avons allumé, puis `disconnect()` | **écrit** (décision du 15.11.2026) ; on ne sait pas si la main lâche l'objet |
| `rearmer` | rien n'est envoyé à la main | **écrit** : les moteurs restent coupés ; les alarmes ne sont jamais effacées par notre système |
| `rejouer_geste` « preparer_la_main » | `set_enable(0, True)`, attendre 1 s ; pour chaque moteur `set_position_velocity(n, 5000)` et `set_max_current(n, 600)`, puis `apply_motion_params()` ; `home_motors(0)`, puis vérifier | **écrit, PROPOSITION**. L'allumage et `home_motors` ont marché sur la vraie main avec la version d'avant ; les réglages écrits juste avant sont nouveaux : testé sur faux robot seulement. Si la main les refuse, la mise en position de départ part quand même, et c'est dit dans l'état |
| `rejouer_geste` « tenir_doucement » | six fois (`set_target_position`, `set_position_velocity`, `set_max_current`), puis `move_motors(0)` | **écrit, PROPOSITION**, testé sur faux robot ; positions de `postures.yaml`, pas mesurées |
| `rejouer_geste` « ouvrir_la_main » | les mêmes appels, toutes les cibles à 0, courant 500 | **écrit, PROPOSITION**, testé sur faux robot |
| `rejouer_geste`, les treize gestes de `gestes.yaml` | pour chaque étape : six fois (`set_target_position`, `set_position_velocity`, `set_max_current`), puis `move_motors(0)` ; l'étape suivante part quand la précédente est vérifiée arrivée (ou, pour la « vague », après sa pause) | **écrit le 15.11.2026 (demande de Hiba), PROPOSITION**, testé sur faux robot ; un arrêt oublie les étapes qui restent ; une étape ratée = geste dit raté |
| `saisir`, `poser` | — | pas écrit : force en newtons inconnue |
| `se_deplacer`, `regarder`, `montrer`, `parler`, `ecouter` | — | pas pour une main seule |

## Le test de conformité sur la vraie main, À REFAIRE : ce que feront exactement les deux commandes
`liaison.py` et `carte.yaml` ont changé après le premier essai réel : le programme refusera la vraie main tant que le
test complet n'aura pas été refait avec ces fichiers (c'est voulu).
Établi en LISANT le code (par le relecteur du 15.11.2026, recompté par l'auteur sur la doublure). Avec la version
d'avant, ces deux commandes ont réussi sur la vraie main ; avec la version d'aujourd'hui, elles ne sont pas essayées.
**Main VIDE pour les deux commandes**, rien entre les doigts, personne ne la touche, responsable sécurité
présent, logiciel du fabricant fermé. Ce sont des feux orange : un humain tape la commande, après le « oui » de Hiba.

**Commande 1 — `python3 lancer.py brancher leadtron_dh116 --conformite --vrai`**
- se connecte SANS allumer les moteurs et SANS mise en position de départ ; lit l'état ;
- **jamais d'allumage, jamais de mouvement commandé** ;
- **deux arrêts d'urgence logiciels** : chacun envoie `stop_motors`, puis **coupe les moteurs** (`set_enable(0, False)`) ;
- **une reconnexion** : la liaison est fermée puis rouverte une fois (avec 0,3 s de pause), et chaque fermeture envoie
  d'abord un arrêt normal (`stop_motors`).

**Commande 2 — `python3 lancer.py brancher leadtron_dh116 --conformite --vrai --complet`**
- **la commande 1, jouée deux fois** (donc quatre arrêts d'urgence qui coupent les moteurs, et des reconnexions) ;
- puis le geste « preparer_la_main » : **moteurs ALLUMÉS**, **1 s d'attente**, nos réglages de vitesse et de courant
  écrits et envoyés (NOUVEAU, pas essayé sur la vraie main), puis la mise en position de départ (`home_motors`) : **LA MAIN S'OUVRE, à la vitesse et au courant du FABRICANT, pas les nôtres** ;
- puis **un arrêt d'urgence final : moteurs COUPÉS** ;
- en tout, la liaison est ouverte 5 fois.

Recompté sur la doublure (une fausse main, pas la vraie) : commande 1 = 2 ouvertures de la liaison, 2 coupures des
moteurs, 6 `stop_motors`, aucun allumage ; commande 2 = 5 ouvertures, 5 coupures (4 avant l'allumage, 1 après),
15 `stop_motors`, 1 allumage, 1 réglage de vitesse et de courant suivi de son envoi, 1 mise en position de départ,
aucun réglage de cible et aucun `move_motors`.

**Seul « preparer_la_main » est joué par ces commandes : AUCUN des treize gestes de `gestes.yaml` ne l'est** : nos limites de vitesse et
de courant ne sont donc essayées par aucune des deux.

## À vérifier en plus, depuis le premier essai réel
- **`apply_motion_params` avant la mise en position de départ** : la main l'accepte-t-elle alors qu'elle n'est pas
  encore « préparée » ? Fait-il bouger quelque chose ? Lu : « Apply target velocity/current changes immediately »,
  pas un mouvement. C'est un choix de l'auteur, pour que nos réglages arrivent VRAIMENT avant `home_motors`. Si la main
  le refuse, la liaison continue et le dit dans l'état.
- **L'hypothèse elle-même** : est-ce bien le petit courant resté dans la main qui bloquait la mise en position de
  départ ? Le kit a un réglage à part pour elle (`set_home_current`, en pour cent), jamais lu ni écrit par nous.
- **« La main se dit encore en mouvement »** : si, après notre arrêt, les doigts sont mesurés immobiles (une demi-seconde)
  mais que la main se dit encore « en marche » ou « en mise en position de départ », « preparer_la_main » **continue
  quand même**. Choix de l'auteur, à confirmer par Hiba : sans cela, d'après ce qui a été vu, la main resterait
  inutilisable jusqu'au redémarrage. Les autres gestes, eux, restent refusés tant que la main se dit en mouvement.
- **Un doigt très lent** (moins de 100 positions par seconde environ) passe pour immobile pendant cette demi-seconde.
- **Les nouvelles limites** (5000, 600, 500, 400) et les positions 3000 / 2500 / 3500 : pas essayées sur la vraie main.
  Commencer main vide. Le filet de vitesse (arrêt si un doigt va plus de deux fois plus vite que demandé) est toujours là.
- **« bouger_les_doigts »** : la durée (10 s) est calculée, pas mesurée ; elle suppose que la main tient notre vitesse
  et dit « arrivé » comme prévu. Les doigts et le pouce se touchent-ils en se fermant ensemble ?

## À vérifier en plus, depuis le deuxième essai réel
- **Toute la force et toute la vitesse** : que fait la main à 1000 pour mille et 20000 quand un doigt bute (sur le
  doudou, sur un autre doigt, sur le pouce) ? Alarme ? Échauffement ? Commencer main VIDE, un geste à la fois.
- **Le pouce** : à quelles positions touche-t-il les autres doigts ? 8000/8000 le pose-t-il bien par-dessus le poing ?
  Dans les gestes à deux étapes, les doigts se ferment d'abord et le pouce ensuite, pour qu'ils ne se croisent pas.
- **« Arrivé »** : pour passer à l'étape suivante, la liaison attend que la main dise « arrivé » ET que le doigt soit à
  moins de 300 positions de sa cible ; ou qu'il soit arrêté sur un objet après avoir avancé de plus de 300 ; ou qu'il
  ait déjà été à sa place. Si la vraie main ne dit pas « arrivé » comme prévu, un geste à plusieurs étapes s'arrêtera
  à la première, et sera dit raté.
- **La « vague »** envoie un nouvel ordre pendant que des doigts bougent encore (toutes les 0,2 s environ). Le
  fabricant le fait dans ses exemples (un ordre par seconde) ; à cette cadence, pas vu.
- **`compter` dure 8 s environ** (calculé) ; en mode lent, plus longtemps ; la limite est 25 s.

## Où en est l'ébauche
- Écrite le 15.11.2026 sur le modèle du Reachy Mini (mêmes protections : un arrêt passe toujours devant, jamais deux
  gestes à la fois, un geste raté est dit raté).
- **Relue par un relecteur neuf le 15.11.2026** : un défaut GRAVE (« tenir_doucement » dit réussi alors qu'aucun doigt
  n'avait bougé, quand la main disait « couple atteint » partout), quatre moyens (pas de pause entre fermer et rouvrir
  le boîtier USB ; un lancement refusé cru « pas parti » ; des moteurs laissés allumés à la fermeture ; libusb pas
  trouvée) et des petits (une clé écrite deux fois dans `postures.yaml`, des textes inexacts). Tous corrigés par
  l'auteur, avec un essai chacun. **Ces corrections n'ont PAS été relues par quelqu'un d'autre que leur auteur.**
- **Après le premier essai réel du 15.11.2026** : limites relevées, réglages écrits avant la mise en position de
  départ, arrêt avant de refuser « prépare la main », nouveau geste « bouger_les_doigts ». Écrit par l'auteur, avec un
  essai par point, sur la doublure. **Pas relu par quelqu'un d'autre, pas essayé sur la vraie main.**
- **Après le deuxième essai réel du 15.11.2026** : limites du fabricant, gestes dans `gestes.yaml`, quatorze gestes.
  Écrit par l'auteur, avec des essais sur la doublure (chaque geste joué en entier sur la fausse main).
  **Pas relu par quelqu'un d'autre, pas essayé sur la vraie main.**
- Le test de conformité (`python3 lancer.py brancher leadtron_dh116 --conformite`) essaie **la vraie liaison de ce
  dossier** avec la doublure : testé sur faux robot.
- La classe qui touche au kit du fabricant (`KitDeLaMain`) est essayée contre un **faux kit écrit par les essais** :
  on vérifie qu'elle appelle les bonnes fonctions, avec les bons nombres. Elle n'a **jamais** été lancée avec le vrai kit.
- La fausse main est inventée : elle ne dit rien de la vraie (voir le haut de `doublure.py`).
- Pour vérifier que les essais mordent, l'auteur a abîmé la liaison exprès, un défaut à la fois (27 défauts : une
  connexion qui allume les moteurs, une limite relevée, un arrêt oublié, un geste raté dit réussi…) : chaque défaut a
  fait échouer au moins un essai. Trois essais manquaient et ont été ajoutés. Ce n'est pas une relecture.
- Avec `--vrai` : voir plus haut « Le premier essai sur la vraie main » (même le test « sans mouvement » coupe les moteurs).
