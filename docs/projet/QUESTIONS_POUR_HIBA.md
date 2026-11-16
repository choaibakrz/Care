# Questions pour Hiba

Message de Hiba pour la nuit (dans la conversation, le 12.11.2026, 01 h 44), recopié tel quel :
« Je vais dormir. Continue la boucle sans moi.
1. Il n'y a pas de limite de tours. Ne t'arrête pas au tour 40, ni à un autre nombre.
2. À la fin de chaque tour, programme toujours le tour suivant, tant qu'il reste une tâche prête.
3. Si une tâche a besoin de ma réponse, écris la question, marque la tâche « EN QUESTION », et passe à la suivante. Ne m'attends pas.
4. Arrête-toi seulement dans deux cas : tout est fini, ou il ne reste que des tâches qui m'attendent. Dans ces deux cas, dis-le clairement.
5. Toutes les règles du cahier et des avenants restent vraies. Les autorisations que je t'ai déjà données ne changent pas. Tu n'en prends aucune nouvelle en mon absence.
6. Si la vérification rapide rate, répare d'abord. Si tu n'y arrives pas en un tour, remets le dépôt dans un état où elle passe, note-le, et continue ailleurs.
7. Écris l'heure dans chaque ligne du journal. »
Ce message ne répond à aucune question ouverte (Q7 à Q15 restent sans réponse : je fais la version « sans ça »).

Avenant 4 reçu le 12.11.2026. Copie dans `docs/projet/AVENANT_LOGICIEL.md` : 189 lignes,
21 362 octets, 4 tâches (L01 à L04), 9 sortes de messages numérotées dans L02, fin correcte. Le contrôle attendait
225 lignes à dix près : raté (il manque 36 lignes ; le poids est bon, ce sont donc sans doute des lignes vides
perdues au collage, comme pour les trois premiers avenants ; à vérifier). L'avenant dit : « Si le contrôle rate,
dis-le et arrête-toi. » Je me suis arrêté, et j'ai demandé : je garde cette copie telle quelle et je finis
l'enregistrement ?
Réponse de Hiba (dans la conversation, le 12.11.2026) : « Garde ta copie ». La copie est gardée telle quelle, et
l'avenant 4 est enregistré (suivi : L01 à L04 ajoutées ; question Q13).

Avenant 3 reçu le 11.11.2026. Copie dans `docs/projet/AVENANT_MATERIEL.md` : 179 lignes,
20 570 octets, 2 tâches (M01, M02), 13 points numérotés dans le protocole, fin correcte. Le contrôle attendait
213 lignes à dix près : raté (il manque 34 lignes ; sans doute des lignes vides perdues au collage, comme pour les
deux premiers avenants ; à vérifier). L'avenant dit : « Si le contrôle rate, dis-le et arrête-toi. » Je me suis
arrêté, et j'ai demandé : je garde cette copie telle quelle et je finis l'enregistrement ?
Réponse de Hiba (dans la conversation, le 11.11.2026) : « Garde ta copie ». La copie est gardée telle quelle, et
l'avenant 3 est enregistré (suivi : M02 et M01 ajoutées ; question Q10).

Avenant 2 reçu le 11.11.2026. Copie dans `docs/projet/AVENANT_CONCOURS.md` : 234 lignes, 27 096 octets, 7 tâches, 7 contrôles, fin
correcte. Le contrôle attendait 291 lignes à dix près : raté (lignes vides et titres sans doute perdus au collage, à
vérifier). Réponse de Hiba (dans la conversation, le 11.11.2026) : « Garde ta copie ». La copie est gardée telle quelle.

Avenant jury reçu le 11.11.2026. Copie dans `docs/projet/AVENANT_JURY.md` : 209 lignes, 20 634 octets, 7 tâches, 8 preuves, fin
correcte. Le contrôle attendait 257 lignes à dix près : raté (lignes vides et titres sans doute perdus au collage, à
vérifier). Réponse de Hiba (dans la conversation, le 11.11.2026) : « Garde ta copie ». La copie est gardée telle quelle.

## Les autorisations (partie 0 du cahier)

| Autorisation | Réponse de Hiba | Date |
|---|---|---|
| A — installer dans le dossier du projet (outils du dépôt, petits outils ouverts de moins de 200 Mo) | **OUI** | 11.11.2026 |
| B — la lecture de texte du Mac pour lire les papiers | **OUI** | 11.11.2026 |
| C — envoyer vers GitHub, branche `clinique-en-boite` seulement | **OUI** | 11.11.2026 |

---

## Q1 — tâches R1 et R3 — 11 novembre
Je voudrais : un oui ou un non pour A, B et C. Avec A, je crée un espace à part `.venv` dans le dossier du projet et j'y
installe les paquets que le dépôt demande déjà (`requirements.txt`, puis `requirements-mac.txt` et
`requirements-yeux.txt` quand une tâche en a besoin). Licences MIT, Apache-2.0 et BSD, déjà dans `LICENCES.md`. Les
tailles exactes sur Mac sont à vérifier ; je les noterai avant chaque installation et je m'arrête si un paquet dépasse 200 Mo.
Sans ça : l'ossature ne passe pas toutes ses vérifications sur l'iMac (8 ratées, 2 fichiers illisibles, faute de `mcp`
et `onnxruntime`). Je construis quand même la tranche 1 avec le Python déjà là, et je note ces 10 manques comme connus.
La porte des agents (brique 14), les yeux et la voix resteront « non essayés sur l'iMac ».
Réponse de Hiba : « Oui à A, B, C » (dans la conversation, le 11.11.2026). Question fermée.

