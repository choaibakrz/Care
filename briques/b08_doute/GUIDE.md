# Brique 8 — « Je ne suis pas sûr » (guide d'une page)

**Rôle** : savoir demander de l'aide au bon moment, au lieu d'agir au hasard. Testé sur faux robot.

## 1. Demande floue → une question courte
- Il manque le lieu ou l'objet (« va là-bas », « prends ça ») : « Où dois-je aller ? », « Quel objet ? ».
- Deux choix possibles (« la cuisine ou la table », « prends et pose ») : « Vous voulez dire : cuisine, table ? ».
- Le cerveau à règles le fait déjà. **Filet pour tous les cerveaux** (`filet_plusieurs_choix`, dans la chaîne) :
  si la phrase nomme deux lieux, deux objets ou deux gestes pour une seule action, c'est une question, même si un
  modèle de langue a choisi l'un des deux avec assurance. Idée de KnowNo (de mémoire, **à vérifier**) : s'il reste
  plus d'un choix possible, on demande. Pas de calcul de probabilités ici : on compte les choix nommés.

## 2. Il bute → il lève la main
Trois cas : **deux « pas compris » de suite** pour la même personne (une question entre deux ne remet pas à zéro ;
une demande comprise, si) ; **deux échecs de suite** (action ratée, ou robot qui refuse / ne répond plus) ;
un verdict **« humain »** du gardien (brique 7).
- À voix haute, dans la langue : « Je lève la main : j'ai besoin d'aide. » (de : « Ich hebe die Hand… »).
- Signal pour l'écran : événement `aide_demandee` (raison, phrases pas comprises ou échecs, n° de demande).
- Compteurs de la fiche (`/api/fiche`) : `questions_posees`, `aides_demandees`, `aides_recues`.
- Interrupteur `reglages.yaml → interrupteurs → main_levee` (éteint : plus de main levée quand il bute ;
  le verdict « humain » du gardien, lui, reste toujours allumé).

## 3. Un humain l'aide → il s'en souvient
- Accepter ou refuser une demande du gardien : `POST /api/aide/repondre` {numero, accepte, qui}.
- Apprendre un mot : `POST /api/aide/apprendre` {mot: "frigo", langue: "fr", sens: "cuisine", qui}.
  Le mot va dans `journal/aides_apprises.yaml` (HORS du dépôt suivi par git : `journal/` est ignoré ; seulement
  des mots, jamais de prénom) et dans le monde : le cerveau le comprend tout de suite, et à chaque démarrage
  (chaque mot est alors revérifié). L'ancien fichier du dépôt (`briques/b08_doute/aides_apprises.yaml`) est relu
  une fois s'il contient des mots, puis vidé.
  Refusé s'il est mal écrit : seulement des lettres (avec accents), espaces, « - », « ' » et caractères chinois
  (pas de chiffre, pas de « < » « > », rien d'invisible ni qui inverse le texte) ; 3 lettres à 40 caractères,
  4 mots au plus ; en chinois, au moins deux caractères.
  Refusé s'il prête à confusion : il contient, ou se cache dans, un « stop », un mot d'action, un « oui » / « non »,
  une négation, ou un nom d'un autre lieu ou objet (« la table » ne peut pas vouloir dire la cuisine).
  « Contient » = mot entier (langues à espaces), morceau de texte (chinois), comme le cerveau à règles lit.
- Chaque aide reçue est gardée : événement `aide_recue` dans la boîte noire (avec `qui`).
- Voir ce qui attend : `GET /api/aides` (demandes du gardien + mots appris). Boutons protégés par le code d'équipe.

## Fichiers
| Fichier | Rôle |
|---|---|
| `doute.py` | la main levée (compteurs) et le filet « deux choix » |
| `aides_apprises.py` | les mots appris, vérifiés, gardés dans `journal/aides_apprises.yaml` |
| `aides_apprises.yaml` | ancien emplacement, vide (relu une fois s'il reste des mots) |
| `demandes_floues.yaml` | les 20 demandes floues d'essai (6 langues) |

## Tester
`python3 lancer.py tests briques/b08_doute` — les 20 demandes floues donnent 20 questions et aucune action ;
la main levée ; « frigo » appris puis compris au démarrage suivant.
