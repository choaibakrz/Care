# Brique 17 — Notes pour le coordinateur

Écrit le 11.11.2026. Tout est **testé sur faux robot** (et hors ligne) ; rien n'est essayé sur un vrai robot ni sur un Mac.

## Ce que j'ai fait
- `briques/etat_des_briques.yaml` : l'état des 17 briques, lisible par la machine, rempli d'après le code et
  NON_TESTE.md. Prêtes : 1, 2, 4, 6, 12. Version minimale : 7, 13, 17. À faire : 3, 5, 8, 9, 10, 11, 14, 15, 16.
  Un test vérifie que l'état va avec le dossier (un dossier qui existe ⇔ pas « à faire »).
- `briques/b17_kit_samedi/` : l'analyseur hors ligne (`analyseur.py`), le générateur de plan et de scénario
  (`plan.py`), la commande (`kit.py`), les données YAML (`mots_cles.yaml`, `connaissances.yaml`,
  `programme_48h.yaml`, `equipes.yaml`), `GUIDE.md`, `TACHES.md`, 31 tests.
- `lancer.py` : seulement la sous-commande `kit-samedi` (une fonction, trois lignes de parseur, une ligne d'aide).
- `exemples/` : un faux défi en français (`defi_exemple.md`) et son plan (`plan_exemple.md`,
  `plan_exemple_scenario.yaml`) ; un faux défi en allemand (`defi_exemple_de.md`). Un faux défi en anglais est dans les tests.
- `docs/projet/SAMEDI_MATIN.md` (racine) : la liste cochable du premier jour.
- `savoir-faire/lire-le-defi/SKILL.md` : la skill (front matter `name`, `description`, puis les étapes).
- Les phrases du brouillon de scénario sont **jouées sur le faux robot** par un test (humanoïde, chien, bras ;
  fr, de, en, it) : chaque étape fait ce que le plan annonce (action, confirmation « oui », question, refus).

## À aligner, à décider
- **Format du scénario (brique 15)** : mon YAML est simple — `etapes:` liste de `{nom, type, dire + langue (+ puis_dire)
  ou action, attendu, duree_max_s, plan_b, critere}`, plus `plans_b`, `langues`, `duree_totale_s`,
  `duree_demonstration_s`. **Le coordinateur doit l'aligner sur le format de la brique 15.** Le code qui l'écrit :
  `plan.py → scenario()` et `rendre_scenario()` ; les étapes viennent de `connaissances.yaml → etapes`.
- **Skill = feu orange** : un fichier dans `savoir-faire/` est une skill active pour l'assistant de code dans ce dépôt.
  docs/projet/REGLES_DES_AGENTS.md met « installer une skill » en feu orange : demander le « oui » de Hiba avant de fusionner ce fichier.
- **Noms des briques 8, 9, 10, 11, 14, 16** : écrits nulle part dans le dépôt ; je les ai déduits d'docs/projet/IDEES.md et des
  TACHES.md (`nom_a_verifier: true`). **Brique 14 : rôle inconnu** (« Rôle à vérifier »). À corriger dans
  `briques/etat_des_briques.yaml`.
- **Après chaque fusion** (brique 15, puis les autres) : mettre à jour `briques/etat_des_briques.yaml` (état, dossier,
  commandes, TACHES.md), sinon le kit annonce une brique « à faire » qui existe. Puis régénérer l'exemple :
  `python3 lancer.py kit-samedi briques/b17_kit_samedi/exemples/defi_exemple.md --sortie briques/b17_kit_samedi/exemples/plan_exemple.md`.
- Heures officielles du Carnival (repas, passage devant le jury) : **à vérifier** ; le plan met la démonstration
  lundi 8 h. À changer dans `programme_48h.yaml` dès qu'on les connaît.

## Problèmes trouvés en passant (hors de ma brique, rien modifié)
1. **Verrou des chiffres incomplet** (brique 6, `briques/b06_cerveau/branchements/regles.py`, testé sur faux robot,
   cerveau à règles) : ces ordres ne sont PAS refusés — la vitesse n'est pas lue, le robot part à sa vitesse normale
   sans le dire : « Va à la cuisine à **cinq** mètres par seconde », « Geh zur Küche mit 5 **Metern** pro Sekunde »,
   « Go to the kitchen at **five** meters per second ». Les mêmes avec un chiffre et « Meter » sont refusés.
   Pas de danger physique (vitesse normale, sous la limite), mais la preuve 2 échoue dans ces formes, et l'écoute
   peut écrire les nombres en lettres. Mon scénario allemand dit donc « 5 Meter pro Sekunde ». À donner au rôle
   Cerveau, avec relecteur sécurité. (J'ai essayé de créer une tâche suggérée : délai dépassé, elle n'existe peut-être pas.)
2. **Message en français dans d'autres langues** : un ratage de saisie répond, en allemand ou en anglais,
   « … « bouteille » est hors de portée » (fin de phrase en français). Petit défaut de traduction (faux robot ou phrases).

## Lignes à ajouter (je n'ai pas modifié ces fichiers)

### LICENCES.md
- Brique 17 (kit du samedi matin) : **aucun nouveau paquet** (seulement PyYAML, déjà listé) ; aucun code copié ;
  tout écrit pour ce projet. Les faux défis d'exemple sont inventés par l'équipe.

### DECISIONS.md (« Prises pendant la brique 17, à relire par Hiba »)
- Kit du samedi matin **hors ligne, par mots-clés** (fr, de, en), sans modèle de langue : même défi → même plan.
  Le kit repère ; un humain relit et ajuste.
- 35 personnes : 11 rôles fixes (responsable, sécurité ×2, relecteurs ×2, architecte, tests ×2, rédacteur,
  démonstration ×2), 14 en équipes de base (adaptateurs ×4, gardien, cerveau, voix, yeux, écran ×2), 10 renforts
  donnés tour à tour aux briques qui manquent, au plus 4 par brique. L'adaptateur (brique 3) est toujours le premier chantier.
- 48 heures : sommeil par rotation la nuit 1 (R1 22 h–4 h, R2 1 h–7 h, R3 4 h–10 h), nuit 2 tout le monde 23 h–5 h ;
  gel des fonctions dimanche 12 h, gel du code dimanche 20 h, répétitions dimanche 14 h, 16 h, 18 h et lundi 7 h ;
  démonstration lundi 8 h (**à vérifier**).
- Vrai robot la nuit : seulement si le responsable sécurité ou son adjoint est réveillé.
- Scénario : toujours un ordre flou (question) et un ordre dangereux (refus expliqué), l'arrêt d'urgence et la fiche
  de vérité ; 20 % de marge sur la durée de la démonstration.

### NON_TESTE.md
- Kit du samedi matin : jamais lancé sur un vrai défi ; mots-clés essayés sur trois faux défis inventés (fr, de, en) ;
  les mots des capacités n'existent qu'en fr, de, en (un défi écrit en italien serait mal lu).
- Phrases du scénario : essayées sur le faux robot avec le cerveau à règles seulement (ni Apertus, ni la voix).
- Skill `lire-le-defi` : jamais lancée dans une session de l'assistant de code (seul son format est testé).
- Ligne « Pas encore construit » : retirer la brique 17 (version minimale construite).
