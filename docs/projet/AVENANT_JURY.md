Avenant « jury » au cahier de la clinique en boîte
Bonjour. Ce texte s'ajoute au cahier `docs/projet/CAHIER_CLINIQUE.md`. Il ne le remplace pas et il ne le change pas. Tu ne touches jamais au cahier.
Hiba a étudié le jury. Cet avenant ajoute sept tâches pour lui montrer des preuves.
Ce que Hiba écrit après la ligne « Fin de l'avenant. » ne fait pas partie de l'avenant : ce sont ses réponses. Note-les dans `docs/projet/QUESTIONS_POUR_HIBA.md`, avec la date.
Enregistrement : ce tour-ci, une seule fois
Ce tour-ci, tu ne construis rien. Tu enregistres l'avenant, tu mets le suivi à jour, et tu t'arrêtes.
Si tu es au milieu d'une tâche. Finis d'abord ton tour proprement, ou remets le dépôt dans un état où la vérification rapide passe. Ensuite seulement, fais les étapes ci-dessous.
Étape 1 — Enregistre ce texte. Mot pour mot, du titre jusqu'à la ligne « Fin de l'avenant. », dans `docs/projet/AVENANT_JURY.md`, à côté du cahier. Puis contrôle ta copie : elle doit faire 257 lignes à dix près, peser entre 20 300 et 21 400 octets, contenir sept tâches de J01 à J07, huit preuves numérotées dans la tâche J07, et finir par « Fin de l'avenant. ». Si le contrôle rate, dis-le et arrête-toi.
Étape 2 — Mets le suivi à jour. Dans `docs/projet/SUIVI_CLINIQUE.md` :

* en haut, ajoute la ligne : « Avenant : `docs/projet/AVENANT_JURY.md`. Ses règles s'ajoutent à celles du cahier. » ;
* ajoute les tâches J01 à J07, à l'état « À FAIRE », aux places données dans la partie 4 ;
* sur la ligne de T29, ajoute : « lis aussi l'avenant, J03 » ;
* sur la ligne de T33, ajoute : « après les tâches J aussi » ;
* mets le bonus B2 en tête des bonus ;
* ne change l'état d'aucune autre tâche, et ne touche pas à tes réparations.

Étape 3 — Note-le. En haut de `docs/projet/QUESTIONS_POUR_HIBA.md` : « Avenant jury reçu le (date). » Ajoute tout de suite la question de la tâche J06, sauf si Hiba y a déjà répondu. Puis une ligne dans `docs/projet/JOURNAL_CLINIQUE.md`.
Étape 4 — Enregistre le travail sur l'ordinateur. Envoie-le vers la branche `clinique-en-boite` seulement si Hiba a dit oui à l'autorisation C.
Étape 5 — Affiche le bilan, puis arrête-toi. Ces quatre lignes, puis l'encadré, et rien après :

```
AVENANT JURY : ENREGISTRÉ
Copie : (lignes), (octets), 7 tâches, 8 preuves, fin correcte
Suivi : 7 tâches ajoutées, aucun autre état changé
Suite : /clear, puis une des deux lignes

```


```
Hiba, pour lancer ou relancer la boucle :
1. Tape /clear.
2. Colle une de ces deux lignes. Elles remplacent celles du cahier.

/goal Construis « la clinique en boîte » en suivant docs/projet/CAHIER_CLINIQUE.md et docs/projet/AVENANT_JURY.md, un tour de boucle à la fois (partie 3 du cahier). Le but est atteint quand tu as affiché dans cette conversation : 1) le fichier docs/projet/SUIVI_CLINIQUE.md où chaque tâche T00 à T33 et J01 à J07 est marquée FAIT ou BLOQUÉ ; 2) la sortie complète de la grande répétition, qui se termine par « RÉPÉTITION : RÉUSSIE » ; 3) la sortie complète de la commande des preuves, qui se termine par « PREUVES : RÉUSSIES ». Tu ne modifies jamais le cahier, l'avenant ni une vérification pour y arriver. Arrête-toi aussi, en le disant, si tout ce qui reste attend une réponse de Hiba, ou après 40 tours.

/loop Tu construis « la clinique en boîte ». Lis docs/projet/CAHIER_CLINIQUE.md, partie 3, et docs/projet/AVENANT_JURY.md, partie 3, puis fais un tour de boucle, un seul, comme il est décrit.

```

1. Pourquoi cet avenant

