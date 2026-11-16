Avenant 2 « concours » au cahier de la clinique en boîte
Bonjour. Ce texte s'ajoute au cahier `docs/projet/CAHIER_CLINIQUE.md` et au premier avenant `docs/projet/AVENANT_JURY.md`. Il ne les remplace pas et il ne les change pas. Tu ne touches jamais au cahier ni au premier avenant.
Hiba a étudié les concours de robots : ceux des robots de service, ceux des robots de soin, et les hackathons récents. Cet avenant ajoute sept petites tâches. Chacune reprend une chose que font les équipes qui gagnent.
Ce que Hiba écrit après la ligne « Fin de l'avenant 2. » ne fait pas partie de l'avenant : ce sont ses réponses. Note-les dans `docs/projet/QUESTIONS_POUR_HIBA.md`, avec la date.
Enregistrement : ce tour-ci, une seule fois
Ce tour-ci, tu ne construis rien. Tu enregistres l'avenant, tu mets le suivi à jour, et tu t'arrêtes.
Si tu es au milieu d'une tâche. Finis d'abord ton tour proprement, ou remets le dépôt dans un état où la vérification rapide passe. Ensuite seulement, fais les étapes ci-dessous.
Étape 0 — Vérifie que le premier avenant est là. Le fichier `docs/projet/AVENANT_JURY.md` doit exister à côté du cahier, et le suivi doit contenir les tâches J01 à J07. Si ce n'est pas le cas, n'enregistre rien : affiche « AVENANT 2 : EN ATTENTE — le premier avenant manque », et arrête-toi. Hiba te le donnera d'abord.
Étape 1 — Enregistre ce texte. Mot pour mot, du titre jusqu'à la ligne « Fin de l'avenant 2. », dans `docs/projet/AVENANT_CONCOURS.md`, à côté du cahier. Puis contrôle ta copie : elle doit faire 291 lignes à dix près, peser entre 26 900 et 28 100 octets, contenir sept tâches de K01 à K07, sept contrôles numérotés dans la partie 6, et finir par « Fin de l'avenant 2. ». Si le contrôle rate, dis-le et arrête-toi.
Étape 2 — Mets le suivi à jour. Dans `docs/projet/SUIVI_CLINIQUE.md` :

* en haut, ajoute la ligne : « Avenant 2 : `docs/projet/AVENANT_CONCOURS.md`. Ses règles s'ajoutent à celles du cahier et du premier avenant. » ;
* ajoute les tâches K01 à K07, à l'état « À FAIRE », aux places données dans la partie 4 ;
* sur la ligne de T25, ajoute : « lis aussi l'avenant 2, K03 et K04 » ;
* sur la ligne de T27, ajoute : « lis aussi l'avenant 2, K02 et K03 » ;
* sur la ligne de T33, ajoute : « après les tâches K aussi » ;
* ne change l'état d'aucune autre tâche, et ne touche pas à tes réparations.

Étape 3 — Note-le. En haut de `docs/projet/QUESTIONS_POUR_HIBA.md` : « Avenant 2 reçu le (date). » Ajoute tout de suite les deux questions de cet avenant (tâches K01 et K06), sauf si Hiba y a déjà répondu. Puis une ligne dans `docs/projet/JOURNAL_CLINIQUE.md`.
Étape 4 — Enregistre le travail sur l'ordinateur. Envoie-le vers la branche `clinique-en-boite` seulement si Hiba a dit oui à l'autorisation C.
Étape 5 — Affiche le bilan, puis arrête-toi. Ces quatre lignes, puis l'encadré, et rien après :

```
AVENANT 2 : ENREGISTRÉ
Copie : (lignes), (octets), 7 tâches, 7 contrôles, fin correcte
Suivi : 7 tâches ajoutées, aucun autre état changé
Suite : /clear, puis une des deux lignes

```


