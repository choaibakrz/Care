# Brique 4 — Les oreilles et la voix (guide d'une page)

**Rôle** : comprendre et parler en plusieurs langues, sans Internet. Testé sur faux robot, sur Linux (processeur seul).

## Essayer
```bash
python3 lancer.py micro                              # parler au faux robot avec le micro du Mac
python3 lancer.py micro --declenchement bouton       # touche Entrée (ou bouton « 🎙 Je parle » de l'écran)
python3 lancer.py micro --declenchement mot_d_appel  # dire « robot » d'abord
python3 lancer.py micro --fichier essai.wav          # sans parler : un enregistrement à la place du micro
python3 lancer.py banc-voix                          # mesures : calme / foule, temps de réponse
python3 lancer.py enregistrer gsw --prenom Hiba      # enregistrer des ordres de l'équipe (restent sur le Mac)
```
Conseil : un casque ou un micro-cravate, pour que le robot ne s'entende pas lui-même.

## Le chemin d'une phrase
```
micro → fin_de_parole.py → ecoute.py → (chaîne : cerveau → gardien → robot) → voix.py → haut-parleur
```
| Fichier | Rôle |
|---|---|
| `fin_de_parole.py` | détecteur de voix (Silero, 1,2 Mo) : début, fin (600 ms de silence), durée max 15 s |
| `ecoute.py` | parole → texte + langue + confiance ; vocabulaire du robot pour les ordres courts ; suisse allemand |
| `branchements/ecoute_*.py` | faster-whisper (testé), mlx-whisper et whisper.cpp (Mac, non testés) |
| `voix.py`, `branchements/voix_*.py` | texte → son : Piper par sherpa-onnx, voix du Mac, ou sous-titres seuls |
| `conversation.py` | la boucle : mot d'appel, bouton, interruption, temps de réponse |
| `peripheriques.py` | micro et haut-parleur (vrais sur Mac, faux pour les tests) |
| `mots_du_pays.yaml` | noms de lieux et mots du Valais ; mots typiques du suisse allemand |

## Règles de comportement
- **Langue** : reconnue sur la phrase, choisie parmi fr, de, gsw, it, en, zh. Réponse dans la même langue.
  Suisse allemand : compris (comme de l'allemand), réponse en allemand, et le robot le dit une fois.
- **« Stop » passe avant tout** : dans tous les modes (même sans mot d'appel ni bouton), même peu sûr, même pendant
  une question. Il annule aussi les phrases plus anciennes pas encore traitées.
- **Confiance basse** (moins de 0,5) : le robot fait répéter au lieu de deviner (sauf « stop »).
- **Actions à risque** (`confirmation.actions` dans `reglages.yaml`, par défaut saisir et poser) :
  le robot répète l'ordre et attend un « oui » net : réponse courte, sans négation, de la même source (micro ou
  clavier), bien entendue, dans les 20 s. Un arrêt d'urgence efface la question. Sinon : rien.
- **Écho** : le robot ignore ce qui ressemble à ce qu'il vient de dire, et ce qui commence pendant qu'il parle
  (sauf s'il a été interrompu). Un casque reste le plus sûr.
- **Modes** : « bouton » n'écoute que pendant l'appui (relâché tout seul après 15 s) ; « mot_d_appel » ignore ce qui
  n'est pas adressé au robot. Dans les deux, « stop » est toujours entendu.
- **Langue gardée** : la langue de la personne précédente est essayée d'abord (plus rapide), acceptée seulement si
  l'écoute est très sûre (0,75) ; sinon la langue est reconnue normalement. Mettre `garder_langue_s: 0` en mode interprète.
- **Annonce** avant d'agir (« Je vais à : cuisine »), puis « C'est fait » ou l'explication de l'échec.
- **Interruption** : si la personne parle 300 ms pendant que le robot parle, il se tait.
- **Mode lent et clair** : `voix.lent: true`.
- **Sans voix pour une langue** : la réponse s'affiche à l'écran (sous-titres), le robot ne reste jamais muet sans le dire.

## Ajouter une langue
Voir `TACHES.md` (« ajouter une langue ») : `commun/langues.yaml`, `commun/phrases.yaml`, `commun/oui_non.yaml`,
noms dans `commun/monde.yaml`, verbes dans `briques/b06_cerveau/branchements/regles_lexique.yaml`, une voix.

## Tester
```bash
python3 lancer.py tests briques/b04_oreilles_voix
```