* Lundi, le jury jugera les démonstrations. Pas les promesses.
* Il vient du terrain : des ingénieurs qui font marcher des robots hors du laboratoire, un spécialiste des enregistrements de robots, un fondateur qui veut un standard pour brancher les robots, un spécialiste du matériel, un industriel, des fondateurs. Et une chercheuse qui étudie pourquoi des robots qui marchent ne sont jamais adoptés ; elle connaît le monde du soin.
* Ils poseront des questions simples et dures. Chaque tâche de cet avenant répond à l'une d'elles par une preuve qu'on peut lancer devant eux.

2. Les règles en plus
Toutes les règles du cahier restent vraies : les feux, les étiquettes, les données inventées, pas de médecine, ne rien casser, dépenser peu. Si l'avenant et le cahier semblent se contredire, la plus prudente gagne, et tu poses la question.

1. Aucun nom de juré. Ni dans le code, ni sur un écran, ni dans un fichier.
2. Un chiffre affiché est calculé. Par une commande, jamais tapé à la main. Ce qui n'a pas été mesuré s'écrit « non mesuré ».
3. Un échec se montre. Aucun essai raté n'est effacé, caché, ou rejoué jusqu'à ce qu'il réussisse.
4. Aucune promesse non mesurée. N'écris nulle part que le robot « ne remplace personne », « fait gagner du temps » ou « soulage les équipes ». Écris ce que le système fait.
5. Aucune parole inventée. Tu n'écris jamais ce qu'un soignant « dirait ».
6. La version simple d'abord. Lisible et vrai suffit. Reprends les écrans et les façons de faire déjà là.
7. Ces sept tâches font partie de la liste. Elles ne sont pas « hors sujet ».

3. Comment ces tâches entrent dans la boucle

* Un tour de boucle se fait comme dans la partie 3 du cahier. Rien ne change : lire l'état, vérifier que rien n'est cassé, choisir une seule tâche, écrire sa vérification d'abord, prouver, ranger, finir par le bilan de quatre lignes.
* Une tâche J se choisit comme les autres : la première de la liste qui est « À FAIRE » ou « ESSAI 1 », et dont les tâches de la ligne « Après » sont finies.
* Pour une tâche J, lis sa description ici, et les parties du cahier qu'elle cite.
* T33 passe après toutes les tâches J.
* Les commandes longues de cet avenant (les vingt essais, les preuves) n'entrent pas dans la vérification rapide. Elle doit rester sous deux minutes.
* La boucle est finie quand les tâches T00 à T33 et J01 à J07 sont toutes FAIT ou BLOQUÉ, que la grande répétition réussit, et que la commande des preuves réussit. Affiche alors le suivi en entier, la sortie complète de la grande répétition, la sortie complète de la commande des preuves, puis la ligne `BOUCLE TERMINÉE`.

4. L'ordre dans la liste
Range les tâches du suivi dans cet ordre. Hiba peut le changer.

* T00 à T12, comme avant ;
* puis J01, J02, J03, J04, J06 ;
* puis T13 à T22 ;
* puis J05 ;
* puis T23 à T31 ;
* puis J07 ;
* puis T32 et T33 ;
* puis les bonus, B2 en premier.

Pourquoi : on prouve d'abord ce qui existe, avant d'ajouter des fonctions.
5. Les sept tâches
J01 — Les essais comptés
Après T12. Lis les parties 8 et 5.11 du cahier.
Le jury demandera : « Sur vingt essais, combien réussissent ? »

* Une commande joue le scénario vingt fois de suite sur le faux robot. À chaque essai, de petits changements : la langue d'arrivée, le point oublié, l'objet demandé, un objet absent de la réserve, un cerveau plus lent.
* Ces changements viennent d'une liste fixe, écrite dans un fichier. Ainsi on peut refaire exactement les mêmes essais.
* Par défaut, les essais se jouent avec le cerveau de test. Une option les joue avec le vrai Apertus. La fiche dit lequel a servi.
* Le résultat : pour chaque étape de la répétition, « réussie tant de fois sur vingt ». Pour chaque échec : le numéro de l'essai, l'étape, et l'heure dans la boîte noire.
* Une étape dont la pièce n'est pas encore construite s'affiche « pas encore construite ».
* La fiche de vérité affiche ce tableau, avec l'étiquette FAUX ROBOT et la date.
* N'ajuste pas la liste des changements pour obtenir vingt sur vingt. Un essai raté est une information : garde-le, et écris sa cause si tu la connais.
* Le compteur d'essais réels. Une petite page pour l'équipe, à utiliser avec un vrai robot pendant le hackathon : le nom du robot, le nom du geste, deux boutons « réussi » et « raté », une note courte. Chaque appui est écrit dans un fichier, avec l'heure. La fiche de vérité affiche ces essais à part, avec l'étiquette RÉEL. Tant que l'équipe n'a rien compté, elle affiche : « RÉEL : aucun essai compté ». Tu n'écris jamais toi-même un essai réel.