## Q2 — tâche R2 — 11 novembre
Je voudrais : télécharger le modèle Apertus 8B (fichier `Apertus-8B-Instruct-2509-Q4_K_M.gguf`, **5,06 Go**, licence
Apache-2.0, depuis Hugging Face, dépôt `unsloth/Apertus-8B-Instruct-2509-GGUF`) dans `modeles/`. Le moteur
(`llama-server`) est déjà sur l'iMac. Il reste 22 Go libres sur le disque. En option, le secours Apertus 4B : 2,43 Go.
Sans ça : T13 et T14 se feront avec le cerveau de test seulement ; « avec le vrai Apertus » restera non prouvé, et
l'écran dira « version simple ».
Réponse de Hiba : « Oui aux deux » (Apertus 8B et modèle d'écoute, dans la conversation, le 11.11.2026). Question fermée.

## Q3 — tâche R4 — 11 novembre
Je voudrais : télécharger le modèle d'écoute `ggml-small.bin` (**488 Mo**, licence MIT, dépôt `ggerganov/whisper.cpp`)
dans `modeles/`. Le moteur whisper.cpp est déjà sur l'iMac.
Sans ça : la voix sera vérifiée au niveau du texte reconnu seulement ; T20 (« l'arrivée dite en italien ») passera par
le plan B à l'écran, et le taux d'erreur de la voix sera « non mesuré ».
Réponse de Hiba : « Oui aux deux » (Apertus 8B et modèle d'écoute, dans la conversation, le 11.11.2026). Question fermée.

## Q4 — règles qui ne disent pas la même chose — 11 novembre
J'ai trouvé quatre écarts entre le dépôt et le cahier. J'applique chaque fois la règle la plus prudente :
1. `DECISIONS.md` donne le feu vert aux paquets de moins de 200 Mo et aux modèles de moins de 500 Mo sans demander.
   Le cahier dit : toujours demander. → Je demande toujours.
2. `docs/projet/REGLES_DES_AGENTS.md` : feu orange au-dessus de 500 Mo. Le cahier : au-dessus de 200 Mo. → 200 Mo.
3. `DECISIONS.md` : 3 ou 4 sous-agents en parallèle. Le cahier : un relecteur, aux tâches de relecture seulement. → Le cahier.
4. `docs/projet/REGLES_DES_AGENTS.md` : « à la fin de chaque étape, cinq lignes à Hiba, puis attendre ». Le cahier : une boucle qui enchaîne
   les tours. La plus prudente serait d'attendre après chaque tour.
Je voudrais : savoir si lancer `/goal` ou `/loop` vaut accord pour enchaîner les tours sans attendre.
Sans ça : je fais un tour, quatre lignes de bilan, et j'attends.
Réponse de Hiba (dans la conversation, le 11.11.2026) : « Oui. Quand je lance /goal ou /loop, tu enchaînes les tours du
cahier sans m'attendre entre deux tours. La règle « attendre après chaque étape » de docs/projet/REGLES_DES_AGENTS.md ne s'applique pas à
cette boucle. Le reste de docs/projet/REGLES_DES_AGENTS.md ne change pas. Les feux du cahier ne changent pas : feu orange, tu écris ta
question et tu passes à une autre tâche ; feu rouge, tu t'arrêtes. » Question fermée.

## Q5 — briques absentes — 11 novembre
Le cahier dit que l'ossature contient « la mémoire » et « deux robots ensemble ». Dans le dépôt, les briques 9
(mémoire), 10 (apprendre un geste) et 16 (deux robots) ne sont pas construites.
Je voudrais : construire le strict nécessaire dans le dossier de la clinique : plusieurs faux robots dans le même
monde (tâche R5, avant T22). Rien pour la mémoire avant le bonus B4.
Sans ça : la flotte montrera un seul faux robot et trois robots dessinés, sans vrai déplacement simulé.
Réponse de Hiba (dans la conversation, le 11.11.2026) : « Oui. Tu peux construire plusieurs faux robots dans le même
monde, dans le dossier de la clinique. Fais la version la plus simple qui permet de vérifier pour de vrai les tâches
T22 à T25 : pas de physique, juste des robots qui se déplacent sur le plan, prennent une tâche et tombent en panne.
Touche le moins possible aux briques de l'ossature, et note chaque changement dans DECISIONS.md. Chaque faux robot
porte l'étiquette FAUX ROBOT. » Question fermée.
Précisé par Q6 : R2, R3, R4 portent « FAUX ROBOT — SIMULÉ ».

## Q6 — tâches R5 et T25 — 11 novembre
Je voudrais : savoir quelle étiquette portent R2, R3 et R4. Le cahier (6.6, 4.2) dit « SIMULÉ » (trois robots simulés
sur quatre). La réponse à Q5 dit « chaque faux robot porte l'étiquette FAUX ROBOT ».
Sans ça : R1 porte « FAUX ROBOT » ; R2, R3, R4 portent les deux mots, « FAUX ROBOT — SIMULÉ », et la fiche de vérité
compte « 3 robots simulés sur 4 », comme le cahier.
Réponse de Hiba : « Les deux mots » (dans la conversation, le 11.11.2026) : R1 « FAUX ROBOT » ; R2, R3, R4
« FAUX ROBOT — SIMULÉ » ; la fiche de vérité compte 3 robots simulés sur 4. Question fermée.

## Q7 — tâche J06 (avenant jury) — 11 novembre
Je voudrais : ta réponse à cette question de l'avenant. « Es-tu d'accord pour que l'équipe écrive, dans un fichier qui
reste sur l'ordinateur, des phrases de vrais soignants sur leur travail, sans nom, avec leur accord, et jamais un mot
sur un patient ? » Avec un oui : un fichier `PAROLES_DES_SOIGNANTS.md` rempli à la main par l'équipe, jamais envoyé vers
GitHub, et la page « Ce qu'on nous a dit » qui l'affiche.
Sans ça : la version simple, sans attendre : le guide d'entretien, les deux étiquettes DIT PAR UN SOIGNANT et
HYPOTHÈSE, et la page qui dit « Aucune parole recueillie pour l'instant ». Pas de fichier de paroles.
Réponse de Hiba (dans la conversation, le 12.11.2026, vers 12 h 10) : « oui, aux conditions que tu écris. » Question fermée. Suite : tâche J06b.

## Q8 — tâche K01 (avenant 2) — 11 novembre
Je voudrais : ta réponse à cette question de l'avenant 2. « Veux-tu une cinquième langue pour l'arrivée et pour le
tirage, par exemple l'espagnol ? »
Sans ça : non. L'arrivée et le tirage restent dans les langues du cahier. Je continue sans attendre.
Réponse de Hiba (dans la conversation, le 12.11.2026, vers 12 h 10) : « non, pas de cinquième langue. » Question fermée.
Nouvelle décision de Hiba (dans la conversation sur le MacBook, le 14.11.2026, au soir) : « Oui, ajoute-le » — l'espagnol, pour l'ARRIVÉE DU HALL seulement, à faire relire par les deux personnes de l'équipe qui parlent espagnol (docs/projet/RELECTURE_ESPAGNOL.md). Le tirage, la répétition et les autres écrans restent dans les quatre langues du cahier.

## Q9 — tâche K06 (avenant 2) — 11 novembre
Je voudrais : ta réponse à cette question de l'avenant 2. « Es-tu d'accord pour recueillir, pendant le hackathon, des
avis anonymes : cinq notes de 1 à 5 et un rôle, sans nom, sans texte libre, dans un fichier qui reste sur
l'ordinateur ? » Avec un oui : la collecte s'allume, les avis restent sur l'ordinateur (jamais vers GitHub), et la page
« Avis » montre le nombre d'avis et les moyennes.
Sans ça : la version simple, sans attendre : le formulaire, essayé avec des avis d'essai effacés ensuite, et la page
qui dit « Aucun avis réel recueilli pour l'instant. »
Réponse de Hiba (dans la conversation, le 12.11.2026, vers 12 h 10) : « oui, aux conditions que tu écris. » Question fermée. Suite : dans la tâche K06, la collecte s'allume, aux conditions écrites ici.

## Q10 — tâche M01 (avenant 3) — 11 novembre
Je voudrais : ta réponse à cette question de l'avenant 3. « Les limites de prudence des trois cartes te
conviennent-elles : 2 m pour le robot à jambes, 1 m pour les deux autres, marche lente, 1 kg sur le dos du robot à
quatre pattes ? »
Sans ça : elles restent comme l'avenant les écrit. Je continue sans attendre.
Réponse de Hiba (dans la conversation, le 12.11.2026, vers 12 h 10) : « oui, ces limites me conviennent. Nous les reverrons samedi avec le fabricant. » Question fermée.

## Q11 — tâche T08 — 11 novembre
Je voudrais : ton choix pour la recherche du médecin. Le cahier donne l'exemple « le dernier rapport de radiologie de
Madame B. ». Dans le faux dossier, Madame Giulia B. n'a pas de rapport de radiologie (le seul est chez Monsieur
Hans K., que le Médecin Exemple ne suit pas). Veux-tu : A) que j'ajoute un rapport de radiologie inventé au dossier de
Madame B. ; ou B) qu'on dise sur scène une autre phrase, par exemple « la lettre du médecin de Madame B. » ?
Et une chose à valider : pour les chiffres du résumé, je n'ai pas pu me servir du verrou des chiffres de l'ossature
(il ne sait lire que vitesse, distance et force). J'ai écrit un contrôle simple à côté (voir `DECISIONS.md`, T08).
Sans ça : B. La recherche répond avec vérité « Je ne trouve pas ce document ». Je continue sans attendre.
Réponse de Hiba (dans la conversation, le 12.11.2026, vers 12 h 10) : « B. Sur scène, nous demanderons aussi le rapport de radiologie, pour montrer la réponse vraie « Je ne trouve pas ce document ». Garde ton contrôle simple des chiffres, et écris sa limite dans NON_TESTE.md. » Question fermée. Suite : tâche H04.

