# Le résumé du médecin (cahier 5.7)

Un guide d'une page. Données inventées. Rien n'a été essayé sur un vrai robot ni avec de vrais patients.

## Rôle
Cinq lignes au plus par patient, chacune avec sa source (un document, la fiche du séjour, le programme, le carnet).
Une phrase sans source est retirée. Deux sources qui ne sont pas d'accord sont montrées toutes les deux. La recherche
ouvre un document. Version simple par des règles ; Apertus peut réécrire, sous un contrôle strict (sinon : version simple).

## Fichiers
- `briques/clinique/resume.py` : le résumé, les sources, « rien de nouveau ».
- `briques/clinique/ecrans_resume.py` : l'écran du médecin, les liens « Source », la recherche.
- `briques/clinique/resume_apertus.py` : la réécriture par Apertus et son contrôle.
- `docs/projet/MESURE_RESUME_APERTUS.md` : ce qu'Apertus a donné, tel quel.

## Lancer et voir
`python3 lancer.py`, puis `/clinique/medecin?badge=medecin-exemple` ; cliquer sur « Source ».
`python3 lancer.py resume-apertus` : la mesure avec le vrai Apertus (il faut le cerveau lancé).

## Les essais
`python3 lancer.py tests briques/clinique/tests/test_resume_medecin.py`, `python3 lancer.py tests briques/clinique/tests/test_resume_apertus.py`, `python3 lancer.py tests briques/clinique/tests/test_recherche_radiologie.py`.

## Ce qui n'est pas testé
- Avec le vrai Apertus, aucune ligne n'a passé le contrôle à la dernière mesure : c'est la version simple qui sert.
- « Deux sources pas d'accord » vient d'un champ écrit à la main dans le faux dossier, pas d'une lecture du texte.
- « Le dernier rapport de radiologie de Madame B. » répond « Je ne trouve pas ce document » (question Q11). Le résumé est en français seulement.
- Pas de diagnostic, jamais : le résumé recopie ce qui est écrit, avec la source.

Les petites tâches : `TACHES.md`, dans ce dossier. Avant de dire « fini » : `python3 lancer.py tests` passe.
