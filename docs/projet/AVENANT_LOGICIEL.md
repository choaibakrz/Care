Avenant 4 « logiciel de la clinique » au cahier de la clinique en boîte
Bonjour. Ce texte s'ajoute au cahier `docs/projet/CAHIER_CLINIQUE.md` et aux trois avenants : `docs/projet/AVENANT_JURY.md`, `docs/projet/AVENANT_CONCOURS.md` et `docs/projet/AVENANT_MATERIEL.md`. Il ne les remplace pas et il ne les change pas. Tu ne touches jamais à ces quatre fichiers.
Hiba a étudié comment le logiciel d'une clinique parle aux autres logiciels. Dans une vraie clinique, il y a souvent deux logiciels : un pour l'administratif, un pour les soins. Cet avenant ajoute quatre petites tâches, pour que notre prototype soit prêt à se greffer sur le premier. Tout reste faux et simulé.
Ce que Hiba écrit après la ligne « Fin de l'avenant 4. » ne fait pas partie de l'avenant : ce sont ses réponses. Note-les dans `docs/projet/QUESTIONS_POUR_HIBA.md`, avec la date.
Enregistrement : ce tour-ci, une seule fois
Ce tour-ci, tu ne construis rien. Tu enregistres l'avenant, tu mets le suivi à jour, et tu t'arrêtes.
Si tu es au milieu d'une tâche. Finis d'abord ton tour proprement, ou remets le dépôt dans un état où la vérification rapide passe. Ensuite seulement, fais les étapes ci-dessous.
Étape 0 — Vérifie que les trois premiers avenants sont là. Les fichiers `docs/projet/AVENANT_JURY.md`, `docs/projet/AVENANT_CONCOURS.md` et `docs/projet/AVENANT_MATERIEL.md` doivent exister à côté du cahier, et le suivi doit contenir les tâches J01 à J07, K01 à K07, M01 et M02. Si ce n'est pas le cas, n'enregistre rien : affiche « AVENANT 4 : EN ATTENTE — un avenant manque », et arrête-toi. Hiba te le donnera d'abord.
Étape 1 — Enregistre ce texte. Mot pour mot, du titre jusqu'à la ligne « Fin de l'avenant 4. », dans `docs/projet/AVENANT_LOGICIEL.md`, à côté du cahier. Puis contrôle ta copie : elle doit faire 225 lignes à dix près, peser entre 21 000 et 22 200 octets, contenir quatre tâches de L01 à L04, neuf sortes de messages numérotées dans la tâche L02, et finir par « Fin de l'avenant 4. ». Si le contrôle rate, dis-le et arrête-toi.
Étape 2 — Mets le suivi à jour. Dans `docs/projet/SUIVI_CLINIQUE.md` :

* en haut, ajoute la ligne : « Avenant 4 : `docs/projet/AVENANT_LOGICIEL.md`. Ses règles s'ajoutent à celles du cahier et des trois premiers avenants. » ;
* ajoute les tâches L01 à L04, à l'état « À FAIRE », aux places données dans la partie 4 ;
* sur la ligne de K03, ajoute : « lis aussi l'avenant 4, L03 » ;
* sur la ligne de T27, ajoute : « lis aussi l'avenant 4, L03 » ;
* sur la ligne de K07, ajoute : « lis aussi l'avenant 4, L02 » ;
* sur la ligne de T33, ajoute : « après les tâches L aussi » ;
* ne change l'état d'aucune autre tâche, et ne touche pas à tes réparations.

Étape 3 — Note-le. En haut de `docs/projet/QUESTIONS_POUR_HIBA.md` : « Avenant 4 reçu le (date). » Ajoute tout de suite la question de cet avenant (tâche L02), sauf si Hiba y a déjà répondu. Puis une ligne dans `docs/projet/JOURNAL_CLINIQUE.md`.
Étape 4 — Enregistre le travail sur l'ordinateur. Envoie-le vers la branche `clinique-en-boite` seulement si Hiba a dit oui à l'autorisation C.
Étape 5 — Affiche le bilan, puis arrête-toi. Ces quatre lignes, puis l'encadré, et rien après :