## Q12 — tâche T10 — 11 novembre
Je voudrais : ton choix pour la règle « dans le hall, le robot ne dit rien sur la santé ». Le cahier dit : « C'est une
règle du gardien. » Le gardien de l'ossature (brique 7) ne juge aujourd'hui que les mouvements du robot, pas ce qu'il
dit. J'ai donc écrit la règle à côté, en clair, dans `briques/clinique/accueil_hall.yaml` (une phrase et des mots).
Veux-tu : A) que je la laisse là ; ou B) que j'ajoute au gardien une nouvelle sorte de règle, « ce que le robot ne dit
pas », avec ses essais (c'est toucher à la brique 7 : un tour entier, et un risque pour ce qui marche) ?
Sans ça : A. La règle marche et elle est essayée ; elle n'est simplement pas dans le gardien. Je continue sans attendre.
Réponse de Hiba (dans la conversation, le 12.11.2026, vers 12 h 10) : « A. Écris dans NON_TESTE.md que la règle de parole du hall n'est pas dans le gardien. » Question fermée. Fait au tour 60 (ligne ajoutée à NON_TESTE.md).

## Q13 — tâche L02 (avenant 4) — 12 novembre
Je voudrais : ta réponse à cette question de l'avenant 4. « Veux-tu que le nom du vrai logiciel de la clinique soit
écrit dans une note du dépôt ? »
Sans ça : non. Aucun nom de vrai logiciel n'est écrit nulle part. Je continue sans attendre.
Réponse de Hiba (dans la conversation, le 12.11.2026, vers 12 h 10) : « non. » Question fermée. Aucun nom de vrai logiciel n'est écrit.

## Q14 — tâche T11 — 12 novembre
Je voudrais : ton accord sur ma lecture du cahier. T11 est « finie quand la grande répétition réussit ». Or cinq
étapes n'ont pas encore de pièce : le soir (9), la dictée (11), la flotte (12), la fiche de vérité (13), « rien n'est
sorti de l'ordinateur » (14). Leurs tâches (T19, T18, T24, T27) viennent après T12, et T12 vient après T11 : sans
rien changer, la boucle se bloque. J'ai donc coupé T11 en quatre : T11a (fait : les sept scènes et leur plan B),
puis T11b, T11c, T11d, qui font une version simple de ces cinq étapes, sans voix, sans modèle. T18, T19, T24 et T27
les enrichiront ensuite. L'autre choix : dire T11 finie avec une répétition « RATÉE — 5 étapes manquantes », et
passer tout de suite à la relecture T12.
Sans ça : je fais T11b, T11c, T11d, sans attendre.
Réponse de Hiba (dans la conversation, le 12.11.2026, vers 12 h 10) : « oui, tu as bien fait. Ajoute une tâche N03, à faire avant T32 : une répétition « d'un seul trait », les sept scènes dans une seule séance, sans repartir d'une clinique neuve, avec la durée mesurée et affichée. Si elle existe déjà, dis-le et ne refais rien. Écris aussi dans les questions, en cinq lignes, le plus petit changement qui permettrait au chef de démonstration de jouer ces sept scènes devant le jury. Ne change pas sa brique sans mon accord. » Question fermée. La répétition d'un seul trait n'existe pas encore (aujourd'hui, chaque étape repart d'une clinique neuve) : tâche N03 ajoutée. Les cinq lignes sont plus bas (Q20).

## Q15 — tâche T12 (relecture), pour T19 — 12 novembre
Je voudrais : ton choix. Le cahier (2.6) dit : à toute question de santé, le prototype répond « Je transmets à
l'équipe » et crée une tâche pour un humain. Le soir, la question de la patiente part chez le médecin : une ligne au
carnet, et elle s'affiche dans son résumé du lendemain. Le prototype ne répond pas. Mais il ne crée pas de « tâche »
au tableau des tâches. Veux-tu : A) que cela suffise (le résumé du médecin vaut « tâche pour un humain ») ; ou
B) que chaque question du soir crée aussi une tâche pour le médecin au tableau des tâches ?
Sans ça : A. Je continue sans attendre ; T19 pourra ajouter B.
Réponse de Hiba (dans la conversation, le 12.11.2026, vers 12 h 10) : « B, en version la plus petite : chaque question du soir crée aussi une tâche pour le médecin. » Question fermée. Suite : tâche H02.

## Q16 — la vérification rapide et ses deux minutes — 12 novembre
Je voudrais : ton choix. La vérification rapide dure 115 secondes ; la limite du cahier est 120. Chaque nouvelle
tâche ajoute des essais. Les essais longs de l'ossature sont déjà mis de côté ; ceux qui restent durent tous moins
de 1,5 seconde. Trois choix : A) monter la limite (par exemple à trois minutes) ; B) m'autoriser à installer un
petit outil gratuit et ouvert qui lance les essais en parallèle (`pytest-xdist`, licence MIT, taille à vérifier,
moins de 1 Mo sans doute), dans `.venv` seulement ; C) laisser de côté aussi les essais de la clinique de plus
d'une seconde et demie (ils restent dans `python3 lancer.py tests`).
Sans ça : je ne change ni la limite ni la liste. Je garde les nouveaux essais courts. Si la limite est dépassée,
la commande l'écrit (« ATTENTION : plus de 120 secondes »), je le note dans le suivi, et je continue.
Depuis le tour 23 (12.11, nuit) : c'est arrivé. La vérification rapide dure 123 secondes. Elle passe (0 ratée), mais elle
ne tient plus la règle des deux minutes du cahier. J'ai besoin de ton choix A, B ou C.
Réponse de Hiba : (dans la conversation, le 12.11.2026, vers 11 h 40) « j'accepte que la vérification rapide dépasse deux minutes, jusqu'à cinq. Pour gagner du temps sans rien affaiblir : au début d'un tour, ne la relance pas si rien n'a changé depuis le dernier enregistrement, et dis-le dans le bilan ; à la fin du tour, lance-la toujours en entier ; si tu peux lancer plusieurs vérifications en même temps sans rien installer, fais-le, et dis le temps gagné. Tu ne retires et tu ne sautes aucune vérification pour aller plus vite. Ajoute aussi à NON_TESTE.md la liste des 30 essais sautés, avec la raison de chacun. » Question fermée. Fait au tour 59 : la liste est dans NON_TESTE.md ; deux vérifications lancées en même temps : 320 s au lieu de 550 s.

