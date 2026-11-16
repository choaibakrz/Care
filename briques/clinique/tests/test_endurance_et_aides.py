"""La clinique en boîte — K02b, toute aide humaine se compte (avenant 2, K02 ; seconde moitié).

« Fini » veut dire :
- la commande « endurance » rejoue le scénario en boucle pendant une durée ; elle écrit la durée tenue, le nombre de
  passages et « aucun arrêt » ; au premier arrêt imprévu elle s'arrête et écrit sa cause ;
- le troisième chiffre, « plus longue durée sans arrêt », s'affiche avec niveau, nombre et date ; sans mesure : « non mesuré » ;
- un humain qui reprend la main (brique 11) compte comme une aide ; un geste télécommandé aussi, avec l'étiquette
  « RÉEL · TÉLÉCOMMANDÉ » sur un vrai robot (et jamais « RÉEL » sur le faux robot) ;
- le compteur d'essais réels a un troisième bouton, « réussi avec aide », et un lien vers le protocole ;
- `docs/projet/PROTOCOLE_ESSAIS_REELS.md` existe, avec les huit points de l'avenant.
Les vérifications de J01 et de K02a ne sont pas changées.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from briques.clinique import aide_humaine, endurance, essais, essais_reels, repetition
from briques.clinique.carnet import Carnet
from briques.clinique.ecrans import brancher_ecrans
from briques.clinique.horloge import HorlogeDeDemonstration
from briques.clinique.listes import ListesDeSoin
from briques.clinique.porte import JournalDesAcces, PorteDeLecture
from briques.clinique.taches import TableauDesTaches
from commun.bus import Bus
from conftest import lancer

RACINE = Path(__file__).resolve().parents[3]
CODE = {"X-Code-Equipe": "code-d-essai"}


def _faux_controles():
    return {n: (lambda: repetition.Resultat(True, "SIMULÉ", "essai")) for n in range(1, 15)}


class FausseMontre:
    """Chaque lecture de l'heure avance de `pas` secondes : l'essai ne dure pas pour de vrai."""

    def __init__(self, pas: float) -> None:
        self.t, self.pas = 0.0, pas

    def __call__(self) -> float:
        self.t += self.pas
        return self.t


def _tenir(tmp_path, duree, controles=None, pas=1.0):
    lignes: list[str] = []
    bilan = endurance.tenir(duree, controles or _faux_controles(), ecrire=lignes.append, dossier=tmp_path, montre=FausseMontre(pas))
    return bilan, lignes


# ---------------------------------------------------------------------------------------------- la durée
@pytest.mark.parametrize("texte, secondes", [("60", 60), ("90s", 90), ("5m", 300), ("2h", 7200), ("1 min", 60)])
def test_la_duree_se_donne_en_secondes_minutes_ou_heures(texte, secondes):
    assert endurance.lire_duree(texte) == secondes


@pytest.mark.parametrize("texte", ["", "bientôt", "0", "-5m"])
def test_une_duree_fausse_est_refusee(texte):
    with pytest.raises(ValueError):
        endurance.lire_duree(texte)


def test_la_duree_s_ecrit_simplement():
    assert endurance.texte_duree(62) == "1 min 02 s" and endurance.texte_duree(45.4) == "45 s"
    assert endurance.texte_duree(7262) == "2 h 01 min 02 s"


# ---------------------------------------------------------------------------------------------- l'endurance
def test_l_endurance_d_une_minute_ecrit_sa_duree_ses_passages_et_aucun_arret(tmp_path):
    bilan, lignes = _tenir(tmp_path, 60, pas=5.0)
    assert bilan["arret"] == "aucun arrêt" and bilan["passages"] >= 2 and bilan["duree_tenue_s"] >= 60
    assert bilan["etiquette"] == "FAUX ROBOT" and bilan["code"] == 0
    fin = next(l for l in lignes if l.startswith("ENDURANCE :"))
    assert "aucun arrêt" in fin and f"{bilan['passages']} passages" in fin and endurance.texte_duree(bilan["duree_tenue_s"]) in fin
    assert "FAUX ROBOT" in lignes[0] and "DONNÉES INVENTÉES" in lignes[0]
    ecrit = [json.loads(l) for l in (tmp_path / "endurance.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(ecrit) == 1 and ecrit[0]["passages"] == bilan["passages"] and ecrit[0]["arret"] == "aucun arrêt"


def test_une_verification_provoque_un_arret_et_l_endurance_ecrit_sa_cause(tmp_path):
    controles = _faux_controles()
    appels = {"n": 0}

    def casse_au_troisieme_passage():
        appels["n"] += 1
        if appels["n"] == 3:
            raise RuntimeError("pièce cassée exprès")
        return repetition.Resultat(True, "SIMULÉ", "essai")

    controles[6] = casse_au_troisieme_passage
    bilan, lignes = _tenir(tmp_path, 600, controles)
    assert bilan["passages"] == 2 and bilan["code"] == 1  # deux passages entiers, le troisième s'arrête
    assert "étape 6" in bilan["arret"] and "pièce cassée exprès" in bilan["arret"]
    assert appels["n"] == 3  # elle s'arrête au premier arrêt : pas de quatrième passage
    assert any(l.startswith("ENDURANCE :") and "arrêt au passage 3" in l and "étape 6" in l for l in lignes)
    assert bilan["duree_tenue_s"] < 600


def test_les_aides_humaines_pendant_l_endurance_sont_comptees(tmp_path):
    controles = _faux_controles()
    controles[2] = lambda: (aide_humaine.signaler("bouton", qui="essai"), repetition.Resultat(True, "SIMULÉ", "essai"))[1]
    bilan, lignes = _tenir(tmp_path, 30, controles, pas=5.0)
    assert bilan["aides_humaines"] == bilan["passages"] > 0
    assert any("aide" in l and str(bilan["aides_humaines"]) in l for l in lignes)


def test_la_plus_longue_duree_est_celle_du_meilleur_essai_d_endurance(tmp_path):
    assert endurance.plus_longue(tmp_path) is None
    _tenir(tmp_path, 20, pas=5.0)
    long, _ = _tenir(tmp_path, 120, pas=5.0)
    _tenir(tmp_path, 40, pas=5.0)
    meilleur = endurance.plus_longue(tmp_path)
    assert meilleur["duree_tenue_s"] == long["duree_tenue_s"] and meilleur["passages"] == long["passages"]


def test_la_commande_est_dans_lancer_et_demande_une_duree(capsys):
    assert '"endurance"' in (RACINE / "lancer.py").read_text(encoding="utf-8")
    assert endurance.main([]) == 2 and "--duree" in capsys.readouterr().out


# ---------------------------------------------------------------------------------------------- le troisième chiffre
def test_le_troisieme_chiffre_s_affiche_avec_niveau_nombre_et_date(tmp_path):
    cases = {c: 0 for c in aide_humaine.CASES}
    cases["du premier coup"] = 20
    sans = aide_humaine.chiffres(cases, 0, 0, "FAUX ROBOT", "12.11.2026")[2]
    assert "plus longue durée sans arrêt : non mesuré" in sans
    mesure, _ = _tenir(tmp_path, 60, pas=5.0)
    avec = aide_humaine.chiffres(cases, 0, 0, "FAUX ROBOT", "12.11.2026", endurance=endurance.plus_longue(tmp_path))[2]
    assert avec.startswith(f"CHIFFRE 3 — plus longue durée sans arrêt : {endurance.texte_duree(mesure['duree_tenue_s'])} ")
    assert "[FAUX ROBOT" in avec and f"{mesure['passages']} passages" in avec and mesure["date"][:4] in avec


def test_les_essais_comptes_lisent_l_endurance_du_meme_dossier(tmp_path):
    mesure, _ = _tenir(tmp_path, 30, pas=5.0)
    lignes: list[str] = []
    essais.jouer_les_essais(essais.charger()[:2], _faux_controles(), ecrire=lignes.append, dossier=tmp_path,
                            compteur_reel=essais.CompteurReel(tmp_path / "reels.jsonl"))
    trois = next(l for l in lignes if l.startswith("CHIFFRE 3"))
    assert endurance.texte_duree(mesure["duree_tenue_s"]) in trois and "non mesuré" not in trois


# ---------------------------------------------------------------------------------------------- la main humaine (brique 11)
def _tableau():
    horloge = HorlogeDeDemonstration()
    carnet = Carnet(horloge=horloge)
    listes = ListesDeSoin(PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), carnet)
    return TableauDesTaches(listes.porte, carnet, listes)


@pytest.mark.parametrize("vrai_robot, etiquette", [(True, "RÉEL · TÉLÉCOMMANDÉ"), (False, "FAUX ROBOT · TÉLÉCOMMANDÉ")])
def test_un_humain_reprend_la_main_puis_telecommande_un_geste(vrai_robot, etiquette):
    bus, tableau = Bus(), _tableau()
    aide_humaine.ecouter_la_main(bus, tableau, vrai_robot=lambda: vrai_robot)

    async def scene():
        await bus.emettre("pilotage_humain", "main_humaine", quoi="reprise", qui="Opératrice Exemple")
        await bus.emettre("pilotage_humain", "main_humaine", quoi="ordre", qui="Opératrice Exemple", action="se_deplacer")
        await bus.emettre("pilotage_humain", "main_humaine", quoi="rendu", qui="Opératrice Exemple", duree_s=4, ordres=1)

    with aide_humaine.compter() as compte:
        lancer(scene())
    assert [a["sorte"] for a in tableau.aides] == ["main", "telecommande"] and len(compte.aides) == 2
    assert tableau.aides[1]["etiquette"] == etiquette and "se_deplacer" in tableau.aides[1]["detail"]
    notes = [e.donnees for e in bus.historique if e.type == "note" and e.donnees.get("quoi") == "AIDE HUMAINE"]
    assert len(notes) == 2 and notes[1]["etiquette"] == etiquette  # dans la boîte noire
    assert aide_humaine.classer(True, len(compte.aides), 0) == "avec une aide humaine"


def test_sur_le_faux_robot_on_ne_dit_jamais_reel():
    assert "RÉEL" not in aide_humaine.etiquette_telecommande(False)
    assert aide_humaine.etiquette_telecommande(True) == "RÉEL · TÉLÉCOMMANDÉ"


# ---------------------------------------------------------------------------------------------- le compteur réel
def _client(tmp_path):
    horloge, app = HorlogeDeDemonstration(), FastAPI()
    clinique = brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                               carnet=Carnet(horloge=horloge), code_equipe="code-d-essai")
    clinique.essais_reels.fichier = tmp_path / "essais_reels_d_essai.jsonl"  # jamais le vrai fichier de l'équipe
    return TestClient(app), clinique


def test_le_troisieme_bouton_reussi_avec_aide(tmp_path):
    client, clinique = _client(tmp_path)
    page = client.get("/clinique/essais-reels").text
    assert "Réussi avec aide" in page and "/clinique/protocole-essais-reels" in page
    corps = {"robot": "robot d'essai", "geste": "poser le coussin", "note": ""}
    assert client.post("/api/clinique/essais_reels", json={**corps, "reussi": True}, headers=CODE).status_code == 200
    r = client.post("/api/clinique/essais_reels", json={**corps, "reussi": True, "avec_aide": True}, headers=CODE)
    assert r.status_code == 200 and r.json()["ligne"]["resultat"] == "réussi avec aide"
    client.post("/api/clinique/essais_reels", json={**corps, "reussi": False}, headers=CODE)
    resume = clinique.essais_reels.resume()
    assert resume["essais"] == 3 and resume["reussis"] == 1 and resume["avec_aide"] == 1  # avec aide ≠ réussi tout court
    assert resume["texte"] == "RÉEL : 1 sur 3 ; réussis avec aide : 1 sur 3"


def test_sans_aide_la_ligne_reel_ne_change_pas(tmp_path):
    compteur = essais_reels.CompteurReel(tmp_path / "r.jsonl")
    assert compteur.resume()["texte"] == "RÉEL : aucun essai compté"
    compteur.compter("robot d'essai", "poser le coussin", True)
    compteur.compter("robot d'essai", "poser le coussin", False)
    assert compteur.resume()["texte"] == "RÉEL : 1 sur 2"


def test_un_essai_rate_avec_aide_reste_rate(tmp_path):
    compteur = essais_reels.CompteurReel(tmp_path / "r.jsonl")
    assert compteur.compter("robot d'essai", "poser le coussin", False, avec_aide=True)["resultat"] == "raté"


# ---------------------------------------------------------------------------------------------- le protocole
def test_le_protocole_des_essais_reels_a_ses_huit_points(tmp_path):
    texte = (RACINE / "docs/projet/PROTOCOLE_ESSAIS_REELS.md").read_text(encoding="utf-8")
    for debut in ("1. Avant de commencer, écrivez le geste", "2. Écrivez les conditions", "3. Faites dix essais de suite",
                  "4. Comptez chaque essai, même raté", "5. Si quelqu'un touche le robot", "6. Un arrêt de sécurité",
                  "7. Notez le résultat dans le compteur tout de suite", "8. Si les conditions changent"):
        assert debut in texte, debut
    assert "le coussin est sur le lit et y reste dix secondes" in texte
    client, _ = _client(tmp_path)
    page = client.get("/clinique/protocole-essais-reels")
    assert page.status_code == 200 and "Faites dix essais de suite" in page.text