```
Hiba, pour lancer ou relancer la boucle :
1. Tape /clear.
2. Colle une de ces deux lignes. Elles remplacent celles du premier avenant.

/goal Construis « la clinique en boîte » en suivant docs/projet/CAHIER_CLINIQUE.md, docs/projet/AVENANT_JURY.md et docs/projet/AVENANT_CONCOURS.md, un tour de boucle à la fois (partie 3 du cahier). Le but est atteint quand tu as affiché dans cette conversation : 1) le fichier docs/projet/SUIVI_CLINIQUE.md où chaque tâche T00 à T33, J01 à J07 et K01 à K07 est marquée FAIT ou BLOQUÉ ; 2) la sortie complète de la grande répétition, qui se termine par « RÉPÉTITION : RÉUSSIE » ; 3) la sortie complète de la commande des preuves, qui se termine par « PREUVES : RÉUSSIES » ; 4) la sortie complète de la commande du concours, qui se termine par « CONCOURS : RÉUSSI ». Tu ne modifies jamais le cahier, les avenants ni une vérification pour y arriver. Arrête-toi aussi, en le disant, si tout ce qui reste attend une réponse de Hiba, ou après 40 tours.

/loop Tu construis « la clinique en boîte ». Lis docs/projet/CAHIER_CLINIQUE.md, partie 3, puis docs/projet/AVENANT_JURY.md, partie 3, et docs/projet/AVENANT_CONCOURS.md, partie 3, puis fais un tour de boucle, un seul, comme il est décrit.

```

1. Pourquoi cet avenant
Ce que montrent les concours de robots, en mots simples :

* Dans le plus grand concours de robots de service, une tâche réussie avec l'aide d'un humain vaut zéro point. Les gagnants comptent donc chaque aide.
* Les gagnants refusent une demande impossible, et disent pourquoi. Ils ne la ratent pas en silence.
* Dans un concours de robots de soin, la moitié de la note venait des personnes servies : le robot a-t-il prévenu avant de bouger, est-il resté à bonne distance, a-t-il surpris ? L'équipe gagnante a gagné sur cette moitié-là.
* Dans un grand concours, ce sont les juges qui tenaient les commandes, pas les équipes.
* Les robots qui gagnent sont lents et sûrs. Ils s'arrêtent avant de se tromper, et un humain peut reprendre la main.
* Dans les hackathons récents, les tableaux de flotte sur de faux robots se ressemblent beaucoup. Ce qui fait la différence : des chiffres mesurés, un vrai geste, et des limites dites sans détour.
* À notre hackathon, d'autres regarderont de près trois choses : l'âge de ce qu'un écran affiche, la différence entre « le robot dit que c'est fait » et « c'est fait », et qui a donné l'accord. Sur ces trois points, nous devons être sans reproche.

2. Les règles en plus
Toutes les règles du cahier et du premier avenant restent vraies. Si deux textes semblent se contredire, la règle la plus prudente gagne, et tu poses la question.

1. Toujours aucun nom de juré. Et sur les écrans, ne cite ni un autre concours, ni une autre équipe, ni une entreprise donnée en exemple. Les noms des outils que nous utilisons restent permis.
2. Toute aide humaine se compte. Une tâche aidée par un humain n'est jamais comptée comme réussie seule.
3. Un bon refus est une réussite. Refuser une demande impossible ou interdite, en disant pourquoi, compte comme une bonne réponse. Faire une chose interdite est la pire des fautes.
4. Dire avant de faire. Avant de bouger, un robot dit ce qu'il va faire.
5. Ce qui est vieux se voit. Un écran ne montre jamais une vieille information comme si elle était neuve.
6. Trois niveaux de preuve, jamais mélangés. Prouvé sur un vrai robot. Prouvé sur le faux robot. Vérifié par des tests seulement. Un chiffre s'affiche toujours avec son niveau, son nombre d'essais et sa date.
7. Tu ajoutes, tu ne changes pas. Chaque tâche K prolonge une pièce qui existe. Elle ne crée pas de nouvelle brique. Tu ne changes aucune vérification qui existe : tu ajoutes les tiennes à côté. Tu ne changes pas le sens des états déjà là (« livrée », « FAIT »…).
8. Aucun outil nouveau. Ces tâches se font avec ce qui est déjà dans le dépôt. Si tu crois qu'il faut un outil ou un modèle de plus : feu orange, et la version simple en attendant.
9. La version simple d'abord, et vite. Si une tâche K dépasse deux tours, coupe-la, ou marque-la BLOQUÉ avec ce qui manque, et passe à la suivante.
10. Ces sept tâches font partie de la liste. Elles ne sont pas « hors sujet ».

