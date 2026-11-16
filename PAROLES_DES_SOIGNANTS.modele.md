# Paroles de soignants — le modèle à remplir

Ce fichier est un MODÈLE. Il ne contient aucune parole. Un agent d'IA n'écrit jamais ce qu'un soignant a dit.

## Comment faire (une personne de l'équipe, à la main)

1. Copier ce modèle ici : `journal/clinique/PAROLES_DES_SOIGNANTS.md`.
   Ce dossier reste sur l'ordinateur : il ne part jamais vers GitHub, et git refuse ce nom de fichier partout.
2. Après un entretien (les dix questions sont dans `docs/projet/GUIDE_ENTRETIEN.md`), écrire une ligne par parole, à la main.
3. Relire chaque ligne avec la personne, si elle est encore là.

## Les quatre règles

- **Pas de nom.** Ni celui de la personne, ni celui d'un collègue, ni celui du lieu.
- **Pas un mot sur un patient.** Ni nom, ni chambre, ni histoire reconnaissable.
- **Avec son accord.** La personne a dit oui pour être citée sans son nom. Sinon, on n'écrit rien.
- **Ses mots à elle.** On recopie ce qu'elle a dit. On n'arrange pas, on n'écrit pas ce qu'elle « dirait ».

## La forme d'une ligne

Une ligne commence par un tiret. La phrase est entre guillemets français. Puis le métier, la date, l'accord.
Remplacer les trois parties entre parenthèses ; tant qu'elles y sont, la ligne ne compte pas.

- « (écrire ici la phrase) » — métier : (à remplir) — date : (à remplir) — accord : oui

Le programme met de côté, sans l'afficher, une ligne qui contient « Madame », « Monsieur », « Dr », « patient » ou
« chambre », ou un métier suivi d'un prénom. C'est un filet, pas une garantie : relire reste nécessaire.
