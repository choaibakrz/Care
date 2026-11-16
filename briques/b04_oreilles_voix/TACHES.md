# Brique 4 — Petites tâches

Chaque tâche : une personne, moins d'une heure, avec son test.

## Avant samedi (sur les Mac)
- [ ] Lancer `python3 lancer.py banc-voix` sur l'iMac et le MacBook ; envoyer les fichiers `mesures/voix_*.md`.
- [ ] Choisir le moteur d'écoute le plus rapide sur Mac (`voix.ecoute.moteur` : mlx_whisper ou whisper_cpp) et le modèle (small ou large-v3-turbo).
- [ ] `say -v '?'` sur chaque Mac : noter les voix disponibles (fr, de, it, en, zh, de_CH ?) dans `branchements/voix_mac_say.py`.
- [ ] 3 personnes enregistrent les ordres en suisse allemand : `python3 lancer.py enregistrer gsw --prenom …`, puis banc-voix.
- [ ] Mesurer l'interruption avec le haut-parleur du Mac (le robot s'entend-il ?) ; régler `interruption_ms` ou utiliser un casque.

## Fonctions
- [ ] « Deux mots suffisent » (idée 1) : décider la langue sur la première seconde et demie, puis écouter la suite dans cette langue (le banc mesure déjà la justesse sur 1,5 s).
- [ ] Mode interprète (idée 2) : deux personnes, deux langues ; traduction par le cerveau (étape 3).
- [ ] Mot d'appel en suisse allemand et en italien ; mesurer les faux réveils pendant 10 minutes de bruit de foule.
- [ ] Afficher la langue et la confiance en direct sur l'écran du jury (étape 4).
- [ ] Mode silence (idée 14) : `voix.parole.moteurs: []` → tout passe par les sous-titres et les pictogrammes.
- [ ] Bouton « lent et clair » sur l'écran.
- [ ] Option suisse allemand : essayer le modèle Flix-AI (3,09 Go, Apache-2.0) converti pour Mac — feu orange (taille).

## Ajouter une langue (exemple : espagnol)
- [ ] `commun/langues.yaml` : une ligne. `commun/phrases.yaml` : copier le bloc « fr » et traduire.
- [ ] `commun/oui_non.yaml`, `commun/monde.yaml` (noms des lieux et objets), `regles_lexique.yaml` (verbes).
- [ ] Une voix : vérifier sa licence ET celle de la voix dont elle est tirée ; l'ajouter à `outils/catalogue.yaml`.
- [ ] Ajouter 12 phrases d'essai dans `donnees_voix/` ; lancer le banc.
