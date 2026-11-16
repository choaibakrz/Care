"""Le serveur d'essai pour regarder les pages dans un navigateur (tâches N01 et N02, message de Hiba du 12.11.2026).

    .venv/bin/python outils/serveur_pages_vues.py [PORT]        puis ouvrir http://127.0.0.1:PORT/clinique

Le même programme que « python3 lancer.py » (l'écran de l'ossature, plus les pages de la clinique), mais :
- il n'écoute que sur CET ordinateur (127.0.0.1) : personne d'autre sur le Wi-Fi ne le voit ;
- faux robot, cerveau à règles, réglages d'exemple : aucun vrai robot, aucun modèle ;
- tout ce qu'il écrit va dans un dossier provisoire : la boîte noire, le faux logiciel administratif, et surtout le
  fichier des essais réels. Appuyer sur « Réussi » ici n'écrit JAMAIS dans le vrai fichier de l'équipe.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))


def main() -> int:
    import uvicorn

    from briques.b13_ecran.serveur import creer_app
    from briques.clinique.coursier import monde_de_la_clinique
    from briques.clinique.ecrans import brancher_ecrans
    from briques.clinique.horloge import HorlogeDeDemonstration
    from commun.systeme import REGLAGES_EXEMPLE, Systeme, charger_reglages

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    provisoire = Path(tempfile.mkdtemp(prefix="pages-vues-"))
    reglages = charger_reglages(REGLAGES_EXEMPLE)
    reglages["cerveau"] = {**reglages["cerveau"], "choix": "regles"}
    systeme = Systeme(reglages, dossier_journal=str(provisoire / "journal"), monde=monde_de_la_clinique())
    app = creer_app(systeme)
    clinique = brancher_ecrans(app, horloge=HorlogeDeDemonstration(bus=systeme.bus), systeme=systeme)
    clinique.essais_reels.fichier = provisoire / "essais_reels_D_ESSAI.jsonl"  # jamais le vrai fichier de l'équipe
    clinique.faux_logiciel.dossier = provisoire / "faux_logiciel"
    clinique.faux_logiciel.remettre_a_zero()
    print(f"SERVEUR D'ESSAI — pages vues — http://127.0.0.1:{port}/clinique — faux robot — tout s'écrit dans {provisoire}", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
