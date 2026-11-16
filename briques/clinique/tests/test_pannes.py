"""La clinique en boîte — J02a, les pannes provoquées : le cadre et la première panne (avenant jury, J02).

« Fini » veut dire, pour cette première partie :
- la page « Pannes » liste les quatre pannes de l'avenant, chacune avec l'étiquette SIMULÉ ; celles qui ne sont pas
  encore construites le disent ; les boutons demandent le code d'équipe ;
- la panne « le lien tombe entre le cerveau et un robot », provoquée, tient les quatre choses obligatoires :
  1. le robot s'arrête là où il est et ne commence rien de nouveau (rien ne part, le gardien n'est même pas sollicité) ;
  2. l'écran dit en mots simples ce qui se passe, ce que le système fait, qui est prévenu ;
  3. la boîte noire l'écrit (et le carnet aussi) ;
  4. quand la panne finit, rien n'est perdu : les coches sont là, les tâches en attente repartent ;
- pendant la panne, ce qui marche sans le robot continue (cocher une liste), et l'écran le dit ;
- la même panne se lance par une commande.
Les trois autres pannes : J02b et J02c. Testé sur faux robot. Internet coupé, aucun modèle.
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from briques.b12_boite_noire.journal import lire
from briques.clinique import pannes as piece
from briques.clinique.carnet import Carnet
from briques.clinique.coursier import monde_de_la_clinique
from briques.clinique.horloge import HorlogeDeDemonstration
from briques.clinique.porte import JournalDesAcces, PorteDeLecture
from conftest import lancer, robot

SOIGNANT = "soignant-etage-2"
CODE = {"X-Code-Equipe": "code-d-essai"}


def _clinique(tmp_path, reglages, avec_robot=True):
    from briques.clinique.ecrans import brancher_ecrans
    from commun.systeme import Systeme

    systeme = None
    if avec_robot:
        r = {**reglages, "ecran": dict(reglages["ecran"]), "cerveau": {**reglages["cerveau"], "choix": "regles"}}
        systeme = Systeme(r, dossier_journal=tmp_path / "journal", acceleration=20.0, monde=monde_de_la_clinique())
    horloge = HorlogeDeDemonstration(bus=systeme.bus if systeme else None)
    app = FastAPI()
    clinique = brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                               carnet=Carnet(horloge=horloge), systeme=systeme, code_equipe="code-d-essai")
    return app, clinique, systeme


def _avec_systeme(systeme, fabrique):
    async def tout():
        await systeme.demarrer()
        try:
            return await fabrique()
        finally:
            await systeme.arreter()

    return lancer(tout())


def _etats(clinique, ident):
    return [l["donnees"]["etat"] for l in clinique.carnet.lignes("tâche") if l["donnees"]["id"] == ident]


def _gestes(systeme):
    return [e.donnees["action"]["nom"] for e in systeme.bus.historique if e.type == "action_demarree" and e.donnees.get("action")]


# ---------------------------------------------------------------------------------------------- la liste et la page
def test_les_quatre_pannes_de_l_avenant_portent_l_etiquette_simule():
    connues = piece.PANNES
    assert list(connues) == ["lien_robot", "lien_tablette", "cerveau_muet", "micro_bruit"]
    for panne in connues.values():
        assert panne["etiquette"] == "SIMULÉ"
        for cle in ("titre", "ce_qui_se_passe", "ce_que_le_systeme_fait", "qui_est_prevenu"):
            assert len(panne[cle]) > 10, cle
    assert connues["lien_robot"]["construite"] is True


def test_la_page_liste_les_pannes_avec_leur_etiquette_et_dit_ce_qui_n_est_pas_construit(tmp_path, reglages):
    app, clinique, _ = _clinique(tmp_path, reglages, avec_robot=False)
    client = TestClient(app)
    page = client.get("/clinique/pannes")
    assert page.status_code == 200 and "DONNÉES INVENTÉES" in page.text
    for panne in piece.PANNES.values():
        assert panne["titre"] in page.text
    assert page.text.count("SIMULÉ") >= 4
    pas_construites = [p for p in piece.PANNES.values() if not p["construite"]]
    assert page.text.count("pas encore construite") == len(pas_construites)
    assert "/clinique/pannes" in client.get("/clinique").text


def test_les_boutons_des_pannes_demandent_le_code_d_equipe(tmp_path, reglages):
    app, clinique, _ = _clinique(tmp_path, reglages, avec_robot=False)
    client = TestClient(app)
    assert client.post("/api/clinique/pannes/lien_robot/provoquer").status_code == 403
    assert clinique.pannes.actives() == []
    assert client.post("/api/clinique/pannes/lien_robot/provoquer", headers=CODE).status_code == 200
    assert clinique.pannes.actives() == ["lien_robot"]
    assert client.post("/api/clinique/pannes/lien_robot/finir").status_code == 403
    assert client.post("/api/clinique/pannes/lien_robot/finir", headers=CODE).status_code == 200
    assert clinique.pannes.actives() == []
    assert client.post("/api/clinique/pannes/panne_inconnue/provoquer", headers=CODE).status_code == 404


def test_une_panne_pas_encore_construite_ne_se_provoque_pas(tmp_path, reglages):
    app, clinique, _ = _clinique(tmp_path, reglages, avec_robot=False)
    pas_construites = [i for i, p in piece.PANNES.items() if not p["construite"]]
    for ident in pas_construites:
        with pytest.raises(piece.PanneRefusee, match="pas encore construite"):
            lancer(clinique.pannes.provoquer(ident))
    assert clinique.pannes.actives() == []


# ---------------------------------------------------------------------------------------------- le lien avec le robot tombe
@pytest.fixture(scope="module")
def panne_jouee(tmp_path_factory):
    """La panne « lien_robot », jouée UNE fois sur le faux robot par la fonction que la commande appelle."""
    return piece.demonstration("lien_robot", tmp_path_factory.mktemp("panne"))


def test_lien_robot_les_quatre_choses_obligatoires(panne_jouee):
    d = panne_jouee
    clinique, systeme, demande = d["clinique"], d["systeme"], d["demande"]
    # 1. le robot ne commence rien de nouveau
    assert d["pendant"]["etat"] == "demandée" and "lien avec le robot" in d["pendant"]["en_attente"]
    assert d["gestes_pendant"] == [] and d["decisions_pendant"] == 0
    # 2. l'écran dit ce qui se passe, ce que le système fait, qui est prévenu, avec l'étiquette
    panne = piece.PANNES["lien_robot"]
    for morceau in (panne["ce_qui_se_passe"], panne["ce_que_le_systeme_fait"], panne["qui_est_prevenu"], "SIMULÉ", "PANNE"):
        assert morceau in d["bandeau"], morceau
    assert "tout va bien" not in d["bandeau"].lower()
    # 3. la boîte noire et le carnet l'écrivent : le début et la fin
    assert [(e.donnees["quoi"], e.donnees["etat"]) for e in d["notes"]] == [("lien_robot", "début"), ("lien_robot", "fin")]
    assert all(e.donnees["provoquee"] is True and e.donnees["etiquette"] == "SIMULÉ" for e in d["notes"])
    assert [l["donnees"]["etat"] for l in clinique.carnet.lignes("panne")] == ["début", "fin"]
    # 4. rien n'est perdu : les deux coches sont là, la tâche en attente est repartie et livrée
    assert d["points"][1] == "fait" and d["points"][2] == "fait"
    assert d["retour"]["reparties"] == [demande["id"]] and d["retour"]["en_attente"] == []
    assert clinique.taches.tache(demande["id"])["etat"] == "livrée"
    assert _etats(clinique, demande["id"]) == ["demandée", "demandée", "attribuée", "en route", "livrée"]
    assert d["gestes"] == ["se_deplacer", "saisir", "se_deplacer", "poser"]
    assert clinique.pannes.actives() == [] and "PANNE" not in d["client"].get("/clinique/heure").text
    depart = systeme.monde.depart
    assert (depart.x, depart.y) != (robot(systeme).x, robot(systeme).y)  # après la panne, il a bien fait la course
    assert d["ok"] is True and d["choses"] == {1: True, 2: True, 3: True, 4: True}


def test_la_demonstration_dit_non_si_une_des_quatre_choses_manque(panne_jouee):
    """La ligne finale vient des quatre contrôles : on vérifie qu'elle n'est pas écrite en dur."""
    assert panne_jouee["lignes"][-1] == "PANNE : TENUE"
    assert [l[:2] for l in panne_jouee["lignes"][1:5]] == ["1.", "2.", "3.", "4."]
    assert all(" oui — " in l for l in panne_jouee["lignes"][1:5])


def test_lien_robot_en_pleine_course_le_robot_s_arrete_ou_il_est_et_la_tache_n_est_pas_perdue(tmp_path, reglages):
    app, clinique, systeme = _clinique(tmp_path, reglages)
    soignant = clinique.badges[SOIGNANT]
    demande = clinique.taches.demander(soignant, "p01", "une couverture")["tache"]

    async def scene():
        course = asyncio.create_task(clinique.coursier.faire(demande["id"]))
        for _ in range(400):  # on attend que le robot soit parti
            if _gestes(systeme):
                break
            await asyncio.sleep(0.005)
        await clinique.pannes.provoquer("lien_robot")
        fin = await course
        gestes_a_la_panne = len(_gestes(systeme))
        position = (robot(systeme).x, robot(systeme).y)
        await asyncio.sleep(0.3)  # le robot ne bouge plus et rien de nouveau ne part
        immobile = position == (robot(systeme).x, robot(systeme).y) and len(_gestes(systeme)) == gestes_a_la_panne
        arret = systeme.prise.arret_urgence_actif
        retour = await clinique.pannes.finir("lien_robot", attendre=True)
        repartie = None
        if arret:  # un humain vérifie et réarme ; ensuite seulement, la demande repart
            avant = len(_gestes(systeme))
            await systeme.prise.rearmer()
            relance = await clinique.pannes.relancer()
            for _ in range(400):
                if len(_gestes(systeme)) > avant:
                    break
                await asyncio.sleep(0.005)
            repartie = (relance["reparties"], len(_gestes(systeme)) > avant, clinique.taches.tache(demande["id"])["etat"])
        return fin, immobile, arret, retour, repartie

    fin, immobile, arret, retour, repartie = _avec_systeme(systeme, scene)
    assert fin["etat"] == "reprise" and "lien avec le robot" in fin["pourquoi"]
    assert immobile
    assert "livrée" not in _etats(clinique, demande["id"])[:4]
    if arret:  # la prise a déclenché l'arrêt d'urgence : seul un humain réarme, la tâche attend, et l'écran le dit
        assert retour["reparties"] == [] and retour["en_attente"] == [demande["id"]]
        assert "réarmer" in retour["dit"]
        # après le réarmement par un humain, la demande repart : le robot se remet en route (on n'attend pas la fin ici)
        assert repartie[0] == [demande["id"]] and repartie[1] is True and repartie[2] in ("attribuée", "en route")
    else:
        assert retour["reparties"] == [demande["id"]]
        assert clinique.taches.tache(demande["id"])["etat"] == "livrée"


def test_sans_robot_branche_la_panne_se_note_quand_meme_et_les_listes_continuent(tmp_path, reglages):
    app, clinique, _ = _clinique(tmp_path, reglages, avec_robot=False)
    client = TestClient(app)
    lancer(clinique.pannes.provoquer("lien_robot"))
    assert "PANNE" in client.get("/clinique/heure").text
    soignant = clinique.badges[SOIGNANT]
    clinique.listes.cocher(soignant, "p01", "installation", 3)
    lancer(clinique.pannes.finir("lien_robot", attendre=True))
    assert [l["donnees"]["etat"] for l in clinique.carnet.lignes("panne")] == ["début", "fin"]
    points = {p["numero"]: p["etat"] for p in clinique.listes.liste(soignant, "p01", "installation")["points"]}
    assert points[3] == "fait"


def test_provoquer_deux_fois_ou_finir_une_panne_absente_est_refuse(tmp_path, reglages):
    app, clinique, _ = _clinique(tmp_path, reglages, avec_robot=False)
    lancer(clinique.pannes.provoquer("lien_robot"))
    with pytest.raises(piece.PanneRefusee, match="encore coupé"):
        lancer(clinique.pannes.relancer())
    assert TestClient(app).post("/api/clinique/pannes/relancer").status_code == 403  # bouton pour l'équipe seulement
    with pytest.raises(piece.PanneRefusee, match="déjà"):
        lancer(clinique.pannes.provoquer("lien_robot"))
    lancer(clinique.pannes.finir("lien_robot", attendre=True))
    with pytest.raises(piece.PanneRefusee, match="pas en cours"):
        lancer(clinique.pannes.finir("lien_robot", attendre=True))


# ---------------------------------------------------------------------------------------------- la commande
def test_la_meme_panne_se_lance_par_une_commande(capsys, monkeypatch, panne_jouee):
    from pathlib import Path

    assert '"pannes"' in (Path(__file__).resolve().parents[3] / "lancer.py").read_text(encoding="utf-8")
    assert piece.main([]) == 0
    sortie = capsys.readouterr().out
    assert all(p["titre"] in sortie for p in piece.PANNES.values()) and "SIMULÉ" in sortie
    appels = []
    # la commande appelle « demonstration » : on lui rend la panne déjà jouée (une seule course de robot pour ce fichier)
    monkeypatch.setattr(piece, "demonstration", lambda ident: appels.append(ident) or panne_jouee)
    assert piece.main(["lien_robot"]) == 0 and appels == ["lien_robot"]
    sortie = capsys.readouterr().out
    for mot in ("1.", "2.", "3.", "4.", "ne commence rien", "boîte noire", "rien n'est perdu", "FAUX ROBOT", "PANNE : TENUE"):
        assert mot in sortie, mot
    monkeypatch.setattr(piece, "demonstration", lambda ident: {**panne_jouee, "ok": False})
    assert piece.main(["lien_robot"]) == 1
    assert piece.main(["panne_inconnue"]) == 2
    monkeypatch.undo()  # la vraie fonction : la panne de la tablette ne se joue pas dans un terminal, la commande le dit
    assert piece.main(["lien_tablette"]) == 2 and "/clinique/pannes" in capsys.readouterr().out