```
AVENANT 4 : ENREGISTRÉ
Copie : (lignes), (octets), 4 tâches, 9 messages, fin correcte
Suivi : 4 tâches ajoutées, aucun autre état changé
Suite : /clear, puis une des deux lignes

```


```
Hiba, pour lancer ou relancer la boucle :
1. Tape /clear.
2. Colle une de ces deux lignes. Elles remplacent celles de l'avenant 3.

/goal Construis « la clinique en boîte » en suivant docs/projet/CAHIER_CLINIQUE.md, docs/projet/AVENANT_JURY.md, docs/projet/AVENANT_CONCOURS.md, docs/projet/AVENANT_MATERIEL.md et docs/projet/AVENANT_LOGICIEL.md, un tour de boucle à la fois (partie 3 du cahier). Le but est atteint quand tu as affiché dans cette conversation : 1) le fichier docs/projet/SUIVI_CLINIQUE.md où chaque tâche T00 à T33, J01 à J07, K01 à K07, M01, M02 et L01 à L04 est marquée FAIT ou BLOQUÉ ; 2) la sortie complète de la grande répétition, qui se termine par « RÉPÉTITION : RÉUSSIE » ; 3) la sortie complète de la commande des preuves, qui se termine par « PREUVES : RÉUSSIES » ; 4) la sortie complète de la commande du concours, qui se termine par « CONCOURS : RÉUSSI ». Tu ne modifies jamais le cahier, les avenants ni une vérification pour y arriver. Arrête-toi aussi, en le disant, si tout ce qui reste attend une réponse de Hiba, ou après 40 tours.

/loop Tu construis « la clinique en boîte ». Lis docs/projet/CAHIER_CLINIQUE.md, partie 3, puis docs/projet/AVENANT_JURY.md, partie 3, docs/projet/AVENANT_CONCOURS.md, partie 3, docs/projet/AVENANT_MATERIEL.md, partie 3, et docs/projet/AVENANT_LOGICIEL.md, partie 3, puis fais un tour de boucle, un seul, comme il est décrit.

```

1. Pourquoi cet avenant

* Notre faux dossier mélange deux choses. L'administratif : qui arrive, dans quelle chambre, quand il sort. Les soins : les habitudes, les listes, le résumé. Dans une vraie clinique, ce sont souvent deux logiciels.
* Un logiciel administratif prévient les autres par de petits messages : tel patient entre, change de chambre, sort. Ces messages suivent un standard public des hôpitaux.
* Il accepte aussi des propositions. Une pré-admission préparée ailleurs arrive dans une liste, et une personne des admissions la valide.
* Certains ont un bouton qui ouvre une autre page sur le bon patient, en lui passant le numéro du patient et le numéro du séjour.
* Si notre prototype sait lire ces messages, préparer ces propositions et s'ouvrir sur le bon patient, la greffe sur un vrai logiciel devient surtout un travail de réglage.
* Et le jury peut le voir : il admet un patient, et le robot de l'accueil le connaît.

2. Les règles en plus
Toutes les règles du cahier et des trois avenants restent vraies. Si deux textes semblent se contredire, la règle la plus prudente gagne, et tu poses la question.

