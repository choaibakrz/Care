"""La clinique en boîte — J03, l'instant précis (avenant jury, J03 ; cahier 5.11).

« Montrez-moi le moment exact où ça a raté. » « Fini » veut dire :
- la page « Moments » lit la boîte noire d'une séance (et son carnet) et liste les moments marquants, du plus récent
  au plus ancien : un échec, un « je ne suis pas sûr », un refus du gardien, une reprise par un humain, une panne, une
  phrase retirée faute de source, un papier non rangé ;
- un clic sur un moment montre quatre choses, dans l'ordre : ce que le système a vu ou entendu ; ce qu'il a décidé, et
  pourquoi ; ce qu'il a fait ; les dix secondes d'avant et d'après ;
- les erreurs attrapées : un compteur (le système s'est arrêté de lui-même, ou a demandé un humain), avec la liste ;
- dans le tableau des essais comptés, chaque échec mène à son moment ;
- rien n'est inventé : un moment ne dit que ce qui est écrit dans la boîte noire ou le carnet.
Une séance fabriquée pour l'essai (aucun robot ne bouge ici). Internet coupé, aucun modèle.
"""
from __future__ import annotations

import asyncio
import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from briques.b12_boite_noire.journal import BoiteNoire
from briques.clinique import essais, moments, repetition
from briques.clinique.carnet import Carnet
from briques.clinique.horloge import HorlogeDeDemonstration
from briques.clinique.porte import JournalDesAcces, PorteDeLecture, charger_badges
from commun.bus import Bus

GENRES = ["un échec", "un « je ne suis pas sûr »", "un refus du gardien", "une reprise par un humain", "une panne",
          "une phrase retirée faute de source", "un papier non rangé"]
CODE = {"X-Code-Equipe": "code-d-essai"}


@pytest.fixture(scope="module")
def seance(tmp_path_factory):
    """Une séance fabriquée : une boîte noire et un carnet, avec un moment de chaque sorte, dans l'ordre du temps."""
    dossier = tmp_path_factory.mktemp("seance")
    bus = Bus()
    boite = BoiteNoire(bus, dossier, nom="2026-11-14_090000")
    carnet = Carnet(fichier=dossier / "carnet_essai.jsonl")
    badges = charger_badges()
    robot, accueil, assistant = badges["robot-r1"], badges["accueil"], badges["assistant"]

    async def jouer():
        await asyncio.sleep(0.004)
        await bus.emettre("parole_entendue", "micro", texte="va dans l'escalier", langue="fr", confiance=0.9, conversation="c1")
        await asyncio.sleep(0.004)
        await bus.emettre("demande_comprise", "cerveau", conversation="c1", action={"nom": "se_deplacer", "parametres": {"lieu": "escalier"}})
        await asyncio.sleep(0.004)
        await bus.emettre("gardien_decision", "gardien", conversation="c1", verdict="non", demandeur="cerveau",
                          action={"nom": "se_deplacer", "parametres": {"lieu": "escalier"}},
                          raisons=[{"code": "zone_interdite", "details": {"lieu": "escalier"}}])
        await asyncio.sleep(0.004)
        await bus.emettre("reponse_dite", "cerveau", conversation="c1", texte="Je ne vais pas dans l'escalier : c'est interdit.")
        await asyncio.sleep(0.004)
        carnet.ecrire(robot, "tâche", {"id": "t1", "etat": "échouée", "sorte": "robot", "quoi": "couverture", "ou": "Chambre 12",
                                       "pour_qui": "p01", "demande": "il manque une couverture",
                                       "pourquoi": "le robot n'a pas réussi « saisir » (objet_absent)"}, False)
        await asyncio.sleep(0.004)
        carnet.ecrire(assistant, "rangement de papier", {"papier": "d-x", "etat": "proposé", "type": "formulaire", "confiance": "basse",
                                            "dit": "Je ne suis pas sûr : écrit à la main.", "raisons": ["écrit à la main"],
                                            "patient": "p01"}, False)
        await asyncio.sleep(0.004)
        carnet.ecrire(assistant, "rangement de papier", {"papier": "f-01", "etat": "à trier", "type": None, "confiance": "basse",
                                            "dit": "Je ne trouve pas de nom sur cette feuille.", "patient": None}, False)
        await asyncio.sleep(0.004)
        carnet.ecrire(robot, "tâche", {"id": "t2", "etat": "reprise", "sorte": "humain", "quoi": "feuille d'exercices",
                                       "ou": "Chambre 12", "pour_qui": "p01",
                                       "pourquoi_un_humain": "aucun robot ne peut reprendre la course (arret_urgence)"}, False)
        await asyncio.sleep(0.004)
        await bus.emettre("panne", "pannes_clinique", quoi="lien_robot", etat="début", provoquee=True, etiquette="SIMULÉ",
                          titre="Le lien tombe entre le cerveau et un robot")
        await asyncio.sleep(0.004)
        carnet.ecrire(assistant, "résumé du médecin", {"patient": "p01", "version": "simple", "refait": False, "lignes": [],
                                            "retirees": [{"point": "change", "texte": "Phrase sans source, retirée."}]}, False)
        await asyncio.sleep(0.004)
        await bus.emettre("note", "essais_clinique", quoi="etape_d_un_essai", essai=3, etape=4, issue="ratee", etiquette="",
                          changements={"langue": "fr"}, ligne=" 4. [—] RATÉE — Les trois papiers… (RuntimeError : pièce cassée exprès)")
        await asyncio.sleep(0.004)
        await bus.emettre("note", "essais_clinique", quoi="etape_d_un_essai", essai=3, etape=5, issue="reussie", etiquette="SIMULÉ",
                          changements={"langue": "fr"}, ligne=" 5. [SIMULÉ] réussie")
        await asyncio.sleep(0.004)
        await bus.emettre("panne", "pannes_clinique", quoi="lien_robot", etat="fin", provoquee=True, etiquette="SIMULÉ",
                          titre="Le lien tombe entre le cerveau et un robot")

    asyncio.run(jouer())
    boite.fermer()
    return {"boite": boite.fichier, "carnet": carnet.fichier, "dossier": dossier}


