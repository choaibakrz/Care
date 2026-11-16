Avenant 3 « matériel » au cahier de la clinique en boîte
Bonjour. Ce texte s'ajoute au cahier `docs/projet/CAHIER_CLINIQUE.md` et aux deux avenants, `docs/projet/AVENANT_JURY.md` et `docs/projet/AVENANT_CONCOURS.md`. Il ne les remplace pas et il ne les change pas. Tu ne touches jamais à ces trois fichiers.
Hiba a regardé quels robots seront peut-être prêtés samedi, et comment un concours récent compte un vrai geste. Cet avenant ajoute deux petites tâches : trois cartes de robots prêtes d'avance, et une page pour compter un vrai geste en dix minutes.
Ce que Hiba écrit après la ligne « Fin de l'avenant 3. » ne fait pas partie de l'avenant : ce sont ses réponses. Note-les dans `docs/projet/QUESTIONS_POUR_HIBA.md`, avec la date.
Enregistrement : ce tour-ci, une seule fois
Ce tour-ci, tu ne construis rien. Tu enregistres l'avenant, tu mets le suivi à jour, et tu t'arrêtes.
Si tu es au milieu d'une tâche. Finis d'abord ton tour proprement, ou remets le dépôt dans un état où la vérification rapide passe. Ensuite seulement, fais les étapes ci-dessous.
Étape 0 — Vérifie que les deux premiers avenants sont là. Les fichiers `docs/projet/AVENANT_JURY.md` et `docs/projet/AVENANT_CONCOURS.md` doivent exister à côté du cahier, et le suivi doit contenir les tâches J01 à J07 et K01 à K07. Si ce n'est pas le cas, n'enregistre rien : affiche « AVENANT 3 : EN ATTENTE — un avenant manque », et arrête-toi. Hiba te le donnera d'abord.
Étape 1 — Enregistre ce texte. Mot pour mot, du titre jusqu'à la ligne « Fin de l'avenant 3. », dans `docs/projet/AVENANT_MATERIEL.md`, à côté du cahier. Puis contrôle ta copie : elle doit faire 213 lignes à dix près, peser entre 20 200 et 21 400 octets, contenir deux tâches, M01 et M02, treize points numérotés dans le protocole de l'épreuve, et finir par « Fin de l'avenant 3. ». Si le contrôle rate, dis-le et arrête-toi.
Étape 2 — Mets le suivi à jour. Dans `docs/projet/SUIVI_CLINIQUE.md` :

* en haut, ajoute la ligne : « Avenant 3 : `docs/projet/AVENANT_MATERIEL.md`. Ses règles s'ajoutent à celles du cahier et des deux premiers avenants. » ;
* ajoute les tâches M01 et M02, à l'état « À FAIRE », aux places données dans la partie 4 ;
* sur la ligne de T31, ajoute : « lis aussi l'avenant 3, M01 » ;
* sur la ligne de K05, ajoute : « lis aussi l'avenant 3, M02 » ;
* sur la ligne de T33, ajoute : « après les tâches M aussi » ;
* ne change l'état d'aucune autre tâche, et ne touche pas à tes réparations.

Étape 3 — Note-le. En haut de `docs/projet/QUESTIONS_POUR_HIBA.md` : « Avenant 3 reçu le (date). » Ajoute tout de suite la question de cet avenant (tâche M01), sauf si Hiba y a déjà répondu. Puis une ligne dans `docs/projet/JOURNAL_CLINIQUE.md`.
Étape 4 — Enregistre le travail sur l'ordinateur. Envoie-le vers la branche `clinique-en-boite` seulement si Hiba a dit oui à l'autorisation C.
Étape 5 — Affiche le bilan, puis arrête-toi. Ces quatre lignes, puis l'encadré, et rien après :

