"""La clinique en boîte — J04a, un robot d'une autre sorte : à roues, sans bras, avec un plateau (avenant jury, J04).

« Fini » veut dire, pour cette première moitié :
- une deuxième carte d'identité existe : un petit robot à roues, sans bras, avec un plateau ; il porte, il ne saisit
  pas, il roule plus lentement, il n'a pas d'écran ; ses chiffres sont marqués « à vérifier » ;
- le cerveau ne change pas : il lit la carte et il s'adapte. Pour le coussin, le robot va à la réserve, demande à un
  humain de poser l'objet sur son plateau, l'apporte, et demande à un humain de le prendre ;
- le robot sans bras ne reçoit JAMAIS une tâche qui demande un bras ;
- l'étape du coussin réussit avec les deux sortes de robot ;
- les fichiers du cerveau sont les mêmes avant et après : rien n'est écrit en dur pour ce robot.
La commande « brancher » et le chronomètre : seconde moitié (J04b). Testé sur faux robot. Internet coupé, aucun modèle.
"""
from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import pytest
import yaml

from briques.b01_prise.carte import CarteIdentite
from briques.clinique import repetition
from briques.clinique.carnet import Carnet
from briques.clinique.coursier import Coursier, monde_de_la_clinique
from briques.clinique.horloge import HorlogeDeDemonstration
from briques.clinique.listes import ListesDeSoin
from briques.clinique.porte import JournalDesAcces, PorteDeLecture, charger_badges
from briques.clinique.taches import TableauDesTaches
from conftest import lancer

RACINE = Path(__file__).resolve().parents[3]
CARTE = RACINE / "briques" / "b02_faux_robot" / "cartes" / "plateau.yaml"
BADGES = charger_badges()
SOIGNANT = BADGES["soignant-etage-2"]
BRAS = ("saisir", "poser", "montrer", "rejouer_geste")
# le cerveau : celui de l'ossature (brique 6) et, dans la clinique, ce qui décide quoi demander au robot
CERVEAU = sorted((RACINE / "briques" / "b06_cerveau").rglob("*.py")) + [RACINE / "briques" / "clinique" / n
                                                                        for n in ("coursier.py", "taches.py")]


def _empreinte() -> str:
    h = hashlib.sha256()
    for f in CERVEAU:
        h.update(f.relative_to(RACINE).as_posix().encode() + f.read_bytes())
    return h.hexdigest()


def _pieces(tmp_path, reglages, carte):
    from commun.systeme import Systeme

    r = {**reglages, "ecran": dict(reglages["ecran"]), "cerveau": {**reglages["cerveau"], "choix": "regles"},
         "robot": {**reglages["robot"], "carte": carte}}
    systeme = Systeme(r, dossier_journal=tmp_path / "journal", acceleration=20.0, monde=monde_de_la_clinique())
    horloge = HorlogeDeDemonstration(bus=systeme.bus)
    porte = PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour)
    carnet = Carnet(horloge=horloge)
    listes = ListesDeSoin(porte, carnet)
    tableau = TableauDesTaches(porte, carnet, listes)
    return systeme, tableau, carnet, Coursier(systeme, tableau, listes, BADGES["robot-r1"], attente_humain_s=0.25)


def _noms(systeme, type_):
    return [e.donnees["action"]["nom"] for e in systeme.bus.historique if e.type == type_ and e.donnees.get("action")]


# ---------------------------------------------------------------------------------------------- la carte
def test_la_deuxieme_carte_un_robot_a_roues_sans_bras_avec_un_plateau():
    carte = CarteIdentite.charger(CARTE)
    assert carte.genre == "roues" and carte.vrai_robot is False
    assert carte.sait("se_deplacer") and not any(carte.sait(a) for a in BRAS)  # il porte, il ne saisit pas, pas d'écran
    humanoide = CarteIdentite.charger(CARTE.with_name("humanoide.yaml"))
    assert 0 < carte.limites.vitesse_max_m_s < humanoide.limites.vitesse_max_m_s  # il roule plus lentement
    assert carte.limites.portee_max_m == 0 and carte.limites.charge_max_kg > 0
    texte = CARTE.read_text(encoding="utf-8")
    assert texte.count("à vérifier") >= 3 and "plateau" in yaml.safe_load(texte)["remarques"]


