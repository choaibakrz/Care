# Le faux dossier (cahier 5.1)

Un guide d'une page. Données inventées. Rien n'a été essayé sur un vrai robot ni avec de vrais patients.

## Rôle
Il tient lieu de logiciel de la clinique : douze patients inventés, leurs séjours, programmes, documents, listes de soin,
plus les lieux et la réserve. Les noms des choses reprennent les mots de FHIR R4 (Patient, Encounter, DocumentReference…),
sans serveur. Chaque fichier porte la marque « inventé » ; sinon le dossier refuse de se charger.

## Fichiers
- `briques/clinique/dossier.py` : la lecture, et le refus d'un fichier sans la marque « inventé ».
- `briques/clinique/faux_dossier/patients/` : un fichier par patient (12).
- `briques/clinique/faux_dossier/lieux.yaml`, `briques/clinique/faux_dossier/reserve.yaml`, `briques/clinique/faux_dossier/listes_de_soin.yaml`, `briques/clinique/faux_dossier/feuilles_sans_patient.yaml`.
- `briques/clinique/sources_des_donnees.yaml` et la page `/clinique/sources` : d'où vient chaque donnée.

## Lancer et voir
Personne ne lit ces fichiers directement : tout passe par la porte de lecture (guide 02).
Pour les voir : ouvrir les fichiers YAML, ou la page `/clinique/sources` avec `python3 lancer.py`.

## Les essais
`python3 lancer.py tests briques/clinique/tests/test_faux_dossier.py` (chargement, marque, les trois cas voulus du cahier 6.2), `python3 lancer.py tests briques/clinique/tests/test_sources_des_donnees.py`.

## Ce qui n'est pas testé
- Inspiré de FHIR, non validé ; aucun lien avec un vrai logiciel de clinique n'a été essayé.
- Les textes en allemand, italien, anglais et portugais n'ont pas été relus par quelqu'un qui parle la langue.
- Les noms « Exemple » sont contrôlés par l'essai, pas par `dossier.py`.

Les petites tâches : `TACHES.md`, dans ce dossier. Avant de dire « fini » : `python3 lancer.py tests` passe.