1. Aucun vrai logiciel. Tu ne te connectes à rien et tu n'essaies rien. Tu n'écris le nom d'aucun vrai logiciel de clinique, ni le mot « compatible ». Le « hors sujet » du cahier reste vrai : pas de lien avec un vrai logiciel de clinique.
2. Lire d'abord. Notre système lit les messages. Il n'écrit jamais dans le faux logiciel. Une seule chose part vers lui : une proposition qu'une personne a validée (L04).
3. Rien de médical dans les messages. Seulement des numéros, un nom inventé, une date de naissance inventée, une langue, une chambre, des dates et une assurance « Exemple ». Jamais la raison du séjour. Aucun nom de médecin ou de soignant. Aucun numéro d'assurance sociale, même inventé.
4. Un message se relie par les numéros. Pour savoir de quel patient parle un message : le numéro du patient et le numéro du séjour, jamais le nom seul. À l'accueil, la personne dit toujours son nom, comme dans le cahier. Si deux arrivées du jour portent le même nom, le robot appelle un humain.
5. Un message illisible n'arrête rien. Il va dans une liste « messages à trier », avec son heure. Ce n'est pas la liste « à trier » des papiers. Une ligne inconnue dans un message est ignorée, sans erreur.
6. Tout est noté. Chaque message lu ou envoyé est dans la boîte noire, avec l'étiquette SIMULÉ.
7. Le standard public, et rien à installer. Les messages suivent le standard « HL7 version 2.5 », dans sa famille de messages « ADT ». Ce sont de simples textes : tu les écris et tu les lis sans outil nouveau. Si tu crois qu'il en faut un : feu orange.
8. Tu ajoutes, tu ne changes pas. Le faux dossier ne change pas. Le scénario ne bouge pas. Sans aucun message, les écrans montrent les mêmes patients et les mêmes données qu'avant. Si tu dois toucher la porte de lecture, fais-le le moins possible et note-le dans `DECISIONS.md`. Tu ne changes aucune vérification qui existe.
9. La version simple d'abord, et vite. Pas de cerveau dans ces tâches : des règles simples. Si une tâche L dépasse deux tours, coupe-la, ou marque-la BLOQUÉ avec ce qui manque.
10. Ces quatre tâches font partie de la liste. Elles ne sont pas « hors sujet ».

3. Comment ces tâches entrent dans la boucle

* Un tour de boucle se fait comme dans la partie 3 du cahier. Rien ne change.
* Une tâche L se choisit comme les autres : la première de la liste qui est « À FAIRE » ou « ESSAI 1 », et dont les tâches de la ligne « Après » sont finies.
* Pour une tâche L, lis sa description ici, et les parties du cahier et des avenants qu'elle cite.
* T33 passe après toutes les tâches J, K, M et L.
* Les vérifications de ces quatre tâches sont courtes. Elles entrent dans la vérification rapide, qui doit rester sous deux minutes. Il n'y a pas de nouvelle commande de fin.
* La boucle est finie quand les tâches T00 à T33, J01 à J07, K01 à K07, M01, M02 et L01 à L04 sont toutes FAIT ou BLOQUÉ, que la grande répétition réussit, que la commande des preuves réussit, et que la commande du concours réussit. Affiche alors le suivi en entier, puis ces trois sorties complètes, puis la ligne `BOUCLE TERMINÉE`.

4. L'ordre dans la liste
Range les tâches du suivi dans cet ordre. Hiba peut le changer.

* T00 à T12, comme avant ;
* puis J01, J02, J03, J04, J06 ;
* puis T13 à T22 ;
* puis K02, M02, M01 ;
* puis L01, L02, L03, L04 ;
* puis K03, K01 ;
* puis J05 ;
* puis T23, K04 ;
* puis T24 à T28, K07 ;
* puis T29 à T31 ;
* puis J07, K05, K06 ;
* puis T32 et T33 ;
* puis les bonus, B2 en premier.

Pourquoi : ces quatre tâches servent lundi, pour montrer la greffe. Elles passent après le scénario complet, et après ce qui sert dès samedi matin.
Si une tâche de cette liste est déjà faite ou déjà commencée, ne la déplace pas : place seulement les tâches L.
5. Les quatre tâches
L01 — D'où vient chaque donnée
Après T03. Lis les parties 5.1 et 5.2 du cahier.
Le jury demandera : « Dans une vraie clinique, d'où viendraient vos données ? »