```
AVENANT 3 : ENREGISTRÉ
Copie : (lignes), (octets), 2 tâches, 13 points, fin correcte
Suivi : 2 tâches ajoutées, aucun autre état changé
Suite : /clear, puis une des deux lignes

```


```
Hiba, pour lancer ou relancer la boucle :
1. Tape /clear.
2. Colle une de ces deux lignes. Elles remplacent celles de l'avenant 2.

/goal Construis « la clinique en boîte » en suivant docs/projet/CAHIER_CLINIQUE.md, docs/projet/AVENANT_JURY.md, docs/projet/AVENANT_CONCOURS.md et docs/projet/AVENANT_MATERIEL.md, un tour de boucle à la fois (partie 3 du cahier). Le but est atteint quand tu as affiché dans cette conversation : 1) le fichier docs/projet/SUIVI_CLINIQUE.md où chaque tâche T00 à T33, J01 à J07, K01 à K07, M01 et M02 est marquée FAIT ou BLOQUÉ ; 2) la sortie complète de la grande répétition, qui se termine par « RÉPÉTITION : RÉUSSIE » ; 3) la sortie complète de la commande des preuves, qui se termine par « PREUVES : RÉUSSIES » ; 4) la sortie complète de la commande du concours, qui se termine par « CONCOURS : RÉUSSI ». Tu ne modifies jamais le cahier, les avenants ni une vérification pour y arriver. Arrête-toi aussi, en le disant, si tout ce qui reste attend une réponse de Hiba, ou après 40 tours.

/loop Tu construis « la clinique en boîte ». Lis docs/projet/CAHIER_CLINIQUE.md, partie 3, puis docs/projet/AVENANT_JURY.md, partie 3, docs/projet/AVENANT_CONCOURS.md, partie 3, et docs/projet/AVENANT_MATERIEL.md, partie 3, puis fais un tour de boucle, un seul, comme il est décrit.

```

1. Pourquoi cet avenant

* Samedi, nous ne choisirons peut-être pas notre robot. Plus de cartes sont prêtes, plus vite nous branchons celui qu'on nous donne.
* Deux robots reviennent souvent dans les concours et les hackathons de cet automne : un robot à deux jambes et un robot à quatre pattes, de la même marque. Cette marque vend aussi un robot à roues à deux bras, le plus proche de notre histoire. Les trois seront peut-être à notre hackathon. Rien n'est sûr.
* Dans un hackathon, les robots sont souvent peu nombreux. Le temps de robot sera sans doute court. Il faut un essai qui tient en dix minutes, prêt avant d'avoir le robot.
* Un concours récent sur l'aide à domicile compte un geste proche du nôtre : déplacer des objets de trois étagères vers une table. Nous reprenons sa façon de compter. Elle est simple, et elle ne laisse pas tricher.

2. Les règles en plus
Toutes les règles du cahier et des deux avenants restent vraies. Si deux textes semblent se contredire, la règle la plus prudente gagne, et tu poses la question.

1. Aucun chiffre inventé sur un robot. Les seuls chiffres permis sur une carte sont ceux écrits dans cet avenant. Tout le reste s'écrit « à remplir samedi ».
2. Les chiffres d'une carte ne sont pas des mesures. Ils viennent de fiches publiques lues par Hiba. Ils s'affichent toujours avec « à vérifier samedi », jamais comme un résultat.
3. Une carte préparée sans le robot le dit. Elle porte la marque « PRÉPARÉE SANS LE ROBOT — non testé sur vrai robot ». N'écris nulle part « compatible ».
4. Le nom d'un modèle peut s'afficher sur sa carte. C'est le nom d'un outil. Rien d'autre sur son fabricant. Toujours aucun nom de juré, et aucun nom de concours.
5. Rien de l'extérieur. Pour ces deux tâches, tu n'installes aucun kit de fabricant, tu ne copies aucun dépôt et tu n'ouvres aucune page en ligne.
6. La prudence se règle, elle ne se devine pas. Les limites de vitesse, de distance et de charge sont écrites en clair, dans les cartes ou dans un fichier de réglages. Seule Hiba les change.
7. Tu n'écris jamais un essai réel. Pour tes vérifications, prends un fichier d'essai, que tu effaces ensuite.
8. Un score ne voyage pas seul. Il s'affiche toujours avec le robot, qui pilotait, le nombre d'aides et la date. Et il ne se compare qu'à nos propres essais.
9. Tu ajoutes, tu ne changes pas. Pas de nouvelle brique. Tu ne changes ni le gardien, ni le cerveau, ni les cartes qui existent, ni une vérification qui existe, ni le sens d'un état.
10. La version simple d'abord, et vite. Si une tâche M dépasse deux tours, coupe-la, ou marque-la BLOQUÉ avec ce qui manque. Ces deux tâches font partie de la liste : elles ne sont pas « hors sujet ».