Fini quand : la commande affiche le tableau des vingt essais ; une vérification casse exprès une pièce, et le tableau montre l'échec avec son heure ; avec un fichier d'essai, le compteur enregistre un « réussi » et un « raté » et la fiche affiche « 1 sur 2 » ; puis le fichier d'essai est effacé et la fiche redit « aucun essai compté ».
J02 — Les pannes provoquées
Après T12. Lis les parties 5.10 et 4.3 du cahier.
Le jury demandera : « Si le Wi-Fi tombe, que fait le robot ? »

* Une page « Pannes », avec un bouton par panne. Les mêmes pannes se lancent aussi par une commande.
* Quatre pannes pour commencer :
   * le lien tombe entre le cerveau et un robot ;
   * le lien tombe entre le cerveau et une tablette ;
   * le cerveau ne répond plus ;
   * le micro n'entend que du bruit.
* Pour chaque panne, quatre choses obligatoires :
   * le robot se met à l'abri en passant par le gardien : il s'arrête là où il est, et il ne commence rien de nouveau ;
   * l'écran le dit en mots simples, en moins de cinq secondes : ce qui se passe, ce que le système fait, qui est prévenu ;
   * la boîte noire l'écrit ;
   * quand la panne finit, rien n'est perdu : les coches et les tâches en attente repartent.
* Pendant une panne, le système continue ce qu'il sait faire sans la pièce absente, et il le dit. Jamais de silence. Jamais de « tout va bien ».
* Une tablette sans lien garde la liste de soin déjà ouverte. On peut continuer à cocher. Elle affiche « hors ligne ».
* Chaque panne provoquée porte l'étiquette SIMULÉ.

Fini quand : pour chacune des quatre pannes, une vérification la provoque et contrôle les quatre choses obligatoires ; après le retour, aucune coche et aucune tâche n'est perdue ; la page liste les pannes avec leur étiquette.
J03 — L'instant précis
Après J01 et J02. Lis la partie 5.11 du cahier.
Le jury demandera : « Montrez-moi le moment exact où ça a raté. »

* Une page « Moments ». Elle lit la boîte noire d'une séance et liste les moments marquants, du plus récent au plus ancien : un échec, un « je ne suis pas sûr », un refus du gardien, une reprise par un humain, une panne, une phrase retirée faute de source, un papier non rangé.
* Un clic sur un moment montre quatre choses, dans l'ordre : ce que le système a vu ou entendu ; ce qu'il a décidé, et pourquoi, en une phrase ; ce qu'il a fait ; les dix secondes d'avant et d'après.
* Dans le tableau des essais comptés (J01), chaque échec mène à son moment.
* Les erreurs attrapées. Un compteur : combien de fois, dans la séance, le système s'est arrêté de lui-même ou a demandé un humain. Avec la liste de ces moments.
* Quand tu feras T29 (le rejeu autonome), mets-y aussi la liste des moments.

Fini quand : une séance qui contient une panne, un « je ne suis pas sûr » et un refus du gardien donne trois moments, chacun avec ses quatre choses ; un échec du tableau de J01 ouvre le bon moment ; le compteur des erreurs attrapées donne le bon nombre ; la page ne charge rien depuis l'extérieur.
J04 — Brancher un robot inconnu, chronomètre en main
Après T12. Lis la partie 5.12 du cahier, et le guide `BRANCHER_UN_ROBOT.md` s'il existe.
Le jury demandera : « Combien de temps pour brancher un robot que vous n'avez jamais vu ? Montrez-le. »

* Une deuxième carte d'identité, pour un robot d'une autre sorte que celui de la partie 5.12 : un petit robot à roues, sans bras, avec un plateau. Il porte, il ne saisit pas, il roule plus lentement, il n'a pas d'écran. Marque ses chiffres « à vérifier ».
* Le cerveau ne change pas. Il lit la carte et il s'adapte. Il ne donne jamais à ce robot une tâche qui demande un bras. Pour le coussin : le robot l'apporte sur son plateau et demande à un humain de le prendre.
* La commande « brancher ». On lui donne une carte. Elle lance le test de conformité de la prise, et elle affiche « contrôles réussis : tant sur tant ». Si un contrôle rate, elle dit lequel, et ce qu'il faut corriger, en une phrase.
* Le chronomètre. Il part quand on dit « je commence ». Il s'arrête seul quand tous les contrôles réussissent. La durée est écrite dans la fiche de vérité, sur deux lignes séparées : FAUX ROBOT, ce que tu mesures toi-même ; RÉEL, qui reste « à mesurer avec le vrai robot » tant que l'équipe ne l'a pas fait.
* Mets à jour le guide `BRANCHER_UN_ROBOT.md`, ou crée-le : une page, les étapes dans l'ordre, la commande, le chronomètre.