* Une table des sources, dans un fichier lisible, à côté du faux dossier. Pour chaque sorte de donnée, elle dit d'où elle viendrait dans une vraie clinique :
   * ADMIN, le logiciel administratif : l'identité, la langue, le séjour et ses dates, la chambre, l'assurance, les papiers administratifs ;
   * SOINS, le dossier de soins : la raison du séjour, les habitudes, les listes de soin, les documents médicaux, le résumé, les questions pour le médecin ;
   * INCONNU : le programme des thérapies. Nous ne savons pas quel outil le planifie ;
   * NOUS : tout ce que le prototype crée, c'est-à-dire le carnet.
* Tu ne modifies pas les fiches du faux dossier. Pour cette tâche, la porte de lecture ne change pas non plus.
* Une page « D'où vient cette donnée ? » : la table, en clair, avec pour chaque ligne les badges qui ont le droit de la lire.
* Le badge « robot » ne reçoit aucune donnée SOINS. C'est déjà la règle du cahier : vérifie-le seulement.

Fini quand : chaque sorte de donnée du faux dossier a une source ; une vérification ajoute une sorte de donnée sans source, et la table la signale ; le robot ne reçoit aucune donnée SOINS ; la page s'affiche ; les vérifications qui existaient passent toujours, sans avoir été changées.
L02 — Le faux logiciel administratif et ses messages
Après T02 et L01. Lis les parties 5.1, 5.3, 6.1, 6.2 et 6.5 du cahier.

* Un petit programme à part : le « faux logiciel administratif ». Il porte l'étiquette SIMULÉ. Ce n'est pas un de nos écrans : il a sa propre page et son propre fichier, rangés à part.
* Son fichier tient la liste administrative : numéro du patient, numéro du séjour, nom inventé, date de naissance, langue, chambre, date d'entrée, date de sortie prévue, assurance « Exemple ».
* Pour les douze patients du faux dossier, recopie seulement ces lignes administratives. Reprends les numéros que le faux dossier donne déjà. S'il n'en donne pas, ne le change pas : tiens une petite table à côté. Si le faux dossier ne donne pas de date de naissance, ce champ reste vide. Une vérification contrôle que les deux fichiers disent la même chose.
* Ajoute trois personnes inventées « en attente » : elles ne sont pas encore arrivées, et notre système ne les connaît pas.
* À chaque événement, le faux logiciel écrit un message dans un dossier « du logiciel vers nous » : un fichier texte par message. Il y a neuf sortes de messages. Le code entre parenthèses est celui du standard :

1. la pré-admission (A05) ;
2. l'admission (A01) ;
3. le changement de chambre (A02) ;
4. la sortie (A03) ;
5. la correction d'une information (A08) ;
6. l'annulation d'une admission (A11) ;
7. l'annulation d'une sortie (A13) ;
8. le départ en congé (A21) ;
9. le retour de congé (A22).

