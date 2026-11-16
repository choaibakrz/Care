"""La clinique en boîte — T04, l'horloge de démonstration (cahier 5.3 et 6.8). Internet coupé, aucun modèle.

On vérifie : on saute au soir puis au lendemain ; la marque « temps accéléré » s'affiche ; la boîte noire reçoit
chaque saut, et la fiche de vérité de la clinique, calculée depuis la boîte noire, le note.
"""
from __future__ import annotations

import asyncio

import pytest

from briques.b12_boite_noire.journal import BoiteNoire, lire
from briques.clinique.fiche import fiche_clinique
from briques.clinique.horloge import HorlogeDeDemonstration, SautRefuse, reperes
from briques.clinique.porte import JournalDesAcces, PorteDeLecture, charger_badges
from commun.bus import Bus


class FauxTemps:
    """Le temps réel, que l'essai fait avancer à la main."""

    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def test_l_horloge_demarre_a_l_arrivee_sans_marque():
    h = HorlogeDeDemonstration()
    etat = h.etat()
    assert (etat["jour"], etat["heure"]) == (1, "09:00")
    assert etat["texte"] == "Jour 1 — 9 h 00"
    assert etat["temps_accelere"] is False and etat["marque"] == "" and etat["sauts"] == 0


def test_entre_deux_sauts_elle_avance_comme_une_vraie_horloge():
    temps = FauxTemps()
    h = HorlogeDeDemonstration(temps=temps)
    temps.t += 10 * 60
    assert h.etat()["heure"] == "09:10" and h.etat()["temps_accelere"] is False
    temps.t += 15 * 3600  # minuit passe : le jour change tout seul
    assert (h.etat()["jour"], h.etat()["heure"]) == (2, "00:10")


def test_on_saute_au_soir_puis_au_lendemain_et_la_marque_s_affiche():
    h = HorlogeDeDemonstration(temps=FauxTemps())
    asyncio.run(h.sauter("le soir"))
    etat = h.etat()
    assert (etat["jour"], etat["heure"]) == (1, "19:00")
    assert etat["temps_accelere"] is True and etat["marque"] == "temps accéléré"
    assert etat["texte"] == "Jour 1 — 19 h 00 · TEMPS ACCÉLÉRÉ"
    asyncio.run(h.sauter("le lendemain matin"))
    etat = h.etat()
    assert (etat["jour"], etat["heure"]) == (2, "07:30") and etat["sauts"] == 2
    assert h.jour() == 2


def test_les_heures_du_scenario_sont_toutes_la():
    attendu = {"arrivée": (1, "09:00"), "papiers": (1, "09:10"), "installation en chambre": (1, "10:00"),
               "questions du soir": (1, "19:00"), "résumé prêt": (2, "07:30"), "visite": (2, "08:00"),
               "tâche pour le thérapeute": (2, "08:05"), "panne d'un robot": (2, "08:10")}
    assert {nom: (r["jour"], r["heure"]) for nom, r in reperes().items()} == attendu
    h = HorlogeDeDemonstration(temps=FauxTemps())
    for nom in list(attendu)[1:]:
        asyncio.run(h.sauter(nom))
        assert (h.etat()["jour"], h.etat()["heure"]) == attendu[nom]
    assert h.etat()["sauts"] == 7


def test_le_soir_quand_il_est_deja_tard_c_est_le_soir_suivant():
    h = HorlogeDeDemonstration(heure="21:00", temps=FauxTemps())
    asyncio.run(h.sauter("le soir"))
    assert (h.etat()["jour"], h.etat()["heure"]) == (2, "19:00")


def test_on_ne_revient_pas_en_arriere_et_un_repere_inconnu_est_refuse():
    h = HorlogeDeDemonstration(temps=FauxTemps())
    asyncio.run(h.sauter("le lendemain matin"))
    with pytest.raises(SautRefuse):
        asyncio.run(h.sauter("papiers"))  # jour 1, 9 h 10 : c'est le passé
    with pytest.raises(SautRefuse):
        asyncio.run(h.sauter("la semaine des quatre jeudis"))
    assert h.etat()["sauts"] == 1 and (h.etat()["jour"], h.etat()["heure"]) == (2, "07:30")


def test_chaque_saut_part_sur_le_bus_avec_son_etiquette():
    bus = Bus()
    h = HorlogeDeDemonstration(bus=bus, temps=FauxTemps())
    asyncio.run(h.sauter("le soir"))
    (ev,) = [e for e in bus.historique if e.source == "horloge_clinique"]
    assert ev.type == "note" and ev.donnees["quoi"] == "saut_horloge"
    assert ev.donnees["etiquette"] == "temps accéléré"
    assert ev.donnees["de"] == {"jour": 1, "heure": "09:00"} and ev.donnees["vers"] == {"jour": 1, "heure": "19:00"}
    assert ev.donnees["repere"] == "le soir"


def test_la_fiche_de_verite_le_note_depuis_la_boite_noire(tmp_path):
    bus = Bus()
    boite = BoiteNoire(bus, tmp_path, nom="essai_horloge")
    h = HorlogeDeDemonstration(bus=bus, temps=FauxTemps())

    async def jouer():
        await h.sauter("le soir")
        await h.sauter("le lendemain matin")

    asyncio.run(jouer())
    boite.fermer()
    fiche = fiche_clinique(lire(boite.fichier))
    assert fiche["marque"] == "données inventées"
    assert fiche["temps_accelere"]["sauts"] == 2 and fiche["temps_accelere"]["marque"] == "temps accéléré"
    assert [(s["de"]["heure"], s["vers"]["heure"]) for s in fiche["temps_accelere"]["liste"]] == [
        ("09:00", "19:00"), ("19:00", "07:30")]
    assert all(s["heure_reelle"] for s in fiche["temps_accelere"]["liste"])


def test_sans_saut_la_fiche_dit_zero():
    fiche = fiche_clinique([])
    assert fiche["temps_accelere"] == {"sauts": 0, "marque": "", "liste": []}


def test_la_porte_de_lecture_suit_le_jour_de_l_horloge():
    h = HorlogeDeDemonstration(temps=FauxTemps())
    porte = PorteDeLecture(journal=JournalDesAcces(), jour=h.jour)
    accueil = charger_badges()["accueil"]
    assert [p["id"] for p in porte.patients(accueil)] == ["p01"]
    asyncio.run(h.sauter("le lendemain matin"))
    assert porte.patients(accueil) == []