3. Comment ces tâches entrent dans la boucle

* Un tour de boucle se fait comme dans la partie 3 du cahier. Rien ne change.
* Une tâche M se choisit comme les autres : la première de la liste qui est « À FAIRE » ou « ESSAI 1 », et dont les tâches de la ligne « Après » sont finies.
* Pour une tâche M, lis sa description ici, et les parties du cahier et des avenants qu'elle cite.
* T33 passe après toutes les tâches J, K et M.
* Les vérifications de ces deux tâches sont courtes. Elles entrent dans la vérification rapide, qui doit rester sous deux minutes. Il n'y a pas de nouvelle commande de fin.
* La boucle est finie quand les tâches T00 à T33, J01 à J07, K01 à K07, M01 et M02 sont toutes FAIT ou BLOQUÉ, que la grande répétition réussit, que la commande des preuves réussit, et que la commande du concours réussit. Affiche alors le suivi en entier, puis ces trois sorties complètes, puis la ligne `BOUCLE TERMINÉE`.

4. L'ordre dans la liste
Range les tâches du suivi dans cet ordre. Hiba peut le changer.

* T00 à T12, comme avant ;
* puis J01, J02, J03, J04, J06 ;
* puis T13 à T22 ;
* puis K02, M02, M01, K03, K01 ;
* puis J05 ;
* puis T23, K04 ;
* puis T24 à T28, K07 ;
* puis T29 à T31 ;
* puis J07, K05, K06 ;
* puis T32 et T33 ;
* puis les bonus, B2 en premier.

Pourquoi : ces deux tâches servent dès samedi matin. Elles passent donc avant les autres tâches K, mais après le scénario complet.
Si une tâche de cette liste est déjà faite ou déjà commencée, ne la déplace pas : place seulement M02 et M01.
5. Les deux tâches
M01 — Trois cartes de robots prêtes d'avance
Après J04. Lis la partie 5.12 du cahier, la tâche J04 du premier avenant, et le guide `BRANCHER_UN_ROBOT.md`.
Samedi, on nous dira : « Voici votre robot. » Sa carte doit déjà être là.

* Écris trois cartes d'identité de plus, dans le même format que la carte du petit robot à plateau (J04). Si un renseignement de la liste ci-dessous n'a pas de place dans ce format, mets-le dans une note de la carte. Ne change pas le format.
* Carte « Unitree G1 » : deux jambes, deux bras.
   * Taille : environ 1,3 m. Poids : environ 35 kg. Batterie : environ 2 heures.
   * Mains : « à remplir samedi ». Charge par bras : « à remplir samedi ».
   * Il marche. Il peut tomber.
   * Limites pour la démonstration : marche lente ; au moins 2 m entre lui et toute personne ; ni escalier ni ascenseur ; il pose l'objet sur une table, il ne le donne pas de la main à la main ; jamais sans une personne à l'arrêt.