* Chaque message a au moins quatre lignes : l'en-tête (qui envoie, quand, la sorte de message, un numéro unique, la version) ; l'événement (son heure) ; le patient (son numéro, son nom, sa date de naissance, sa langue) ; le séjour (son numéro, la chambre, les dates). Dans le standard, ces lignes s'appellent MSH, EVN, PID et PV1.
* Chaque message dit quel système l'a créé. Les heures sont celles de l'horloge de démonstration.
* La page « Faux logiciel administratif », pour le chef de démonstration : la liste, et un bouton par sorte de message. Chaque bouton écrit le bon message.
* Les boutons n'agissent que sur les personnes en attente et sur celles admises par message. Les douze patients du faux dossier sont dans la liste, mais verrouillés. Ainsi le scénario ne bouge pas.
* Pour admettre ou changer de chambre, le bouton propose une chambre parmi les lieux du cahier (partie 6.5). Deux personnes peuvent partager une chambre : le faux logiciel ne refuse pas.
* Un bouton « Remettre le faux logiciel à zéro » vide les dossiers de messages et remet les trois personnes en attente. Il n'efface pas la boîte noire. Chaque répétition et chaque vérification commence ainsi. Quand tu feras K07, sa remise à zéro fera aussi celle-ci.
* Deux liens. Sur cette page, un bouton « Ouvrir l'assistant » ouvre notre écran sur le bon patient. Il lui passe seulement le numéro du patient et le numéro du séjour, jamais un nom. On choisit son badge comme d'habitude, et la porte décide de ce qu'on voit. Sur notre écran de l'accueil, un bouton ouvre la fiche du patient dans le faux logiciel.
* Écris dans `NON_TESTE.md` : « messages fabriqués par nous au standard HL7 version 2.5 ; jamais essayés avec un vrai logiciel de clinique ».
* Question pour Hiba (écris-la, et continue sans attendre) : « Veux-tu que le nom du vrai logiciel de la clinique soit écrit dans une note du dépôt ? » Sans réponse : non.

Fini quand : chaque bouton écrit un message de la bonne sorte ; une vérification relit les neuf sortes de messages et y retrouve le numéro du patient, le numéro du séjour et la chambre ; aucun message ne contient la raison du séjour ; un patient verrouillé ne bouge pas ; le bouton « Ouvrir l'assistant » ouvre le bon patient ; la page porte l'étiquette SIMULÉ ; les vérifications qui existaient passent toujours, sans avoir été changées.
L03 — Le traducteur : lire les messages, tenir la vue à jour
Après L02 et T10. Lis les parties 5.2, 5.4 et 5.9 du cahier.
Le jury dira : « J'admets un patient. Votre robot le sait-il ? »

* Un programme, le traducteur, lit le dossier « du logiciel vers nous ». Il tient à jour la « vue administrative » : les personnes arrivées par message, leur chambre, leurs dates, leur état (attendu, présent, en congé, sorti).
* La porte de lecture donne cette vue, en plus du faux dossier. Nos écrans continuent de tout lire par la porte.
* Les règles des badges ne changent pas. Pour une personne arrivée par message, chaque badge voit la même sorte de choses que pour les autres : la direction ne voit aucun nom ; le robot ne voit que le prénom, la langue et le lieu.
* Une personne arrivée par message n'a que des données ADMIN. Les écrans de soins affichent pour elle : « dossier de soins : rien pour ce patient ».
* L'accueil (partie 5.9 du cahier) cherche la personne dans les arrivées du jour : celles du faux dossier, et celles de la vue. Si elle n'a pas de programme, le robot ne dit rien sur le programme.
* Une pré-admission seule ne suffit pas : la personne est « attendue », sans chambre. Le robot fait comme pour un nom inconnu : il appelle un humain.
* Sept règles de lecture :
   * un message se relie par les numéros (règle 4) ;
   * un message lu deux fois ne compte qu'une fois, grâce à son numéro unique ;
   * des messages arrivés dans le désordre sont remis en ordre par leur heure, puis par leur numéro ;
   * une annulation défait l'événement ;
   * un message illisible va dans « messages à trier » ;
   * une ligne inconnue est ignorée ;
   * un message créé par notre propre système n'est pas lu comme une nouveauté.
* L'écran de l'accueil affiche l'heure de la dernière nouvelle reçue. Si le faux logiciel se tait, la vue reste, et cette heure se voit. Quand tu feras K03, cette zone suivra sa règle.
* Mesure le temps entre l'écriture d'un message et sa lecture. Affiche-le sur la page du faux logiciel : « dernier message lu en tant de secondes », avec l'étiquette SIMULÉ.
* La boîte noire écrit chaque message lu. Ajoute à la fiche de vérité, si elle existe déjà, sinon quand tu feras T27 : « logiciel administratif : SIMULÉ ; messages lus : tant ; messages à trier : tant ».