## Q17 — tâche R2 — 12 novembre (nuit)
Je voudrais : que le modèle Apertus 8B arrive sur l'iMac. Tu as dit oui le 11.11 (Q2). Cette nuit, j'ai vérifié en
ligne, sans rien télécharger : le fichier fait 5 057 885 440 octets (5,06 Go), licence Apache-2.0, aucune condition à
accepter. Puis j'ai lancé le téléchargement : une protection de l'outil (l'assistant de code) l'a refusé, parce que c'est un
fichier venu de l'extérieur. Ce n'est pas un refus de ta part, mais je ne contourne pas cette protection.
Deux façons de débloquer, au choix :
A) Tu lances toi-même cette commande dans un terminal, depuis le dossier du projet (une seule ligne, environ 5 Go) :
   mkdir -p modeles/apertus-8b-gguf && curl -L --fail -C - -o modeles/apertus-8b-gguf/Apertus-8B-Instruct-2509-Q4_K_M.gguf "https://huggingface.co/unsloth/Apertus-8B-Instruct-2509-GGUF/resolve/main/Apertus-8B-Instruct-2509-Q4_K_M.gguf"
   Puis, pour contrôler le fichier : shasum -a 256 modeles/apertus-8b-gguf/Apertus-8B-Instruct-2509-Q4_K_M.gguf
   L'empreinte attendue : 87e7f0eb5a1d33e1a8ea4e7fdd2363764e0465061dd92962e0073aec31a7944d
B) Tu me dis, dans la conversation, de relancer le téléchargement, et tu acceptes la demande de l'outil quand elle s'affiche.
Sans ça : R2 reste « EN QUESTION » ; T13 (le résumé écrit par Apertus) attend ; tout ce qui dit « avec le vrai Apertus »
reste « non mesuré ». Je continue avec les autres tâches. Le modèle d'écoute (R4, 488 Mo) aura sans doute le même refus.
Ajout du tour 36 (12.11, vers 5 h) : non, le modèle d'écoute est passé. L'outil a laissé télécharger ce fichier-là (488 Mo).
Je n'ai pas réessayé Apertus de moi-même : l'outil l'avait refusé, et il demande alors de te laisser décider. Si tu
choisis B, je relance le téléchargement d'Apertus ; il se peut qu'il passe maintenant.
Réponse de Hiba (dans la conversation, le 12.11.2026, vers 12 h 10) : « B. Relance le téléchargement d'Apertus 8B maintenant. Je suis devant l'écran et j'accepterai la demande de l'outil. Ensuite, contrôle la taille et l'empreinte du fichier, dis le résultat, puis fais R2 et T13. Si l'outil refuse encore, dis-le : je lancerai la commande moi-même. » Fait au tour 60, vers 12 h 15 : le téléchargement est relancé, et cette fois l'outil ne l'a pas refusé. Le contrôle de la taille et de l'empreinte se fait dès qu'il finit ; puis R2, puis T13.

