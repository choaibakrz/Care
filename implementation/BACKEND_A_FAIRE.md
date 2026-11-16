# Backend : tout ce qu'il reste à construire

Mis à jour le 14.11.2026. Pour toute l'équipe (jobs 1, 2, 3), et pour Hiba qui valide.

**En une phrase :** la console admin, l'app et le robot existent ou sont prêts à brancher ; ce qui manque, c'est **le serveur central (job 3)**, **le lien robot ↔ serveur (b16, job 2)**, **le service de reconnaissance des outils (job 1)**, et le **branchement de la traduction** qui existe déjà côté robot.

Règles qui s'appliquent partout (rappel de `architecture.md`) :
- **Hors ligne.** Tout tourne sur nos ordinateurs, en Wi-Fi local. Aucun service cloud, aucun modèle téléchargé le jour J.
- **Le serveur ne bouge jamais un robot.** Il crée des tâches. Le robot décide, via cerveau → gardien → prise.
- **Pas d'images, pas d'audio, pas de santé** dans le serveur. Une tâche = un objet, deux lieux, un état.
- **Dire ce qui est testé.** Tout ce qui n'a pas tourné sur un vrai robot est marqué « non testé ».

---

## 1. État des lieux

| Partie | Existe | Manque |
|---|---|---|
| Console admin (job 5) | Faite, avec une clinique de démo dans le navigateur, 22 tests unitaires + 6 tests de bout en bout | Le vrai serveur à qui parler |
| App personnel (job 4) | Guide écrit | Tout, attend le serveur |
| Serveur central (job 3) | Rien | `openapi.yaml`, serveur Rust, base, WebSockets |
| Lien robot ↔ serveur (job 2) | Robot Python complet : `Coursier`, tâches, répartiteur, gardien, prise | `briques/b16_lien_serveur/` |
| Voix et traduction | `b04_oreilles_voix`, `clinique/interprete.py`, mesuré (voir §4) | Session interprète déclenchée depuis l'app, mots fixés médicaux |
| Vision | `b05_yeux` : 80 objets génériques (COCO) | Détecteur des outils de la clinique, service C1 |

```
App (Flutter) ─┐                         ┌─ b16 ─ Coursier ─ gardien ─ prise ─ robot
               ├─ C3 ─ SERVEUR ─ C2 ─────┤
Console admin ─┘   (REST + WS)  (WS)     └─ b05 yeux ─ C1 ─ service modèle (outils)
```

---

## 2. Serveur central (job 3) — ce que la console attend

Stack prévue : Rust, axum, tokio, PostgreSQL (SQLite accepté en secours, en le disant).

### 2.1 Premier livrable (débloque tout le monde)
- [ ] `implementation/server/openapi.yaml` (C3) et `ws_messages.md` (C2), avec un exemple par message.
- [ ] Un faux serveur qui répond avec des données fixes, et un faux robot qui envoie des positions.

### 2.2 Routes REST attendues par la console

Tous les appels : JSON, `Authorization: Bearer <token>`, erreurs `{ "error": { "code", "message" } }`, heures en UTC ISO-8601. Les champs en snake_case conviennent : la console lit `mic_open`, `pos`, `from_place`, etc. (`admin/src/lib/adapt.ts`).