# ---------------------------------------------------------------------------------------------- la liste
def test_les_sept_sortes_de_moments_sont_trouvees_du_plus_recent_au_plus_ancien(seance):
    trouves = moments.moments(moments.lire_seance(seance["boite"], seance["carnet"]))
    assert [m["genre"] for m in trouves] == ["un échec", "une phrase retirée faute de source", "une panne",
                                             "une reprise par un humain", "un papier non rangé",
                                             "un « je ne suis pas sûr »", "un échec", "un refus du gardien"]
    assert set(m["genre"] for m in trouves) == set(GENRES)
    heures = [m["heure"] for m in trouves]
    assert heures == sorted(heures, reverse=True)
    assert len({m["id"] for m in trouves}) == len(trouves)
    # ce qui n'est pas un moment marquant n'y est pas : une étape réussie, la fin d'une panne, une phrase entendue
    assert not any("réussie" in m["titre"] for m in trouves) and sum(m["genre"] == "une panne" for m in trouves) == 1


def test_un_moment_montre_quatre_choses_dans_l_ordre(seance):
    trouves = moments.moments(moments.lire_seance(seance["boite"], seance["carnet"]))
    refus = next(m for m in trouves if m["genre"] == "un refus du gardien")
    assert list(refus["quatre"]) == ["vu", "decide", "fait", "autour"]
    assert "va dans l'escalier" in refus["quatre"]["vu"]  # la phrase entendue, retrouvée par la conversation
    assert "non" in refus["quatre"]["decide"] and "zone_interdite" in refus["quatre"]["decide"]
    assert "rien n'est parti" in refus["quatre"]["fait"] and "Je ne vais pas dans l'escalier" in refus["quatre"]["fait"]
    autour = refus["quatre"]["autour"]
    assert any("parole_entendue" in a["quoi"] for a in autour["avant"]) and any("reponse_dite" in a["quoi"] for a in autour["apres"])
    echec = next(m for m in trouves if m["genre"] == "un échec" and m["origine"] == "boîte noire")
    assert "essai 3" in echec["titre"] and "étape 4" in echec["titre"]
    assert "pièce cassée exprès" in echec["quatre"]["decide"] and "ni effacé ni rejoué" in echec["quatre"]["fait"]
    course = next(m for m in trouves if m["genre"] == "un échec" and m["origine"] == "carnet")
    assert "il manque une couverture" in course["quatre"]["vu"] and "objet_absent" in course["quatre"]["decide"]
    retiree = next(m for m in trouves if m["genre"] == "une phrase retirée faute de source")
    assert "Phrase sans source, retirée." in retiree["quatre"]["vu"] and "sans source" in retiree["quatre"]["decide"]


