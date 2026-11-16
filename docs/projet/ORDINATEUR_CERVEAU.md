# L'ordinateur-cerveau

Tous les chiffres sans mesure sont des **estimations** calculées à partir de la taille des fichiers.
Les vrais chiffres viendront de `./preparer_mac.sh` (dossier `mesures/`).

## Machine minimale et machine idéale

- **Minimale** : Mac à puce Apple (M1 ou plus récent), 16 Go de mémoire, 30 Go libres sur le disque. Version de macOS minimale : **à vérifier** (dépend de MLX).
- **Idéale** : Mac à puce Apple récente (M4 Pro ou plus), 32 Go de mémoire ou plus, 100 Go libres. On peut alors garder Apertus 8B en meilleure qualité et l'écoute la plus précise.
- **Chez nous** : iMac M4 16 Go = cerveau principal (puce plus récente, probablement plus rapide : **à mesurer**) ; MacBook M2 16 Go = secours (il a une batterie, c'est un atout en cas de coupure).

## Mémoire du kit léger, tout chargé en même temps (estimation)

| Morceau | Mémoire |
|---|---|
| Apertus 8B, compressé 4 bits (fichier de 5,06 Go) | ~5,1 Go |
| Mémoire de conversation du modèle (4096 jetons : 32 couches × 8 têtes × 128 × 2 × 2 octets × 4096) | ~0,5 Go |
| Écoute Whisper « small » (fichier de 0,49 Go) | ~0,5 à 1 Go |
| 5 voix Piper (5 × 63 Mo) | ~0,3 Go |
| Programme, écran, boîte noire | ~0,3 Go (**à mesurer**) |
| **Total kit léger** | **~6,7 à 7,2 Go** |
| macOS et un navigateur ouvert | ~4 à 5 Go (**à mesurer**) |
| **Marge sur 16 Go** | **~4 Go** |

Avec Apertus v1.1 4B à la place du 8B : environ 3 Go de moins.

## Les deux cerveaux ne tournent jamais ensemble sur 16 Go

Apertus 8B (~5,6 Go) + 4B (~2,8 Go) + écoute + voix + macOS dépasseraient 16 Go. Le 8B est lancé au démarrage ;
le 4B seulement **au besoin**, si le 8B tombe (quelques secondes de chargement, pendant lesquelles le cerveau à
règles répond). Avec deux Mac : 8B sur l'iMac, 4B sur le MacBook.

## Une version plus petite d'Apertus, en secours

Vérifié sur Hugging Face le 11.11.2026 (dépôt officiel `swiss-ai`, licence Apache-2.0, sans conditions à accepter) :
- **Apertus v1.1 4B Instruct** : version officielle pour Mac (MLX, 4 bits) de 2,61 Go. Il existe aussi une version GGUF de 2,43 Go, convertie par un particulier.
- **Apertus v1.1 1.5B Instruct** : version officielle MLX 4 bits de 1,10 Go.
- **Apertus v1.1 0.5B Instruct** : 1,16 Go non compressé.
Leur qualité pour choisir la bonne action : **à mesurer** au banc d'essai (étape 3).
Apertus 1.5 8B complet fait 18,4 Go : il ne tient pas sur 16 Go.

## Deux Mac allumés : proposition de partage (à mesurer avant de décider)

```
MacBook M2 (« poste robot »)                               iMac M4 (« poste cerveau »)
  oreilles + voix + écran + boîte noire                       cerveau Apertus 8B (llama.cpp ou MLX)
  gardien + prise + adaptateur ──── Wi-Fi ou câble ────►     répond aux demandes « quelle action ? »
  cerveau de secours (Apertus 4B ou « à règles »)
```

- **Un seul Mac parle au robot** : celui où tournent le gardien, la prise et l'adaptateur. On n'a jamais deux chefs pour le même robot.
- Le cerveau est le morceau le plus lourd. Sur l'autre Mac, il ne dispute plus la puce graphique à l'écoute.
- **Si le Mac cerveau tombe**, le poste robot passe tout seul à son cerveau de secours après 2 s sans réponse (à construire à l'étape 3). Pour le robot, rien ne change : même gardien, même prise.
- **Si le poste robot tombe**, on relance `python3 lancer.py` sur l'autre Mac. L'adaptateur se reconnecte au robot ; la boîte noire repart dans un nouveau fichier. Une copie régulière du journal sur l'autre Mac est à construire.
- **Risque** : le Wi-Fi d'une halle pleine. Un câble réseau entre les deux Mac est plus sûr (**à vérifier** sur place).
- **Mesure** : lancer `./preparer_mac.sh --garder-cerveau` sur l'iMac, puis `./preparer_mac.sh --autre-mac <adresse de l'iMac>` sur le MacBook. Le rapport compare le cerveau local et le cerveau distant.

## Si le MacBook (poste robot) tombe : l'iMac reprend tout seul

**Oui, c'est possible.** Chaque Mac a le même dossier, le même kit léger et son propre `reglages.yaml`.
Il faut juste qu'un seul Mac à la fois parle au robot. Préparer avant samedi : sur l'iMac, `./preparer_mac.sh` déjà
lancé une fois (paquets et modèles installés), et le robot joignable depuis l'iMac (même Wi-Fi ou câble).

Les trois gestes :

1. **Appuyer sur le bouton d'arrêt PHYSIQUE du robot.** Tant que l'ancien poste ne répond plus, on ne sait pas ce
   qu'il a laissé en cours. (Le chien de garde du robot doit aussi l'avoir arrêté : à vérifier sur chaque vrai robot.)
2. **Sur l'iMac, ouvrir le Terminal dans le dossier du projet et lancer** `python3 lancer.py`.
   L'iMac prend alors tout : oreilles, voix, cerveau, gardien, prise, écran. Il démarre une nouvelle boîte noire.
3. **Sur l'écran (http://<adresse de l'iMac>:8000), vérifier « liaison ok », puis cliquer « Réarmer ».**
   Prévenir l'équipe de la nouvelle adresse de l'écran.

Le mode « deux Mac » reprend quand le MacBook revient : on le relance, et l'iMac redevient seulement le cerveau
(à construire à l'étape 3). Non testé : il faudra le répéter une fois avant la démonstration.
