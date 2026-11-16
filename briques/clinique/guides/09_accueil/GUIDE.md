# L'accueil (cahier 5.9)

Un guide d'une page. Données inventées. Rien n'a été essayé sur un vrai robot ni avec de vrais patients.

## Rôle
Le robot du hall reçoit une patiente dans sa langue (italien, allemand, français, anglais), lui dit sa chambre et son
programme, montre le chemin, ne l'accompagne pas, et prévient l'étage. À une question de santé : « Je transmets à
l'équipe », et un humain est appelé. Un nom inconnu appelle aussi un humain.

## Fichiers
- `briques/clinique/accueil.py` et `briques/clinique/accueil_hall.yaml` : les règles et les phrases du hall.
- `briques/clinique/ecrans_accueil.py` : les pages du hall et de l'accueil.
- `briques/clinique/accueil_voix.py` : l'accueil à la voix (écoute, réponse dite, plan B à l'écran).
- `briques/clinique/a_vous.py` et `briques/clinique/a_vous.yaml` : « À vous », le jury change la langue.

## Lancer et voir
`python3 lancer.py`, puis `/clinique/hall` : taper une phrase d'arrivée.
`python3 lancer.py accueil-voix --essai` : une phrase italienne dite par la voix de synthèse du Mac, puis la réponse (pas de micro en direct).
`python3 lancer.py a-vous --langue de` : l'arrivée en allemand, sans toucher au code.

## Les essais
`python3 lancer.py tests briques/clinique/tests/test_accueil.py`, `python3 lancer.py tests briques/clinique/tests/test_accueil_voix.py`, `python3 lancer.py tests briques/clinique/tests/test_a_vous.py`, `python3 lancer.py tests briques/clinique/tests/test_accueil_sans_texte_medical.py`.

## Ce qui n'est pas testé
- L'arrivée est tapée ; à la voix, seulement une phrase italienne de synthèse. Pas de micro en direct, pas de bruit de hall.
- Aucune preuve d'identité : qui tape « je suis Giulia B. » reçoit sa chambre. « Rien sur la santé » est une liste de mots, pas une règle du gardien.
- Le robot dit la première heure du programme, même si elle est passée. Il n'accompagne personne.

Les petites tâches : `TACHES.md`, dans ce dossier. Avant de dire « fini » : `python3 lancer.py tests` passe.