Fini quand : une personne en attente, admise dans le faux logiciel, est connue de l'accueil en moins de dix secondes, avec sa chambre ; avant l'admission, le robot appelle un humain ; son changement de chambre se voit ; la correction de sa langue change la langue de la réponse ; sa sortie la retire des présents ; l'annulation de la sortie la remet ; le même message lu deux fois ne change rien ; deux messages inversés donnent le bon état ; un message abîmé va dans « messages à trier » et rien ne s'arrête ; une ligne inconnue est ignorée ; un message qui porte le nom de notre système ne compte pas comme une nouveauté ; sans aucun message, les écrans montrent les mêmes patients et les mêmes données qu'avant ; les vérifications qui existaient passent toujours, sans avoir été changées.
L04 — L'assistant prépare, une personne valide : la pré-admission
Après L03 et T09. Lis les parties 5.1 et 5.8 du cahier.
Le jury demandera : « Votre assistant écrit-il dans le logiciel de la clinique ? » La réponse : jamais seul.

* Fabrique deux papiers inventés de plus, en texte seulement, pour une quatrième personne que personne ne connaît encore : une lettre de médecin et une carte d'assurance « Exemple ». Le numéro de la carte est du type « EXEMPLE-0001 ».
* Ces deux papiers n'arrivent que sur demande, par un bouton du chef de démonstration : « Faire arriver deux papiers ». Sans cela, rien ne change. La remise à zéro les retire.
* Comme aucun patient ne correspond, ces papiers attendent dans « à trier », comme le veut le cahier. Là, un bouton nouveau : « Préparer une pré-admission ».
* L'écran de l'accueil propose alors une pré-admission déjà remplie : nom, prénom, date de naissance, langue, assurance, date d'arrivée prévue. Par des règles simples, comme pour T09.
* Chaque champ montre le papier d'où il vient, et un niveau de confiance. Un champ incertain, ou absent des papiers, reste vide, avec « je ne suis pas sûr ». Aucune information médicale n'est reprise.
* La proposition vit dans le carnet, comme les autres.
* Une personne, avec le badge « accueil », corrige, puis valide d'un doigt. Alors seulement, un message de pré-admission est écrit dans un dossier « de nous vers le logiciel ». Avant, rien ne part.
* Le faux logiciel administratif affiche la demande dans sa liste « pré-admissions reçues ». Une personne y appuie sur « admettre » : un message d'admission repart, et le traducteur le lit. La boucle est fermée.
* Le numéro de la pré-admission relie la demande et la réponse. Le carnet marque alors la proposition « admise ».
* La boîte noire écrit le badge de la personne qui a validé, et l'heure.
* Sur l'écran, une phrase fixe : « L'assistant prépare. Une personne décide. »

Fini quand : à partir des deux papiers inventés, la pré-admission est proposée avec ses sources ; sans validation, le dossier « de nous vers le logiciel » reste vide ; après validation, le message part et s'affiche dans la liste du faux logiciel ; « admettre » fait revenir une admission, et l'accueil connaît la personne ; un champ que les papiers ne donnent pas reste vide ; le message ne contient rien de médical ; le badge et l'heure de la validation sont dans la boîte noire.
6. Si tu es perdu

* Tu ne connais pas un détail du standard : fais simple, et écris-le dans `NON_TESTE.md`. N'invente pas ce que ferait un vrai logiciel.
* Une tâche L t'oblige à changer une vérification qui existe, ou le faux dossier : arrête-toi. C'est une question pour Hiba.
* Une vérification qui existe prend le faux logiciel pour un de nos écrans : ne change pas la vérification. Range le faux logiciel ailleurs, ou pose la question.
* La porte de lecture devrait beaucoup changer : arrête-toi, et propose la version simple.
* Le temps manque : fais L02 et L03. C'est ce que le jury peut voir.
* Tu ne sais plus où tu en es : relis le suivi et le journal.

Fin de l'avenant 4.
