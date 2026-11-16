# La fiche de vérité et le rejeu (cahier 5.11)

Un guide d'une page. Données inventées. Rien n'a été essayé sur un vrai robot ni avec de vrais patients.

## Rôle
La fiche de vérité dit ce qui est vrai : données inventées, robots simulés, temps accéléré, part de l'humain, phrases
retirées, taux d'erreur, et les chiffres des avenants. Tout est compté, rien n'est tapé. Le rejeu autonome est un
dossier de pages qui racontent une répétition (étapes, fiche, moments), ouvert par un double-clic, sans serveur. Il ne
remontre pas les écrans et ne rejoue pas le temps. Jamais mis en ligne sans l'accord de Hiba.

## Fichiers
- `briques/clinique/fiche.py` et `briques/clinique/ecrans_fiche.py` : la fiche, et la page `/clinique/fiche-de-verite`.
- `briques/clinique/rejeu_autonome.py` : le dossier du rejeu (par défaut dans `journal/`).
- `briques/clinique/moments.py` : les moments marquants d'une séance.
- `briques/clinique/rien_dehors.py` : pendant une répétition, compte (et bloque) les connexions de ce programme vers l'extérieur.

## Lancer et voir
`python3 lancer.py repetition` : la fiche s'affiche à l'étape 13 et est gardée pour la page.
`python3 lancer.py rejeu-autonome` : le dossier du rejeu, vérifié.
`python3 lancer.py moments` : les moments d'une séance.

## Les essais
`python3 lancer.py tests briques/clinique/tests/test_fiche_complete.py`, `python3 lancer.py tests briques/clinique/tests/test_fiche_et_rien_dehors.py`, `python3 lancer.py tests briques/clinique/tests/test_rejeu_autonome.py`, `python3 lancer.py tests briques/clinique/tests/test_moments.py`.

## Ce qui n'est pas testé
- Les chiffres viennent du faux robot et de robots simulés. La fiche n'est pas écrite dans la boîte noire.
- « Rien n'est sorti » surveille ce programme seulement, pendant la répétition : pas le serveur du modèle, pas le navigateur, pas la démonstration avec les écrans.
- « Réussis du premier coup : 12 sur 12 » compte des étapes, pas des gestes de robot. La page montre la dernière répétition, pas la séance en cours.
- Le dossier du rejeu n'a pas été ouvert sur un autre ordinateur.

Les petites tâches : `TACHES.md`, dans ce dossier. Avant de dire « fini » : `python3 lancer.py tests` passe.
