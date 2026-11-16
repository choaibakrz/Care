# Brique 2 — Le faux robot (guide d'une page)

**Rôle** : un robot imaginaire, pour que 35 personnes travaillent sans matériel. Il respecte la prise universelle.

## Le lancer
```bash
python3 lancer.py                 # humanoïde
python3 lancer.py --robot bras    # bras fixe sur la table
python3 lancer.py --robot chien   # chien rapide, sans main
```
Ouvrir `http://localhost:8000` : vue de dessus, robot (rond noir), objets (points orange), lieux (rectangles).

## Les trois cartes (`cartes/`)
| Carte | Sait faire | Ne sait pas |
|---|---|---|
| humanoïde | tout | — |
| chien | se déplacer, regarder, écouter, parler, gestes | saisir, poser, montrer |
| bras | regarder, saisir, poser, montrer, gestes | se déplacer, écouter, parler |

Les chiffres des cartes sont inventés pour la simulation.

## Les pannes d'entraînement (boutons de l'écran, ou `provoquer_panne()`)
| Panne | Effet |
|---|---|
| `lenteur` | répond et bouge 4 fois plus lentement |
| `refus` | refuse toute nouvelle action |
| `perte_liaison` | ne répond plus ; son chien de garde l'arrête en 0,6 s |
| `batterie_faible` | batterie à 5 % |
| `arret_ignore` | ignore l'arrêt d'urgence logiciel : l'écran demande le bouton physique |

`reparer()` (bouton « réparer ») enlève toutes les pannes.

## Le monde
Lieux et objets : `commun/monde.yaml`, avec leurs noms en 6 langues. Samedi : y mettre les vrais lieux.

## Tester
```bash
python3 lancer.py tests briques/b02_faux_robot
```
