# Les pages vues dans un vrai navigateur

Demandé par Hiba le 12.11.2026 (tâches N01 et N02). **Vu dans un vrai navigateur par l'assistant de code, sur cet ordinateur.**
Ce n'est **pas** « vu par un humain sur un vrai téléphone » : voir `NON_TESTE.md`.

Comment : le serveur d'essai `outils/serveur_pages_vues.py` (sur cet ordinateur seulement, faux robot, tout ce qui
s'écrit va dans un dossier provisoire ; le vrai fichier des essais réels n'est jamais touché). Aucun site extérieur.
Rien n'a été installé.
- **Navigateur A** : le navigateur intégré de l'application de l'assistant de code (bureau). Il ouvre la page, lit les erreurs du
  navigateur, appuie sur les boutons, et se règle en largeur de téléphone (375 × 812) ou en grand écran (1440 × 900).
- **Navigateur B** : Google Chrome 157, déjà sur l'ordinateur, lancé sans fenêtre. Il fait les images en grand écran, et
  la mesure automatique « rien ne dépasse à 375 points » (`briques/clinique/tests/test_pages_sur_telephone.py`).
- Les images : `pages_vues/n01a/` (une en largeur de téléphone, une en grand écran, par page).

## Premier passage, premier groupe (N01a) — 12.11.2026, tour 60 — les dix écrans principaux