3. Comment ces tâches entrent dans la boucle

* Un tour de boucle se fait comme dans la partie 3 du cahier. Rien ne change.
* Une tâche K se choisit comme les autres : la première de la liste qui est « À FAIRE » ou « ESSAI 1 », et dont les tâches de la ligne « Après » sont finies.
* Pour une tâche K, lis sa description ici, et les parties du cahier et du premier avenant qu'elle cite.
* T33 passe après toutes les tâches J et K.
* Les commandes longues de cet avenant (le tirage, l'endurance, les ordres de l'invité, la commande du concours) n'entrent pas dans la vérification rapide. Elle doit rester sous deux minutes.
* La boucle est finie quand les tâches T00 à T33, J01 à J07 et K01 à K07 sont toutes FAIT ou BLOQUÉ, que la grande répétition réussit, que la commande des preuves réussit, et que la commande du concours réussit. Affiche alors le suivi en entier, puis ces trois sorties complètes, puis la ligne `BOUCLE TERMINÉE`.

4. L'ordre dans la liste
Range les tâches du suivi dans cet ordre. Hiba peut le changer.

* T00 à T12, comme avant ;
* puis J01, J02, J03, J04, J06 ;
* puis T13 à T22 ;
* puis K02, K03, K01 ;
* puis J05 ;
* puis T23, K04 ;
* puis T24 à T28, K07 ;
* puis T29 à T31 ;
* puis J07, K05, K06 ;
* puis T32 et T33 ;
* puis les bonus, B2 en premier.

Pourquoi : chaque tâche K vient après la pièce qu'elle prolonge. Et le scénario complet, avec la voix et le cerveau, passe avant elles.
Si une tâche de cette liste est déjà faite ou déjà commencée, ne la déplace pas : place seulement les tâches K.
5. Les sept tâches
K01 — Les demandes tirées au hasard
Après J01 et T14. Lis les parties 5.6, 5.9, 2.6 et 4.3 du cahier.
Dans le grand concours des robots de service, les demandes sont tirées au hasard par un outil. Nous faisons pareil.

* La liste de mots. Un fichier de réglages : les personnes du scénario ; les objets de la réserve, et trois objets qui n'y sont pas ; les lieux du scénario, et deux lieux qui n'existent pas ; les gestes permis ; les gestes interdits (parler de santé dans le hall, donner un avis sur un soin ou une dose, entrer dans un lieu que la carte de rôle interdit, faire saisir un objet par un robot sans bras).
* La commande « tirage ». Elle fabrique trente demandes au hasard à partir de cette liste, dans les langues du cahier. Environ un tiers sont impossibles, floues ou interdites. Chaque demande porte la réponse attendue : faire ; poser une question ; dire que l'objet manque et passer à un humain ; passer le relais ; transmettre à l'équipe ; refuser poliment. Un numéro de tirage permet de refaire exactement le même.
* Le système répond à chaque demande par le chemin normal : le tableau des tâches, le répartiteur s'il existe, le gardien. Un refus dit pourquoi, en une phrase simple, dans la langue de la demande.
* Le résultat. Un tableau par sorte de demande : « bonne réponse : tant sur tant ». Et une ligne à part : « gestes interdits exécutés : tant ». Ce nombre doit être zéro. C'est le gardien qui l'assure, pas le cerveau.
* Par défaut, le tirage se joue avec le cerveau de test : il prouve que le chemin est sûr. Une option le joue avec le vrai Apertus : là, il mesure ce que le cerveau comprend. Le tableau dit lequel a servi. Ne présente jamais le chiffre du cerveau de test comme un chiffre de compréhension.
* Le bouton « Demande au hasard ». Sur l'écran du chef de démonstration. Il tire une demande, l'affiche, et la joue.
* Question pour Hiba (écris-la, et continue sans attendre) : « Veux-tu une cinquième langue pour l'arrivée et pour le tirage, par exemple l'espagnol ? » Sans réponse : non.

