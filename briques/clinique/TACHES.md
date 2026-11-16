# La clinique en boîte — Petites tâches

La liste complète et son état sont dans `docs/projet/SUIVI_CLINIQUE.md` (T00 à T33, J01 à J07). Ici : ce qui reste pour l'équipe
sur le squelette. Chaque tâche : une personne, moins d'une heure, avec son essai. Cocher quand l'essai passe.

## Le squelette
- [ ] Refaire la mesure des essais longs sur le MacBook M2 et comparer avec `essais_longs.txt` (mesuré sur l'iMac seulement).
- [ ] Si la vérification rapide dépasse deux minutes : mesurer (`python3 lancer.py tests --durations=40`) et ajouter
      à `essais_longs.txt` les essais de l'ossature de 1,5 seconde ou plus. Jamais un essai de la clinique.
- [ ] Le cerveau de test (réponses fixes) : à créer avec la première pièce qui appelle le cerveau (cahier, 2.8).
- [ ] Écrire la grande répétition dans la boîte noire, pour la fiche de vérité (avec T27).

## Le faux dossier (`faux_dossier/`, `dossier.py`)
- [ ] Faire relire les textes des documents inventés par quelqu'un qui parle la langue : italien (p01, p06), allemand (p02, p04, p07, p10), anglais (p08), portugais (p11).
- [ ] Remplacer les trois listes d'exemple par les listes de la clinique (`listes_de_soin.yaml`), en gardant la même forme.
- [ ] Donner un étage aux chambres 15 à 24 et les ajouter au plan (`lieux.yaml`) si la démonstration en a besoin.
- [ ] Fabriquer les images des six documents et de la feuille volante, avec « INVENTÉ » en travers (avec T15).

## La porte de lecture (`porte.py`, `badges.yaml`)
- [ ] Ajouter l'outil `lire_dossier` à la commande `python3 lancer.py porte-agents` (une option, par exemple `--clinique`), puis l'essayer avec un vrai agent.
- [ ] Donner un étage aux patients des chambres 15 à 24 : aujourd'hui aucun soignant ne les voit (étage non précisé).
- [ ] Décider qui sont « les patients » d'un médecin et d'un thérapeute dans la vraie clinique (ici : une liste inventée dans `badges.yaml`).
- [ ] Envoyer aussi chaque accès dans la boîte noire (brique 12), pour la fiche de vérité (avec T27).

## L'horloge de démonstration (`horloge.py`, `heures_scenario.yaml`)
- [ ] Mettre les vraies heures de la démonstration dans `heures_scenario.yaml` si le scénario change.
- [ ] Un bouton « revenir au début » pour rejouer la démonstration sans relancer le programme (aujourd'hui : relancer).

## Les écrans (`ecrans.py`, `essai_reseau.py`)
- [ ] Ouvrir `…/clinique` depuis un vrai téléphone et depuis le MacBook, sur le Wi-Fi du lieu, et noter le résultat dans `NON_TESTE.md`.
- [ ] Faire relire les mots des écrans (`TEXTES` dans `ecrans.py`) : allemand, italien, anglais.
- [ ] Écran du patient : le plan « où dois-je aller ? » (la porte ne donne pas encore les lieux au badge patient).
- [ ] Écran du patient : le bouton « un humain, s'il vous plaît » (il lui faut le carnet, qui vient avec T06).
- [ ] Traduire le programme du patient (aujourd'hui en français, comme dans le faux dossier).
- [ ] Brancher les pages sur le flux en direct de la brique 13 (aujourd'hui : mise à jour toutes les deux secondes).
- [ ] Le motion design : les pages sont volontairement simples ; le style est dans `STYLE`, en haut de `ecrans.py`.

## Le carnet et les listes de soin (`carnet.py`, `listes.py`)
- [ ] Relire les noms courts et les mots proches des points (`faux_dossier/listes_de_soin.yaml`) avec un soignant.
- [ ] Faire relire `mots_des_points.yaml` (allemand, italien, anglais) par quelqu'un qui parle la langue, et y ajouter les mots vraiment dits.
- [ ] Brancher les vraies oreilles (brique 4) sur `listes.entendre` quand le modèle d'écoute est là (R4), et mesurer : sur vingt « sonnette, fait » dits par plusieurs personnes, combien cochent le bon point.
- [ ] Dire « je sors » à la voix ; répondre dans la langue de la personne.
- [ ] Donner au thérapeute et à l'accueil la vue des listes prévues, pour qu'ils cochent leurs points (liste « sortie », « avant la physiothérapie »).
- [ ] Relire le carnet au démarrage, pour retrouver les coches après un redémarrage.
- [ ] Écrire aussi chaque ligne du carnet dans la boîte noire (avec T27).
- [ ] « Je sors » : dire aussi les points en attente d'un objet (avec T07).
- [ ] Essayer les boutons sur une vraie tablette, avec un soignant : taille des boutons, « Je sors », fin de poste.
- [ ] Fin de poste : ranger les points par patient, et replier les listes pas commencées (21 points, c'est long).
- [ ] Remplacer la petite fenêtre « Pourquoi reporter ce point ? » par des raisons toutes prêtes à toucher.
- [ ] Traduire les pages des listes en allemand (aujourd'hui en français seulement).
- [ ] Une vraie notion de poste (matin, soir, nuit) pour « ce que le poste d'avant n'a pas fini ».

## Le tableau des tâches et la demande au robot (`taches.py`)
- [ ] Décider avec Hiba quel point de la liste « le coussin » coche dans le scénario (le cahier dit « le point se coche », mais aucune des trois listes ne parle d'un coussin).
- [ ] Sur la page d'une liste : un bouton « il manque un objet » sur chaque point (aujourd'hui la demande par bouton n'est liée à aucun point ; le lien existe déjà dans `demander(..., liste=, numero=)`).
- [ ] Comprendre la demande en allemand, italien, anglais (noms des objets de la réserve dans les quatre langues), à la voix comme au bouton.
- [ ] Faire dire la question (« Lequel … ? ») par la voix du Mac ou du robot, et l'écrire comme le cahier : « Le grand, ou celui pour la nuque ? ».
- [ ] Oublier une question posée à la voix après une minute sans réponse.
- [ ] Montrer les tâches « pour un humain » à la bonne personne (poste de soins), et permettre de les fermer.
- [ ] Décompter la réserve dans le carnet (aujourd'hui, les quantités ne baissent pas).
- [ ] Poser la question courte avec la brique 8 (« je ne suis pas sûr »), pour qu'elle passe aussi par la voix.

## Le coursier (`coursier.py`, `monde_clinique.yaml`)
- [ ] Robot à plateau : dire la demande dans la langue de la personne ; rappeler l'humain après 30 secondes.
- [ ] Robot à plateau : mettre le bouton « C'est fait » aussi sur la page de la liste et sur l'écran du thérapeute.
- [ ] Samedi : remplacer les chiffres « à vérifier » de la carte par ceux du vrai robot (vitesse, charge du plateau).
- [ ] Samedi : mesurer la salle et mettre les vraies positions dans `monde_clinique.yaml` (réserve, chambre du mannequin).
- [ ] Avec le vrai robot : suivre `BRANCHER_UN_ROBOT.md` d'abord ; la première course se lance par un humain, gardien allumé.
- [ ] Après un échec en route : ramener l'objet à la réserve, ou passer la tâche à un humain.
- [ ] Brancher l'accord d'un humain (écran du gardien) pour les courses de la clinique.
- [ ] Le robot dit ce qu'il va faire avant de bouger (avenant 2, K04).
- [ ] Faire dire au robot, dans la chambre, une phrase dans la langue de la personne (« Voici votre coussin »).

## Le résumé du médecin (`resume.py`, `ecrans_resume.py`)
- [ ] Faire relire les cinq lignes par un médecin : est-ce le bon contenu, dans le bon ordre ?
- [ ] « Ce qui attend une décision » : aujourd'hui, seulement les sources pas d'accord. Décider avec un médecin quoi ajouter.
- [ ] « Ses questions » : la ligne se remplira avec les questions du soir (T19) ; elle lit déjà les lignes « question… » du carnet.
- [ ] La mention « je prépare… » à l'écran pendant qu'un résumé est refait (utile avec Apertus, T13 ; la version simple est immédiate).
- [ ] Appeler `preparer()` au repère « résumé prêt » de l'horloge (avec T11, le chef de démonstration).
- [ ] Donner une date aux documents du faux dossier, pour que « le dernier » veuille dire quelque chose dans la recherche.
- [ ] Traduire le résumé en allemand (aujourd'hui en français seulement, même sur l'écran allemand du médecin).
- [ ] Les papiers validés (T09) sont dans le carnet : les compter comme documents du résumé.

## Les papiers (`papiers.py`, `ecrans_papiers.py`)
- [ ] Faire relire la liste des endroits du dossier (`TYPES` dans `papiers.py`) par quelqu'un de l'accueil d'une clinique : elle est inventée.
- [ ] Faire relire les mots allemands et italiens qui font reconnaître un type de papier.
- [ ] Donner à l'humain un moyen de ranger à la main un papier « à trier » (choisir le patient). Aujourd'hui il attend, c'est tout.
- [ ] Laisser l'humain corriger aussi le patient, la date et l'auteur (aujourd'hui : le type seulement).
- [ ] Brancher le vrai Apertus sur la porte `lire(texte, types, patients)` du rangement (après R2), avec un formulaire imposé, et mesurer : combien de papiers bien rangés sur les six du faux dossier, en combien de temps.
- [ ] Choisir, dans les réglages, qui propose le rangement : les règles ou le cerveau (aujourd'hui : les règles).
- [ ] Photographier de vrais papiers INVENTÉS (imprimés, tamponnés « INVENTÉ », un formulaire rempli à la main par quelqu'un de l'équipe), les lire avec `lecture_mac`, et noter le taux d'erreur dans `NON_TESTE.md`.
- [ ] Brancher le lecteur d'images dans la page des papiers (un réglage), et montrer à l'accueil « texte lu depuis l'image ».
- [ ] Régler le seuil « lecture peu sûre » (0,9) sur de vrais papiers.
- [ ] Montrer au médecin et au soignant les papiers validés (ils sont au carnet ; le résumé du médecin ne les compte pas encore).
- [ ] Essayer la page sur une vraie tablette, à l'accueil.

## L'accueil du hall (`accueil.py`, `accueil_hall.yaml`, `ecrans_accueil.py`)
- [ ] Faire relire les phrases allemandes, italiennes et anglaises du robot par quelqu'un qui parle la langue.
- [ ] Faire relire les mots de la règle « rien sur la santé dans le hall » dans les quatre langues, et en ajouter.
- [ ] Décider avec Hiba si cette règle doit entrer dans le gardien de l'ossature (question Q12).
- [x] L'accueil à la voix (T20, tour 37) : `accueil_voix.py`, à partir d'un enregistrement ; la voix du Mac répond.
- [ ] L'accueil à la voix : un bouton « parler » sur l'écran du hall (micro en direct), et l'essai avec de vraies personnes dans les quatre langues.
- [ ] Permettre à la personne de l'accueil de fermer un appel du hall (« j'y vais »).
- [ ] Dessiner le chemin sur un plan simple (aujourd'hui : une liste de lieux avec les mètres).
- [ ] Le portugais (cinquième langue du faux dossier) : pas de phrases, le robot répond en français.

## La parole des soignants (`paroles.py`, `docs/projet/GUIDE_ENTRETIEN.md`)
- [ ] Demander à Hiba sa réponse à Q7 ; avec un oui : le fichier des paroles, rempli à la main par l'équipe, jamais envoyé vers GitHub.
- [ ] Imprimer `docs/projet/GUIDE_ENTRETIEN.md` et parler vingt minutes avec une personne qui fait ce travail, avant ou pendant le hackathon.
- [ ] Poser l'étiquette HYPOTHÈSE sur les autres écrans qui décrivent le travail des gens (fin de poste, habitudes, accueil).

## Brancher une carte (`brancher.py`, `BRANCHER_UN_ROBOT.md`)
- [ ] Samedi matin, une personne de l'équipe : écrire la carte du robot reçu, dire « je commence », passer le test sur le faux robot, noter la durée.
- [ ] Mesurer le temps RÉEL pour brancher le vrai robot (étapes 0 à 6 du guide), et l'écrire dans la fiche de vérité, ligne RÉEL.
- [ ] Casser exprès une carte (une capacité que le robot n'a pas) et vérifier que le conseil « à corriger » aide vraiment.

## Les moments (`moments.py`)
- [ ] Ouvrir la page sur une vraie séance avec le faux robot (un refus du gardien, un arrêt d'urgence, une main humaine) et corriger ce qui s'affiche mal.
- [ ] Recopier le carnet de la clinique dans la boîte noire (T27), pour ne lire qu'un seul fichier.
- [ ] Permettre d'ouvrir la page depuis une tablette de l'équipe (un champ pour le code d'équipe).
- [ ] Mettre la liste des moments dans le rejeu autonome (T29).
- [ ] Relire avec l'équipe ce qui compte comme « erreur attrapée ».

## Les pannes provoquées (`pannes.py`)
- [ ] Samedi : couper pour de vrai le Wi-Fi d'une tablette ouverte sur une liste, cocher, rallumer, et noter le résultat dans `NON_TESTE.md`.
- [ ] Essayer la tablette hors ligne dans Safari sur iPad et sur un téléphone.
- [ ] Hors ligne : garder aussi « Je sors » et les trois choix de fin de poste ; afficher l'heure où la coche a été faite.
- [ ] Rejouer « le cerveau ne répond plus » avec le vrai Apertus (arrêter `llama-server`) et « le micro » avec un vrai micro dans le bruit.
- [ ] Montrer sur la page des papiers la phrase « n papiers sans proposition : le cerveau ne répond plus ».
- [ ] Décider si, micro en panne, une demande au robot faite au doigt peut partir.
- [ ] Faire passer les pièces à la voix (T16, T17, T20) par `Pannes.entendre()`.
- [ ] Afficher le bandeau de panne aussi sur les pages à formulaire (hall, soir, dictée, essais réels).
- [ ] Prévenir quelqu'un pour de bon pendant une panne (un appel sur l'écran du poste de soins, un son).
- [ ] Samedi : provoquer la panne du lien avec le vrai robot, gardien allumé, un humain près du bouton d'arrêt ; noter ce que fait le robot.
- [ ] Mesurer le temps entre la panne et le bandeau sur une vraie tablette (but : moins de cinq secondes).

## Les essais comptés (`essais.py`, `essais.yaml`)
- [ ] Faire varier aussi les autres étapes (papiers d'un autre patient, autre question du soir, autre dictée, autre panne).
- [ ] Jouer les vingt essais avec le vrai Apertus quand une pièce l'appellera (R2, T13) ; mesurer « cerveau plus lent ».
- [ ] Samedi : mettre `ecran.local_sans_code: false` et un code d'équipe dans `reglages.yaml`, puis compter les essais réels sur `/clinique/essais-reels` (une personne qui regarde le robot, pas celle qui le pilote).
- [ ] Essayer la page des essais réels sur un téléphone ; grossir les deux boutons si besoin.
- [ ] Proposer les noms des robots et des gestes dans une liste, pour éviter deux écritures du même geste.
- [ ] Montrer le dernier tableau (`journal/essais_dernier.json`) sur la page des preuves (J07).
- [ ] Faire relire les phrases d'arrivée des essais par quelqu'un qui parle la langue.

## La fiche de vérité et « rien n'est sorti » (`fiche.py`, `rien_dehors.py`)
- [ ] Écrire la répétition et sa fiche dans la boîte noire, et montrer la fiche sur un écran (T27).
- [ ] Allumer la surveillance du réseau aussi pendant la démonstration avec les écrans, et afficher son compte.
- [ ] Vérifier de l'extérieur que rien ne sort : couper le Wi-Fi et rejouer ; ou écouter le réseau avec un outil déjà présent sur le Mac.
- [ ] Compter les aides humaines pendant une vraie démonstration, pour la ligne « part de l'humain » (avenant 2, K02).
- [ ] Remplir « taux d'erreur de lecture des papiers » (T15) et « taux d'erreur de la voix, par langue » (T16 à T20).

## La flotte, version simple (`flotte.py`, `flotte.yaml`)
- [ ] Deux boutons sur la page de la flotte, pour l'équipe seulement : « R3 tombe en panne » et « reprendre la course ».
- [x] Plusieurs faux robots qui se déplacent sur le plan (R5, tour 38) : `monde_robots.py`.
- [ ] Relier le monde des robots à la flotte : `Flotte.partir` et `Flotte.panne` passent par le monde (T23, T24) ; la page de la flotte montre où sont les robots et leur batterie (T25).
- [x] Les cartes de rôle : cinq fichiers, appliqués dans le monde simulé et à la voix (T22a, tour 39) : `cartes.py`.
- [x] Les cartes de rôle appliquées par le gardien pour R1 (T22b, tour 40) : `cartes_gardien.py` ; la page de la flotte montre la carte et ses changements.
- [ ] Un bouton à l'écran pour changer la carte d'un robot (T25) ; la répétition joue R1 en carte Accueil (scène 1) puis Étage (scène 3), cahier 6.6.
- [ ] Le volume de la voix du robot : la prise n'a pas ce réglage (à voir samedi avec le vrai robot).
- [ ] Faire relire le contenu des cinq cartes par l'équipe (lieux, vitesses, volumes : inventés).
- [ ] Le répartiteur : le robot libre le plus proche, avec la bonne carte et assez de batterie (T23).
- [ ] « Un humain reprend la main » : brancher la brique 11 et l'écrire dans la boîte noire (T24).
- [ ] Réparer un robot en panne (aujourd'hui il reste en panne jusqu'à la fin de la séance).
- [ ] Décider qui a le droit de voir la page de la flotte (aujourd'hui : pas de badge).

## Le soir et la dictée (`soir.py`, `ecrans_soir.py`)
- [ ] Faire relire les phrases du soir (`PHRASES` dans `soir.py`) et les deux questions du scénario : italien, allemand, anglais.
- [ ] Brancher Apertus sur la porte `traduire(texte, de, vers)` (après R2) et mesurer sur vingt questions inventées, relues par quelqu'un qui parle la langue : combien de traductions justes.
- [ ] Faire relire l'italien des deux questions du scénario (`traductions_scenario.yaml`).
- [ ] La dictée à la voix (T18) ; la question du soir à la voix.
- [ ] Laisser le médecin corriger ou effacer son brouillon avant que la tâche parte.
- [ ] Laisser le thérapeute dire « fait » ou « pas pu » sur une tâche (aujourd'hui il la voit, c'est tout).
- [ ] Relire avec un médecin la liste des premiers mots (`DESTINATAIRES` dans `soir.py`) : « Physio », « Soins », « Accueil »…
- [ ] Une tâche pour un métier que personne ne suit (pas de thérapeute pour ce patient) : décider à qui elle va (aujourd'hui : le prototype prévient le médecin, c'est tout).
- [ ] Question de santé le soir : créer aussi une « tâche pour un humain » ? (question Q15)
- [ ] Essayer la page du soir sur une vraie tablette, avec une personne qui lit l'italien.

## Le scénario (`scenario_clinique.yaml`, `chef_clinique.py`)
- [ ] Jouer les sept scènes avec des personnes, chronomètre en main, et noter la durée dans `NON_TESTE.md` (but : cinq minutes).
- [ ] Essayer chaque plan B avec la personne qui le fait (accueil, soignante, médecin) et corriger les consignes.
- [ ] Faire afficher l'annonce et le plan B d'une scène sur l'écran de l'équipe pendant la démonstration.
- [ ] Une seule séance : faire s'enchaîner les scènes dans la même clinique, avec la même horloge (aujourd'hui chaque étape repart de zéro).
- [ ] Traduire les annonces des scènes (allemand, italien, anglais) et les faire relire.
- [ ] Brancher le scénario sur le chef de l'ossature (brique 15) pour les scènes où le robot bouge (la scène 3).

## Les pièces
Une ligne par pièce sera ajoutée ici quand elle sera construite, avec ses petites tâches.
- [x] Toute aide humaine se compte, première moitié (K02a, tour 41) : `aide_humaine.py`, page `/clinique/aide-humaine`, quatre cases et chiffres dans `lancer.py essais`.
- [x] K02b (tour 42) : `endurance.py`, le geste télécommandé, `docs/projet/PROTOCOLE_ESSAIS_REELS.md`, le bouton « réussi avec aide », l'écoute de « pilotage_humain » (brique 11).
- [ ] Une longue endurance (30 minutes, 2 heures) : c'est Hiba qui la lance (`python3 lancer.py endurance --duree 2h`).
- [ ] Mettre les trois chiffres dans la fiche de vérité (T27).
- [x] L'épreuve des étagères (M02, tour 43) : `etageres.py`, page `/clinique/etageres`, `docs/projet/EPREUVE_ETAGERES.md`.
- [ ] Quand K05 sera faite : le lien vers « Étagères » dans la page « Concours », et la capacité « déplacer des objets d'une étagère à une table » dans le tableau.
- [ ] Regarder la page « Étagères » sur un vrai téléphone ; garder l'essai en cours si le programme redémarre.
- [x] Trois cartes prêtes d'avance (M01, tour 44) : `unitree_g1`, `unitree_go2`, `unitree_g1d` ; `docs/projet/CARTE_A_REMPLIR.md` ; neuf lignes dans `docs/projet/SAMEDI_MATIN.md`.
- [ ] Samedi : remplir les chiffres des trois cartes avec la personne du fabricant ; une personne de l'équipe enlève la marque en écrivant la date.
- [x] D'où vient chaque donnée (L01, tour 45) : `sources_des_donnees.yaml`, `sources.py`, page `/clinique/sources`.
- [ ] Faire relire la table des sources par quelqu'un qui connaît une clinique ; remplir les « INCONNU ».
- [ ] Selon la réponse à Q18 : limiter ce que l'accueil lit des documents médicaux.
- [x] Le faux logiciel administratif, première moitié (L02a, tour 46) : `faux_logiciel_admin/` (hors de la clinique).
- [ ] L02b : la page du faux logiciel, les boutons, « Ouvrir l'assistant », le bouton de l'accueil, les messages dans la boîte noire.
- [ ] Faire vérifier la forme des messages (MSH, EVN, PID, PV1, IN1) par quelqu'un qui connaît le standard.
- [x] L02b (tour 47) : la page `/faux-logiciel`, « Ouvrir l'assistant » (`/clinique/ouvrir`), le lien de l'accueil, la boîte noire.
- [ ] Regarder la page du faux logiciel dans un navigateur et presser chaque bouton à la main.
- [x] L03a (tour 48) : `traducteur.py`, la vue administrative et les sept règles de lecture.
- [x] L03b (tour 49) : la porte donne la vue administrative ; l'accueil du hall et les écrans s'en servent ; le numéro de séjour est contrôlé.
- [ ] Répondre dans la langue de la fiche quand la langue de la phrase n'est pas sûre, pour TOUS les patients (aujourd'hui : seulement ceux arrivés par message, pour ne changer aucune vérification).
- [ ] Qui, côté médecin, voit une personne arrivée par message ? (aujourd'hui : aucun médecin)
- [x] L04a (tour 50) : `pre_admission.py`, les deux papiers inventés, la proposition avec ses sources, la validation par l'accueil, le message A05 qui part.
- [x] L04b (tour 51) : la boucle fermée (« pré-admissions reçues », « admettre », le carnet marque « admise ») et les boutons à l'écran.
- [ ] Jouer toute la boucle à la main dans un navigateur : deux papiers, préparer, corriger, valider, admettre, puis l'accueil du hall.
- [ ] Passer la civilité dans le message de pré-admission (aujourd'hui : « M./Mme »).
- [x] K03a (tour 52) : les trois temps (DEMANDÉ, CONFIRMÉ, CONSTATÉ) dans la boîte noire ; « constaté : oui / pas encore » ; « réussis et constatés » dans `lancer.py essais`.
- [x] K03b (tour 53) : l'âge de l'information (zone grisée après dix secondes), le bouton « Je l'ai vu », le badge et l'heure dans la boîte noire quand l'accueil valide un papier.
- [ ] Regarder la zone grisée dans un vrai navigateur, en coupant le Wi-Fi d'une tablette.
- [ ] Mettre « réussis et constatés » dans la fiche de vérité (T27).
- [x] K01a (tour 54) : `tirage.py`, `tirage_mots.yaml`, `python3 lancer.py tirage`.
- [x] K01b (tour 55) : le bouton « Demande au hasard » (`/clinique/tirage`) ; l'option `--apertus` dit « pas encore possible ».
- [ ] Quand Apertus sera là (R2) : faire comprendre chaque demande du tirage par le vrai cerveau, et afficher ce chiffre à part.
- [ ] Faire relire les phrases du tirage en allemand, italien et anglais.
- [x] J05a (tour 56) : `pauses.py`, page `/clinique/soignant/pauses` ; le gardien applique la pause avec la carte de rôle.
- [x] J05b (tour 57) : `qui_decide.py`, page `/clinique/qui-decide` ; recherche des promesses non mesurées : aucune.
- [ ] Faire relire la page « Qui décide » par des soignants ; donner la carte Accueil à un robot pour la scène du hall (cahier 6.6).
- [ ] Après une pause : faire repartir toutes seules les tâches qui attendaient ; appliquer les pauses aux robots simulés (monde des robots).
- [x] T23 (tour 58) : `repartiteur.py` — le plus proche, la bonne carte, la batterie, le relais proposé.
- [ ] Jouer le relais : deux tâches à la suite, la seconde part quand le premier robot est arrivé au point de passage.
- [ ] Brancher le répartiteur à la flotte (T24 : panne et reprise par le plus proche ; T25 : tableau de flotte) et le bouton « Pourquoi ? » (K04).
- [x] K04 (tour 59) : le choix expliqué (robots regardés, phrase), l'annonce avant chaque départ, le bouton « Pourquoi ? ».
- [ ] Dire l'annonce à voix haute (la voix du Mac, ou la voix du robot par le gardien) ; l'afficher sur l'écran du hall et de l'étage.
- [x] Le bouton « Pourquoi ? » dans le tableau de flotte (T25, tour 80).
- [x] N01a (tour 60) : dix écrans vus dans un vrai navigateur ; tableaux coupés sur téléphone corrigés ; `test_pages_sur_telephone.py`.
- [ ] N01b : les pages de travail et l'écran de l'ossature, même méthode.
- [ ] Tableaux sur téléphone : une ligne par carte plutôt que des colonnes étroites (plus de mots coupés).
- [ ] Selon la réponse à Q19 : traduire les textes fixes en allemand, ou retirer le lien « de ».
- [x] R2 (tour 61) : `apertus_essai.py`, commande `apertus-essai` — le vrai Apertus 8B sur l'iMac, 112 sur 120, aucune réponse de plus de 5 s.
- [ ] Apertus répète « merci » au lieu de ne rien faire : voir si une ligne de consigne ou un exemple de plus le corrige (brique 6 : demander à Hiba avant d'y toucher).
- [ ] Mesurer Apertus en même temps que l'écoute et la voix (mémoire, temps) ; mesurer sur le MacBook M2.
- [ ] H06 : brancher Apertus sur le rangement des papiers et sur le tirage ; H05 : l'étape « contrôle » de la brique 15.
- [x] T13 (tour 62) : `resume_apertus.py`, commande `resume-apertus` — mesuré : 0 ligne gardée sur 13, 6,4 s par ligne ; la version simple reste.
- [ ] Résumé par Apertus : essayer un texte plus court à écrire (une phrase, 60 jetons) et un exemple dans la consigne, puis remesurer ; lui donner la ligne simple à redire plutôt que les sources.
- [ ] Résumé par Apertus : l'écrire « pendant la nuit » hors de la page (sans bloquer les écrans), avec la mention « je prépare… ».
- [ ] H07 : la chaîne entière (écoute, Apertus, voix) mesurée ensemble ; `apertus-essai` ne doit plus effacer docs/projet/MESURE_APERTUS.md.
- [x] H06a (tour 63) : `papiers_apertus.py`, commande `papiers-apertus` — 2 sûrs sur 9 avec Apertus, 6 sur 9 avec les règles ; 0 mal rangé dit sûr.
- [ ] Papiers par Apertus : ne pas lui demander la date ni l'auteur (les règles les trouvent), seulement le type ; remesurer.
- [ ] H06b : le tirage de trente demandes compris par le vrai Apertus. H08 : deux ébauches de branchement et docs/projet/PREMIERE_HEURE.md.
- [x] H06b (tour 64) : `tirage_apertus.py`, commande `tirage-apertus` — compris 26 sur 30, 0 geste interdit, 1 geste parti à tort, 2 réponses de plus de 5 s.
- [ ] Tirage par Apertus : jouer les tirages 2 et 3 ; donner aux lieux de la clinique un nom dans les langues (Hall) pour que la carte de rôle soit vraiment mise à l'épreuve.
- [ ] Un robot qui annonce un geste qu'il ne peut pas faire (« je vais prendre… ») : voir avec la réponse de Hiba à Q21.
- [ ] Ordres au robot : 8 à 9 s avec le plan de la clinique dans la consigne ; mesurer avec la consigne gardée en mémoire (H07).
- [x] H07 (tour 65) : `chaine_mesure.py`, commande `chaine-mesure` — 2,5 s au milieu, 4,2 s au plus ; la mémoire manque par la règle écrite (iMac pas vide).
- [ ] Refaire `chaine-mesure` sur l'iMac avec tout le reste fermé, puis avec les écrans de la clinique ouverts ; puis Apertus sur un Mac, le reste sur l'autre.
- [ ] « Stop » mal entendu : essayer plusieurs voix et plusieurs « stop » par langue ; rappeler partout que l'arrêt est un bouton.
- [x] H08a (tour 66) : `briques/b03_adaptateurs/robots/unitree_go2/` — ébauche Unitree Go2, conformité réussie avec une doublure.
- [ ] H08b : ébauche « robot à roues ROS 2 » (vitesse, arrêt, position) et docs/projet/PREMIERE_HEURE.md.
- [ ] Samedi : lire la doc officielle d'Unitree pour le sujet de l'état, la batterie, l'arrêt ; si c'est un G1, refaire la liaison avec LocoClient.
- [x] H08b (tour 67) : `briques/b03_adaptateurs/robots/roues_ros2/` — ébauche ROS 2 (vitesse, arrêt, position), conformité réussie avec une doublure ; `docs/projet/PREMIERE_HEURE.md`.
- [ ] Samedi : remplir les « à vérifier samedi » des deux ébauches avec la personne du fabricant ; faire relire docs/projet/PREMIERE_HEURE.md par le responsable sécurité avant le premier essai.
- [ ] Robot à roues : sa navigation vers un lieu nommé (pour apporter un objet), son vrai arrêt d'urgence.
- [x] T21 (tour 68) : relecture de la tranche 2 (13 points, 23 essais) ; `mesures_cerveau.py` : cinq lignes du cerveau dans la fiche de vérité.
- [ ] H09 : un badge pour le cerveau, ses lectures au journal des accès ; `papiers_images.py` par la porte.
- [ ] Faire passer la répétition par les vraies pièces de la tranche 2 (voix, image, modèle) : voir N03.
- [ ] Garder l'historique des mesures du cerveau (aujourd'hui : la dernière seulement).
- [x] H09 (tour 69) : le cerveau lit sous le badge « assistant » ; une ligne au journal par texte donné ; `papiers_images` et `papiers_apertus` par la porte.
- [ ] Montrer les lignes de l'assistant sur la page du journal des accès (un filtre « ce que le cerveau a reçu »).
- [x] H01 (tour 70) : l'accueil sans le texte des papiers, sans programme, sans liste de soin ; `porte.papiers_a_ranger` pour la pièce qui range.
- [ ] Ne plus garder le texte du papier dans le carnet (garder une empreinte, relire par la porte au besoin).
- [ ] Selon la réponse à Q24 : l'accueil coche ses trois points de la liste de sortie, et eux seuls.
- [x] H02 (tour 71) : une question du soir crée une tâche pour le médecin (`taches.pour_la_question_du_soir`), vue en haut de son écran.
- [ ] Un bouton « répondu » pour le médecin sur cette tâche ; l'étape 9 de la répétition la contrôle ; prévenir si aucun médecin ne suit la patiente.
- [x] H03a (tour 72) : `traductions_ecrans.yaml` (un seul fichier, pas relu) et `traductions.py` ; l'allemand des deux écrans principaux du soignant et du médecin.
- [ ] H03b : allumer la table sur l'écran du patient (attend la réponse à Q25).
- [ ] Faire relire `traductions_ecrans.yaml` ; traduire les pages secondaires (liste, fin de poste, dictée, source).
- [x] H04 (tour 73) : la scène 5 et l'étape 10 demandent aussi le rapport de radiologie ; réponse vraie, rien ne s'ouvre.
- [x] J06b-a (tour 74) : `paroles_fichier.py` (lecture seule), `PAROLES_DES_SOIGNANTS.modele.md`, le nom refusé par git.
- [ ] J06b-b : brancher la page « Ce qu'on nous a dit » (attend la réponse à Q26) ; l'étiquette DIT PAR UN SOIGNANT sur les écrans concernés.
- [x] N01b (tour 75) : le clic sur « Source » corrigé (la page ne se réécrit plus sans raison) ; `test_clic_dans_le_navigateur.py`, vrais gestes de souris dans Chrome.
- [ ] N01c : les autres pages de travail dans le navigateur ; regarder si leurs petits programmes à elles perdent aussi un clic.
- [ ] H10 : le mode interprète (français dit → anglais affiché et dit), mots fixés, réponses préparées.
- [x] H10a (tour 76) : `interprete.py`, `interprete_mots.yaml`, `interprete_reponses.yaml`, commande `interprete-mesure` — deux temps : 8 sur 10, 1,8 s ; direct : 4 sur 10.
- [ ] H10b : les deux boutons sur un écran de régie (tenir pour écouter ; réponse préparée), l'anglais en grand.
- [ ] Interprète : donner à l'écoute une liste de mots attendus (course, robot, palier) pour qu'elle les entende mieux — à vérifier dans l'aide de whisper.cpp, rien à télécharger.
- [x] H10b (tour 77) : `interprete_ecran.py`, page `/clinique/regie` — le bouton à tenir, l'anglais en grand, les réponses préparées, le fichier des délais.
- [ ] Par l'équipe : dix phrases dites dans le vrai micro, sur l'iMac ; puis relire les phrases anglaises.
- [ ] Régie : un bouton « effacer les sons gardés » ; dire aussi à voix haute une réponse préparée, si Hiba le veut.
- [x] N01c (tour 78) : `outils/pages_vues_chrome.py` — les pages de travail passées dans Chrome (1440, 375, boutons) ; deux défauts de la régie corrigés.
- [ ] Pour N02 : ouvrir aussi les cinq pages manquantes (créer d'abord une tâche et une arrivée), presser tous les boutons, remplir les champs avant d'appuyer.
- [ ] Remplacer la fenêtre de question du navigateur (« Pourquoi reporter ? ») par un champ dans la page.
- [x] T24 (tour 79) : `panne_reprise.py`, commande `panne-reprise` — batterie basse ou blocage → « reprise » ; le plus proche reprend ; sinon un humain.
- [x] T25 : le tableau de flotte branché sur le monde, le répartiteur et la panne ; un bouton pour provoquer une panne (tour 80).
- [ ] L'étape 12 par le plus proche (pas fait dans T25).
- [ ] Un bouton pour changer la carte d'un robot (pas fait dans T25).
- [ ] Une tâche « porter l'objet du robot en panne au robot suivant » pour un humain, quand l'objet est resté en route.
- [x] H11 (tour 82) : la carte de rôle refusée par le gardien lui-même pour les lieux de l'ossature et les actions hors carte (relecture de la tranche 3).
- [x] H12 (tour 83 ; l'affichage sur le tableau attend Q28) : la place de R1 lue sur la prise ; la reprise par R1 dès le début ; l'objet cherché là où il est resté.
- [x] H13 (tour 84) : panne et passage à un humain dans la boîte noire ; feu du gardien sur « Pourquoi ? » du tableau ; changement de carte visible.
- [x] H14 (tour 105) : une parole proposée par le cerveau ne part jamais ; phrase fixe « Je ne peux pas faire cela. » (testé sur faux robot, pas avec Apertus).
- [~] H16 (tour 106) : fait pour les demandes au robot à la voix (« C'est bien ça ») ; les coches à la voix attendent la question Q32.
- [x] H17 (tour 107) : l'accueil voit et coche seulement ses trois points de la liste de sortie (porte étroite ; H01 tient).
- [x] H18 (tour 108) : la place de R1 lue sur le robot, sur le tableau de flotte (le chiffre de la batterie : Q34).
- [~] H19 (tour 109) : segno installé, codes QR dessinés et relus par le Mac ; pas encore sur la page des téléphones (question Q35).
- [x] H20 (tour 110) : modèle d'écoute medium téléchargé et mesuré à côté de small (même justesse, deux fois plus lent) ; small reste par défaut.
- [x] T27 : la fiche de vérité complète, gardée dans un fichier et montrée sur `/clinique/fiche-de-verite` (tour 85).
- [ ] Une étape de la répétition qui lit des messages du faux logiciel (la ligne « messages lus » reste à 0).
- [x] T28 : « À vous », commande `python3 lancer.py a-vous` et fichier `a_vous.yaml` (tour 86).
- [x] K07a : l'écran « Invité » (`/clinique/invite`), quatre boutons, marque INVITÉ, remise à zéro (tour 87).
- [x] K07b : les six ordres et la taille du texte, commande `python3 lancer.py invite-essai` (tour 88).
- [ ] Faire lire les écrans Invité et Patient à une vraie personne.
- [x] T29 : le rejeu autonome, `python3 lancer.py rejeu-autonome` (tour 89).
- [ ] Ouvrir un dossier de rejeu sur un autre ordinateur, sans Internet.
- [x] T30 : la page des téléphones et `python3 lancer.py telephones` (tour 90).
- [ ] Ouvrir `/clinique/telephones` sur un vrai téléphone du même Wi-Fi.
- [ ] Les codes QR, après la réponse de Hiba à Q29.
- [x] T31 : la carte d'exemple `roues_deux_bras`, l'ébauche d'adaptateur, la liste dans docs/projet/SAMEDI_MATIN.md (tour 91).
- [x] J07a : la page des preuves, huit boutons, « Où tourne quoi » (tour 92).
- [x] J07b : la commande des preuves, `python3 lancer.py preuves` (tour 93).
- [ ] Mesurer le temps de réponse du gardien et des écrans, pour « Où tourne quoi ».
- [x] K05 : le tableau des capacités, docs/projet/PAS_RESOLU.md, la page « Concours » (tour 94).
- [x] KC : la commande du concours, `python3 lancer.py concours` (tour 96).
- [ ] Compléter docs/projet/PAS_RESOLU.md avec l'équipe.
- [x] K06 : l'avis des personnes, formulaire et page « Avis » (tour 95).
- [ ] Faire remplir le formulaire par de vraies personnes pendant le hackathon (anonyme).
- [x] H05 : l'étape « contrôle » dans la brique 15 (tour 97).
- [x] N03a : la séance unique, scènes 1 à 3, jouée par le chef de démonstration (tour 98).
- [x] N03b : les sept scènes d'un seul trait, `python3 lancer.py seance-unique` (tour 99).
- [x] N02 : le dernier passage des pages dans Chrome, 48 pages (tour 100).
- [ ] Regarder les pages sur un vrai téléphone avec une personne.