| Route | Rôle | Ce que la console envoie / attend |
|---|---|---|
| `POST /auth/login` | tous | `{username, password}` → `{token, role, operator?}`. La console refuse si `role != admin` |
| `GET /map` | tous | `floors[{id, label, outline}]`, `rooms[{id, floor, label, kind, polygon}]`, `walls[{floor, points}]`, `places[{id, label, floor, x, y, kind}]`, `props[]` optionnel. Mètres, x vers l'est, y vers le sud |
| `GET /robots` | admin | `[{id, name, role, simulated, pos{x,y,heading,floor}, battery, state, holding, mic_open, task_id, last_seen}]` |
| `POST /robots/{id}/command` | admin | `{name: pause\|resume\|dock\|estop}` → `{accepted, reason}`. Un refus = 409 avec `message` lisible |
| `GET /tasks`, `GET /tasks/{id}` | tous | `{id, kind, item, from_place, to_place, state, robot_id, requested_by, created_at, updated_at, reason, history[{at, actor, label}]}` |
| `POST /tasks/{id}/cancel` | admin, demandeur | la tâche mise à jour |
| `GET /inventory` | tous | `[{id, label, place, count, low_at, last_robot_count, last_robot_count_at, updated_at}]` |
| `POST /inventory/{item}/adjust` | admin | `{delta}` (entier non nul), jamais en dessous de 0 |
| `GET /zones`, `PUT /zones/{id}`, `DELETE /zones/{id}` | admin | `{id, name, floor, kind: deaf\|restricted, polygon, deliveries[{robot_id, status}]}`. `DELETE` n'est pas dans C3 : **à ajouter** |
| `GET /schedules`, `PUT /schedules/{id}` | admin | `{id, label, enabled, time "HH:MM", robot_id, last_run, last_result, last_counts[{place, item, expected, counted}]}` |
| `GET /audit?from=&to=&actor=` | admin | `[{id, at, actor, action, target, result: ok\|refused\|failed, detail}]`. Lecture seule, aucune route de modification |
| `PUT /me/location` | personnel | pour l'app (salle ou QR) |

### 2.3 WebSocket `/ws`
- [ ] La console envoie `{type: "auth", token}` juste après l'ouverture (le jeton n'est jamais dans l'URL). Un jeton refusé ferme la connexion.
- [ ] Messages poussés : `robot.updated {robot}`, `task.updated {task}`, `inventory.updated {item}`, `zone.updated {zone}`, `zone.deleted {zone_id}`, `schedule.updated {schedule}`, `alert {level: info|warning|critical, message}`.
- [ ] `robot.updated` au moins **toutes les secondes** par robot : la console grise un robot muet depuis 5 s.
- [ ] Types inconnus ignorés des deux côtés, jamais fatals.

### 2.4 Logique du serveur
- [ ] **Base** : `users`, `robots`, `tasks`, `inventory`, `places`, `zones`, `schedules`, `audit_log` (ajout seulement).
- [ ] **Import des YAML** au premier démarrage : `lieux.yaml`, `reserve.yaml`, `flotte.yaml`, `badges.yaml`, `cartes_de_role/`. Marqué « données inventées ».
- [ ] **Répartiteur** : même règle que `clinique/repartiteur.py` (robot libre le plus proche, bonne carte de rôle, batterie suffisante, sinon « confié à un humain »). Les tests Python servent de spécification.
- [ ] **Robot muet 5 s** → `offline`, alerte, tâche réattribuée si c'est sûr.
- [ ] **Stock** : `delivered` décrémente ; `inventory.seen` met à jour le dernier comptage et signale l'écart.
- [ ] **Zones** : à l'enregistrement, `zones.update` à chaque robot ; statut de réception par robot remonté dans `deliveries` ; renvoi à la reconnexion.
- [ ] **Tournée de nuit** : une tâche `restock_round` créée à l'heure prévue, résultat stocké dans le planning.
- [ ] **`estop`** : seule commande transmise directement, rôle admin, chemin de code séparé du répartiteur, testé.
- [ ] **Rôles vérifiés sur chaque route** : une infirmière ne peut ni changer une zone ni envoyer `estop`.

### 2.5 Fait quand
- Une tâche créée en REST arrive au faux robot, chaque état revient sur `/ws`.
- La console en `VITE_USE_MOCK=false` affiche les robots et les arrête (« Confirmed stopped »).
- Robot coupé en pleine tâche → alerte `offline` en moins de 5 s.

---

## 3. Lien robot ↔ serveur (job 2, `briques/b16_lien_serveur/`)