def test_les_dix_secondes_d_avant_et_d_apres_ne_prennent_que_dix_secondes():
    entrees = [{"heure": f"2026-11-14T09:00:{s:02d}.000+00:00", "origine": "boîte noire", "type": "note", "source": "x",
                "donnees": {}, "id": f"e{s}", "conversation": None} for s in (0, 5, 14, 16, 25, 27, 40)]
    autour = moments.autour(entrees, entrees[3])
    assert [a["id"] for a in autour["avant"]] == ["e14"] and [a["id"] for a in autour["apres"]] == ["e25"]
    assert moments.autour(entrees, entrees[0])["avant"] == []


def test_les_erreurs_attrapees_sont_comptees_avec_leur_liste(seance):
    trouves = moments.moments(moments.lire_seance(seance["boite"], seance["carnet"]))
    attrapees = moments.erreurs_attrapees(trouves)
    assert attrapees["compte"] == 4
    assert sorted(m["genre"] for m in attrapees["liste"]) == sorted(["un refus du gardien", "un « je ne suis pas sûr »",
                                                                     "un papier non rangé", "une reprise par un humain"])
    assert "s'est arrêté de lui-même ou a demandé un humain" in attrapees["texte"]
    # une panne provoquée et un échec ne sont pas des erreurs « attrapées »
    assert not any(m["genre"] in ("une panne", "un échec") for m in attrapees["liste"])


def test_une_seance_vide_le_dit_sans_rien_inventer(tmp_path):
    assert moments.moments(moments.lire_seance(None, None)) == []
    assert moments.erreurs_attrapees([])["texte"].startswith("0 ")
    vide = tmp_path / "vide.jsonl"
    vide.write_text("ligne abîmée\n", encoding="utf-8")
    assert moments.moments(moments.lire_seance(vide, vide)) == []


def test_avec_les_vraies_pieces_les_lignes_du_carnet_donnent_bien_des_moments(tmp_path, monkeypatch):
    """Pas une séance fabriquée : les vrais papiers, le vrai résumé, la vraie demande. Leurs lignes de carnet sont lues."""
    from briques.clinique import resume
    from briques.clinique.ecrans import brancher_ecrans

    horloge = HorlogeDeDemonstration(temps=lambda: 0.0)
    carnet = Carnet(horloge=horloge, fichier=tmp_path / "carnet_vrai.jsonl")
    clinique = brancher_ecrans(FastAPI(), porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour),
                               horloge=horloge, carnet=carnet, code_equipe="x")
    clinique.papiers.pile(clinique.badges["accueil"])  # les papiers du jour : une feuille sans nom, un formulaire à la main
    clinique.taches.demander(clinique.badges["soignant-etage-2"], "p01", "il manque un fauteuil roulant")  # objet absent
    vraies = resume.ResumeDuMedecin._phrases

    def avec_une_phrase_sans_source(self, vue, jour):
        phrases = vraies(self, vue, jour)
        phrases["change"].append({"texte": "Phrase glissée exprès, sans source.", "sources": ["source-qui-n-existe-pas"]})
        return phrases

    monkeypatch.setattr(resume.ResumeDuMedecin, "_phrases", avec_une_phrase_sans_source)
    clinique.resume.resume(clinique.badges["medecin-exemple"], "p01")
    trouves = moments.moments(moments.lire_seance(None, carnet.fichier))
    genres = [m["genre"] for m in trouves]
    assert "un papier non rangé" in genres and "une phrase retirée faute de source" in genres
    retiree = next(m for m in trouves if m["genre"] == "une phrase retirée faute de source")
    assert "Phrase glissée exprès, sans source." in retiree["quatre"]["vu"]
    non_range = next(m for m in trouves if m["genre"] == "un papier non rangé")
    assert "f-01" in non_range["titre"]
    # la demande d'un objet absent passe à un humain : ce n'est pas un moment « pourquoi_un_humain »… on regarde ce qui est écrit
    taches = [l for l in carnet.lignes("tâche")]
    assert taches and taches[0]["donnees"]["sorte"] == "humain"
    assert ("une reprise par un humain" in genres) == bool(taches[0]["donnees"].get("pourquoi_un_humain"))


# ---------------------------------------------------------------------------------------------- la page
def _clinique(seance):
    from briques.clinique.ecrans import brancher_ecrans

    horloge = HorlogeDeDemonstration()
    app = FastAPI()
    clinique = brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                               carnet=Carnet(horloge=horloge), code_equipe="code-d-essai")
    clinique.moments.dossier = seance["dossier"]
    clinique.moments.carnets = {"2026-11-14_090000": seance["carnet"]}
    return TestClient(app), clinique


