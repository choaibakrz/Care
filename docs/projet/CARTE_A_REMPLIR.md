# La carte à remplir — pour un robot que personne n'a prévu

Une page à imprimer. On pose les questions à la personne du fabricant, dans cet ordre, et on écrit ses réponses.
Puis on recopie dans un fichier `briques/b02_faux_robot/cartes/NOM.yaml` (modèle : `plateau.yaml`). Voir `BRANCHER_UN_ROBOT.md`.
Tant que le robot n'a pas été essayé, la carte garde la marque : « PRÉPARÉE SANS LE ROBOT — non testé sur vrai robot ».

**D'abord, la sécurité**
- Que fait le robot quand on appuie sur l'arrêt (il se fige, il s'assoit, il tombe) ? ______________________________
- Où est le bouton d'arrêt qui coupe le courant ? Qui le tient ? ______________________________

**Qui est-il**
- `id` (un mot court, sans espace) : ________________    `nom` : ________________________
- `genre` (humanoide, chien, bras, roues, autre) : ____________
- `fabricant` : ________________    `modele` et version (celle qu'on peut programmer ?) : ________________

**Ce qu'il sait faire** — `capacites` : entourer seulement ce qui a été vu
se_deplacer · regarder · ecouter · parler · saisir · poser · montrer · rejouer_geste · arreter (toujours) · etat (toujours)

**Ses limites** — `limites` : écrire le chiffre, et d'où il vient
- `vitesse_max_m_s` (mètres par seconde) : ________    pour la démonstration, plus lent : ________
- `portee_max_m` (longueur du bras ; 0 sans bras) : ________
- `charge_max_kg` (par bras, ou sur le plateau, le panier) : ________
- `force_max_n` (serrage de la main ; 0 sans main) : ________

**Ses gestes enregistrés** — `gestes` : ______________________________

**Le reste** — `remarques` : tout ce qui n'a pas de case
- Taille : ________  Poids : ________  Batterie (durée, recharge) : ________
- Mains ou pinces ? Que peut-il saisir ? ______________________________
- Peut-il tomber ? Lui faut-il un support ou une sangle ? ______________________________
- Distance à garder avec les personnes : ________  Escalier, ascenseur : ________
- Peut-on le télécommander ? Avec quoi, et qui en a le droit ? ______________________________
- Micro et haut-parleur : les siens ou les nôtres ? ______________________________

Rempli par : ________________  avec : ________________  le : ____________  à : ________