* Carte « Unitree Go2 » : quatre pattes, pas de bras.
   * Il ne saisit rien. Il porte seulement si un panier est fixé sur son dos : « à vérifier samedi ».
   * Taille, poids, charge, batterie : « à remplir samedi ».
   * Limites pour la démonstration : marche lente, ni course ni saut ; au moins 1 m entre lui et toute personne ; 1 kg au plus sur le dos ; pas d'escalier ; jamais sans une personne à l'arrêt.
* Carte « Unitree G1-D » : deux bras sur une base à roues.
   * Poids : environ 80 kg avec sa base à roues. Hauteur : d'environ 1,3 m à environ 1,7 m. Chaque bras porte environ 3 kg. Il atteint environ 2 m de haut.
   * Sa base peut rouler vite. Mains ou pinces, batterie : « à remplir samedi ».
   * Limites pour la démonstration : il roule très lentement ; au moins 1 m entre lui et toute personne ; il pose l'objet sur une table, il ne le donne pas de la main à la main ; pas d'escalier ; jamais sans une personne à l'arrêt.
* Sur les trois cartes, une ligne « Version » : « il faut peut-être la version faite pour les développeurs : à vérifier samedi ».
* Pour le faux robot seulement, fais comme si les deux robots à bras pouvaient saisir un objet léger, et comme si le panier du robot à quatre pattes était là. Écris-le sur la carte.
* Chaque carte porte la marque de la règle 3. Seule une personne de l'équipe l'enlève, en écrivant la date où le vrai robot a été vu.
* Le cerveau ne change pas. Il lit la carte et il s'adapte, comme dans J04. Le robot à quatre pattes ne reçoit jamais une tâche qui demande un bras : pour le coussin, il l'apporte et demande à un humain de le prendre.
* La carte à remplir. Un fichier `docs/projet/CARTE_A_REMPLIR.md`, sur une page à imprimer : les lignes d'une carte, vides, dans l'ordre où on les demandera à la personne du fabricant. Elle sert pour un robot que personne n'a prévu. Mets un lien vers elle dans `BRANCHER_UN_ROBOT.md`.
* Samedi matin, en plus. Ajoute ces neuf lignes à `docs/projet/SAMEDI_MATIN.md`, sous le titre « En plus, pour le matériel ». Si le fichier n'existe pas encore, crée-le avec ces seules lignes : T31 y ajoutera les siennes sans rien effacer.
   * Quels modèles sont là, et dans quelle version : celle qu'on peut programmer ?
   * Combien de robots pour notre équipe, et pour combien de temps ?
   * Qui, chez le fabricant, peut nous aider sur place ?
   * Que fait le robot quand on appuie sur l'arrêt : il se fige, il s'assoit, il tombe ?
   * Un robot à jambes a-t-il besoin d'un support ou d'une sangle au début ?
   * A-t-il des mains ou des pinces ? Que peut-il saisir, et jusqu'à quel poids ?
   * Peut-on le télécommander ? Avec quoi, et qui en a le droit ?
   * Pour un robot sans bras : y a-t-il un panier ou un plateau ?
   * Y a-t-il trois niveaux d'étagère et une table pour l'épreuve (M02) ?
* Écris dans `NON_TESTE.md` : « les trois cartes n'ont été essayées que sur le faux robot ».
* Question pour Hiba (écris-la, et continue sans attendre) : « Les limites de prudence des trois cartes te conviennent-elles : 2 m pour le robot à jambes, 1 m pour les deux autres, marche lente, 1 kg sur le dos du robot à quatre pattes ? » Sans réponse : elles restent.

