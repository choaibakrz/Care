# Brique 14 — Petites tâches

## Avant samedi
- [ ] **Feu orange, Hiba** : enregistrer le serveur dans l'assistant de code sur le Mac de la démonstration (commande dans
      `GUIDE.md`), puis une vraie séance : « regarde la carte », « va à la table », accepter sur l'écran, « stop ».
      Noter ce qui se passe (jamais essayé dans une vraie session de l'assistant de code).
- [ ] Répéter la démonstration du jury (`GUIDE.md`, 7 étapes) sur le faux robot, avec l'écran du jury ouvert.
- [ ] Sur Mac : `pip install -r requirements.txt` (ajoute `mcp` 2.3.0 et ses dépendances, ~6 Mo), puis
      `python3 lancer.py tests briques/b14_porte_agents`.
- [ ] Décider (Hiba) : `accord_humain` reste allumé pendant la démonstration, ou éteint pour montrer l'agent seul ?

## Améliorer
- [ ] **Version HTTP locale**, dans le MÊME programme que l'écran principal (`python3 lancer.py`) : un seul système,
      une seule liaison avec le robot. Monter le serveur MCP (« streamable HTTP » du paquet `mcp`) sous `/mcp`, protégé
      par le code d'équipe (`controle_acces` de `serveur.py`), et refuser toute page venue d'un autre site.
      Obligatoire avant tout vrai robot : aujourd'hui, `porte-agents` crée son propre système (faux robot seulement).
- [ ] Écran (brique 13) : un badge « agent » quand la source commence par `agent:` ; une ligne simple pour
      `porte_agents` dans `flux_simple.py` (aujourd'hui son texte est vide) ; afficher qui a demandé une aide.
- [ ] Une limite pour les lectures (`voir_etat` en boucle) si un agent appelle trop vite (aujourd'hui : sans limite).
- [ ] Plusieurs agents en même temps (une porte par agent, ou une limite par nom).
- [ ] L'agent peut attendre la réponse d'un humain (aujourd'hui : il suit avec `voir_etat`).
- [ ] Faire relire par le relecteur sécurité le petit ajout dans `briques/b07_gardien/gardien.py` (accord humain pour les agents).