def test_la_page_liste_les_moments_et_un_clic_montre_les_quatre_choses(seance):
    client, _ = _clinique(seance)
    page = client.get("/clinique/moments", params={"seance": "2026-11-14_090000"}, headers=CODE)
    assert page.status_code == 200 and "DONNÉES INVENTÉES" in page.text
    for genre in GENRES:
        assert genre in page.text, genre
    assert "Erreurs attrapées : 4" in page.text
    liens = re.findall(r'href="(/clinique/moments/voir\?[^"]+)"', page.text)
    assert len(liens) == 8
    ordre = [page.text.index(g) for g in ("essai 3, étape 4", "Le lien tombe", "zone_interdite")]
    assert ordre == sorted(ordre)  # du plus récent au plus ancien
    trouves = moments.moments(moments.lire_seance(seance["boite"], seance["carnet"]))
    refus = next(m for m in trouves if m["genre"] == "un refus du gardien")
    assert any(f"m={refus['id']}" in l for l in liens)
    vue = client.get("/clinique/moments/voir", params={"seance": "2026-11-14_090000", "m": refus["id"]}, headers=CODE).text
    titres = ["1. Ce que le système a vu ou entendu", "2. Ce qu'il a décidé, et pourquoi", "3. Ce qu'il a fait",
              "4. Les dix secondes d'avant et d'après"]
    places = [vue.index(t) for t in titres]
    assert places == sorted(places) and "zone_interdite" in vue and "va dans l&#x27;escalier" in vue


def test_la_page_est_pour_l_equipe_et_refuse_une_seance_inconnue(seance):
    client, _ = _clinique(seance)
    assert client.get("/clinique/moments").status_code == 403  # sans code, depuis un autre ordinateur : refusé
    assert client.get("/clinique/moments/voir", params={"seance": "2026-11-14_090000", "m": "x"}).status_code == 403
    assert client.get("/clinique/moments", params={"seance": "../../etc/passwd"}, headers=CODE).status_code == 404
    assert client.get("/clinique/moments/voir", params={"seance": "2026-11-14_090000", "m": "inconnu"}, headers=CODE).status_code == 404
    assert "/clinique/moments" in client.get("/clinique").text


def test_une_balise_dans_la_boite_noire_ne_passe_pas_a_l_ecran(tmp_path):
    bus = Bus()
    boite = BoiteNoire(bus, tmp_path, nom="2026-11-14_100000")
    asyncio.run(bus.emettre("gardien_decision", "gardien", verdict="non", action={"nom": "<script>alert(1)</script>"},
                            raisons=[{"code": "<b>x</b>", "details": {}}]))
    boite.fermer()
    client, clinique = _clinique({"dossier": tmp_path, "carnet": tmp_path / "rien.jsonl"})
    page = client.get("/clinique/moments", params={"seance": "2026-11-14_100000"}, headers=CODE).text
    assert "<script>alert(1)" not in page and "<b>x</b>" not in page


# ---------------------------------------------------------------------------------------------- les essais comptés
def test_dans_le_tableau_des_essais_chaque_echec_mene_a_son_moment(tmp_path):
    controles = {n: (lambda: repetition.Resultat(True, "SIMULÉ", "essai")) for n in range(1, 15)}
    appels = {"n": 0}

    def cassee_une_fois():
        appels["n"] += 1
        if appels["n"] == 2:
            raise RuntimeError("pièce cassée exprès")
        return repetition.Resultat(True, "SIMULÉ", "essai")

    controles[6] = cassee_une_fois
    lignes: list[str] = []
    bilan = essais.jouer_les_essais(essais.charger()[:3], controles, ecrire=lignes.append, dossier=tmp_path)
    echec = next(l for l in lignes if l.startswith("  - essai 2, étape 6"))
    lien = re.search(r"moment : (/clinique/moments/voir\?seance=([\w.-]+)&m=(\w+))", echec)
    assert lien, echec
    trouves = moments.moments(moments.lire_seance(bilan["boite_noire"], None))
    assert [m["id"] for m in trouves] == [lien.group(3)] and lien.group(2) == bilan["boite_noire"].stem
    assert "pièce cassée exprès" in trouves[0]["quatre"]["decide"]
    assert bilan["echecs"][0]["moment"] == lien.group(1)


def test_la_commande_moments_liste_une_seance(seance, capsys):
    from pathlib import Path

    assert '"moments"' in (Path(__file__).resolve().parents[3] / "lancer.py").read_text(encoding="utf-8")
    assert moments.main([str(seance["boite"]), "--carnet", str(seance["carnet"])]) == 0
    sortie = capsys.readouterr().out
    assert "8 moments" in sortie and "Erreurs attrapées : 4" in sortie and "un refus du gardien" in sortie
    assert moments.main([str(seance["dossier"] / "absent.jsonl")]) == 2
