"""Parler au faux robot avec le micro du Mac. NON TESTÉ sur Mac (pas de micro ici) ; testé avec --fichier.

    python3 lancer.py micro                          écoute en continu, écran sur http://localhost:8000
    python3 lancer.py micro --declenchement bouton   touche Entrée = « je parle » / « j'ai fini » (ou le bouton de l'écran)
    python3 lancer.py micro --declenchement mot_d_appel   il faut dire « robot » d'abord
    python3 lancer.py micro --langue gsw             forcer une langue
    python3 lancer.py micro --fichier essai.wav      un enregistrement à la place du micro

Conseil : un casque ou un micro-cravate évite que le robot s'entende lui-même (sinon il peut se couper la parole).
"""
from __future__ import annotations

import asyncio
import sys
import threading

from commun.evenements import Evenement


def _afficher(ev: Evenement) -> None:
    d = ev.donnees
    lignes = {
        "transcription": lambda: f"🗣  [{d.get('langue')}] « {d.get('texte')} »  (confiance {d.get('confiance')}, {d.get('calcul_ms')} ms)",
        "reponse_dite": lambda: f"💬 [{d.get('langue')}] {d.get('texte')}",
        "voix_debut": lambda: f"   ⏱  réponse {d.get('latence_ms')} ms après la fin de la phrase" if d.get("latence_ms") else None,
        "action_demarree": lambda: f"🤖 {d.get('action', {}).get('nom')} {d.get('action', {}).get('parametres')}",
        "action_terminee": lambda: f"🤖 {d.get('statut')} {d.get('message') or ''}",
        "interruption": lambda: "✋ interruption : le robot se tait",
        "mot_d_appel": lambda: "👂 mot d'appel entendu",
        "arret_urgence": lambda: "🛑 ARRÊT D'URGENCE",
    }
    f = lignes.get(ev.type)
    texte = f() if f else None
    if texte:
        print(texte, flush=True)


def main(args) -> int:
    from commun.systeme import Systeme, charger_reglages

    from .audio import lire
    from .ecoute import creer_ecoute
    from .peripheriques import HautParleurFactice, MicroFichier
    from .voix import creer_voix
    from .conversation import Conversation

    reglages = charger_reglages()
    v = reglages.setdefault("voix", {})
    if args.declenchement:
        v["declenchement"] = args.declenchement
    if args.langue:
        v["langue_forcee"] = args.langue
    if args.robot:
        reglages["robot"]["carte"] = args.robot

    print("Chargement de l'écoute et de la voix…", flush=True)
    systeme = Systeme(reglages)
    ecoute, voix = creer_ecoute(reglages), creer_voix(reglages)
    print(f"Écoute : {ecoute.nom}. Voix : {voix.nom or 'aucune (sous-titres seulement)'}. Testé sur faux robot.", flush=True)
    systeme.bus.abonner(_afficher)

    async def tourner() -> None:
        try:
            from .peripheriques import HautParleurMac
            hp = HautParleurMac()
        except Exception as e:  # pas de haut-parleur utilisable : on continue avec les sous-titres
            print(f"Haut-parleur indisponible ({e}) : réponses en texte seulement.")
            hp = HautParleurFactice()
        conv = Conversation(systeme, ecoute, voix, hp, v)
        await conv.prechauffer()
        if args.fichier:
            micro = MicroFichier(lire(args.fichier), vitesse=1.0)
        else:
            from .peripheriques import MicroMac
            micro = MicroMac()
        if v.get("declenchement") == "bouton":
            boucle = asyncio.get_running_loop()
            print("Mode bouton : Entrée pour parler, Entrée pour finir.", flush=True)

            def clavier():
                appuye = False
                for _ in sys.stdin:
                    appuye = not appuye
                    boucle.call_soon_threadsafe(conv.appuyer if appuye else conv.relacher)
                    print("🎙  je parle…" if appuye else "…fini", flush=True)

            threading.Thread(target=clavier, daemon=True).start()
        taches = [conv.ecouter(micro)]
        if not args.sans_ecran:
            import uvicorn

            from briques.b13_ecran.serveur import creer_app

            app = creer_app(systeme, conversation=conv)
            port = reglages["ecran"]["port"]
            print(f"Écran : http://localhost:{port}", flush=True)
            serveur = uvicorn.Server(uvicorn.Config(app, host=reglages["ecran"]["hote"], port=port, log_level="warning"))
            taches.append(serveur.serve())
            await asyncio.sleep(1.0)  # laisser l'écran démarrer le système
        else:
            await systeme.demarrer()
        print("Parlez au robot. Ctrl+C pour arrêter.", flush=True)
        try:
            await asyncio.gather(*taches)
        finally:
            conv.fermer()
            micro.fermer()
            if args.sans_ecran:
                await systeme.arreter()

    try:
        asyncio.run(tourner())
    except KeyboardInterrupt:
        pass
    return 0