Fini quand : la deuxième carte passe le test de conformité ; l'étape du coussin réussit avec les deux sortes de robot ; une vérification compare les fichiers du cerveau avant et après, et prouve qu'aucun n'a changé ; le robot sans bras ne reçoit jamais une tâche qui demande un bras ; le chronomètre écrit une durée sur la ligne FAUX ROBOT et laisse la ligne RÉEL à « à mesurer ».
J05 — Qui décide : la main des soignants
Après T22 et T06. Lis les parties 5.10 et 5.5 du cahier.
Le jury demandera : « Qu'est-ce qui change pour les soignants, et qui l'a décidé ? »

* La pause. Depuis sa tablette, un soignant met en pause une chose que font les robots à son étage : rouler dans le couloir, parler, livrer, entrer dans une chambre. Il choisit une durée, et une raison dans une courte liste : soin en cours, repos, visite, autre.
* Le gardien applique la pause tout de suite. Le robot qui devait agir dit pourquoi il attend. La pause finit seule à l'heure dite, ou quand le soignant la lève. Tout est écrit dans la boîte noire.
* La page « Qui décide ». Pour chaque chose que fait le système (accueillir, orienter, livrer, rappeler un point, résumer pour le médecin, poser les questions du soir, ranger un papier) : qui peut l'allumer, qui peut la mettre en pause, qui est prévenu, et ce que le système ne fait jamais seul.
* Cette page se fabrique à partir des réglages réels : les cartes de rôle et les droits des badges. Elle n'est pas écrite à la main. Si un réglage change, la page change.
* Relis les textes de tous les écrans déjà construits, et enlève toute promesse non mesurée (règle 4 de cet avenant).

Fini quand : une action mise en pause est refusée tout de suite par le gardien, et le refus dit qui a mis la pause et jusqu'à quand ; la pause finit seule à l'heure dite ; une vérification change un réglage, et la page « Qui décide » change ; chaque pause est dans la boîte noire ; une vérification cherche les promesses de la règle 4 dans les textes des écrans et n'en trouve aucune.
J06 — La parole des soignants
Après T05.
Le jury demandera : « Avez-vous passé du temps avec des soignants ? » Aujourd'hui, la réponse est non. Cette tâche prépare la place pour leurs mots, sans rien inventer.
C'est un feu orange. Le cahier interdit les données de vraies personnes. Pose cette question à Hiba, sauf si elle y a déjà répondu : « Es-tu d'accord pour que l'équipe écrive, dans un fichier qui reste sur l'ordinateur, des phrases de vrais soignants sur leur travail, sans nom, avec leur accord, et jamais un mot sur un patient ? »
Sans réponse, ou avec un non : la version simple. Fais-la sans attendre, et marque J06 FAIT (version simple). Si Hiba dit oui plus tard, la tâche revient « À FAIRE » pour la suite. Pas de fichier de paroles. Tu fais seulement :

* le guide d'entretien : copie les dix questions ci-dessous dans `docs/projet/GUIDE_ENTRETIEN.md`, sur une page à imprimer ;
* deux étiquettes en plus, pour tout ce qu'un écran dit du travail des gens : DIT PAR UN SOIGNANT, ou HYPOTHÈSE ;
* une page « Ce qu'on nous a dit », qui affiche : « Aucune parole recueillie pour l'instant. Ce que nous disons du travail des soignants est une hypothèse. »

Avec un oui de Hiba : en plus.

* Un fichier `PAROLES_DES_SOIGNANTS.md`, rempli à la main par l'équipe. Une parole par ligne : la date, le métier sans nom, un thème (accueil, rappels, livraison, papiers, nuit, autre), « pour », « contre » ou « question », la phrase, et « accord pour citer : oui ».
* Ce fichier reste sur l'ordinateur. Il ne part jamais vers GitHub : tu as le droit d'ajouter une ligne au fichier `.gitignore` du dépôt pour cela.
* Tu n'y écris jamais une parole toi-même. Pour tes vérifications, prends un autre fichier d'essai, que tu effaces ensuite.
* La page « Ce qu'on nous a dit » affiche le nombre de paroles et de métiers, puis les phrases, rangées par thème. Les « contre » et les questions sont montrés autant que les « pour ». Seules les lignes qui ont l'accord sont affichées.
* En haut de la page, toujours : « Pas de nom. Pas un mot sur un patient. »

