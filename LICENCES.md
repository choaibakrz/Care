# Licences

Tout ce que le projet utilise ou reprend, son auteur et sa licence. Mis à jour le 11.11.2026.
**Aucun code n'a été copié depuis un autre dépôt à ce jour.** Tout le code du dossier a été écrit pour ce projet.

Règles : MIT ou Apache → possible en citant l'auteur. GPL / AGPL → le dire à Hiba avant. Sans licence → s'inspirer des idées, ne pas copier.

## Paquets Python installés (étape 1, testés sur Linux)

Utilisés tels quels, sans modification, installés depuis PyPI.

| Paquet | Version | Licence | Auteur / projet |
|---|---|---|---|
| fastapi | 0.162.4 | MIT | Sebastián Ramírez |
| uvicorn | 0.54.0 | BSD-3-Clause | Encode (Tom Christie) |
| starlette | 1.10.0 | BSD-3-Clause | Encode (Tom Christie) |
| websockets | 17.4 | BSD-3-Clause | Aymeric Augustin |
| pydantic | 2.14.3 | MIT | Pydantic (Samuel Colvin et al.) |
| pydantic_core | 2.50.4 | MIT | Pydantic |
| PyYAML | 6.0.3 | MIT | Kirill Simonov |
| pytest | 9.2.0 | MIT | Équipe pytest |
| httpx | 0.28.1 | BSD-3-Clause | Encode (Tom Christie) |
| httpcore | 1.0.9 | BSD-3-Clause | Encode |
| psutil | 7.2.2 | BSD-3-Clause | Giampaolo Rodola |
| anyio | 4.16.0 | MIT | Alex Grönholm |
| h11 | 0.16.0 | MIT | Nathaniel J. Smith |
| idna | 3.20 | BSD-3-Clause | Kim Davies |
| click | 8.5.1 | BSD-3-Clause | Pallets |
| certifi | 2026.10.23 | **MPL-2.0** (copyleft léger, fichier par fichier : aucune obligation tant qu'on ne modifie pas ses fichiers) | Kenneth Reitz |
| annotated-types, annotated-doc, typing-inspection, iniconfig, pluggy | — | MIT | divers |
| typing_extensions | 4.16.0 | PSF-2.0 | Python Software Foundation |
| packaging | 26.3 | Apache-2.0 ou BSD-2-Clause | PyPA |
| Pygments | 2.21.0 | BSD-2-Clause | Georg Brandl |
| opentelemetry-api | 1.45.2 | Apache-2.0 | OpenTelemetry |

## Paquets de la voix (étape 2, testés sur Linux)

| Paquet | Version | Licence | Rôle |
|---|---|---|---|
| faster-whisper | 1.2.1 | MIT (SYSTRAN) | écoute, **sur Linux seulement** (tests, banc) ; tire PyAV, voir plus bas |
| ctranslate2 | 4.9.0 | MIT (OpenNMT) | calcul de l'écoute |
| onnxruntime | 1.31.1 | MIT (Microsoft) | calcul du détecteur de voix et des voix |
| sherpa-onnx (+ core) | 2.0.1 | Apache-2.0 (k2-fsa) | voix ; **ne contient plus espeak-ng** depuis la version 2.0 |
| numpy | 2.5.4 | BSD-3-Clause (+ 0BSD, MIT, Zlib, CC0) | calcul |
| soundfile | 0.14.0 | BSD-3-Clause ; contient libsndfile (**LGPL-2.1**, bibliothèque séparée : aucune obligation tant qu'on ne la modifie pas et qu'on ne distribue pas) | lire et écrire les sons |
| av (PyAV) | 19.0.2 | BSD-3-Clause ; contient FFmpeg **avec libx264 et libx265 (GPL)** — vérifié dans le paquet | tiré par faster-whisper ; nous ne l'utilisons pas (on donne le son déjà décodé) |
| tokenizers | 0.23.3 | Apache-2.0 | découpage du texte (écoute) |
| huggingface_hub, hf-xet | 2.4.0, 1.8.0 | Apache-2.0 | tirés par faster-whisper (non utilisés pour télécharger : notre script le fait) |
| tqdm | 4.70.1 | MPL-2.0 et MIT | barre de progression (tirée par faster-whisper) |
| protobuf, flatbuffers, filelock, fsspec, cffi, pycparser, truststore, httpx2, httpcore2 | — | BSD, Apache-2.0, MIT, MIT-0 | dépendances |

## Paquets du cerveau (étape 3) — Linux seulement, pour les tests (sur Mac : le programme llama.cpp)

| Paquet | Version | Licence |
|---|---|---|
| llama-cpp-python (avec son serveur) | 0.3.36 | MIT (contient llama.cpp, MIT) — construit depuis les sources |
| diskcache | 5.6.3 | Apache-2.0 |
| Jinja2, MarkupSafe | 3.1.6, 3.0.4 | BSD-3-Clause |
| pydantic-settings, starlette-context | 2.16.2, 0.3.6 | MIT |
| python-dotenv, sse-starlette | 1.2.4, 3.7.0 | BSD-3-Clause |

## Repris des dépôts de Hiba (avec son accord, 11.11.2026)

| Quoi | D'où | Comment |
|---|---|---|
| Idée : réessayer par un « appel d'outil » forcé si un service refuse le formulaire imposé | `sahimhiba-debug/Flexsis-`, `python/src/flexradar/llm/base.py` | réécrit (`briques/b06_cerveau/branchements/llm.py`) |
| Idée : clé lue dans une variable ou le trousseau du Mac, jamais écrite ; `User-Agent` envoyé | `Flexsis-`, `llm/secrets.py` | réécrit |
| Faits : l'API du CSCS (`api.inference.cscs.ch`) sert Apertus v1.5 70B et accepte un formulaire imposé (01.10.2026) | `sahimhiba-debug/HackVS`, `docs/audit/probe_publicai.md` | cité dans les réglages |

## Brique 15 (chef de démonstration)

Aucun nouveau paquet. Aucun code copié : écrite pour ce projet (pydantic et PyYAML, déjà listés).

## Brique 17 (kit du samedi matin)

Aucun nouveau paquet (PyYAML, déjà listé). Aucun code copié : écrite pour ce projet. Les faux défis d'exemple sont inventés.

## Lot B (briques 7, 8, 13)

Aucun nouveau paquet, aucun code copié. Idées seulement (de mémoire, pages non relues : **à vérifier**) : RoboGuard et
ASIMOV (règles en langue simple vérifiées hors du modèle), KnowNo (demander quand plus d'un choix reste possible).
Pictogrammes SVG de l'écran du jury dessinés pour le projet ; polices du système. Test du navigateur : Playwright pour
Node 1.63.0 (Apache-2.0) et Chromium (licence de type BSD), déjà présents sur l'ordinateur de test, ni installés ni
distribués par le projet ; le test saute s'ils manquent.

## Brique 3 (adaptateurs)

Aucun paquet ajouté, aucun code copié, aucun kit installé. Lu pour s'informer (11.11.2026) :
`unitreerobotics/unitree_sdk2_python` (**BSD-3-Clause**, © HangZhou YuShu Technology / Unitree Robotics),
`unitreerobotics/unitree_ros2` (**BSD-3-Clause**), `flexivrobotics/flexiv_rdk` (**Apache-2.0**),
`flexivrobotics/flexiv_ros2` (**Apache-2.0**), `AgibotTech/agibot_D1_Edu-Ultra` (**BSD-3-Clause**),
`AgibotTech/agibot_agentsdk_sample_code` (**MIT**), `ros2/rclpy` et `ros2/common_interfaces` (**Apache-2.0**).
Seuls des noms de fonctions et de champs sont cités (fiches, commentaires), pour brancher. Le faux ROS 2 reprend les
noms et arguments de rclpy et les champs des messages ROS 2 (Apache-2.0), sans code. Sans licence affichée → idées
seulement : `AgibotTech/Agibot_D1_Max`, `Agibot_D1_MaxPro`, `agibot_x1_*`. Licence « Other » à lire avant usage :
`AgibotTech/agibot_x2_urdf`.

## Brique 14 (porte des agents)

Paquet ajouté (PyPI, utilisé tel quel ; licences lues dans les métadonnées PyPI le 11.11.2026), 5,6 Mo à télécharger :

| Paquet | Version | Licence | Auteur / projet |
|---|---|---|---|
| mcp | 2.3.0 | MIT | Model Context Protocol, a Series of LF Projects, LLC |
| mcp-types | 2.3.0 | MIT | idem |
| jsonschema, jsonschema-specifications, referencing | 4.26.0, 2025.9.1, 0.37.0 | MIT | Julian Berman |
| attrs | 26.1.0 | MIT | Hynek Schlawack |
| rpds-py | 2026.9.1 | MIT | Julian Berman |
| PyJWT | 2.15.1 | MIT | Jose Padilla |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause | The Python Cryptographic Authority |
| python-multipart | 0.0.33 | Apache-2.0 | Andrew Dunham |

Aucun code copié : la porte est écrite pour ce projet.

## Brique 5 (les yeux) — en option, `requirements-yeux.txt` (installé avec `--no-deps`), testé sur Linux seulement

| Paquet | Version | Licence | Rôle |
|---|---|---|---|
| opencv-contrib-python-headless | 5.0.0.93 | Apache-2.0 ; contient FFmpeg (**LGPL-2.1**, bibliothèque séparée, non modifiée), OpenSSL ; sur Mac aussi libgmp, libidn2, libunistring (LGPL-3) ; libgfortran et libquadmath non citées (**à vérifier**) | images, marqueurs ArUco |
| mediapipe | 1.2.2 | Apache-2.0 (NOTICE : composants tiers, dont gfortran, GPL-3 avec exception) | personnes et objets courants |
| matplotlib | 3.11.2 | licence matplotlib (type PSF, permissive ; **pas MIT/Apache/BSD au sens strict**) — importé par MediaPipe | — |
| rapidocr | 3.10.0 | Apache-2.0 ; modèles PP-OCRv6 inclus, Apache-2.0 (Baidu / PaddleOCR) | lire un texte |
| pillow | 13.0.0 | MIT-CMU (permissive) | images |
| fonttools, pyparsing, six, pyclipper, colorlog, urllib3, charset-normalizer, sounddevice | — | MIT | dépendances |
| contourpy, cycler, kiwisolver, shapely, omegaconf, python-dateutil | — | BSD | dépendances |
| absl-py, requests, tzdata | — | Apache-2.0 | dépendances |

Modèle : EfficientDet-Lite0 int8 v1 (Google, pour MediaPipe), 4,6 Mo, Apache-2.0 d'après son origine (google/automl) ;
fiche MediaPipe **à vérifier**. Images d'essai fabriquées par le projet. Aucun code copié.

## Brique 11 (la main humaine)

Aucun nouveau paquet, aucun code repris. Test du navigateur : Playwright pour Node et Chromium déjà présents sur
l'ordinateur de test, ni installés ni distribués par le projet ; le test saute s'ils manquent.

## Repris d'ailleurs

| Quoi | Auteur, licence | Où |
|---|---|---|
| Correspondance des noms de poids Whisper (Hugging Face → MLX) | Apple Inc., `ml-explore/mlx-examples` (whisper/convert.py), **MIT** | `outils/essai_suisse_allemand.py` |

## Installé sur l'iMac le 11.11.2026 (clinique en boîte, tâche R1)

Dans `.venv` seulement : les paquets des tableaux « étape 1 », « voix » et « porte des agents » ci-dessus, aux mêmes
versions, **sauf** faster-whisper et ce qu'il tire (PyAV, ctranslate2, tokenizers, huggingface_hub, hf-xet, tqdm, filelock,
fsspec) : non installés, à cause de la partie GPL de PyAV. onnxruntime 1.31.1 (MIT) est installé à part.
Licences lues dans les fiches des paquets au moment de l'installation : MIT, Apache-2.0, BSD, MIT-0, PSF-2.0 (typing_extensions),
MPL-2.0 (certifi, déjà noté plus haut). Aucune GPL, aucune AGPL. `requirements-mac.txt` et `requirements-yeux.txt` : pas encore installés.

## Paquets prévus pour les Mac (requirements-mac.txt) — non installés ici, non testés sur Mac

| Paquet | Version | Licence (PyPI) | Rôle |
|---|---|---|---|
| mlx | 0.32.4 | MIT | calcul sur puce Apple |
| mlx-lm | 0.32.2 | MIT | cerveau avec MLX |
| mlx-whisper | 0.4.3 | MIT | écoute avec MLX |
| pywhispercpp | 1.5.1 | MIT | écoute avec whisper.cpp |
| faster-whisper | 1.2.1 | MIT | écoute sur processeur (comparaison) |
| sherpa-onnx | 2.0.1 | Apache-2.0 | voix (lit les voix Piper sans la licence GPL) |
| numpy | 2.5.4 | BSD-3-Clause (+ 0BSD, MIT) | calcul |
| sounddevice | 0.5.6 | MIT | micro et haut-parleur |
| llama.cpp (programme) | dernière version | MIT | cerveau sur puce graphique |

## Modèles (catalogue : outils/catalogue.yaml)

| Modèle | Licence | Remarque |
|---|---|---|
| Apertus 8B Instruct 2509 (Swiss AI) | Apache-2.0 | conversions GGUF (Unsloth) et MLX (mlx-community) |
| Apertus v1.1 4B Instruct (Swiss AI) | Apache-2.0 | MLX officiel ; GGUF par un particulier (**à vérifier**) |
| Whisper (OpenAI), fichiers whisper.cpp | MIT | |
| Whisper, conversions MLX (mlx-community) | **à vérifier** (la fiche ne donne pas de licence) | modèle d'origine MIT |

## Écoute, données d'essai

| Élément | Licence | Remarque |
|---|---|---|
| Whisper base et small, format faster-whisper (Systran) | MIT | modèle d'origine OpenAI Whisper (MIT) |
| Silero VAD v6, fichier inclus `briques/b04_oreilles_voix/modeles_inclus/silero_vad_v6.onnx` | MIT, © Silero Team | copié depuis faster-whisper (MIT) ; inclus pour ne pas dépendre de faster-whisper sur Mac |
| FLEURS (Google), 12 phrases par langue | CC-BY-4.0 | vraies voix, `donnees_voix/fleurs/` ; citer : Conneau et al. 2022 |
| Flix-AI/flix-swissgerman-full (essai en option sur Mac, **non téléchargé**) | Apache-2.0 | 3,09 Go ; converti en MLX 8 bits par `outils/essai_suisse_allemand.py` |
| Autres Whisper suisses allemands vus : Flurin17 turbo, BabaStardust MLX | **CC-BY-NC-4.0 (non commercial) : écartés** | |
| gcoli/whisper-large-v3-swiss-german (MLX) | « other » : **à vérifier** | non utilisé |
| Apertus v1.1 0.5B Instruct, GGUF (mradermacher) | Apache-2.0 | 382 Mo, **tests seulement** |

### Vraies voix suisses allemandes pour mesurer (recherche du 11.11.2026)

- **STT4SG-350** (ZHAW, FHNW, UZH ; 343 h) : licence **pas claire** (licence « SwissNLP » ? accès sur inscription ?).
  À vérifier par Hiba sur swissnlp.org ; je n'accepte aucune condition à sa place.
- **Swiss Parliaments Corpus** : copies sur Hugging Face **sans licence affichée** → non utilisées.
- **SwissDial** : recherche seulement → écarté.
- En attendant : enregistrer l'équipe (`python3 lancer.py enregistrer gsw`), avec son accord.

## Voix Piper — licence de chaque voix (lue dans sa fiche le 11.11.2026)

| Voix | Langue | Licence des données | Remarque |
|---|---|---|---|
| fr_FR-siwis-medium | français | CC-BY-4.0 | citer « SIWIS » |
| de_DE-thorsten-medium | allemand | CC0 | |
| ~~it_IT-paola-medium~~ | italien | **écartée** | affinée depuis « lessac », dont la licence (Blizzard 2013) interdit tout usage commercial |
| it_IT-serena-medium | italien | CC-BY-4.0 | apprise de zéro sur des données synthétiques (Qwen3-TTS, Apache-2.0, voix de référence synthétique) |
| en_GB-cori-medium | anglais | CC-BY-4.0 | citer « Hi-Fi TTS, NVIDIA » |
| zh_CN-chaowen-medium | chinois | CC0 | |
| (aucune) | suisse allemand | — | pas de voix trouvée : réponse en allemand |

Origine vérifiée : siwis, chaowen et cori sont affinées depuis la voix « hifi_tts_92 » (Hi-Fi TTS, CC-BY-4.0) ;
thorsten depuis la voix « rdh » (CC0) ; serena apprise de zéro.

### Mentions à afficher (voix sous CC-BY-4.0)

À mettre dans le générique de la démonstration, sur l'écran « À propos », et dans toute vidéo où l'on entend ces voix :

- « Voix française : Piper fr_FR-siwis, données SIWIS French Speech Synthesis Database (Université d'Édimbourg / Idiap), CC-BY 4.0. »
- « Voix anglaise : Piper en_GB-cori, données Hi-Fi Multi-Speaker English TTS (NVIDIA Corporation), lecture de Cori Samuel, CC-BY 4.0. »
- « Voix italienne : Piper it_IT-serena, données serena-synthetic-it-27h (Committa), CC-BY 4.0 ; phrases Tatoeba (CC-BY 2.0 FR). »
- « Voix française et chinoise : affinées depuis Piper hifi_tts_92 (Hi-Fi TTS, NVIDIA, CC-BY 4.0). »
- « Enregistrements d'essai : FLEURS (Google), CC-BY 4.0. »

### PyAV et la GPL (x264, x265) — à signaler à Hiba

faster-whisper a besoin de PyAV, qui contient des bibliothèques vidéo sous GPL. Nous ne nous en servons pas, et il ne
sert que sur Linux (tests et banc dans le nuage). **Sur les Mac, faster-whisper n'est plus installé** (retiré de
`requirements-mac.txt`) : l'écoute passe par mlx-whisper ou whisper.cpp (MIT), et le détecteur de voix est inclus.

### Le texte → sons : espeak-ng (GPL-3.0) — décision de Hiba

Les voix Piper (sauf le chinois, qui a un lexique) ont besoin d'espeak-ng, sous **GPL-3.0**, pour transformer le
texte en sons. sherpa-onnx 2.x ne l'inclut plus : il faudrait l'ajouter (paquet `piper-phonemize`, qui contient
espeak-ng). **Non installé, en attente de décision.** La GPL n'impose rien tant qu'on ne distribue pas le
logiciel ; elle impose de fournir le code source si on le distribue.
Le dépôt de conversion `csukuangfj2/vits-piper-zh_CN-chaowen-medium` (voix chinoise prête) n'affiche pas de licence :
la voix elle-même est CC0 ; la licence des fichiers ajoutés (lexique) est **à vérifier**.

Écartées à cause de leur licence : it_IT-paola (dérivée de lessac, non commercial), fr_FR-upmc (dérivée de lessac), fr_FR-tom (AGPL), en_US-ryan (non commercial), zh_CN-xiao_ya (non commercial),
zh_CN-huayan (licence inconnue), lb_LU-marylux (non commercial).
Le programme `piper1-gpl` est sous **GPL-3.0** : on ne l'utilise pas. Correction du 11.11 : sherpa-onnx lit les mêmes
voix, mais il leur faut aussi espeak-ng (GPL-3.0), voir plus haut.

## Écarté pour cause de licence

- YOLO d'Ultralytics : **AGPL-3.0**.

## Lecture de texte du Mac (clinique en boîte, R3, le 12.11.2026)

| Quoi | Licence | Remarque |
|---|---|---|
| Cadre « Vision » de macOS (lecture de texte), appelé par `outils/lecture_mac.swift` | fourni avec macOS (logiciel d'Apple, pas un logiciel libre) | rien n'est installé ni copié dans le dépôt : le programme appelle une fonction du système. Autorisation B de Hiba (11.11.2026). Conditions d'usage d'Apple pour ce cadre : **à vérifier** si le prototype sort du hackathon |
| `outils/lecture_mac.swift` | écrit pour ce projet | construit avec le compilateur Swift déjà sur le Mac (Xcode) |

## Ébauche Unitree Go2 (H08a, 12.11.2026)
`briques/b03_adaptateurs/robots/unitree_go2/` : écrit pour ce projet. Du kit public `unitreerobotics/unitree_sdk2_python` (**BSD-3-Clause**), seuls des NOMS de fonctions et de champs ont été lus en ligne et cités (`SportClient`, `StandUp`, `Move`, `StopMove`, `SportModeState_`…), avec la date de lecture. Aucun code du fabricant n'est copié dans le dépôt ; le kit n'est ni cloné ni installé.

## Ébauche AgileX PiPER (14.11.2026)
`briques/b03_adaptateurs/robots/agilex_piper/` et `briques/b03_adaptateurs/fiches/agilex_piper.md` : écrits pour ce projet. Du kit public `agilexrobotics/piper_sdk` (**MIT**, © 2024 Agilex Robotics Co., Ltd.), seuls des NOMS de fonctions, de champs et des codes ont été lus en ligne et cités (`C_PiperInterface_V2`, `ConnectPort`, `GetArmStatus`, `GetArmHighSpdInfoMsgs`…), avec la date de lecture. Aucun code du fabricant n'est copié dans le dépôt ; le kit n'est ni cloné ni installé.

## Ébauche Reachy Mini (15.11.2026)
`briques/b03_adaptateurs/robots/reachy_mini/` et `briques/b03_adaptateurs/fiches/reachy_mini.md` : écrits pour ce projet. Du dépôt public `pollen-robotics/reachy_mini` (**Apache-2.0**), seuls des NOMS d'adresses web, de champs et d'options ont été lus en ligne et cités (`/api/daemon/status`, `/api/move/running`, `/api/move/stop`, `/api/motors/set_mode/…`, `--no-wake-up-on-start`…), avec la date de lecture. Aucun code du fabricant n'est copié dans le dépôt. Notre liaison lui parle par des demandes web, avec la bibliothèque standard de Python.

**Le kit du fabricant, installé À PART le 15.11.2026** (accord de Hiba dans la conversation : « Oui installe ») : `reachy-mini` 1.14.0 (**Apache-2.0**) et ses 81 dépendances, depuis pypi.org, dans `~/reachy_env` (Python 3.12, hors du dossier du projet, 1,2 Go sur le disque). Rien n'en est copié dans le dépôt, rien n'est redistribué : notre projet ne l'importe pas, il lui parle par des demandes web.
- **Correction** : j'avais annoncé à Hiba « deux paquets en partie sous GPL ». En relisant ce que les paquets installés déclarent, ils sont **cinq** à citer « GPL-2.0-or-later » parmi leurs licences : `gstreamer-plugins`, `gstreamer-plugins-libs`, `gstreamer-plugins-gpl`, `gstreamer-plugins-gpl-restricted`, `gstreamer-libs` (son et image). D'autres sont sous LGPL. Signalé à Hiba (Q31) : si elle préfère, on désinstalle (`rm -rf ~/reachy_env`).
- Tant qu'on se sert de ces paquets sans les copier ni les redistribuer, la GPL ne s'étend pas à notre code (à faire confirmer par quelqu'un qui connaît le droit si le projet est un jour distribué AVEC ce kit).
- Le programme de fond n'a été lancé qu'en mode simulé (`--mockup-sim`), mesures d'usage coupées (`DO_NOT_TRACK=1`, `REACHY_MINI_TELEMETRY=0`), sans téléchargement de gestes. Vu à son démarrage : il s'annonce sur le réseau local (mDNS, « service registered »), même en n'écoutant que sur l'ordinateur.

## Ébauche « robot à roues ROS 2 » (H08b, 12.11.2026)
`briques/b03_adaptateurs/robots/roues_ros2/` : écrit pour ce projet. De `ros2/common_interfaces` et `ros2/rclpy` (**Apache-2.0**), seuls des NOMS de messages, de champs et de fonctions ont été lus en ligne et cités (`Twist`, `Odometry`, `create_publisher`…), avec la date de lecture. Aucun code n'est copié dans le dépôt ; ROS 2 n'est ni cloné ni installé.

## Outil du fabricant de la main (15.11.2026) — hors du projet
`LHandPro` 1.4.5 pour Mac (fichier `LHandPro-v1.4.5-macos-arm64-2026-10-31-09-59-74147a03.dmg`, 211,7 Mo), téléchargé le 15.11.2026 dans `~/Downloads/lhandpro-1.4.5-mac/`, avec l'accord de Hiba (« c'est le bon, tu peux télécharger »). Source : le dépôt GitHub `sorrowfeng/LHandPro-Releases` ; **je n'ai pas pu vérifier moi-même que ce compte est celui du fabricant** (Leadshine / Leadtron) : c'est Hiba qui le confirme. Contrôle SHA-256 identique à celui publié sur la même page (cela prouve que le fichier est arrivé intact, pas d'où il vient). **Licence : non indiquée.** Apple n'a pas vérifié ce programme (la page le dit : signé « ad hoc », pas notarié). Rien de ce programme n'entre dans le dépôt ; il sert à un essai humain de la main, sans Iris ni le gardien. Ouvert par Hiba, pas par un agent.
Lu aussi, sans rien copier : le manuel du kit `LHandProLib` (noms des commandes), pour préparer plus tard une pièce de Iris pour la main. Licence du kit : non indiquée → idées seulement.

## pyusb (15.11.2026)
`pyusb` 1.3.1 (licence **BSD**, 58 Ko, aucune dépendance), installé dans `.venv` le 15.11.2026 avec l'accord de Hiba (« Oui, installe-le »), depuis pypi.org. Il sert au kit du fabricant de la main (Leadtron DH116) pour parler à son boîtier USB. Rien n'en est copié dans le dépôt.
Le kit du fabricant de la main, `LHandProLib` du 31.10.2026 pour Mac (2,6 Mo), est téléchargé dans `~/Downloads/lhandprolib-20261031-mac/`, hors du projet, depuis le dépôt GitHub `sorrowfeng/LHandProLib-Releases` (source confirmée par Hiba, non vérifiée par moi). **Licence du kit : non indiquée** → aucun code copié, seulement des noms de fonctions cités. Il contient `gsusb-canfd` (licence **MIT**, fichier LICENSE lu) et `libusb` (LGPL, bibliothèque fournie telle quelle).

## La mascotte « marteau du bisse » reprise du projet Proxsis (16.11.2026)
Avec l'accord de Hiba (« Oui, reprends-les », nuit du 15 au 16.11.2026), cinq fichiers ont été copiés depuis son autre projet, `~/code/proxsis/docs/identite/mascotte/`, vers `film/marteau/` : `portrait.jpg`, `vues.jpg` (images), `toc.mp3`, `toc-court.mp3`, `eau.mp3` (sons). La fiche de Proxsis dit qu'ils ont été fabriqués par Hiba avec Runway (numéros de tâche dans `MASCOTTE.md` de Proxsis). Conditions d'usage de Runway pour ces fichiers : à vérifier par Hiba. Au générique : « Images et sons de la mascotte : Runway ». Aucun code de Proxsis n'a été copié.

## Codes QR de la clinique (H19, 13.11.2026)

| Paquet | Version | Licence | Auteur / projet |
|---|---|---|---|
| segno | 1.6.6 | BSD-3-Clause (lue dans son fichier `LICENSE` le 13.11.2026 : « Copyright (c) 2016 - 2025, Lars Heuer ») | Lars Heuer — dessine les codes QR ; installé dans `.venv` de l'iMac avec l'accord de Hiba (Q30), depuis le fichier téléchargé de 76 503 octets (empreinte SHA-256 28c7d081…90c7, la même que sur pypi.org ; environ 572 Ko une fois installé), sans dépendance de plus avec Python 3.13 |

Le lecteur `outils/lire_code_qr.swift` (écrit ici) se sert de CoreImage, livré avec macOS : rien n'est installé pour lui.

## Modèle d'écoute « medium » (H20, 13.11.2026)

`modeles/ggml-medium.bin` : Whisper (OpenAI) converti pour whisper.cpp, dépôt public ggerganov/whisper.cpp, **licence MIT** (fiche du dépôt), 1 533 763 059 octets, sha256 6c14d5adee5f86394037b4e4e8b59f1673b6cee10e3cf0b11bbdbee79c156208 (vérifiés après téléchargement). Téléchargé avec l'accord de Hiba (Q30). Hors de git.

## Serveur de la clinique (Rust) — page `/docs` (tâche 4, 15.11.2026)

| Quoi | Version | Licence | Où |
|---|---|---|---|
| Scalar API Reference (`@scalar/api-reference`, fichier `dist/browser/standalone.js`) | 1.76.4 (publiée le 30.10.2026) | **MIT** (« Copyright (c) 2023-present Scalar », texte copié dans `implementation/server/static/scalar/LICENSE`) | `implementation/server/static/scalar/standalone.js`, copié tel quel, servi par le serveur à `/docs/scalar-standalone.js` pour que `/docs` marche sans Internet |

Téléchargé depuis registry.npmjs.org (archive vérifiée avec l'empreinte sha512 publiée), 4 912 231 octets, sha256 93951f1794b0463b87ab58d0557a6610075af79a9f94c2a3f261c993bc7f3913. La page `/docs` coupe les polices web et la télémétrie de Scalar (`withDefaultFonts: false`, `telemetry: false`) : elle ne demande rien à l'extérieur du serveur.


## Le dépôt public (16.11.2026)
- **Licence du projet : MIT** (choix de Hiba, 16.11.2026 ; fichier `LICENSE`), pour le code écrit par l'équipe. À confirmer par chaque coéquipier pour sa partie (`implementation/`, `api/`, `supabase/`, `models/`). Les composants de tiers, les échantillons de voix de `donnees_voix/` et l'image de la mascotte gardent leurs propres licences et conditions.
- **`models/` s'appuie sur la bibliothèque Ultralytics (YOLO), distribuée sous AGPL-3.0** (à vérifier dans `models/requirements.txt` et sur le site d'Ultralytics) : s'en servir entraîne les obligations de cette licence, même si notre propre code est sous MIT.
- **`models/weights.pt`** (le modèle de reconnaissance entraîné par l'équipe, 40 Mo) **n'est pas dans le dépôt.** S'il vient d'un modèle YOLO d'Ultralytics, il est en général sous licence AGPL-3.0, qui oblige à publier le code qui s'en sert : à vérifier par l'équipe avant de le publier.
- **Le film de présentation** (`docs/media/` : `iris-leukerbad-720.mp4`, l'aperçu animé et l'affiche qui en sont tirés) : fait par l'équipe. Son générique dit : images fabriquées avec Runway et Google Gemini, voix Google Gemini ; c'est un film d'idée, rien n'y est une prise de vue réelle. La mascotte Iris (le marteau du bisse) a été créée par Hiba avec Runway pour son projet Proxsis. Conditions d'usage de ces outils : à vérifier par Hiba.
- Les deux clés du serveur (`implementation/server/keys/`) qui se trouvaient dans le dépôt de travail privé ne sont pas reprises ici.
- **`docs/media/detection-instrument-tray.png`** : une vraie photo prise par l'équipe pendant l'événement, avec les boîtes dessinées par le modèle des coéquipiers. Donnée par Hiba le 16.11.2026.