- [ ] Client WebSocket `/ws/robot/{id}` : `hello` à la connexion, `robot.state` chaque seconde (`pos`, `battery`, `state`, `holding`, `mic_open`).
- [ ] `task.assign` → `TableauDesTaches` → `Coursier.faire()`. États traduits dans les deux sens (`delivered` ↔ `livrée`…).
- [ ] `task.event` à chaque changement, avec `reason` en cas d'échec ou de passage à un humain.
- [ ] **Coupure réseau** : le robot finit ou s'arrête proprement, garde les événements, resynchronise. Il ne bouge jamais plus parce que le lien est tombé.
- [ ] Commandes : `estop` → arrêt d'urgence de la prise (réarmement humain obligatoire) ; `pause`, `resume`, `dock` → actions normales via le gardien.
- [ ] **Zones sourdes appliquées par le robot** : dernière liste reçue gardée en local ; micro coupé dans une zone sourde ; **position inconnue = micro coupé** ; `mic_open` remonté. Relecture sécurité obligatoire.
- [ ] Ne jamais toucher `b01_prise/prise.py`, `ticket.py`, `b07_gardien/` sans le relecteur sécurité.

---

## 4. Traduction des paroles (patient ↔ soignant)

### Ce qui existe déjà (mesuré le 13.11.2026, voir `docs/projet/MESURE_INTERPRETE.md`)

| Chemin | Comment | Délai médian | Qualité sur 10 phrases |
|---|---|---|---|
| Direct | whisper.cpp « small » traduit seul vers l'anglais | 924 ms | 4/10 sans erreur, ne respecte pas les mots fixés |
| Deux temps | whisper écrit le français, Apertus 8B traduit avec les mots fixés | 1 614 ms | 8/10 sans erreur |

Mesures faites avec une voix de synthèse, sans bruit, sans robot : **non testé** en conditions réelles.

### Ce qu'il faut faire
- [ ] **Déclencher une session depuis l'app** : bouton « interprète dans cette salle » → tâche `interpreter_session` (nouveau `kind`, à ajouter à C2/C3). La traduction tourne **sur le robot**, jamais sur le serveur.
- [ ] **Les deux sens** : soignant (fr) → patient (de, en, it, zh, gsw) et retour. Langue détectée automatiquement, ou choisie dans l'app.
- [ ] **Mots fixés médicaux** dans `clinique/interprete_mots.yaml` : vocabulaire de soins courant, validé par Hiba. Le chemin « deux temps » par défaut, le chemin « direct » en secours si la machine est chargée.
- [ ] **Affichage** des deux phrases (originale + traduite) sur l'écran du robot, étiquette « TRADUCTION AUTOMATIQUE ».
- [ ] **Aucun conseil médical** : le robot traduit, il ne répond jamais lui-même à une question de santé (règle existante).
- [ ] **Vie privée** : l'audio et le texte restent sur le robot. Le serveur ne reçoit que « session démarrée / terminée, salle, langues ». Rien de ce qui est dit n'est stocké.
- [ ] Zones sourdes prioritaires : pas d'interprète dans une zone où le micro doit être coupé.
- [ ] En option (job 1, P2) : `POST /v1/transcribe` et `POST /v1/translate`, simples enveloppes HTTP autour de `b04` et `interprete.py`.

---

## 5. Réactivité : objectifs de délai

| Chaîne | Objectif | Comment le tenir |
|---|---|---|
| Robot bouge → affiché dans la console | < 1,5 s | `robot.state` chaque seconde, poussé tout de suite sur `/ws` ; la console interpole |
| Tâche créée dans l'app → robot choisi | < 1 s | répartiteur en mémoire, pas de requête lente par tâche |
| Bouton arrêt d'urgence → robot arrêté | < 1 s | chemin `estop` séparé, sans file d'attente ni répartiteur |
| Fin de phrase → traduction dite | < 2 s | chemin « deux temps » mesuré à 1,6 s médian ; « direct » si besoin |
| Photo d'étagère → objets reconnus | < 200 ms | modèle ONNX petit (voir §6) |
| Zone enregistrée → reçue par les robots | < 3 s | `zones.update` immédiat, accusé de réception par robot |

