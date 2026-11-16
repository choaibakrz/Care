# Brique 6 — Le cerveau (guide d'une page)

**Rôle** : comprendre la demande et choisir UNE action de la carte d'identité, ou poser UNE question. Il ne commande
jamais les moteurs : le gardien vérifie, la prise exécute. Testé sur faux robot, sur Linux.

## La cascade (reglages.yaml → cerveau)
```
(option, éteinte) Apertus par Internet  →  Apertus 8B (sur le Mac)  →  Apertus 4B (secours)  →  cerveau à règles
```
- Trop lent (6 s par défaut), éteint, ou réponse hors formulaire : on passe au suivant, noté dans la boîte noire
  (`cerveau_secours`). Le cerveau en échec est mis de côté 30 s.
- Le 4B est lancé « au besoin » : il n'occupe la mémoire que si le 8B tombe.
- Le cerveau à règles est toujours le dernier : il ne dépend de rien.

## Le formulaire (`formulaire.py`)
La seule réponse permise : `{"type":"action", "action": <de la carte>, "parametres": {...}}` ou
`{"type":"question", "question": "..."}`. Avec llama.cpp, le modèle est FORCÉ de le suivre (grammaire) ; sinon
la réponse est vérifiée et refusée si elle ne le suit pas. Lieux, objets, gestes : seulement ceux du monde et de la carte.

## Cinq filets de sécurité, indépendants du modèle
1. **Formulaire** : aucune action hors carte, aucun lieu ou objet inventé, aucun paramètre inconnu.
2. **Rien d'inventé** : lieu, objet, distance ou geste que la personne n'a pas dits → question.
3. **Verrou des chiffres** (dans la chaîne) : une vitesse, une distance ou une force dite en chiffres est recopiée dans
   l'action (en gardant le sens choisi), même si le modèle l'a oubliée → le gardien refuse et explique.
4. **Négation** : « ne va pas… » → question (sauf « ne bouge pas » = stop).
5. **Stop d'abord** : un « stop » arrivé pendant que le cerveau réfléchit annule sa réponse.

## Commandes
```bash
python3 lancer.py cerveau                 # lancer Apertus sur ce Mac (8B ; 4B au besoin)
python3 lancer.py cerveau --partager      # sur l'iMac : joignable par le MacBook (mettre son adresse dans reglages.yaml)
python3 lancer.py banc-cerveau            # 30 demandes × 6 langues pour chaque cerveau
python3 outils/banc_cerveaux_mac.py       # chaque Apertus, un à la fois (lancé par preparer_mac.sh)
```

## Fichiers
| Fichier | Rôle |
|---|---|
| `prise_cerveau.py` | la forme commune (`Decision`) et le filet « jamais hors carte » |
| `formulaire.py` | le formulaire, les instructions et les exemples donnés au modèle, les vérifications |
| `branchements/llm.py` | Apertus par un serveur compatible OpenAI (llama.cpp, mlx-lm, service en ligne) |
| `branchements/cascade.py` | le passage automatique au cerveau de secours |
| `branchements/regles.py` | le cerveau à règles (mots-clés), et la lecture des chiffres |
| `serveurs.py` | lancer et arrêter les modèles sur cet ordinateur |
| `banc_cerveau.py`, `banc_demandes.yaml` | le banc d'essai (dont 12 demandes pièges) |