## Q18 — tâche L01 (avenant 4) — 12 novembre (nuit)
La table des sources (page `/clinique/sources`) montre ce que chaque badge lit. Un point m'a surpris : le badge
« accueil » lit aujourd'hui le texte entier des documents médicaux (lettre du médecin traitant, ordonnance, liste de
médicaments, rapport de radiologie) et les listes de soin. C'est la porte de lecture telle qu'elle est depuis T03 :
l'accueil trie les papiers. Le patient, lui, ne voit que le titre de ses documents.
Je voudrais : savoir si c'est voulu. A : oui, l'accueil doit lire ces papiers pour les ranger. B : non, l'accueil ne
doit voir que le genre et le titre des documents médicaux (c'est un changement de la porte et de ses vérifications).
Sans ça : je ne change rien (l'avenant 4 dit que la porte ne change pas pour L01). Je continue.
Réponse de Hiba (dans la conversation, le 12.11.2026, vers 12 h 10) : « B. L'écran de l'accueil ne montre que le genre, la date, l'auteur et le patient d'un papier. Jamais le texte d'un document médical. Jamais les listes de soin. La pièce qui range les papiers peut lire le texte d'un papier à ranger, avec son propre badge, pour préparer sa proposition. Pour ce changement seulement, tu peux adapter les vérifications de la porte qui disaient le contraire : écris lesquelles dans DECISIONS.md. Si cela dépasse un tour ou casse le rangement des papiers, arrête-toi et fais la version simple : retire seulement les listes de soin et les documents déjà rangés. » Question fermée. Suite : tâche H01.

## Message de Hiba — les pages dans un vrai navigateur — 12 novembre, vers 11 h 45 (dans la conversation)
« Tu peux ouvrir des pages dans un vrai navigateur. Sers-toi de l'outil que tu as déjà. N'installe rien pour cela : s'il te manque un outil, dis-le et arrête cette tâche. Ajoute deux tâches au suivi. Elles font partie de la liste, et T33 passe après elles. N01 — Les pages vues dans un vrai navigateur, premier passage. À faire au prochain tour. N02 — Le même contrôle, dernier passage. À faire juste avant T32. Pour chaque page que nous avons construite : 1. Ouvre-la dans le navigateur, sur cet ordinateur. Seulement nos pages : aucun site extérieur. 2. Regarde si elle s'affiche, et si le navigateur signale une erreur. 3. Vérifie le bandeau « DONNÉES INVENTÉES », l'heure, le badge et les étiquettes. 4. Essaie chaque bouton une fois, comme une personne le ferait. 5. Regarde-la en largeur de téléphone, puis en grand écran. Aucun texte ne doit être coupé, dans aucune des quatre langues. 6. Garde une image de chaque page dans un dossier du dépôt. Écris le résultat dans docs/projet/PAGES_VUES.md : une ligne par page, avec le navigateur, la taille, ce qui marche et ce qui ne va pas. Si tu trouves un défaut : petit et dans ton propre travail : corrige-le, avec une vérification qui l'aurait vu ; gros, ou dans une brique de l'ossature : note-le dans les questions, ne touche à rien. Tu ne changes aucune vérification qui existe. Si la tâche dépasse un tour, coupe-la par groupes de pages. Dis vrai dans le bilan : « vu dans un vrai navigateur par l'assistant de code, sur cet ordinateur ». Ce n'est pas encore « vu par un humain sur un vrai téléphone » : garde cette ligne dans NON_TESTE.md. »
C'est une autorisation de Hiba (ouvrir nos pages dans le navigateur déjà là, sur cet ordinateur ; rien à installer ; aucun site extérieur). Tâches N01 et N02 ajoutées au suivi.

## Q19 — tâche N01 (les pages vues dans un navigateur) — 12 novembre
En regardant les écrans dans les quatre langues, j'ai vu des langues mêlées. (1) Sur l'écran du patient, en italien, allemand et
anglais : les titres sont traduits, mais les lignes du programme (« installation en chambre », « physiothérapie ») et le genre des
documents (« lettre du médecin traitant ») restent en français : ce sont les données du faux dossier, que je n'ai pas le droit de changer.
(2) Sur les écrans du soignant et du médecin, en allemand : seul le titre « Meine Patienten » est traduit ; la prise de poste, les
demandes et le résumé restent en français.
Je voudrais : savoir quoi faire. A : je traduis les textes fixes des écrans du soignant et du médecin en allemand (écrit par moi, pas relu
par quelqu'un qui parle allemand), et j'ajoute une petite table de traduction pour le programme du patient, à côté du faux dossier.
B : on garde le français pour le soignant et le médecin, on retire le lien « de » de ces deux écrans, et on dit sur l'écran du patient
« programme en français ». C : on laisse comme c'est, et on le dit dans NON_TESTE.md.
Sans ça : C. Je ne change rien ; c'est écrit dans docs/projet/PAGES_VUES.md et NON_TESTE.md. Je continue.
Réponse de Hiba (dans la conversation, le 12.11.2026, vers 12 h 10) : « A. Traduis les textes fixes des écrans du soignant et du médecin en allemand, et ajoute la petite table de traduction pour le programme du patient. Mets toutes les phrases traduites dans un seul fichier, pour qu'un équipier qui parle la langue les relise. Tant qu'elles ne sont pas relues, écris-le dans NON_TESTE.md. » Question fermée. Suite : tâche H03.

## Q20 — le chef de démonstration et les sept scènes (demandé par Hiba dans sa réponse à Q14) — 12 novembre
Le plus petit changement qui permettrait au chef de démonstration de l'ossature (brique 15) de jouer les sept scènes, en cinq lignes :
1. Aujourd'hui, une étape de son scénario ne sait faire qu'une chose à la fois, et toujours avec le robot (une phrase dite, une panne, une attente) ; nos scènes passent surtout par les écrans.
2. Le changement : une nouvelle sorte d'étape, « contrôle », qui appelle par son nom une pièce déjà écrite (nos quatorze contrôles de `repetition.py`) et reçoit « réussie » ou « ratée », avec une ligne de détail.
3. Où : `briques/b15_chef_demo/scenario.py` (accepter « controle: NOM » dans une étape) et `chef.py` (une fonction de plus pour jouer cette étape) ; ses minuteries, ses plans B et son compte rendu serviraient tels quels.
4. Ce qui ne changerait pas : ses scénarios actuels, ses essais, le gardien, la prise ; notre `scenario_clinique.yaml` deviendrait un scénario de la brique 15, et `chef_clinique.py` pourrait disparaître.
5. Le coût : environ un tour, plus les essais ; le risque : toucher une brique qui marche à deux jours du hackathon. Je n'y touche pas sans ton accord.
Je voudrais : ton accord, ou ton refus. Sans ça : je ne touche pas à la brique 15 ; le scénario de la clinique reste joué par `chef_clinique.py`.
Réponse de Hiba : (dans la conversation, le 12.11.2026, vers 12 h 20) « oui, à ces conditions. Tu ajoutes seulement une nouvelle sorte d'étape à la brique 15 ; tu ne changes aucune étape qui existe. Toutes les vérifications de l'ossature passent sans être changées. Tu notes le changement dans DECISIONS.md. Un tour, pas plus : si c'est plus gros, tu annules et tu me le dis. Fais-le juste avant N03, puis fais jouer N03 par le chef de démonstration. » → tâche H05 ajoutée au suivi, avant N03.

## Deux autres demandes de Hiba, le 12.11.2026, vers 12 h 20 (pas des réponses à une question)
- « Le clic sur « Source », écran du médecin : c'est une priorité. Dans le navigateur, un clic doit ouvrir le document, comme pour une personne. Corrige-le dans N01b, avec une vérification qui clique vraiment. » → noté sur N01b.
- « Après T13 : refais avec le vrai Apertus tout ce qui est marqué « non mesuré » : le rangement des papiers (T14) et un tirage de trente demandes (K01). Écris les chiffres tels quels, même s'ils sont moins bons qu'avec le cerveau de test. Note aussi le temps de réponse, et dis-moi si une réponse met plus de cinq secondes. » → tâche H06 ajoutée au suivi, après T13.

## Q21 — Apertus et les « merci » (demandé par Hiba le 12.11, vers 12 h 35) — 12 novembre
Ce qui se passe : on dit « Merci beaucoup ! » ou « Il fait beau », et Apertus propose de faire répéter la phrase par le robot (5 fois sur 12 dans la mesure du tour 61). Rien de dangereux, mais le robot parlerait sans qu'on le lui demande.
La plus petite correction, deux choix (aucun n'est essayé : « à vérifier ») :
A) Dans la brique 6, ajouter UN exemple fixe à ceux que le modèle reçoit déjà : « Merci beaucoup ! » → pas d'action. Une ligne dans un fichier de l'ossature, plus un essai. À mesurer ensuite avec `python3 lancer.py apertus-essai` : le chiffre peut monter, ou d'autres réponses peuvent bouger.
B) Sans toucher au modèle : une règle après le cerveau, dans la chaîne — si l'action proposée est « parler » et que le texte à dire est la phrase entendue, recopiée, on ne fait rien. Quelques lignes dans `commun/chaine.py`, plus un essai. Ne dépend pas du modèle ; ne corrige que ce cas-là.
Je recommande B (sûr, mesurable, marche avec tous les cerveaux) ; A et B touchent tous deux l'ossature : je ne fais rien sans ton accord.
Ajout du tour 64 (13 h 09) : le tirage a montré un cas voisin — à un robot sans bras, Apertus fait dire « je vais prendre le coussin ». La règle B ne l'arrêterait pas (ce n'est pas la phrase entendue). Une règle C, plus large, l'arrêterait : sur un ordre au robot, une action « parler » proposée par le cerveau ne part jamais toute seule ; le robot dit à la place une phrase fixe (« Je ne peux pas faire cela. »). À vérifier, pas essayé.
Je voudrais : A, B, C, plusieurs, ou rien. Sans ça : rien ne change ; la ligne reste dans NON_TESTE.md.
Réponse de Hiba (dans la conversation, le 12.11.2026, vers 22 h 30) : « C ». Question fermée → tâche H14 au suivi.

## Deux messages de Hiba pendant les tours 62 et 63 (12.11.2026, vers 12 h 35 et 12 h 50) — pas des réponses à une question
- « Ajoute une tâche H07, après H06 : mesurer la chaîne entière sur l'iMac, avec l'écoute, le vrai Apertus et la voix en même temps. […] » → tâche H07 au suivi. « Les « merci » et « il fait beau » : ne corrige pas maintenant. Écris-le dans NON_TESTE.md, et propose dans les questions la plus petite correction. » → fait : NON_TESTE.md et question Q21 (elle attend ta réponse, plus haut).
- « Message de Hiba : préparer le branchement du vrai robot. Ajoute une tâche H08, après H07. […] Fini quand : les deux ébauches passent le test de conformité avec une doublure à la place du robot, et rien d'autre n'a changé. » → tâche H08 au suivi, avec toutes les conditions recopiées.

## Q22 — la mémoire de l'iMac (tâche H07) — 12 novembre, 13 h 20
Je voudrais : savoir comment tu veux trancher. Mesuré : avec l'écoute, Apertus et la voix ensemble, il restait 1,48 Go libres au plus bas et le disque a pris 0,62 Go de mémoire d'échange en plus ; par ma règle, la mémoire manque. Mais l'iMac n'était pas vide (cet agent, un navigateur, d'autres applications).
A) Tu fermes tout le reste sur l'iMac et tu lances `python3 lancer.py chaine-mesure` (une minute) : on saura si l'iMac seul suffit.
B) On décide tout de suite de partager : Apertus sur l'iMac (`python3 lancer.py cerveau --partager`), le reste sur le MacBook. Jamais essayé : il faudra le mesurer samedi matin au plus tard.
C) On garde tout sur l'iMac tel quel et on accepte le risque (les temps mesurés restent sous 5 secondes).
Sans ça : rien ne change ; la ligne reste dans NON_TESTE.md. Je ne ferme aucun de tes programmes.
Réponse de Hiba (dans la conversation, le 12.11.2026, vers 22 h 30) : « B » (partager tout de suite : Apertus sur l'iMac, le reste sur le MacBook). Question fermée → tâche H15 au suivi ; la mesure à deux Mac se fait samedi matin.

## Q23 — « validée par un humain » pour une phrase entendue (relecture de la tranche 2, T21) — 12 novembre, 14 h 13
Ce qui se passe : une coche, une demande au robot ou une dictée arrivée « à la voix » est écrite au carnet avec « validée par un humain : oui ». Aujourd'hui la phrase est tapée par la personne, donc c'est vrai. Le jour où une vraie écoute sera branchée, ce sera la machine qui aura compris, et personne n'aura confirmé.
A) On laisse ainsi pour la démonstration (tout est tapé), et la limite reste écrite dans NON_TESTE.md.
B) Une phrase entendue est écrite « validée : non », et la personne confirme d'un doigt (un bouton « c'est bien ça »). Plus juste ; un geste de plus pour le soignant ; environ un tour.
Je recommande A pour samedi si aucun micro n'est branché aux écrans, B dès qu'un micro l'est.
Je voudrais : A ou B. Sans ça : rien ne change.
Ajout sur Q22 (14 h 13) : à la mesure du tour 68, la mémoire n'a pas manqué (1,63 Go libres au plus bas, aucun échange en plus). Le résultat dépend donc de ce qui est ouvert sur l'iMac ; le choix A (refaire la mesure avec tout fermé) reste le plus sûr.
Réponse de Hiba (dans la conversation, le 12.11.2026, vers 22 h 30) : « B ». Question fermée → tâche H16 au suivi.

