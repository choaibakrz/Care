"""L'accord humain donné d'avance pour quelques gestes de la main (décision de Hiba, 15.11.2026).

NON TESTÉ SUR VRAI ROBOT. Ces essais tournent sur la fausse main (doublure) : testé sur faux robot.
« Fini » veut dire :
- éteint par défaut : le gardien demande un humain et rien ne part ;
- allumé pour la main et ses gestes : le gardien demande toujours un humain (c'est dans le journal), la réponse « oui »
  est donnée d'avance, le gardien revérifie et le geste part par la prise ; le journal dit qui a répondu ;
- un geste qui n'est pas dans la liste, un autre robot, un réglage sans robot ou sans geste : pas d'accord d'avance ;
- pendant un arrêt d'urgence : pas d'accord d'avance.
"""
import asyncio
import copy

import pytest

from commun.systeme import Systeme, charger_reglages

QUI = "Hiba (accord d'avance, essai)"
ACCORD = {"actif": True, "robot": "leadtron-dh116", "gestes": ["preparer_la_main", "ouvrir_la_main"], "qui": QUI}


def _jouer(tmp_path, phrases, accord=None, adaptateur="leadtron_dh116", urgence=False):
    r = copy.deepcopy(charger_reglages())
    r["robot"].update({"adaptateur": adaptateur, "vrai_robot": False})
    r["cerveau"]["choix"] = "regles"
    r.setdefault("interrupteurs", {}).pop("accord_d_avance", None)
    if accord is not None:
        r["interrupteurs"]["accord_d_avance"] = accord

    async def scenario():
        s = Systeme(r, dossier_journal=tmp_path, acceleration=10)
        evenements = []
        s.bus.abonner(evenements.append)
        await s.demarrer()
        try:
            assert s.prise.carte().mention_test() == "testé sur faux robot"
            if urgence:
                await s.prise.arret_urgence()
            for texte in phrases:
                await asyncio.wait_for(s.chaine.traiter(texte, "fr", confiance_ecoute=1.0, source="tablette"), 30)
                await s.accord_d_avance.attendre()
                for _ in range(400):  # laisser le geste finir
                    if not any(e.type == "action_demarree" for e in evenements) or \
                            sum(e.type == "action_terminee" for e in evenements) >= sum(e.type == "action_demarree" for e in evenements):
                        break
                    await asyncio.sleep(0.05)
            return evenements, s.accord_d_avance.donnes, s.gardien.demandes_en_attente()
        finally:
            await s.arreter()

    return asyncio.run(scenario())


def _gestes(evenements, type_):
    return [(e.donnees.get("action") or {}).get("parametres", {}).get("nom") for e in evenements if e.type == type_
            and (e.donnees.get("action") or {}).get("nom") == "rejouer_geste"]


def test_eteint_par_defaut_le_gardien_demande_un_humain_et_rien_ne_part(tmp_path):
    evenements, donnes, en_attente = _jouer(tmp_path, ["Prépare la main"])
    assert donnes == 0 and _gestes(evenements, "action_demarree") == [] and len(en_attente) == 1
    assert [e.donnees["verdict"] for e in evenements if e.type == "gardien_decision"] == ["humain"]


def test_allume_pour_la_main_le_gardien_demande_toujours_puis_l_accord_d_avance_repond(tmp_path):
    evenements, donnes, en_attente = _jouer(tmp_path, ["Prépare la main"], accord=ACCORD)
    verdicts = [e.donnees["verdict"] for e in evenements if e.type == "gardien_decision"]
    assert verdicts[0] == "humain" and "oui" in verdicts[1:]  # le gardien a demandé, puis REVÉRIFIÉ et dit oui
    assert donnes == 1 and en_attente == []
    assert _gestes(evenements, "action_demarree") == ["preparer_la_main"]
    assert [e.donnees.get("statut") for e in evenements if e.type == "action_terminee"] == ["reussie"]
    assert any(e.type == "note" and e.source == "accord_d_avance" and QUI in e.donnees.get("texte", "") for e in evenements)
    assert any(e.type == "aide_demandee" for e in evenements)  # la demande reste écrite dans le journal


def test_un_geste_hors_de_la_liste_attend_toujours_un_humain(tmp_path):
    evenements, donnes, en_attente = _jouer(tmp_path, ["Tiens doucement"], accord=ACCORD)  # pas dans la liste d'ACCORD
    assert donnes == 0 and _gestes(evenements, "action_demarree") == [] and len(en_attente) == 1


@pytest.mark.parametrize("accord", [
    {**ACCORD, "robot": "un-autre-robot"}, {**ACCORD, "robot": ""}, {**ACCORD, "gestes": []},
    {**ACCORD, "actif": "oui"}, {**ACCORD, "actif": False}, {"actif": True}, "oui", None])
def test_un_reglage_incomplet_ou_pour_un_autre_robot_ne_donne_aucun_accord(tmp_path, accord):
    evenements, donnes, _ = _jouer(tmp_path, ["Prépare la main"], accord=accord)
    assert donnes == 0 and _gestes(evenements, "action_demarree") == []


def test_avec_un_autre_robot_dans_le_systeme_rien_ne_change(tmp_path):
    evenements, donnes, _ = _jouer(tmp_path, ["Secoue la tête"], accord=ACCORD, adaptateur="reachy_mini")
    assert donnes == 0 and _gestes(evenements, "action_demarree") == []


def test_pas_d_accord_d_avance_pendant_un_arret_d_urgence(tmp_path):
    evenements, donnes, _ = _jouer(tmp_path, ["Prépare la main"], accord=ACCORD, urgence=True)
    assert donnes == 0 and _gestes(evenements, "action_demarree") == []
