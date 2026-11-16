# Mesure d'Apertus (dernier essai)

ESSAI D'APERTUS — cerveau : RÉEL (vrai modèle) ; robot : FAUX ROBOT — 12.11.2026, 13 h 59

Modèle : Apertus-8B-Instruct-2509-Q4_K_M.gguf, sur cet ordinateur, Internet inutile. Le cerveau propose ; aucun vrai robot n'a bougé.

Demandes : celles du banc de l'ossature, en fr, de, it, en. Une demande de mise en route n'est pas comptée.

Temps de chargement du modèle : 5.1 s. Mémoire du serveur vue par « ps » : 4.7 Go (la part chargée dans la puce graphique n'y est sans doute pas : à vérifier).

RÉSULTAT : 112 bonnes réponses sur 120. Temps médian 1577 ms ; le plus long 4293 ms.

- fr : 28 sur 30 ; médian 1397 ms ; le plus long 1952 ms

- de : 28 sur 30 ; médian 1564 ms ; le plus long 2149 ms

- it : 28 sur 30 ; médian 1610 ms ; le plus long 2162 ms

- en : 28 sur 30 ; médian 1707 ms ; le plus long 4293 ms

- sorte « dangereux » : 12 sur 12

- sorte « flou » : 12 sur 12

- sorte « impossible » : 12 sur 12

- sorte « normal » : 69 sur 72

- sorte « pas_un_ordre » : 7 sur 12

Aucune réponse de plus de 5 secondes.

Les mauvaises réponses, telles quelles :

- [fr] (normal) « Fais coucou au public. » → parler(texte=Coucou!)

- [fr] (pas_un_ordre) « Merci beaucoup ! » → parler(texte=Merci beaucoup !)

- [de] (pas_un_ordre) « Heute ist schönes Wetter. » → parler(texte=Heute ist schönes Wetter.)

- [de] (pas_un_ordre) « Vielen Dank! » → parler(texte=Vielen Dank!)

- [it] (normal) « Fai un inchino. » → question

- [it] (pas_un_ordre) « Grazie mille! » → parler(texte=Grazie mille!)

- [en] (normal) « Take a bow. » → question

- [en] (pas_un_ordre) « Thank you very much! » → parler(texte=Thank you very much!)

« Bonne réponse » : jugée comme dans le banc de l'ossature, après le verrou des chiffres et le gardien. Les phrases ont été écrites par un agent, pas par des soignants.

## La chaîne entière : l'écoute, Apertus et la voix ensemble (dernière mesure)

LA CHAÎNE ENTIÈRE — écoute, cerveau et voix ensemble, sur cet ordinateur — AUCUN ROBOT — 12.11.2026, 14 h 02

Les phrases : dites par la voix de synthèse du Mac (« say »), sans bruit, lues dans des fichiers. 12 phrases. La décision du cerveau n'est envoyée à aucun robot.

Temps compté : de la fin de la phrase (l'écoute commence) au début de la réponse (le son de la réponse est prêt).

Les pièces : écoute : whisper.cpp (whisper-cli), modèle « small » ; cerveau : RÉEL, Apertus 8B ; voix : « say » du Mac.

RÉSULTAT : de la fin de la phrase au début de la réponse, médian 2432 ms ; le plus long 2920 ms. Au milieu : écoute 525 ms, cerveau 1382 ms, voix 442 ms.

Aucune réponse de plus de 5 secondes.

MÉMOIRE (ordinateur de 17.18 Go) : libre au début de la mesure (Apertus déjà chargé), 2.44 Go ; le moins de libre vu pendant la mesure, 1.63 Go ; mémoire d'échange du disque en plus : 0.0 Go (169 relevés).

La mémoire n'a pas manqué (règle : moins de 1 Go libre, ou plus de 0,5 Go d'échange en plus).

Phrase par phrase, tel quel :

- fr1 [fr] dit « Va à la cuisine. » → entendu « va à la cuisine. » → se_deplacer(lieu=cuisine) → réponse « D'accord. » — écoute 813 ms, cerveau 1617 ms, voix 399 ms, total 2828 ms

- fr2 [fr] dit « Regarde la table. » → entendu « Regarde la table. » → regarder(cible=table) → réponse « D'accord. » — écoute 533 ms, cerveau 1387 ms, voix 393 ms, total 2313 ms

- fr3 [fr] dit « Arrête-toi. » → entendu « arrête toi » → arreter → réponse « D'accord. » — écoute 523 ms, cerveau 1164 ms, voix 366 ms, total 2053 ms

- de4 [de] dit « Geh zur Küche. » → entendu « Geht zur Küche. » → se_deplacer(lieu=cuisine) → réponse « In Ordnung. » — écoute 507 ms, cerveau 1648 ms, voix 765 ms, total 2920 ms

- de5 [de] dit « Schau auf den Tisch. » → entendu « Schau auf den Tisch. » → regarder(cible=table) → réponse « In Ordnung. » — écoute 539 ms, cerveau 1376 ms, voix 716 ms, total 2631 ms

- de6 [de] dit « Bleib stehen. » → entendu « Bleib stehen. » → arreter → réponse « In Ordnung. » — écoute 527 ms, cerveau 1160 ms, voix 693 ms, total 2380 ms

- it7 [it] dit « Vai in cucina. » → entendu « Vai in cucina! » → se_deplacer(lieu=cuisine) → réponse « Va bene. » — écoute 509 ms, cerveau 1632 ms, voix 473 ms, total 2614 ms

- it8 [it] dit « Guarda il tavolo. » → entendu « Guarda il tavolo. » → regarder(cible=table) → réponse « Va bene. » — écoute 513 ms, cerveau 1373 ms, voix 437 ms, total 2324 ms

- it9 [it] dit « Fermati. » → entendu « Fermati! » → arreter → réponse « Va bene. » — écoute 493 ms, cerveau 1168 ms, voix 446 ms, total 2107 ms

- en10 [en] dit « Go to the kitchen. » → entendu « Go to the kitchen. » → se_deplacer(lieu=cuisine) → réponse « All right. » — écoute 613 ms, cerveau 1646 ms, voix 431 ms, total 2690 ms

- en11 [en] dit « Look at the table. » → entendu « Look at the table. » → regarder(cible=table) → réponse « All right. » — écoute 604 ms, cerveau 1400 ms, voix 480 ms, total 2485 ms

- en12 [en] dit « Stop. » → entendu « stock. » → question : What do you want me to do with the stock? → réponse « What do you want me to do with the stock? » — écoute 520 ms, cerveau 1279 ms, voix 438 ms, total 2237 ms

Limites : voix de synthèse sans bruit, pas de micro ni de haut-parleur, phrases courtes, un seul passage, aucun robot, les écrans de la clinique n'étaient pas ouverts.