## Q24 — l'accueil et la liste « Préparation de la sortie » (tâche H01) — 12 novembre, 14 h 41
Ta réponse à Q18 dit : « Jamais les listes de soin » pour l'accueil. C'est fait. Mais le cahier donne à l'accueil trois points de la liste « Préparation de la sortie » : la liste des rendez-vous, le transport, les documents à envoyer. Ces trois points ne sont pas médicaux ; les autres points de la même liste sont pour le médecin et le soignant.
A) L'accueil ne voit aucune liste (c'est l'état d'aujourd'hui) : ses trois points sont cochés par le soignant, ou restent « à faire ».
B) L'accueil voit et coche SEULEMENT ses trois points de la liste de sortie, pas les autres points ni les autres listes. Environ un tour.
Je recommande B : c'est ce que le cahier décrit, et rien de médical n'est montré.
Je voudrais : A ou B. Sans ça : rien ne change (A).
Réponse de Hiba (dans la conversation, le 12.11.2026, vers 22 h 30) : « B ». Question fermée → tâche H17 au suivi.

## Q25 — l'écran du patient et deux essais établis (tâche H03) — 12 novembre, 15 h 10
Ta réponse à Q19 demande une table de traduction pour le programme du patient. Elle est écrite et essayée (allemand, italien, anglais). Mais je ne l'ai PAS allumée sur l'écran du patient : deux essais établis de `briques/clinique/tests/test_ecrans.py` demandent que l'écran de la patiente italienne montre son programme en français.
- `test_le_patient_ne_voit_que_lui_dans_sa_langue` : la ligne `assert "physiothérapie" in texte and "visite du médecin" not in texte`.
- `test_l_ecran_suit_l_horloge_et_montre_temps_accelere` : la ligne `assert "visite du médecin" in client.get("/clinique/patient/contenu").text`.
Ces deux lignes vérifient autre chose (le programme du bon jour) ; elles le font avec les mots français. Avec la table, l'écran dit « fisioterapia » et « visita del medico ».
A) Tu m'autorises à adapter ces deux lignes, et seulement elles (elles chercheront les mots italiens de la table), et j'allume la table. Je note les lignes dans DECISIONS.md.
B) On laisse la table éteinte sur l'écran du patient : son programme reste en français, et c'est dit dans NON_TESTE.md.
Je recommande A. Je voudrais : A ou B. Sans ça : B (la table reste prête, éteinte).
Réponse de Hiba (dans la conversation, le 12.11.2026, vers 22 h 30) : « A ». Question fermée → H03b redevient À FAIRE ; seules les deux lignes citées seront adaptées.

## Q26 — la page « Ce qu'on nous a dit » et deux essais établis (tâche J06b) — 12 novembre, 15 h 30
Tu as dit oui à Q7. Le fichier des paroles a sa place (`journal/clinique/PAROLES_DES_SOIGNANTS.md`, jamais vers GitHub), son modèle à remplir, et la lecture est écrite et essayée. Mais la page « Ce qu'on nous a dit » ne lit PAS encore ce fichier : deux essais établis de `briques/clinique/tests/test_parole_des_soignants.py`, écrits quand Q7 était sans réponse, disent le contraire.
- `test_les_deux_etiquettes_existent_et_tant_qu_il_n_y_a_pas_de_parole_tout_est_hypothese` : la ligne `assert paroles.paroles_recueillies() == 0` (elle raterait dès que l'équipe écrit une parole).
- `test_rien_n_est_invente_aucune_parole_aucun_fichier` : la ligne `assert "open(" not in source and "read_text" not in source` (« la page ne lit aucun fichier de paroles »).
A) Tu m'autorises à adapter ces deux lignes, et seulement elles : « zéro parole tant que le fichier de l'équipe n'existe pas », et « la page ne lit que ce fichier-là, par la pièce de lecture ». Je branche la page et je note les lignes dans DECISIONS.md.
B) La page reste en version simple : elle dit « Aucune parole recueillie », même si l'équipe remplit le fichier.
Je recommande A. Je voudrais : A ou B. Sans ça : B.
Réponse de Hiba (dans la conversation, le 12.11.2026, vers 22 h 30) : « A ». Question fermée → J06b-b redevient À FAIRE ; seules les deux lignes citées seront adaptées.

## Message de Hiba — le mode interprète — 12 novembre, vers 15 h 40 (dans la conversation)
« Lundi, la personne qui présente répondra au jury en français. La boîte redira chaque phrase en anglais, à voix haute. C'est décidé. Ajoute une tâche H09, après H07. Si tu as déjà reçu mon essai de traduction, fais-le d'abord : il sert à choisir le chemin. 1. Un bouton « Interprète » sur l'écran de régie. Tant qu'il est tenu, la boîte écoute. Quand on le relâche, elle traduit la phrase en anglais, la dit, et l'affiche en grand. 2. L'écran porte l'étiquette « TRADUCTION AUTOMATIQUE EN DIRECT ». 3. Une liste de mots fixés d'avance, dans un fichier que je peux lire et changer : soignant, course, boîte, palier, seuil d'arrêt. La traduction les respecte. 4. Les chiffres s'affichent en chiffres. 5. Un deuxième bouton affiche la version anglaise préparée d'une réponse, avec l'étiquette « TRADUCTION PRÉPARÉE ». Les réponses préparées sont dans un fichier. 6. Rien ne sort de l'ordinateur. Tout marche sans Internet. Fini quand : dix phrases dites en français sortent en anglais à l'écran et à la voix, le délai est noté pour chacune, et les erreurs sont comptées telles quelles. Tu ne télécharges rien. Si un plus gros modèle d'écoute te paraît nécessaire, pose la question. »
→ tâche ajoutée au suivi sous le nom **H10** (H09 est déjà le badge du cerveau, fait au tour 69). **Je n'ai reçu aucun « essai de traduction » dans cette conversation** : si tu l'as écrit, il ne m'est pas arrivé ; renvoie-le et je le ferai en premier.