À mesurer et écrire dans un `MESURES.md` avec la machine utilisée. Mémoire : l'iMac M4 et le MacBook M2 (16 Go) font tourner Apertus 8B, la voix **et** la vision en même temps.

---

## 6. Reconnaissance des outils (job 1, `implementation/model_service/`)

### Service C1 (le robot appelle un point d'accès, jamais un modèle précis)
- [ ] `GET /v1/health`, `POST /v1/detect` (JPEG → boîtes `[x, y, l, h]`, étiquette, confiance), `POST /v1/classify`, `GET /v1/classes`.
- [ ] Une fausse version qui renvoie des boîtes fixes **dès la première heure**.

### Liste des classes (`classes.yaml`, noms en 5 langues)
Les 5 objets de la réserve (grand coussin, coussin de nuque, couverture, bouteille d'eau, feuille d'exercices) + environ 7 outils : stéthoscope, thermomètre, ciseaux, rouleau de bande, seringue factice, brassard tensiomètre, boîte de gants. Liste confirmée par Hiba.

### Entraînement
1. **Photos** : 40 à 60 par classe, fonds, lumières et distances variés, objets en partie cachés, plusieurs par image. Plus des images du point de vue du robot.
2. **Annotation** : CVAT ou Label Studio en local ; pré-annotation possible avec un détecteur « zero-shot » (OWLv2, Grounding DINO), corrigée à la main.
3. **Découpage par séance de photos**, pas par image (sinon les scores mentent).
4. **Modèle** : affiner un petit détecteur à licence ouverte (torchvision SSDlite / Faster R-CNN MobileNetV3, RT-DETR, YOLOX, EfficientDet-Lite0). **Pas d'Ultralytics YOLO** (AGPL) sans l'accord de Hiba.
5. **Export ONNX**, exécution onnxruntime (CoreML sur Mac). Budget : < 1 Go de mémoire, < 200 ms par image.
6. **Classifieur des sosies** (grand coussin vs coussin de nuque) sur chaque boîte. Sous le seuil de confiance → `unknown`, qui déclenche le « je ne suis pas sûr » existant (`b08_doute`) au lieu d'un mauvais nom.
7. **Ajouter un outil** avec ~20 photos en réentraînant seulement le classifieur.

### Évaluation (`model_service/MESURES.md`)
mAP@0.5 et rappel par classe, matrice de confusion, fausses détections sur étagère vide, taux de `unknown` sur objets hors liste, délai et mémoire, écart simulation / réel.

### Branchement robot
- [ ] `briques/b05_yeux/branchements/service_http.py` : appelle `/v1/detect`, rend des `Objet`. Service absent = branche absente, le reste continue.
- [ ] Job 2 : le robot vérifie que l'objet est vu sur l'étagère avant de le prendre ; sinon `failed` + `item_not_found`. La tournée de nuit envoie `inventory.seen` à partir des comptages.
- [ ] Photos d'entraînement hors du dépôt git ; images jamais écrites sur disque par défaut.

---

## 7. En plus, si le reste est solide

- **Résumés validés par le soignant** : le robot rédige, un médecin approuve dans l'app avant tout envoi (`GET /summaries`, `POST /summaries/{id}/decision`, à ajouter à C3). Réutilise `clinique/resume.py`.
- **Mode confort** : comportement doux et lent pour une chambre (carte de rôle dédiée).
- **Zones « restreintes » branchées au gardien** : aujourd'hui « advisory only ». Décision sécurité à prendre (question ouverte 5).
- **Journal d'audit chaîné** (chaque entrée signe la précédente) et export CSV.
- **Notifications** locales « votre demande est livrée » dans l'app.
- **Clients générés** depuis `openapi.yaml` pour Dart et TypeScript.
- **Monde Webots** pour des images d'entraînement réalistes et une démo plus belle (seulement après M2).