Le guide d'entretien. Avant de commencer : dire qui l'on est, que c'est un prototype pour un concours, et que rien n'est noté sans accord.

1. Racontez-moi votre dernière matinée de travail, du début à la fin.
2. Qu'est-ce qui vous prend du temps et qui n'est pas du soin ?
3. Qu'est-ce qui s'oublie le plus facilement quand la journée est chargée ?
4. Quand il vous manque un objet dans la chambre, que faites-vous ?
5. Comment apprenez-vous les habitudes d'un nouveau patient ?
6. Que se passe-t-il quand un patient ne parle pas votre langue ?
7. Avez-vous connu un robot ou un nouvel outil qui a été abandonné ? Pourquoi ?
8. Voici notre prototype. Qu'est-ce qui vous gênerait ? Qu'est-ce qui vous servirait ?
9. Qui devrait décider de ce que le robot a le droit de faire dans votre service ?
10. Qu'est-ce qu'un robot ne devrait jamais faire ici ?

Pour finir : « Pouvons-nous citer une de vos phrases, sans votre nom ? »
Fini quand, version simple : le guide tient sur une page ; la page « Ce qu'on nous a dit » affiche la phrase « Aucune parole recueillie… » ; les deux étiquettes existent.
Fini quand, avec le oui : en plus, avec un fichier d'essai de trois lignes dont une sans accord, la page en affiche deux et en compte deux ; une vérification prouve que le fichier des paroles ne fait pas partie de ce qui part vers GitHub ; le fichier d'essai est effacé.
J07 — La page des preuves
Après J01 à J06 (FAIT ou BLOQUÉ). Lis la partie 4.3 du cahier.
C'est la suite de « À vous ». Le jury choisit une question, on lui montre la preuve.

* Une page « Preuves », que le chef de démonstration ouvre après la scène 7. Huit boutons, écrits comme des questions :

1. « Sur vingt essais, combien réussissent ? » : le tableau de J01, et les essais réels s'il y en a.
2. « Montrez-moi le moment où ça a raté. » : la page « Moments ».
3. « Coupez le lien. » : la page « Pannes », avec aussi la panne de robot de T24.
4. « Comment sait-il qu'il se trompe ? » : les erreurs attrapées de la séance.
5. « Branchez un autre robot. » : la commande « brancher » et son chronomètre.
6. « Qui décide ? » : la page « Qui décide », et une pause en direct.
7. « Qu'en disent les soignants ? » : la page « Ce qu'on nous a dit ». Si elle est vide, elle le dit, et c'est une preuve honnête.
8. « Où tourne quoi ? » : un tableau fabriqué par le système. Pour chaque pièce (cerveau, écoute, voix, yeux, gardien, écrans, boîte noire) : la machine où elle tourne, « a besoin d'internet : non », son temps de réponse mesuré, la mémoire qu'elle prend. Ce qui n'est pas mesuré s'écrit « non mesuré ». La consommation électrique s'écrit « non mesurée », sauf si un outil déjà présent la donne.

* La commande des preuves. Elle joue les huit preuves l'une après l'autre sur le faux robot. Elle affiche une ligne par preuve, avec son étiquette, puis `PREUVES : RÉUSSIES` ou `PREUVES : RATÉES — (ce qui manque)`.
* Mêmes garde-fous que la grande répétition : jamais « RÉUSSIES » si une preuve est sautée ; une vérification casse exprès une pièce et contrôle que la commande dit bien « RATÉES ».

Fini quand : les huit boutons ouvrent chacun une preuve qui marche, sans toucher au code ; la commande affiche `PREUVES : RÉUSSIES` ; la vérification qui casse une pièce obtient `PREUVES : RATÉES`.
6. Si tu es perdu

* Une tâche J est trop grosse pour un tour : coupe-la en deux dans le suivi (J02a, J02b), comme le cahier le permet.
* Une preuve demande un outil que tu n'as pas : feu orange, comme dans le cahier. En attendant, fais la version simple.
* Tu es tenté d'arranger un chiffre : ne le fais pas. Un « 17 sur 20 » vrai vaut mieux qu'un « 20 sur 20 » arrangé.
* Tu ne sais plus où tu en es : relis le suivi et le journal.

Fin de l'avenant.