# ---------------------------------------------------------------------------------------------- le cerveau s'adapte
def test_le_coussin_sur_le_plateau_deux_demandes_a_un_humain_et_jamais_de_bras(tmp_path, reglages):
    systeme, tableau, carnet, coursier = _pieces(tmp_path, reglages, "plateau")
    tache = tableau.demander(SOIGNANT, "p01", "il manque le grand coussin", liste="installation", numero=4)["tache"]

    async def scene():
        await systeme.demarrer()
        try:
            course = asyncio.create_task(coursier.faire(tache["id"]))
            attentes = []
            for _ in range(2):  # deux fois, un humain répond « c'est fait »
                for _ in range(2000):
                    actuelle = tableau.tache(tache["id"])
                    if actuelle.get("attend") and actuelle["attend"] not in attentes:
                        break
                    await asyncio.sleep(0.005)
                attentes.append(actuelle["attend"])
                assert coursier.confirmer(tache["id"], SOIGNANT) is True
            return await course, attentes
        finally:
            await systeme.arreter()

    fin, attentes = lancer(scene())
    assert fin["etat"] == "livrée" and fin["remise"] == "prise par un humain sur le plateau"
    assert "pose" in attentes[0] and "plateau" in attentes[0] and "prend" in attentes[1]
    assert _noms(systeme, "action_demarree") == ["se_deplacer", "parler", "se_deplacer", "parler"]
    demandes = _noms(systeme, "gardien_decision")
    assert not any(a in BRAS for a in demandes)  # jamais une tâche qui demande un bras, même refusée
    assert demandes == ["se_deplacer", "parler", "se_deplacer", "parler"]  # chaque geste a d'abord eu son « oui »
    dits = [e.donnees["action"]["parametres"]["texte"] for e in systeme.bus.historique
            if e.type == "action_demarree" and e.donnees["action"]["nom"] == "parler"]
    assert "grand coussin" in dits[0] and "plateau" in dits[0] and "Prenez" in dits[1]
    etats = [l["donnees"]["etat"] for l in carnet.lignes("tâche") if l["donnees"]["id"] == tache["id"]]
    assert etats[0] == "demandée" and etats[-1] == "livrée" and "échouée" not in etats
    point = {p["numero"]: p for p in coursier.listes.liste(SOIGNANT, "p01", "installation")["points"]}[4]
    assert point["etat"] == "fait" and point["comment"] == "livraison du robot"


def test_si_personne_ne_pose_l_objet_la_tache_n_est_pas_livree_et_le_dit(tmp_path, reglages):
    systeme, tableau, _, coursier = _pieces(tmp_path, reglages, "plateau")
    tache = tableau.demander(SOIGNANT, "p01", "une couverture")["tache"]

    async def scene():
        await systeme.demarrer()
        try:
            return await coursier.faire(tache["id"])  # personne ne confirme
        finally:
            await systeme.arreter()

    fin = lancer(scene())
    assert fin["etat"] == "échouée" and "personne" in fin["pourquoi"] and "plateau" in fin["pourquoi"]
    assert _noms(systeme, "action_demarree") == ["se_deplacer", "parler"]  # il n'est pas parti vers la chambre à vide


def test_seul_un_humain_de_l_equipe_confirme_et_seulement_quand_le_robot_attend(tmp_path, reglages):
    _, tableau, _, coursier = _pieces(tmp_path, reglages, "plateau")
    tache = tableau.demander(SOIGNANT, "p01", "une couverture")["tache"]
    assert coursier.confirmer(tache["id"], SOIGNANT) is False  # le robot n'attend rien
    with pytest.raises(Exception):
        coursier.confirmer(tache["id"], BADGES["robot-r1"])
    with pytest.raises(Exception):
        coursier.confirmer(tache["id"], BADGES["patient-p01"])


def test_un_objet_trop_lourd_pour_le_plateau_passe_a_un_humain(tmp_path, reglages, monkeypatch):
    systeme, tableau, _, coursier = _pieces(tmp_path, reglages, "plateau")
    systeme.monde.objet("couverture").poids_kg = 9.0  # plus que la charge de la carte
    tache = tableau.demander(SOIGNANT, "p01", "une couverture")["tache"]

    async def scene():
        await systeme.demarrer()
        try:
            return await coursier.faire(tache["id"])
        finally:
            await systeme.arreter()

    fin = lancer(scene())
    assert fin["sorte"] == "humain" and "trop lourd" in fin["pourquoi_un_humain"]
    assert _noms(systeme, "action_demarree") == []