---

## 7 bis. App patient (`implementation/patient-web/`) — routes à brancher

L'app appelle déjà ces routes via `patient-web/patient-api.js`. Tant qu'elles
n'existent pas (404, 405, 501 ou réponse non JSON), elle affiche des données de
démo marquées « Exemple ». Toutes passent par la session patient (cookie
HttpOnly déjà en place pour `/api/auth/*`) : le patient ne voit que ses propres
données, jamais un diagnostic.

| Route | Réponse | Notes |
|---|---|---|
| `GET /api/patient/program` | `{items: [{time "HH:MM", kind, until? "HH:MM"}]}` | `kind` ∈ `breakfast, round, physio, lunch, visits, dinner` (sinon ignoré). Source : le planning du séjour (FHIR `Appointment`). Aucun libellé médical : l'app traduit le `kind`. |
| `GET /api/patient/questions` | `{items: [{id, text, created_at (ms)}]}` | Les questions du patient pour le médecin, du séjour en cours. |
| `POST /api/patient/questions {text}` | `{id, text, created_at}` | `text` 1–300 caractères. Crée aussi une tâche « question du patient » pour le médecin (comme H02 dans `briques/clinique/soir.py`) : la tâche renvoie à la question, ne la recopie pas. |
| `DELETE /api/patient/questions/{id}` | `204` | Seulement ses propres questions. |
| (à venir) `POST /api/patient/requests {kind}` | `{id, status}` | Remplacera les demandes simulées en mémoire (`water, blanket, wheelchair, pain, interpreter, care-team`). `pain` = priorité haute pour l'équipe. Statut poussé ensuite : `sent → seen → on_the_way → done`. |
| (à venir) `POST /api/patient/mood {value 1–5}` | `204` | « Comment vous sentez-vous ? ». Va seulement à l'équipe de soins du patient ; 1–2 peut lever une alerte douce. |

- [x] Les tables patient (`patient_day_items`, `patient_questions`, `patient_requests`, `patient_mood`) sont définies dans `supabase/patient_data.sql`, avec RLS « le patient ne lit que ses lignes ».
- [x] `GET /api/patient/program` crée ou lit le planning du jour du compte connecté ; le remplacement par le planning clinique réel garde le même contrat.
- [ ] L'onglet « Pause » (respiration, jeu de paires, sons) est 100 % local : aucun backend, aucun score envoyé.

## 8. Ordre de travail

| Étape | Qui | Fait quand |
|---|---|---|
| **M0** Contrats et faux services | Job 3 (`openapi.yaml`, faux serveur, faux robot), job 1 (faux C1 + `classes.yaml`) | La console et l'app affichent les données du faux serveur |
| **M1** Première chaîne complète | Jobs 2 et 3 | Une demande dans l'app fait rouler le faux robot via b16, gardien et prise ; la console le voit bouger |
| **M2** Missions réelles | Jobs 1, 2, 3 | Livraison avec mise à jour du stock, tournée de nuit avec comptage, session interprète, vrai détecteur |
| **M3** Version complète | Tous | Zones sourdes de bout en bout, résumés validés, répétition avec le scénario du jury |

**Décisions à prendre** (avec la valeur par défaut) :
1. Ajouter `DELETE /zones/{id}` et le `kind` `interpreter_session` à C3/C2 → **oui**.
2. Liste finale des outils à reconnaître → **5 objets + 7 outils, Hiba confirme**.
3. Chemin de traduction par défaut → **« deux temps »** (plus juste), « direct » en secours.
4. Zones restreintes vers le gardien → **non pour l'instant** (relecteur sécurité).
