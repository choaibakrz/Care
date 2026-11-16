# Carnaval — l'ossature du robot

Une personne parle au robot dans sa langue. Le robot comprend, vérifie que c'est sans danger, agit ou demande de
l'aide, répond dans la même langue, et tout est gardé en mémoire. Avec n'importe quel robot, sans Internet.

**État : testé sur faux robot, et sur un seul vrai robot** (une main Leadtron DH116, le 15.11.2026). Le détail : `NON_TESTE.md`.

## Lancer (une commande)

Sur un Mac de l'équipe, la première fois :

```bash
./preparer_mac.sh
```

Il vérifie la machine, installe ce qu'il faut **après votre « oui »**, lance les tests, télécharge les modèles
**après votre « oui »** et mesure les vitesses. Il ne fait jamais bouger de robot.

Ensuite, chaque fois :

```bash
python3 lancer.py
```

Puis ouvrir `http://localhost:8000`. Les autres membres de l'équipe, sur le même Wi-Fi, ouvrent
`http://<adresse-du-mac>:8000` : rien à installer pour eux.

Pour que l'équipe puisse parler au robot depuis le Wi-Fi, choisir un code d'équipe dans `reglages.yaml`
(`ecran.code_equipe`). Sans code, seuls les boutons de l'ordinateur-cerveau marchent. Le bouton **ARRÊT** marche partout.

Changer de faux robot : `python3 lancer.py --robot bras` (ou `chien`, `humanoide`).

## Tester

```bash
python3 lancer.py tests
```

Tous les tests tournent avec Internet coupé pour le programme. Avant de dire « c'est fini », ils doivent tous passer.

```bash
python3 lancer.py demo
```

Une petite démonstration dans le terminal, puis la fiche de vérité.

```bash
python3 lancer.py rejouer
```

Rejoue la dernière session enregistrée dans la boîte noire (dossier `journal/`).

## Comment c'est rangé

| Dossier | Contenu |
|---|---|
| `briques/b01_prise` | la prise universelle : les actions, la carte d'identité, le ticket |
| `briques/b02_faux_robot` | le faux robot et ses trois cartes |
| `briques/b06_cerveau` | le cerveau (pour l'instant : « à règles », sans modèle) |
| `briques/b07_gardien` | le gardien (version 0) |
| `briques/b12_boite_noire` | journal, fiche de vérité, rejeu |
| `briques/b13_ecran` | l'écran (version minimale) |
| `commun/` | la chaîne, le bus, les langues, les phrases, le monde (lieux et objets) |
| `outils/` | téléchargement des modèles, mesures |
| `reglages.yaml` | tous les réglages, y compris les 16 interrupteurs |

Chaque brique a un `GUIDE.md` (une page) et un `TACHES.md` (petites tâches à distribuer).

## À lire
`docs/projet/PRODUCT.md` (la promesse) · `DECISIONS.md` · `NON_TESTE.md` · `LICENCES.md` · `docs/projet/REGLES_DES_AGENTS.md` (règles) · `AGENTS.md` (rôles).