# ---------------------------------------------------------------------------------------------- les deux sortes de robot
def test_l_etape_du_coussin_reussit_avec_le_robot_a_plateau_et_le_cerveau_n_a_pas_change():
    """Avec le robot à bras : c'est l'essai de T07 (test_course_du_robot.py), toujours là. Ici : le robot à plateau."""
    avant = _empreinte()
    with repetition.variation({"robot": "plateau"}):
        resultat = repetition.CONTROLES[8]()
    assert resultat.reussie is True, resultat.detail
    assert resultat.etiquette == "FAUX ROBOT"
    for mot in ("plateau", "un humain pose", "un humain prend", "faits par le programme", "0 geste de bras"):
        assert mot in resultat.detail, mot
    assert _empreinte() == avant  # aucun fichier du cerveau n'a changé entre les deux sortes de robot
    assert (RACINE / "briques/clinique/tests/test_course_du_robot.py").read_text(encoding="utf-8").count("def test_l_etape_8_de_la_grande_repetition")


def test_rien_n_est_ecrit_en_dur_pour_ce_robot_dans_le_cerveau():
    """Le cerveau choisit d'après ce que la carte sait faire, jamais d'après le nom ou la sorte du robot."""
    for fichier in CERVEAU:
        texte = fichier.read_text(encoding="utf-8")
        for mot in ("faux-plateau", "faux-humanoide", '"roues"', "'roues'", "plateau.yaml"):
            assert mot not in texte, (fichier.name, mot)
        if fichier.parent.name == "clinique":  # dans la clinique, aucune décision d'après la sorte du robot
            for mot in ("carte.genre", "carte().genre", ".genre =="):
                assert mot not in texte, (fichier.name, mot)
    assert "sait(" in (RACINE / "briques/clinique/coursier.py").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------------------------- le bouton de l'humain
def test_le_bouton_c_est_fait_est_sur_l_ecran_du_soignant_quand_le_robot_attend(tmp_path, reglages):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from briques.clinique.ecrans import brancher_ecrans
    from commun.systeme import Systeme

    r = {**reglages, "ecran": dict(reglages["ecran"]), "cerveau": {**reglages["cerveau"], "choix": "regles"},
         "robot": {**reglages["robot"], "carte": "plateau"}}
    systeme = Systeme(r, dossier_journal=tmp_path / "journal", acceleration=20.0, monde=monde_de_la_clinique())
    horloge = HorlogeDeDemonstration(bus=systeme.bus)
    app = FastAPI()
    clinique = brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                               carnet=Carnet(horloge=horloge), systeme=systeme, code_equipe="x")
    client = TestClient(app)
    tache = clinique.taches.demander(SOIGNANT, "p01", "une couverture")["tache"]
    assert "C'est fait" not in client.get("/clinique/soignant", params={"badge": SOIGNANT.id}).text
    # le robot attend : la ligne de la tâche le dit, avec le bouton
    clinique.taches.changer_etat(BADGES["robot-r1"], tache["id"], "en route", robot="robot-r1",
                                 attend="un humain pose « couverture » sur le plateau du robot")
    clinique.coursier._attentes[tache["id"]] = asyncio.Event()
    page = client.get("/clinique/soignant", params={"badge": SOIGNANT.id}).text
    assert "un humain pose « couverture » sur le plateau du robot" in page and "C'est fait</button>" in page
    refus = client.post("/clinique/soignant/tache/confirmer", params={"badge": "patient-p01", "tache": tache["id"]}, follow_redirects=False)
    assert refus.status_code == 403 and not clinique.coursier._attentes[tache["id"]].is_set()
    ok = client.post("/clinique/soignant/tache/confirmer", params={"badge": SOIGNANT.id, "tache": tache["id"]}, follow_redirects=False)
    assert ok.status_code == 303 and clinique.coursier._attentes[tache["id"]].is_set()
    assert clinique.taches.tache(tache["id"])["confirme_par"] == SOIGNANT.id
