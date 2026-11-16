"""Brique 12 — boîte noire, fiche de vérité, rejeu. Testé sur faux robot."""
from __future__ import annotations

from briques.b12_boite_noire.fiche import calculer
from briques.b12_boite_noire.journal import lire
from briques.b12_boite_noire.rejeu import recit, rejouer
from commun.bus import Bus
from conftest import lancer

DEMO = [("Va à la cuisine", "fr"), ("Geh in die Küche", "de"), ("blabla", "en"), ("va", "fr"),
        ("Go to the stage at 9 meters per second", "en"), ("prends la bouteille", "fr"), ("oui", "fr")]
# Étape 4 : « la valise » est maintenant refusée par le gardien (objet interdit) ; la bouteille, loin du robot
# (il est à la cuisine), donne toujours un raté « hors de portée ».


def _demo(fabrique_systeme):
    async def scenario():
        s = fabrique_systeme()
        await s.demarrer()
        for texte, langue in DEMO:
            await s.chaine.traiter(texte, langue)
        await s.bus.emettre("pilotage_humain", "test", quoi="reprise")
        await s.bus.emettre("pilotage_humain", "test", quoi="rendu")
        await s.arreter()
        return s

    return lancer(scenario())


def test_chaque_evenement_est_garde_avec_l_heure(fabrique_systeme):
    s = _demo(fabrique_systeme)
    evs = lire(s.boite_noire.fichier)
    assert len(evs) == len(s.bus.historique) > 20
    assert all(e.heure and e.t for e in evs)
    types = {e.type for e in evs}
    assert {"parole_entendue", "demande_comprise", "gardien_decision", "action_demarree", "action_terminee",
            "reponse_dite", "question_posee", "session_debut", "session_fin"} <= types


def test_la_fiche_se_remplit_toute_seule(fabrique_systeme):
    s = _demo(fabrique_systeme)
    f = calculer(lire(s.boite_noire.fichier))
    assert f.mention == "testé sur faux robot"
    assert f.demandes == len(DEMO)
    assert f.reussites == 2 and f.rates == 1  # cuisine x2 ; bouteille hors de portée
    assert f.questions_posees == 1 and f.confirmations_demandees == 1  # « prends » demande un « oui »
    assert f.refus_gardien == 1  # 9 m/s : au-dessus de la limite de sécurité
    assert f.par_langue["en"].non_comprises == 1  # « blabla »
    assert f.temps_premiere_reponse.nb == len(DEMO)
    assert 0 <= f.part_humain_pct < 100


def test_le_rejeu_redonne_la_meme_fiche(fabrique_systeme):
    s = _demo(fabrique_systeme)
    evs = lire(s.boite_noire.fichier)
    bus = Bus()
    lancer(rejouer(evs, bus))
    assert [e.id for e in bus.historique] == [e.id for e in sorted(evs, key=lambda e: (e.t, e.numero))]
    assert calculer(bus.historique) == calculer(evs)
    assert any("cuisine" in l or "Küche" in l for l in recit(evs))


def test_une_ligne_abimee_ne_bloque_pas_la_lecture(fabrique_systeme):
    s = _demo(fabrique_systeme)
    with open(s.boite_noire.fichier, "a", encoding="utf-8") as f:
        f.write('{"type": "parole_ent')  # coupure de courant au milieu d'une ligne
    assert len(lire(s.boite_noire.fichier)) > 20