Fini quand : les trois cartes passent le test de conformité sur le faux robot, par la commande « brancher » ; l'étape du coussin réussit avec chacune ; avec la carte du robot à quatre pattes, aucune tâche qui demande un bras n'est donnée, et un humain est appelé pour prendre l'objet ; une vérification compare les fichiers du cerveau avant et après, et prouve qu'aucun n'a changé ; une vérification lit les trois cartes, et contrôle la marque de la règle 3 et « à vérifier samedi » sur chaque chiffre qui décrit le robot ; `docs/projet/CARTE_A_REMPLIR.md` tient sur une page ; `docs/projet/SAMEDI_MATIN.md` contient les neuf lignes ; les vérifications qui existaient passent toujours, sans avoir été changées.
M02 — L'épreuve des étagères : dix minutes, tout est compté
Après J01 et K02. Lis la tâche J01 du premier avenant et la tâche K02 de l'avenant 2.
Le jury demandera : « Et sur un vrai robot, ça donne quoi ? » Nous répondrons par un essai de dix minutes, compté devant lui.

* L'épreuve. En dix minutes, un robot déplace des objets de trois niveaux d'étagère vers une table. Chez nous, les étagères sont la réserve, et la table est celle de la chambre.
* Les points. 5 pour un objet pris en haut, 8 pour un objet pris au milieu, 10 pour un objet pris en bas. 3 en moins pour chaque objet tombé en route.
* La page « Étagères ». Une page pour l'équipe, lisible sur un téléphone, à côté du compteur d'essais réels (J01).
   * Avant le départ, on choisit : la carte du robot ; qui pilote (« le robot tout seul » ou « une personne ») ; si le robot saisit lui-même (« oui » ou « non ») ; et une note courte.
   * Le bouton « Départ » lance dix minutes, à la vraie heure, pas à l'horloge de démonstration.
   * Pendant l'essai : trois gros boutons « posé — haut », « posé — milieu », « posé — bas » ; un bouton « tombé » ; un bouton « J'ai aidé » ; un bouton « Arrêt de sécurité ». Le temps qui reste et le score s'affichent en gros.
   * Après dix minutes, ou après un arrêt de sécurité, l'essai est fini : un appui de plus est refusé. L'arrêt s'écrit avec son heure et une note.
   * Une erreur de doigt se corrige par le bouton « Annuler le dernier appui ». L'appui et son annulation restent écrits tous les deux.
* Ce qui s'écrit. Chaque appui va dans le fichier des essais réels, avec l'heure, comme dans J01. Un objet posé est un essai « réussi ». Un objet tombé est un essai « raté ». Le geste s'appelle « étagères, haut », « étagères, milieu » ou « étagères, bas ».
* L'aide. Après un appui sur « J'ai aidé », l'objet suivant compte « réussi avec aide » (K02). Si une personne pilote, tous les objets comptent « réussi avec aide », et l'essai porte l'étiquette « RÉEL · TÉLÉCOMMANDÉ ». Sinon, il porte l'étiquette « RÉEL ».
* Le résultat. Une ligne complète, jamais le score seul : le score, les objets par niveau, les objets tombés, les aides, qui pilotait, la carte du robot, la date. En dessous, toujours : « Ce score ne se compare qu'à nos propres essais. »
* Le mode « porteur », pour un robot qui ne saisit pas : une personne charge l'objet, une autre le prend à la table. La page compte les trajets, les objets arrivés, les objets tombés et les aides. Elle n'affiche aucun point. Dans ce mode, le geste s'appelle « porter ».
* Tant que l'équipe n'a rien compté, la page affiche : « RÉEL : aucun essai compté ».
* Le protocole. Copie le texte ci-dessous dans `docs/projet/EPREUVE_ETAGERES.md`, sur une page à imprimer. Mets un lien vers lui dans la page « Étagères ».
* Mets un lien vers la page « Étagères » dans la page « Concours », si elle existe et si aucune vérification qui existe n'en est changée. Sinon, écris son adresse en haut du suivi.
* Quand tu feras K05, ajoute au tableau la capacité « déplacer des objets d'une étagère à une table ».
* Écris dans `NON_TESTE.md` : « la page Étagères n'a compté aucun essai sur un vrai robot ».

L'épreuve des étagères (pour l'équipe, avec un vrai robot) :

