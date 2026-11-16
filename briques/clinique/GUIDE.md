# La clinique en boîte (guide d'une page)

**Rôle** : montrer, en miniature, « une clinique, un cerveau, plusieurs robots ». Tout se joue sur le faux robot,
avec un faux dossier. **Données inventées. Pas de médecine.** Rien n'a été essayé sur un vrai robot.

Le cahier (ce qu'on construit, les règles) : `docs/projet/CAHIER_CLINIQUE.md`. L'avenant pour le jury : `docs/projet/AVENANT_JURY.md`.
Où on en est : `docs/projet/SUIVI_CLINIQUE.md`. Ce qui reste : `TACHES.md`, dans ce dossier.
Un guide d'une page et de petites tâches pour chaque pièce : `guides/LISEZ_MOI.md` (tâche T32).

## Lancer
```bash
python3 lancer.py verif-rapide     # les vérifications courtes, moins de deux minutes
python3 lancer.py repetition       # la grande répétition : sept scènes (scenario_clinique.yaml), quatorze étapes, une ligne par étape
python3 lancer.py tests            # toutes les vérifications, longues comprises (environ 3 minutes)
python3 lancer.py                  # les écrans : l'adresse à ouvrir sur un téléphone s'affiche (…/clinique)
python3 -m briques.clinique.essai_reseau   # les pages répondent-elles à l'adresse du Wi-Fi ?
```

## La vérification rapide
Elle lance les vérifications de l'ossature et de la clinique, sauf les essais longs de l'ossature (liste mesurée :
`essais_longs.txt`). Elle finit par une ligne : `VÉRIFICATION RAPIDE : 58 réussies, 0 ratée`.
Elle dit aussi combien d'essais sont sautés (une pièce absente de la machine) et combien sont laissés de côté.

## La grande répétition
Elle joue le scénario entier, étape par étape. Chaque ligne porte une étiquette : RÉEL, FAUX ROBOT, SIMULÉ ou JOUÉ.
Elle finit par `RÉPÉTITION : RÉUSSIE` ou `RÉPÉTITION : RATÉE — (ce qui manque)`.
- Une pièce pas encore construite compte comme ratée. C'est normal.
- Une étape sautée ou sans étiquette compte comme ratée. La répétition ne triche pas.

## Ajouter une pièce (pour l'équipe)
1. Écrire la pièce dans ce dossier, avec ses essais dans `tests/`.
2. Dans `repetition.py`, ajouter son contrôle dans `CONTROLES` : le numéro de l'étape, et une fonction qui joue
   l'étape à travers les vraies pièces et rend `Resultat(réussie, étiquette, détail)`.
3. Tout ordre au robot passe par le gardien. Rien d'autre.
4. Lancer `python3 lancer.py verif-rapide`, puis `python3 lancer.py repetition`.

## État (11.11.2026)
Le squelette (les deux commandes) et le faux dossier (`faux_dossier/`, lu par `dossier.py` : 12 patients inventés,
3 listes de soin d'exemple, les lieux, la réserve), la porte de lecture (`porte.py` : huit badges, journal des accès,
aucune écriture), l'horloge de démonstration (`horloge.py` : sauts « le soir », « le lendemain matin », marque
« temps accéléré », notée par `fiche.py`), les écrans (`ecrans.py` : patient, soignant, médecin, accueil,
thérapeute, journal des accès ; ils montrent ce que la porte donne, rien ne s'écrit encore), le carnet (`carnet.py` :
tout ce que le prototype crée) et la logique des listes de soin (`listes.py` : cocher, « je sors », fin de poste,
comptes de la direction), avec ses pages (`ecrans_listes.py` : ouvrir une liste, cocher au doigt, « je sors », fin de
poste, point de prise de poste, page de la direction). Le tableau des tâches (`taches.py` : demande claire, demande floue → question, objet absent → un humain) et le
coursier (`coursier.py` : le faux robot va de la réserve à la chambre, chaque geste sous le gardien ; la livraison
coche le point en attente). Le résumé du médecin, version simple (`resume.py`, `ecrans_resume.py` : cinq lignes au plus par
patient, par des règles, sans modèle ; chaque ligne ouvre sa source ; « deux sources ne sont pas d'accord » ; « rien de
nouveau » ; la recherche d'un document). Les papiers, version simple (`papiers.py`, `ecrans_papiers.py` : à partir du
texte de référence, par des règles, une proposition de rangement — type, date, auteur, patient, endroit, confiance ;
l'accueil valide d'un doigt ; la validation va au carnet ; la feuille sans nom reste « à trier »).
L'accueil du hall, version écrite (`accueil.py`, `accueil_hall.yaml`, `ecrans_accueil.py` : la phrase d'arrivée est
tapée ; réponse en italien, allemand, français ou anglais avec la chambre, l'étage, la première heure et le chemin ;
message à l'étage ; rien sur la santé dans le hall ; nom inconnu → un humain est appelé).
Répétition : étapes 1 à 7 et 10 (SIMULÉ) et 8 (FAUX ROBOT) réussies, 5 manquent.