## Q27 — le mode interprète : les mots anglais, le chemin, le modèle d'écoute (tâche H10) — 12 novembre, 16 h 03
Trois choses à trancher. Aucune ne bloque H10b : je continue avec mes propositions.
1. **Les mots fixés en anglais.** Tu as donné les mots français. J'ai proposé : soignant = caregiver ; course = errand ; boîte = box ; palier = level ; seuil d'arrêt = stop threshold. Change-les dans `briques/clinique/interprete_mots.yaml`, ou dis-moi les tiens. (« palier » : je ne sais pas ce qu'il veut dire dans ta présentation.)
2. **Le chemin.** Mesuré sur dix phrases en voix de synthèse : le chemin direct est rapide (1 s) mais faux (4 phrases sur 10 sans erreur comptée) ; le chemin en deux temps, par Apertus, met 1,8 s et donne 8 sur 10 (7 sur 10 à ma lecture). Je prends le chemin en deux temps, sauf si ton essai de traduction dit autre chose — je ne l'ai pas reçu.
3. **Un plus gros modèle d'écoute ?** Le modèle « small » a mal entendu « course au robot » (« coursoire beau ») et « course » (« cour se »). Un modèle plus gros entendrait peut-être mieux, mais il faut le télécharger (taille à vérifier avant ; de l'ordre de 1,5 Go pour « medium », à vérifier) et il sera plus lent. A : on reste sur « small », et la personne qui présente parle lentement. B : tu m'autorises à vérifier la taille, puis à télécharger et mesurer un plus gros modèle. Sans ça : A.
Réponse de Hiba (dans la conversation, le 12.11.2026, vers 22 h 30) : « Pour l'interprète je te laisse faire parce que tu sais mieux que moi. » Mon choix pour 1 et 2 : les mots anglais restent ceux proposés (« palier » = level, sens à vérifier avec la personne qui présente) ; le chemin en deux temps, par Apertus. Pour 3 (le modèle d'écoute) : j'ai compris « B » dans les lignes suivantes de ta réponse, à confirmer (télécharger environ 1,5 Go est un feu orange).


## Q28 — montrer sur le tableau de flotte la place de R1 lue sur le robot ? (tâche H12) — 12 novembre, 17 h 43
Depuis H12, la place de R1 est lue sur le robot (le lieu du plan le plus proche de sa position), et elle sert à choisir qui reprend une course. Mais le tableau de flotte écrit toujours « place pas suivie sur ce plan » et « batterie pas lue » pour R1. Je ne l'ai pas changé : un essai que j'ai écrit au tour 81 (`briques/clinique/tests/test_relecture_tranche_3.py`, « point 3, avec le faux robot branché ») demande exactement ces mots, et je ne change pas un essai établi sans ton accord.
- **A (recommandé)** : j'adapte cet essai (trois mots dans une ligne) et le tableau écrit « près de « Salon » (lu sur le robot) » et la batterie « lue sur le robot ». Un petit tour.
- **B** : on laisse comme c'est. Le tableau ne dit rien de la place de R1.
Réponse de Hiba (dans la conversation, le 12.11.2026, vers 22 h 30) : j'ai compris « A » (lignes de la réponse comptées dans l'ordre) ; à confirmer, parce que tu as donné dix lignes pour neuf questions.

## Q29 — les codes QR de la page des téléphones (tâche T30) — 12 novembre, 19 h 10
Le cahier demande un code QR pour chaque écran. Aucun outil pour les dessiner n'est sur cet ordinateur (ni module Python, ni programme). Installer un outil est un feu orange : je n'ai rien installé. En attendant, la page `/clinique/telephones` écrit chaque adresse en gros (8 écrans), et `python3 lancer.py telephones` vérifie que chacune mène au bon écran par le Wi-Fi.
- **A (recommandé)** : installer un petit module Python qui dessine des codes QR (par exemple « segno », écrit en Python seul). Sa licence et sa taille sont à vérifier avant ; je te les montre, puis j'attends ton « oui ».
- **B** : j'écris moi-même le dessin des codes QR, sans rien installer. Plus long, et je ne pourrai pas le vérifier sans un téléphone qui scanne.
- **C** : pas de codes QR. Les adresses en gros suffisent.
Réponse de Hiba (dans la conversation, le 12.11.2026, vers 22 h 30) : j'ai compris « A » (installer un petit module, après t'avoir montré sa licence et sa taille) ; à confirmer, pour la même raison. Rien n'est installé.

Confirmation de Hiba (dans la conversation, le 12.11.2026, vers 22 h 35) : « Oui, c'est juste » : Q27 (modèle d'écoute) = B, Q28 = A, Q29 = A. → tâches H18, H19, H20 au suivi.

## Q30 — deux feux orange : le module des codes QR et le modèle d'écoute (Q29 A, Q27 B) — 12 novembre, 22 h 40
Lu sur les pages publiques le 12.11.2026 (pypi.org/pypi/segno/json ; huggingface.co, dépôt ggerganov/whisper.cpp) :
- **segno 1.6.6** (codes QR, écrit en Python seul) : 76 503 octets (environ 77 Ko). Licence : « BSD » dans sa fiche PyPI, à confirmer dans son fichier LICENSE. Aucune dépendance de plus avec Python 3.13. S'installe dans `.venv` ; une ligne dans `LICENCES.md`.
- **Modèle d'écoute** (aujourd'hui « small », 487 601 967 octets ≈ 488 Mo) : « medium » 1 533 763 059 octets (≈ 1,53 Go) ; « medium q8_0 » 823 369 779 octets (≈ 823 Mo) ; « medium q5_0 » 539 212 467 octets (≈ 539 Mo). Je recommande « medium q5_0 » : à peine plus gros que l'actuel, plus doux pour la mémoire de l'iMac (Q22). Que notre whisper.cpp lise les modèles compressés, et la licence des modèles : à vérifier avant de le garder. Il sera plus lent : je mesurerai sur les dix phrases de l'interprète, tel quel.
Je voudrais : « oui » ou « non » pour chacun. Sans ça : rien n'est installé ni téléchargé.
Réponse de Hiba (dans la conversation, le 12.11.2026, vers 22 h 45) : segno : « Oui, installe » ; modèle d'écoute : « medium complet (1,53 Go) ». Question fermée → H19 et H20 À FAIRE. Condition gardée : si le fichier de licence de segno n'est pas BSD, je m'arrête et je le dis.