Fini quand : la commande affiche le tableau pour trois numéros de tirage différents ; « gestes interdits exécutés » vaut zéro sur les trois ; chaque refus a sa phrase ; une vérification retire exprès une règle du gardien, dans une copie d'essai, et le tableau affiche alors un geste interdit exécuté ; le bouton tire et joue une demande.
K02 — Toute aide humaine se compte
Après J01. Lis la partie 5.11 du cahier, et la tâche J01 du premier avenant.
Une entreprise qui fait travailler des centaines de robots donne trois chiffres : la part des gestes réussis du premier coup, le nombre de gestes pour une aide humaine, et le temps sans arrêt. Nous donnons les mêmes, mesurés chez nous.

* L'aide humaine. Un nouvel événement dans la boîte noire : AIDE HUMAINE. Il s'écrit quand quelqu'un appuie sur le bouton « J'ai aidé » (écran du chef de démonstration), quand un humain reprend la main (brique 11), quand une tâche est relancée à la main, ou quand un geste est télécommandé.
* Quatre cases pour chaque essai : réussi du premier coup ; réussi après une reprise automatique ; réussi avec une aide humaine ; raté. Un essai ne va que dans une case.
* Trois chiffres, affichés avec leur niveau de preuve, leur nombre d'essais et leur date :
   * « réussis du premier coup : tant sur tant » ;
   * « une aide humaine pour tant de tâches », ou « aucune aide sur tant de tâches » ;
   * « plus longue durée sans arrêt : tant ».
* La commande « endurance ». On lui donne une durée. Elle rejoue le scénario en boucle sur le faux robot. Elle s'arrête au premier arrêt imprévu, et elle écrit : la durée tenue, le nombre de passages, la cause de l'arrêt. Dans un tour de boucle, ne la lance jamais plus de cinq minutes. Les longues durées, c'est Hiba qui les lance : écris-lui la commande exacte en haut du suivi.
* Un geste télécommandé par une personne porte l'étiquette « RÉEL · TÉLÉCOMMANDÉ », et il compte comme une aide humaine.
* Le protocole des essais réels. Copie le texte ci-dessous dans `docs/projet/PROTOCOLE_ESSAIS_REELS.md`, sur une page à imprimer. Mets un lien vers lui dans la page du compteur d'essais réels (J01), et ajoute à ce compteur un troisième bouton : « réussi avec aide ».
* Quand tu feras T27, mets ces trois chiffres dans la fiche de vérité.

