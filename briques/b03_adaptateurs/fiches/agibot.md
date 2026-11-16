# Fiche d'ébauche — AGIBOT (X2, A2, G2, D1… : le modèle est inconnu)

**Non testé sur vrai robot.** Ce que les pages publiques disent, lu le **11.11.2026**, et ce qui reste **à vérifier**.
Aucune ligne ne prétend marcher. **Peu d'information publique sur le pilotage** : c'est le robot le plus risqué pour
« brancher en 30 minutes ». Demander tôt aux organisateurs : quel modèle, quel kit, quelle version, qui l'installe.

## Ce que les pages publiques disent vraiment (lu le 11.11.2026)

| Quoi | Ce qui est écrit | Où |
|---|---|---|
| Dépôts publics | organisation GitHub `AgibotTech`, 33 dépôts : surtout simulation, recherche, mains (OmniHand) ; **aucun kit de pilotage public trouvé pour X2, A2 ou G2** | https://github.com/AgibotTech |
| Chien D1 (?) | `agibot_D1_Edu-Ultra`, **BSD-3-Clause** : « AgiBot robotic platforms, including the ZSL-1 model » ; C++ et Python ; Ubuntu 22.04 ; robot en **192.168.234.1** (Wi-Fi) ou **192.168.168.168** (câble) ; appels `standUp()`, `lieDown()`, `move(vx, vy, yaw_rate)`, `jump()`, `frontJump()`, `backflip()`, `shakeHand()`, `attitudeControl(...)` ; **aucun arrêt d'urgence ni mode amorti décrit** | https://github.com/AgibotTech/agibot_D1_Edu-Ultra |
| Autres D1 | `Agibot_D1_Max`, `Agibot_D1_MaxPro` (C++) : **licence non affichée** → idées seulement | même organisation |
| X2 | `agibot_x2_urdf` : modèles 3D du X2, licence « Other » (à lire avant usage) | même organisation |
| Conversation | `agibot_agentsdk_sample_code`, **MIT** : exemple « guide d'hôpital » sur l'AgentSDK ; paquet `linksoul-agentsdk==1.4.0a0` à télécharger à part ; identifiants `AGIBOT_APP_ID`, `AGIBOT_APP_KEY`, `AGIBOT_APP_SECRET`, `AGIBOT_AGENT_CODE` ; gestes `blow_kiss`, `hand_heart`, `wave_hands`, `goodbye` ; une intention « stop » interrompt la réponse en cours | https://github.com/AgibotTech/agibot_agentsdk_sample_code |
| X1 (recherche) | `agibot_x1_infer`, `agibot_x1_train`, `agibot_x1_hardware` : licence non affichée → idées seulement | même organisation |

## Vu seulement dans un résumé de recherche (page NON lue : à vérifier)
- Le kit du X2 s'appellerait **AimDK_X2**, construit sur **ROS 2**, en Python et C++, et s'obtiendrait **auprès du
  service après-vente** (site x2-aimdk.agibot.com, non autorisé dans la session de préparation).
- Un guide « Genie 02 GDK v2.1.0 » (PDF chez un revendeur) parlerait d'installer le kit du G2 et de vérifier la
  connexion réseau. Non lu.

## À vérifier (sur place)
- **Quel robot**, quel kit, quelle version, déjà installé sur un ordinateur des organisateurs ?
- **Arrêt d'urgence PHYSIQUE** : où ? Rien lu.
- **Chien de garde du fabricant** : rien lu. À mesurer (robot suspendu ou sur support).
- Arrêt logiciel le plus sûr (sans chute) : rien lu. Il doit rendre un code (rien = « non confirmé ») et avoir un
  délai court (un arrêt qui attend longtemps sa réponse ne sert à rien) : à vérifier.
- Si le kit est sur ROS 2 : noms des sujets et des messages, `ROS_DOMAIN_ID`, version de ROS 2 → chemin **ros2**.
- L'AgentSDK demande des identifiants et un compte : **accepter des conditions = feu rouge pour un agent** ; décision de
  Hiba. Il ne sert pas au pilotage des moteurs (d'après l'exemple lu).

## Chemin probable
**ros2** si c'est un X2 avec AimDK (à vérifier) ; **sdk** pour le D1 / ZSL-1 (appels Python lus ci-dessus).
Correspondance D1 proposée (à vérifier) : `se_deplacer` → `move(vx, vy, 0)` répété ; `arreter` → `move(0, 0, 0)` ;
gestes → `shakeHand()` ; **jamais** `jump()`, `frontJump()`, `backflip()`.

## Premier essai (feu orange)
Comme pour tout robot : responsable sécurité présent, arrêt physique trouvé et essayé, robot suspendu ou stable,
test sans mouvement d'abord, puis 0,1 m/s.