## Q31 — le kit du Reachy Mini : cinq paquets citent la GPL, pas deux — 15 novembre, vers 3 h
J'avais écrit « deux paquets en partie sous GPL ». C'était faux : en relisant ce que les paquets installés déclarent, ils sont **cinq** (`gstreamer-plugins`, `gstreamer-plugins-libs`, `gstreamer-plugins-gpl`, `gstreamer-plugins-gpl-restricted`, `gstreamer-libs` : le son et l'image). Le kit est installé à part (`~/reachy_env`), rien n'est copié dans le projet, rien n'est redistribué.
- **A (recommandé)** : on le garde. Notre projet ne contient aucun de ces paquets ; il parle au programme du fabricant par des demandes web.
- **B** : on le désinstalle (`rm -rf ~/reachy_env`) et on passe par le Mac du collègue.
Sans réponse : A, puisque ton « oui » portait sur l'installation ; mais je voulais que tu aies le bon chiffre.

## Q32 — la tête peut-elle faire « oui » et « non » sans l'accord d'un humain ? — 15 novembre, vers 3 h
La règle n° 1 du gardien (`briques/b07_gardien/regles.yaml`) dit : « Le robot reste toujours à 1 mètre des personnes, quand il se déplace, prend, pose ou fait un geste. » S'il ne sait pas où sont les gens, il demande à un humain. Posée sur la table à côté de la patiente, la tête ne fait donc « oui » ou « non » qu'après un « oui » sur l'écran. Tourner la tête (« regarder ») n'est pas dans la règle : cela passe sans accord. Je n'ai rien changé à la règle : c'est la tienne, et c'est une règle de sécurité.
- **A (recommandé pour lundi)** : on garde la règle. Dans la scène, la tête TOURNE vers la patiente et vers le bras (sans accord), et le refus est DIT et affiché. Si on veut le « non » de la tête, quelqu'un touche « oui » sur l'écran — et la maman le dit : « Iris asks a human before any gesture near a person. »
- **B** : avec le responsable sécurité, tu décides que les deux petits gestes de tête sont permis sans accord (la tête ne sort pas de sa place, 15° de chaque côté). Il faudrait alors changer la règle (retirer « rejouer_geste » pour ce robot seulement — à écrire), puis allumer `interrupteurs → non_de_la_tete → actif: true`. Deux réglages : je ne les fais pas sans ton « oui ».
Sans réponse : A.

## Décisions de Hiba pour la main — 15 novembre, vers 19 h (dans la conversation)
- « tu peux juste éviter d'être trop prudent, personne ne s'approche de la main et il n'y aura que des objets qui seront en contact avec » → limites de la main relevées (courant jusqu'à 600 pour mille, vitesse jusqu'à 5000).
- À la question « La main doit-elle bouger sans "oui" sur l'écran à chaque geste ? » : « Oui, sans accord » → `reglages.yaml`, `interrupteurs → accord_d_avance`, pour le robot `leadtron-dh116` et ses quatre gestes seulement. Aucune règle du gardien n'est changée : la demande reste écrite dans le journal, la réponse est donnée d'avance au nom de Hiba.
- Cela ne vaut que pour la main. La tête (Q32) garde l'accord à chaque geste.

## Q31 — rendre Apertus visible au MacBook (tâche H15) — 13 novembre, nuit
Pour partager le travail (Q22 B), l'iMac doit lancer Apertus en le rendant visible sur le Wi-Fi local : `python3 lancer.py cerveau --partager` (adresse 192.168.1.43:8089, Wi-Fi local seulement). La règle de sécurité de ma session refuse que je le lance moi-même (« ouvrir un service sur le réseau local »). Je ne la contourne pas.
- **A (recommandé)** : tu tapes toi-même cette commande dans un Terminal de l'iMac, dans le dossier du projet, et tu la laisses ouverte. Je fais le reste : la session du MacBook branche son écoute et ses écrans sur cette adresse, et je mesure.
- **B** : tu ajoutes une permission pour que je puisse lancer cette commande (dans les réglages de l'assistant de code sur l'iMac). C'est un réglage : je ne le fais pas moi-même.
- **C** : on ne partage pas ; tout tourne sur l'iMac, le MacBook sert de secours.
Je voudrais : A, B ou C. Et, à part : mettre Chrome à jour sur le MacBook (150 → 157), pour les trois essais qui y ratent.
Réponse de Hiba (dans la conversation, le 13.11.2026, nuit) : « C : tout sur l'iMac ». Question fermée → on ne partage pas ; le MacBook, déjà préparé, sert de secours. H15 est fermée avec ce choix.
Puis, quelques minutes plus tard : « non je veux qu'on continue sur le macbook, je veux pas tout ici sur l'imac c'était une erreur ». Nouveau choix de Hiba : **D — Apertus sur le MacBook lui-même** (aucun service ouvert sur le Wi-Fi) ; elle accepte le téléchargement du modèle sur le MacBook (5,06 Go, feu orange). → H15 rouverte avec ce choix.

## Q32 — H16, les coches à la voix et un essai établi — 13 novembre, tour 106
Ta réponse à Q23 (B) : une phrase entendue est écrite « validée : non », puis la personne confirme d'un doigt (« C'est bien ça »).
C'est fait pour les demandes au robot à la voix (tour 106). Pour les coches à la voix, un essai établi dit l'inverse :
- `briques/clinique/tests/test_cocher_a_la_voix.py`, ligne 48 : `assert ligne["donnees"]["entendu"] == phrase and ligne["valide_par_un_humain"] is True`.
A) Tu m'autorises à changer seulement la fin de cette ligne (`is True` devient `is False`), et je fais le bouton « C'est bien ça » pour les coches. Je le note dans DECISIONS.md.
B) Les coches à la voix restent « validée : oui » ; la limite reste écrite dans NON_TESTE.md.
Les dictées : aujourd'hui il n'y a pas de dictée arrivée à la voix (le médecin tape) ; sa phrase devient un brouillon, déjà hors du dossier. Rien à changer.
Je voudrais : A ou B. Sans ça : rien ne change pour les coches.

## Q33 — H17, quelles sorties l'accueil voit — 13 novembre, tour 107
C'est fait : l'accueil voit et coche ses trois points de la liste de sortie, et rien d'autre (aucun mot médical ; la règle H01 tient).
Une chose n'est pas tranchée : quelles personnes l'accueil voit.
A) Toutes les personnes qui ont la liste de sortie (c'est l'état d'aujourd'hui ; une personne déjà sortie reste affichée).
B) Seulement celles qui sortent aujourd'hui ou demain. Quelques lignes, plus un essai.
En plus (oui ou non) : la fin de poste de l'accueil rappelle ses points de sortie pas faits (aujourd'hui : non).
Je recommande B et oui. Sans ça : rien ne change (A, et pas de rappel).

## Q34 — H18, le chiffre de la batterie de R1 — 13 novembre, tour 108
C'est fait (Q28 : A) : avec le faux robot branché, le tableau de flotte écrit « près de « Salon » (lu sur le robot) » et « batterie lue sur le robot ».
Le chiffre n'est pas montré : la même ligne de l'essai établi (`test_relecture_tranche_3.py`, ligne 103) demande aussi `"100 %" not in ligne` (au tour 81, ce chiffre aurait été inventé ; maintenant il est lu).
A) Tu m'autorises à retirer seulement `"100 %" not in ligne and ` de cette ligne, et le tableau écrit « 100 % (lu sur le robot) ».
B) On laisse : « batterie lue sur le robot », sans chiffre.
Sans ça : B.

## Q35 — H19, brancher les codes QR sur la page des téléphones — 13 novembre, tour 109
Fait : segno 1.6.6 est installé (licence BSD lue dans son fichier LICENSE). La pièce `briques/clinique/codes_qr.py` dessine un code QR par adresse ; le Mac lui-même relit chaque code (essai `test_codes_qr.py`). Pas essayé avec un vrai téléphone.
Pas encore sur la page : un essai établi la décrit sans codes QR :
- `briques/clinique/tests/test_reseau_local.py`, ligne 64 : `assert "Codes QR : pas encore" in page and "Q29" in page and "<img" not in page and "<svg" not in page`.
A) Tu m'autorises à changer cette ligne : elle demandera un code QR (un dessin `<svg>`) à côté de chaque adresse, et plus « pas encore ». Je mets les codes sur la page. Je le note dans DECISIONS.md.
B) Les codes restent hors de la page (la pièce est prête, pas branchée).
Sans ça : B.