Le protocole des essais réels (pour l'équipe, avec un vrai robot) :

1. Avant de commencer, écrivez le geste, et ce que « réussi » veut dire. Exemple : « le coussin est sur le lit et y reste dix secondes ».
2. Écrivez les conditions : le robot, la salle, la lumière, le bruit, l'heure, qui est aux commandes.
3. Faites dix essais de suite. Changez la position de départ de l'objet selon une liste écrite avant.
4. Comptez chaque essai, même raté. Aucun essai n'est effacé, ni refait « pour voir ».
5. Si quelqu'un touche le robot, l'objet ou le clavier pendant l'essai : c'est « réussi avec aide », ou « raté ».
6. Un arrêt de sécurité n'est pas un échec à cacher : notez-le, et dites pourquoi.
7. Notez le résultat dans le compteur tout de suite, pas de mémoire.
8. Si les conditions changent (autre salle, autre lumière), recommencez une série.

Fini quand : un essai où « J'ai aidé » a été pressé tombe dans la case « avec aide », jamais dans « du premier coup » ; l'endurance d'une minute écrit sa durée, ses passages et « aucun arrêt » ; une vérification provoque un arrêt, et l'endurance écrit sa cause ; les trois chiffres s'affichent avec niveau, nombre et date ; la ligne RÉEL dit « aucun essai compté » tant que l'équipe n'a rien compté.
K03 — Ce qui est vieux se voit ; demandé, confirmé, constaté
Après J02. Lis les parties 5.4 et 5.6 du cahier.

* L'âge de l'information. Chaque écran affiche « mis à jour il y a tant de secondes ». Au-delà d'une limite réglable (dix secondes pour commencer), la zone concernée se grise et affiche « information vieille de tant de secondes ». Quand tu feras T25, le tableau de flotte suivra la même règle.
* Trois temps pour chaque geste d'un robot, écrits dans la boîte noire avec leur heure :
   * DEMANDÉ : par qui (le badge), et pour qui ;
   * CONFIRMÉ : le robot dit qu'il a fini ;
   * CONSTATÉ : autre chose que la parole du robot le montre. Pour le faux robot : l'état du monde simulé, avec l'étiquette SIMULÉ. Pour un vrai robot : une personne qui appuie sur « je l'ai vu », ou un capteur.
* N'efface pas et ne renomme pas les états du cahier (demandée, attribuée, en route, livrée, échouée, reprise). Ajoute à côté une ligne : « constaté : oui » ou « constaté : pas encore ».
* Ajoute aux chiffres de K02 une ligne : « réussis et constatés : tant sur tant ». Ne change pas les lignes déjà là.
* Qui a donné l'accord. Quand un humain valide ou autorise quelque chose (un papier rangé, une pause, une reprise en main), la boîte noire écrit son badge et l'heure. Si c'est déjà le cas, vérifie-le seulement.

Fini quand : une vérification coupe les mises à jour d'un écran, et la zone se grise en moins de douze secondes ; un faux robot qui confirme sans que le monde change laisse la tâche à « constaté : pas encore », et l'essai n'entre pas dans « réussis et constatés » ; pour une livraison normale, la boîte noire contient les trois temps dans l'ordre ; les vérifications qui existaient passent toujours, sans avoir été changées.
K04 — Le choix expliqué, et dire avant de faire
Après T23. Lis la partie 5.10 du cahier.
Les meilleurs systèmes comparent plusieurs façons de faire avant d'agir, et ils savent dire pourquoi ils en ont choisi une.

* Pour chaque tâche de robot, le répartiteur garde la liste des robots qu'il a regardés. Pour chacun : libre ou non, la distance, la batterie, et si sa carte de rôle permet le lieu et le geste.
* Il écrit son choix en une phrase simple, fabriquée à partir de ces faits. Exemple : « J'envoie le robot de l'étage : il est libre, c'est le plus proche, et sa carte permet la chambre 12. Le robot du hall n'a pas le droit de monter. »
* Si aucun robot ne convient, la phrase le dit, et la tâche passe à un humain.
* Le bouton « Pourquoi ? », sur chaque tâche de robot du tableau des tâches : il montre les robots regardés, le choix, et le feu du gardien. Quand tu feras T25, mets le même bouton dans le tableau de flotte.
* Dire avant de faire. Avant tout départ, le robot annonce ce qu'il va faire et où il va : par la voix si elle existe, sinon par un texte à l'écran. La phrase est courte et calme. C'est la clinique qui fait l'annonce, juste avant d'envoyer l'ordre au gardien. Ne change pas le gardien pour cela.
* Tout est écrit dans la boîte noire. Ce sont des règles simples. Pas de nouveau modèle.

Fini quand : la même demande, jouée dans deux situations (un robot occupé, puis une batterie basse), donne deux choix différents et deux phrases différentes ; dans la boîte noire d'une répétition, chaque départ est précédé de son annonce ; le bouton « Pourquoi ? » montre les robots regardés ; quand aucun robot ne convient, la tâche passe à un humain et la phrase le dit.
K05 — Le tableau des capacités, et ce qui n'est pas résolu
Après J07. Lis la partie 5.12 du cahier.
Une équipe d'un grand concours publie un tableau : chaque capacité, et la façon dont elle a été vérifiée. Nous faisons le nôtre.

* La page « Ce que le système sait faire, et comment on le sait ». Une ligne par capacité : accueillir dans une langue, ranger un papier, suivre une liste de soin, rappeler le point oublié, apporter un objet, refuser un geste interdit, passer le relais, reprendre après une panne, brancher un robot inconnu, se rejouer seul. Ajoute celles qui manquent.
* Quatre colonnes : PROUVÉ SUR UN VRAI ROBOT (nombre d'essais, date) ; PROUVÉ SUR LE FAUX ROBOT (nombre d'essais) ; VÉRIFIÉ PAR DES TESTS SEULEMENT ; PAS FAIT.
* La page se fabrique à partir des résultats : la boîte noire, les essais comptés, le compteur d'essais réels, les vérifications. Elle n'est pas écrite à la main. Une capacité sans essai réel ne peut pas être dans la première colonne.
* « Ce que nous n'avons pas résolu ». En bas de la page, le contenu du fichier `docs/projet/PAS_RESOLU.md`. Crée-le avec cette liste de départ, que l'équipe complétera : un vrai service avec de vrais patients ; l'hygiène ; le réseau d'une vraie clinique ; la nuit ; l'accord du personnel ; les règles sur les appareils médicaux ; la saisie d'objets par un vrai bras ; le lien avec le logiciel d'une clinique. Pour chaque ligne : « pas essayé », ou « essayé, raté ». Jamais « bientôt ».
* La vraie salle. Ajoute six lignes à `docs/projet/SAMEDI_MATIN.md` : la lumière de la salle est-elle celle de nos essais ; y a-t-il des reflets ou des objets brillants ; quel est le bruit ; le Wi-Fi tient-il quand la salle est pleine ; a-t-on répété une fois dans la vraie salle, à l'heure de la démonstration ; l'heure exacte de la démonstration finale est-elle confirmée par les organisateurs.

Fini quand : la page s'ouvre depuis la page « Concours » (partie 6) ; avec un fichier d'essai, comme dans J01, un essai « réel » enregistré fait passer une ligne dans la première colonne, et la ligne revient quand le fichier est effacé ; une capacité dont la pièce est BLOQUÉ s'affiche PAS FAIT ; le contenu de `docs/projet/PAS_RESOLU.md` s'affiche en bas.
K06 — L'avis des personnes
Après T28 et J07.
Dans les concours de robots de soin, ce sont les personnes servies qui notent le robot. Lundi, nous voulons pouvoir montrer des avis, pas seulement des tests.
C'est un feu orange, comme J06 : le cahier interdit les données de vraies personnes. Pose cette question à Hiba, sauf si elle y a déjà répondu : « Es-tu d'accord pour recueillir, pendant le hackathon, des avis anonymes : cinq notes de 1 à 5 et un rôle, sans nom, sans texte libre, dans un fichier qui reste sur l'ordinateur ? »
Sans réponse, ou avec un non : la version simple. Fais-la sans attendre, et marque K06 FAIT (version simple). Si Hiba dit oui plus tard, la tâche revient « À FAIRE » pour la suite.

* Le formulaire : cinq questions, une note de 1 à 5 pour chacune, et un rôle à choisir : soignant, patient ou proche, visiteur, ingénieur, autre. Pas de nom. Pas de texte libre.
   * Le robot a-t-il dit ce qu'il allait faire avant de bouger ?
   * Est-il resté à une distance qui vous convenait ?
   * Vous a-t-il surpris ? (1 : souvent ; 5 : jamais)
   * Avez-vous compris ses refus, et ses « je ne suis pas sûr » ?
   * Seriez-vous d'accord pour qu'il aide dans un service de soins ?
* La page « Avis » affiche : « Aucun avis réel recueilli pour l'instant. »
* Pour tes vérifications, prends des avis d'essai, marqués ESSAI, que tu effaces ensuite. Tu n'écris jamais toi-même un avis réel.

Avec un oui de Hiba : en plus.

* La collecte s'allume : une adresse, et un code QR si T30 est fait. Avant les questions, une phrase : « Vos réponses sont anonymes. Elles servent à un prototype de concours. Vous pouvez arrêter quand vous voulez. »
* Les avis vont dans un fichier qui reste sur l'ordinateur. Il ne part jamais vers GitHub : une ligne dans `.gitignore`.
* La page « Avis » affiche le nombre d'avis, par rôle, et la moyenne de chaque question. En dessous de cinq avis, pas de moyenne : « trop peu d'avis ». Les mauvaises notes sont montrées comme les bonnes.

Fini quand, version simple : le formulaire enregistre un avis d'essai, puis l'efface ; la page affiche « Aucun avis réel… » ; elle s'ouvre depuis la page « Concours ».
Fini quand, avec le oui : avec six avis d'essai, la page affiche six avis et cinq moyennes ; avec quatre, elle affiche « trop peu d'avis » ; une vérification prouve que le fichier des avis ne fait pas partie de ce qui part vers GitHub ; les avis d'essai sont effacés.
K07 — L'invité aux commandes
Après T28, K01 et J02. Lis la partie 4.3 du cahier.
Lundi, le mieux est qu'un juré tienne lui-même les commandes. Il faut donc un écran que l'on comprend sans nous.

* L'écran « Invité ». Quatre grands boutons, chacun avec une phrase d'aide :
   * « Tirer une demande au hasard » (K01) ;
   * « Changer la langue » (partie 4.3) ;
   * « Cacher un objet » (partie 4.3) ;
   * « Provoquer une panne » (J02).
* Rien de dangereux n'est possible depuis cet écran. Il n'ouvre aucun réglage.
* Tout ce que fait l'invité est écrit dans la boîte noire, avec la marque INVITÉ.
* Le bouton « Remettre à zéro ». Il remet le scénario prêt à jouer, en moins de dix secondes, sans relancer les programmes. Il n'efface pas la boîte noire.
* Lisible par une personne âgée. Sur l'écran Invité et sur l'écran Patient : de gros caractères, un fort contraste, une idée par ligne. Une vérification mesure la plus petite taille de texte de ces deux écrans, et la compare à un seuil écrit dans les réglages.

Fini quand : chaque bouton marche depuis l'écran Invité, sans passer par un autre écran ; une commande essaie les quatre boutons dans six ordres différents, avec une remise à zéro entre chaque, et le scénario se rejoue ensuite sans erreur ; la remise à zéro prend moins de dix secondes ; les actions de l'invité portent la marque INVITÉ ; la vérification de la taille du texte passe.
6. La page et la commande du concours
La page « Concours ». La première tâche K que tu finis la crée. C'est une page de liens, pour le chef de démonstration : le tirage, les trois chiffres, le tableau des capacités, les avis, l'écran Invité. Chaque tâche K y ajoute son lien. Tu ne changes pas la page des preuves du premier avenant. Tu peux y ajouter un lien vers la page « Concours », mais seulement si aucune vérification qui existe n'en est changée.
La commande du concours. Une nouvelle commande, à côté de la grande répétition et de la commande des preuves. Tu ne changes ni l'une ni l'autre.
Chaque tâche K y ajoute son contrôle quand elle est finie. Ajouter le contrôle d'une nouvelle tâche est prévu : ce n'est pas « modifier une vérification ». Changer ou retirer un contrôle déjà écrit, si.
Les sept contrôles, joués sur le faux robot :

1. Le tirage : trois tirages, et « gestes interdits exécutés : 0 ».
2. L'aide humaine : une aide déclarée change la case de l'essai ; une endurance d'une minute finit sans arrêt.
3. L'âge de l'information : un écran coupé se grise ; une tâche confirmée mais pas constatée ne compte pas.
4. Le choix expliqué : deux situations, deux choix, deux phrases ; chaque départ a son annonce.
5. Le tableau des capacités : aucune capacité dans la colonne du vrai robot sans essai réel.
6. Les avis : le formulaire marche ; aucun avis d'essai ne reste ; la page dit vrai sur le nombre d'avis réels.
7. L'invité : les quatre boutons marchent ; la remise à zéro prend moins de dix secondes.

La commande affiche une ligne par contrôle, avec son étiquette. Tant que des tâches K ne sont pas finies, elle finit par `CONCOURS : INCOMPLET — (tant) contrôles sur 7`. Quand les sept existent : `CONCOURS : RÉUSSI` ou `CONCOURS : RATÉ — (ce qui manque)`.
Mêmes garde-fous que la grande répétition : jamais « RÉUSSI » si un contrôle est sauté ; une vérification casse exprès une pièce et contrôle que la commande dit bien « RATÉ ». Un contrôle dont la tâche est BLOQUÉ compte comme raté : écris-le, et Hiba décidera.
7. Si tu es perdu

* Une tâche K est trop grosse pour un tour : coupe-la en deux dans le suivi (K02a, K02b), comme le cahier le permet.
* Une tâche K t'oblige à changer une vérification qui existe, ou le sens d'un état : arrête-toi. C'est une question pour Hiba.
* Une tâche K demande un outil que tu n'as pas : feu orange. En attendant, fais la version simple.
* Un chiffre est mauvais : affiche-le quand même. Un « 21 sur 30 » vrai vaut mieux qu'un « 30 sur 30 » arrangé.
* Le temps manque : suis l'ordre de la liste. C'est Hiba qui choisit ce qu'on saute.
* Tu ne sais plus où tu en es : relis le suivi et le journal.

Fin de l'avenant 2.