1. Préparez trois niveaux d'étagère : en haut, le robot reste droit ; au milieu, il se penche ; en bas, il se baisse jusqu'au sol. Et une table, à quelques mètres.
2. Posez neuf objets légers, trois par niveau. Ils ne cassent pas et ne roulent pas. Avec neuf objets, le score le plus haut est 69.
3. Tracez la zone au sol. Pendant l'essai, personne n'y entre. Le public reste derrière la ligne : à 2 m au moins d'un robot à jambes, à 1 m au moins d'un autre robot.
4. Donnez les rôles : une personne tient l'arrêt et ne fait rien d'autre ; une personne tient la page « Étagères » ; une personne parle au public.
5. Avec un robot à jambes, demandez d'abord à la personne du fabricant comment l'arrêter sans le faire tomber.
6. Écrivez avant de commencer : le robot, qui pilote, la salle, la lumière, l'heure.
7. Le temps part quand le robot commence à bouger. Dix minutes, pas une de plus.
8. Un objet compte quand il est posé sur la table, lâché, et qu'il y reste.
9. Les points : 5 en haut, 8 au milieu, 10 en bas. 3 en moins par objet tombé en route.
10. Si quelqu'un touche le robot, un objet ou le clavier : appuyez sur « J'ai aidé ». Si une personne pilote le robot, dites-le : c'est un essai télécommandé.
11. Un arrêt de sécurité met fin à l'essai. Gardez le score du moment et notez pourquoi. Ce n'est pas un échec à cacher.
12. Aucun essai n'est effacé, ni refait « pour voir ». Un deuxième essai est un deuxième essai.
13. Dites le résultat en entier : le score, les objets tombés, les aides, qui pilotait. Ce score ne se compare qu'à nos propres essais.

Pour un robot sans bras : une personne charge l'objet à l'étagère, une autre le prend à la table. Comptez les trajets, les objets arrivés, les objets tombés et les aides. Pas de points.
Sans la page : comptez sur une feuille, avec les mêmes cases, et dites que le compte est fait à la main.
D'où vient cette façon de compter : de l'épreuve de tri d'objets d'un concours public de robots d'aide à domicile, tenu fin septembre 2026. Nous reprenons sa façon de compter, pas ses résultats.
Fini quand : avec un fichier d'essai, deux objets du haut, un du milieu, un du bas et un objet tombé donnent 25 points ; un appui sur « J'ai aidé » fait compter l'objet suivant « avec aide », et la ligne de résultat dit « aides : 1 » ; avec « une personne » aux commandes, tous les objets comptent « avec aide » et l'étiquette est « RÉEL · TÉLÉCOMMANDÉ » ; avec une heure d'essai, un appui fait après dix minutes est refusé ; un appui annulé ne compte plus, mais reste écrit ; en mode « porteur », aucun point ne s'affiche ; le fichier d'essai est effacé et la page redit « RÉEL : aucun essai compté » ; `docs/projet/EPREUVE_ETAGERES.md` tient sur une page ; les vérifications qui existaient passent toujours, sans avoir été changées.
6. Si tu es perdu

* Le format des cartes ne prévoit pas un renseignement : mets-le dans une note. Ne change pas le format.
* Une limite de prudence fait rater l'étape du coussin sur le faux robot : ne change ni l'étape, ni le gardien, ni la limite. Écris-le dans les questions.
* Une tâche M t'oblige à changer une vérification qui existe, le gardien ou le cerveau : arrête-toi. C'est une question pour Hiba.
* Tu connais un chiffre sur un de ces robots qui n'est pas dans cet avenant : ne l'écris pas. Écris « à remplir samedi ».
* Le temps manque : fais d'abord M02. La page et le protocole servent avec n'importe quel robot.
* Tu ne sais plus où tu en es : relis le suivi et le journal.

Fin de l'avenant 3.