| Page | Navigateur, tailles | Ce qui marche | Ce qui ne va pas |
|---|---|---|---|
| `/clinique` (la liste des écrans) | A : 375 et 1440 ; B : image 1440 | s'affiche ; aucune erreur ; bandeau « DONNÉES INVENTÉES — DÉMONSTRATION » ; heure « Jour 1 — 9 h 00 » ; rien ne dépasse ; les liens mènent aux pages | pas d'âge de l'information (page fixe : normal) |
| `/clinique/patient` | A : 375 et 1440, en fr, de, it, en ; B : image 1440 | s'affiche dans la langue de la patiente (italien) ; bandeau, heure, badge « Patiente, chambre 12 », « mis à jour il y a 0 seconde » ; rien ne dépasse dans les quatre langues ; les liens de langue marchent | **les lignes du programme et le genre des documents restent en français** dans les quatre langues (« installation en chambre », « lettre du médecin traitant ») : ce sont les données du faux dossier ; question Q19 |
| `/clinique/soignant` | A : 375 et 1440, en fr et de ; B : image 1440 | s'affiche ; bandeau, heure, badge, âge ; rien ne dépasse ; le lien « Fin de poste » ouvre la page (26 points) | **en allemand, seul le titre « Meine Patienten » est traduit** : la prise de poste et les demandes restent en français ; question Q19. Les boutons « Il manque un objet » et les listes : pas encore essayés (groupe suivant) |
| `/clinique/medecin` | A : 375 et 1440, en fr et de ; B : image 1440 | s'affiche ; bandeau, heure, badge, âge ; le résumé et ses sources ; le lien « Source : Fiche du séjour » ouvre la fiche | **en allemand, le résumé reste en français** (question Q19). Mon premier clic sur « Source » n'a rien ouvert (la page s'est remise à jour pendant le clic) ; le lien suivi par son adresse marche : à revoir à la main |
| `/clinique/accueil` | A : 375 et 1440 ; B : image 1440 | s'affiche ; bandeau, heure, badge, âge ; « Logiciel administratif (SIMULÉ) : aucune nouvelle reçue » ; l'arrivée du jour ; le lien « Papiers à valider (3) » ouvre la pile | rien vu |
| `/clinique/therapeute` | A : 375 et 1440 ; B : image 1440 | s'affiche ; bandeau, heure, badge, âge ; quatre patients ; rien ne dépasse | rien vu |
| `/clinique/direction` | A : 375 et 1440 ; B : image 1440 | s'affiche ; bandeau, heure, âge ; des comptes par étage, aucun nom | **DÉFAUT TROUVÉ ET CORRIGÉ** : sur téléphone, le tableau était coupé à droite (« Points repor… », image `direction_AVANT_la_correction…`). Corrigé (style des tableaux sur petit écran) ; une vérification le voit maintenant. Reste : quelques mots courts sont coupés en deux dans le tableau (« Étag-e ») |
| `/clinique/hall` | A : 375 et 1440 ; B : image 1440 | s'affiche ; bandeau, heure, badge « Robot R1 », étiquette SIMULÉ ; le bouton « Dire » essayé avec « Buongiorno, sono Giulia B. » : la réponse en italien, le chemin et « étage prévenu » s'affichent | le champ de saisie est petit sur téléphone (lisible) ; pas d'âge de l'information (page fixe) |
| `/clinique/flotte` | A : 375 et 1440 ; B : image 1440 | s'affiche ; bandeau, heure, âge ; les quatre robots, leur carte, leur étiquette (FAUX ROBOT, FAUX ROBOT — SIMULÉ) ; rien ne dépasse | aucun bouton sur cette page (ils viendront avec T25) |
| `/clinique/journal` | A : 375 et 1440 ; B : image 1440 | s'affiche ; bandeau, heure ; des numéros de dossier, aucun nom | **DÉFAUT TROUVÉ ET CORRIGÉ** : sur téléphone, les colonnes « Résultat » et « Raison » étaient coupées (image `journal_AVANT_la_correction…`). Même correction. Reste : des mots coupés aux syllabes dans les colonnes étroites |

Erreurs du navigateur : aucune sur ces dix pages. Une seule ligne « connexion refusée » est apparue deux fois : c'était
pendant que je relançais moi-même le serveur d'essai (la page redemandait son contenu) ; pas un défaut de la page.

## Ce qui reste à voir (N01b et suivants)

Les listes de soin et « Il manque un objet » (tablette du soignant), fin de poste (les boutons), les papiers (valider),
la recherche et la dictée du médecin, le soir du patient, les pauses, « Pourquoi ? », « Qui décide », « D'où vient cette
donnée ? », la pré-admission, le faux logiciel administratif, « Demande au hasard », l'aide humaine, les essais réels et
les étagères (sur le fichier d'essai seulement), les pannes, les moments, « Ce qu'on nous a dit », les protocoles, et les
pages de l'écran de l'ossature (pour celles-là : regarder, noter, ne rien toucher).

## N01b — tour 75, 12.11.2026 — le clic sur « Source », les pages du médecin, les papiers de l'accueil
Vu dans un vrai navigateur par l'assistant de code, sur cet ordinateur. Pas encore vu par un humain sur un vrai téléphone.
Navigateurs : A = le navigateur intégré (regarder, cliquer, lire les erreurs) ; B = Chrome 157 sans fenêtre (images en 1440, mesure en 375, vrais gestes de souris).

| Page | Navigateur, taille | Ce qui marche | Ce qui ne va pas |
|---|---|---|---|
| `/clinique/medecin` | A : clic sur « Source : Fiche du séjour » ; B : vrais gestes de souris (court, lent, dès l'ouverture) | **le clic ouvre la source**, dans les trois cas ; la page se met encore à jour toute seule | avant la correction : un clic lent pendant un rafraîchissement se perdait (cause trouvée, corrigée, essai qui clique vraiment) |
| `/clinique/medecin/source` (fiche du séjour, lettre) | A ; B : image 1440, mesure 375 | bandeau, heure, badge, « Retour » ; le texte de la source, sa référence ; rien ne dépasse | le bouton « Retour » n'a pas été pressé |
| `/clinique/medecin/recherche` (la lettre ; le rapport de radiologie) | B : image 1440, mesure 375 | la lettre s'ouvre ; le rapport de radiologie : « Je ne trouve pas ce document… » ; rien ne dépasse | le formulaire n'a pas été rempli à la main : les deux demandes sont venues par l'adresse |
| `/clinique/medecin/dictee` | B : image 1440, mesure 375 | s'affiche, rien ne dépasse | le bouton n'a pas été pressé ; pas de micro |
| `/clinique/medecin?langue=de` | B : image 1440 | les titres du résumé, la recherche, « Quelle: » en allemand ; « nicht übersetzt » est dit | l'en-tête (« Badge », « Jour 1 — 9 h 00 »), « mis à jour il y a… » et l'aide du champ de recherche restent en français ; phrases non relues |
| `/clinique/soignant?langue=de` | B : image 1440 | la prise de poste, le programme et les listes en allemand | les habitudes restent en français (des données) ; phrases non relues |
| `/clinique/accueil/papiers` | B : image 1440, mesure 375 | depuis H01 : aucune ligne du papier ; le type, le patient, l'endroit, la date, l'auteur, la confiance ; rien ne dépasse | « Valider ce rangement » n'a pas été pressé dans le navigateur |

Erreurs du navigateur : aucune sur ces pages pendant le passage. Le journal du navigateur intégré gardait 325 lignes « connexion refusée » : ce sont les demandes de la page restée ouverte depuis le tour 60, pendant que le serveur d'essai était arrêté.
Images : `pages_vues/n01b/` (7 images en 1440). Pas d'image en 375 pour ce groupe : la largeur de téléphone est mesurée (rien ne dépasse), pas photographiée.
Pas encore vues : toutes les autres pages de travail et l'écran de l'ossature (N01c).

## N01c — tour 78, 12.11.2026 — les pages de travail, passées par un programme dans Chrome
Vu dans un vrai navigateur par l'assistant de code, sur cet ordinateur. Pas encore vu par un humain sur un vrai téléphone.
Navigateur : B = Chrome 157 sans fenêtre, piloté par `outils/pages_vues_chrome.py` : chaque page ouverte en 1440 puis en 375 points (vraie largeur de téléphone, pas un cadre), une image de chaque, les erreurs du navigateur relevées, et chaque bouton pressé une fois par un vrai geste de souris, sur une page fraîche (huit boutons au plus par page). Serveur d'essai : faux robot, fichiers provisoires — aucun vrai fichier de l'équipe n'est touché.

| Page | Navigateur, taille | Ce qui marche | Ce qui ne va pas |
|---|---|---|---|
| `/clinique/soignant/liste` | B : 1440 et 375 | s'ouvre ; bandeau oui ; en 375 : rien ne dépasse ; 8 boutons pressés sur 15, aucune erreur de programme | 7 boutons pas pressés ; le navigateur demande une petite image d'onglet qui n'existe pas (sans effet) |
| `/clinique/soignant/fin-de-poste` | B : 1440 et 375 | s'ouvre ; bandeau oui ; en 375 : rien ne dépasse ; 8 boutons pressés sur 69, aucune erreur de programme | 3 bouton(s) ouvrent une fenêtre de question du navigateur ; 61 boutons pas pressés |
| `/clinique/soignant/pauses` | B : 1440 et 375 | s'ouvre ; bandeau oui ; en 375 : rien ne dépasse ; 1 bouton pressé sur 1, aucune erreur de programme | rien vu |
| `/clinique/patient/soir` | B : 1440 et 375 | s'ouvre ; bandeau oui ; en 375 : rien ne dépasse ; 0 bouton pressé sur 0, aucune erreur de programme | aucun bouton à presser dans cet état |
| `/clinique/qui-decide` | B : 1440 et 375 | s'ouvre ; bandeau oui ; en 375 : rien ne dépasse ; 0 bouton pressé sur 0, aucune erreur de programme | aucun bouton à presser dans cet état |
| `/clinique/sources` | B : 1440 et 375 | s'ouvre ; bandeau oui ; en 375 : rien ne dépasse ; 0 bouton pressé sur 0, aucune erreur de programme | aucun bouton à presser dans cet état |
| `/clinique/pre-admission` | B : 1440 et 375 | s'ouvre ; bandeau oui ; en 375 : rien ne dépasse ; 2 boutons pressés sur 2, aucune erreur de programme | rien vu |
| `/faux-logiciel` | B : 1440 et 375 | s'ouvre ; bandeau oui ; en 375 : rien ne dépasse ; 8 boutons pressés sur 28, aucune erreur de programme | 2 refus affichés en clair (bouton pressé sans remplir les champs : normal) ; 20 boutons pas pressés |
| `faux_logiciel_fiche` | B | — | **pas ouverte** : aucun lien vers cette page depuis la page d'avant |
| `/clinique/tirage` | B : 1440 et 375 | s'ouvre ; bandeau oui ; en 375 : rien ne dépasse ; 1 bouton pressé sur 1, aucune erreur de programme | rien vu |
| `/clinique/aide-humaine` | B : 1440 et 375 | s'ouvre ; bandeau oui ; en 375 : rien ne dépasse ; 1 bouton pressé sur 1, aucune erreur de programme | rien vu |
| `/clinique/essais-reels` | B : 1440 et 375 | s'ouvre ; bandeau oui ; en 375 : rien ne dépasse ; 3 boutons pressés sur 3, aucune erreur de programme | 3 refus affichés en clair (bouton pressé sans remplir les champs : normal) |
| `/clinique/protocole-essais-reels` | B : 1440 et 375 | s'ouvre ; bandeau oui ; en 375 : rien ne dépasse ; 0 bouton pressé sur 0, aucune erreur de programme | aucun bouton à presser dans cet état |
| `/clinique/etageres` | B : 1440 et 375 | s'ouvre ; bandeau oui ; en 375 : rien ne dépasse ; 8 boutons pressés sur 9, aucune erreur de programme | 8 refus affichés en clair (bouton pressé sans remplir les champs : normal) ; 1 boutons pas pressés |
| `/clinique/epreuve-etageres` | B : 1440 et 375 | s'ouvre ; bandeau oui ; en 375 : rien ne dépasse ; 0 bouton pressé sur 0, aucune erreur de programme | aucun bouton à presser dans cet état |
| `/clinique/pannes` | B : 1440 et 375 | s'ouvre ; bandeau oui ; en 375 : rien ne dépasse ; 5 boutons pressés sur 5, aucune erreur de programme | 1 refus affichés en clair (bouton pressé sans remplir les champs : normal) |
| `/clinique/moments` | B : 1440 et 375 | s'ouvre ; bandeau oui ; en 375 : rien ne dépasse ; 0 bouton pressé sur 0, aucune erreur de programme | aucun bouton à presser dans cet état |
| `/clinique/ce-qu-on-nous-a-dit` | B : 1440 et 375 | s'ouvre ; bandeau oui ; en 375 : rien ne dépasse ; 0 bouton pressé sur 0, aucune erreur de programme | aucun bouton à presser dans cet état |
| `/clinique/regie` | B : 1440 et 375 | s'ouvre ; bandeau oui ; en 375 : 2 éléments dépassent ; 3 boutons pressés sur 3, aucune erreur de programme | dépassait à droite en 375 (corrigé ce tour) |
| `pourquoi` | B | — | **pas ouverte** : aucun lien vers cette page depuis la page d'avant |
| `/` | B : 1440 et 375 | s'ouvre ; bandeau non ; en 375 : rien ne dépasse | pas de bandeau « DONNÉES INVENTÉES » |

Erreurs de programme signalées par le navigateur : aucune, sur aucune page. Les « erreurs » relevées sont des réponses « 400 » du serveur à un bouton pressé sans remplir les champs ; la page affiche alors « Refusé : … » avec la raison.
Défauts trouvés et corrigés ce tour, dans mon propre travail : sur `/clinique/regie`, deux chemins de fichiers dépassaient à droite en 375 points (la mesure automatique l'aurait vu : la page y est ajoutée) ; une zone d'erreurs vide restait affichée (une barre jaune sans texte).
Regardé sans rien toucher : l'écran de l'ossature (`/`). Il s'affiche ; il porte « testé sur faux robot », pas le bandeau « DONNÉES INVENTÉES » (il ne montre aucune donnée de patient) ; il affichait « liaison perdue » parce que le passage venait de provoquer les pannes d'entraînement sur le serveur d'essai.
Images : `pages_vues/n01c/` (une en 1440 et une en 375 par page ouverte) et `passage.json` (le détail, bouton par bouton).
Pas vues : la fiche d'une personne dans le faux logiciel, « Pourquoi ? » (il faut une tâche en cours), « Ouvrir l'assistant », la page d'un moment, le soir du patient le soir (à 9 h, elle n'a pas de bouton), et 89 boutons sur 137 (huit au plus par page). Le bouton du micro de la régie n'est pas pressé ici.


## N02 — tour 100, 12.11.2026 — dernier passage, toutes les pages, par un programme dans Chrome

Le même contrôle que N01, sur **48 pages demandées** : les dix écrans principaux de N01a (le patient en quatre langues), les pages de N01b et N01c, et les douze pages faites après N01 (tableau de flotte, fiche de vérité, Invité, téléphones, preuves et leurs deux pages, « Où tourne quoi », capacités, concours, avis, formulaire d'avis). Outil : `.venv/bin/python outils/pages_vues_chrome.py --n02` (Chrome sans fenêtre, serveur d'essai sur cet ordinateur seulement, fichiers provisoires). Images : `pages_vues/n02/` (une en 1440 et une en 375 points par page) ; détail : `pages_vues/n02/passage.json`.

- **Ouvertes : 46 sur 48.** Les deux autres (la fiche du faux logiciel, la page « Pourquoi ? » d'une tâche) s'atteignent par un lien depuis la page d'avant ; dans l'ordre de ce passage, ce lien n'était pas là (même cas qu'à N01c). La page « Pourquoi ? » du tableau de flotte est mesurée par `test_pages_n02.py`. Le bandeau « DONNÉES INVENTÉES » est sur les 46, sauf l'écran de l'ossature (déjà noté à N01c).
- **Rien ne dépasse en largeur de téléphone (375 points)**, sur aucune page. Un défaut trouvé et corrigé ce tour : sur la page « Avis », la longue adresse du formulaire dépassait à droite ; elle se coupe maintenant. Une vérification le garde (`test_pages_n02.py`, la même mesure que `test_pages_sur_telephone.py`, réutilisée sans la changer).
- **Erreurs du programme des pages : aucune.** Le navigateur a relevé des réponses « 400 » quand un bouton est pressé sans remplir ses champs (essais réels, étagères, faux logiciel, pannes) : la page dit alors « Refusé : … » en clair. Plus une icône d'onglet absente (404), sans effet.
- **Boutons pressés par un vrai geste de souris : 69** (au plus huit par page).

Noté, pas corrigé :
- Sur un téléphone, le tableau des capacités (cinq colonnes) est serré : les mots sont coupés aux syllabes. Il reste lisible et ne dépasse pas.
- Quand une panne est en cours, ses bandeaux rouges s'affichent aussi sur l'écran Invité et poussent les quatre grands boutons vers le bas.
- Vu par un programme, pas par une personne ; pas sur un vrai téléphone ni dans Safari.
