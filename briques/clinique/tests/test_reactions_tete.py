"""Quand Iris dit non, la tête fait « non » (demande de Hiba, 15.11.2026).

NON TESTÉ SUR VRAI ROBOT. Ces essais tournent sur la doublure du Reachy Mini et sur le faux robot : testé sur faux robot.
« Fini » veut dire :
- la réaction est ÉTEINTE par défaut : sans le réglage exprès, un refus ne lance rien ;
- allumée, AVEC LES RÈGLES DU PROJET : le gardien demande un humain pour un geste près d'une personne (il ne sait pas
  où est le robot), donc la réaction abandonne, ne laisse aucune demande en attente à l'écran, et le note ;
- allumée, avec des règles D'ESSAI où le geste est permis sans accord (un fichier de règles fabriqué pour l'essai, qui
  imite une décision que seule Hiba peut prendre) : un refus lance UN geste « non », par le gardien et la prise, avec
  son propre numéro de conversation ; la réaction ne se relance jamais elle-même et ne dit aucune phrase ;
- pendant un arrêt d'urgence : aucun geste ; un robot sans le geste « non » (le faux humanoïde) : rien ne change.
"""
import asyncio
import copy

import pytest

import yaml

from briques.b07_gardien.regles import CHEMIN_REGLES
from briques.clinique.reactions_tete import PREFIXE
from commun.systeme import Systeme, charger_reglages

ALLUMEE = {"non_de_la_tete": {"actif": True}}


def _regles_d_essai(tmp_path):
    """Un fichier de règles POUR L'ESSAI SEULEMENT : le geste est retiré de la règle des personnes.
    Dans le projet, seule Hiba (avec le responsable sécurité) peut décider cela ; regles.yaml n'est pas touché."""
    regles = yaml.safe_load(CHEMIN_REGLES.read_text(encoding="utf-8"))
    (regle,) = [x for x in regles["regles"] if x["id"] == "distance_personnes"]
    assert "rejouer_geste" in regle["valeurs"]["actions"]  # la vraie règle du projet demande bien un humain pour un geste
    regle["valeurs"]["actions"] = [a for a in regle["valeurs"]["actions"] if a != "rejouer_geste"]
    fichier = tmp_path / "regles_d_essai.yaml"
    fichier.write_text(yaml.safe_dump(regles, allow_unicode=True), encoding="utf-8")
    return str(fichier)


def _systeme(tmp_path, adaptateur="reachy_mini", geste_permis=False, **interrupteurs):
    r = copy.deepcopy(charger_reglages())
    r["robot"].update({"adaptateur": adaptateur, "vrai_robot": False})
    if adaptateur == "faux_robot":
        r["robot"]["carte"] = "humanoide"
    r["cerveau"]["choix"] = "regles"
    r.setdefault("interrupteurs", {}).pop("non_de_la_tete", None)
    r["interrupteurs"].update(interrupteurs)
    if geste_permis:
        r.setdefault("gardien", {})["regles"] = _regles_d_essai(tmp_path)
    s = Systeme(r, dossier_journal=tmp_path, acceleration=10)
    evenements = []
    s.bus.abonner(evenements.append)
    return s, evenements


async def _dire(s, texte, langue="fr"):
    await asyncio.wait_for(s.chaine.traiter(texte, langue, confiance_ecoute=1.0, source="tablette"), 30)
    await s.reactions.attendre()


def _gestes_non(evenements, type_="action_demarree"):
    return [e for e in evenements if e.type == type_ and (e.donnees.get("action") or {}).get("nom") == "rejouer_geste"
            and (e.donnees.get("action") or {}).get("parametres", {}).get("nom") == "non"]


async def _fin_des_gestes(evenements, combien, max_s=30.0):
    for _ in range(int(max_s / 0.05)):
        if len(_gestes_non(evenements, "action_terminee")) >= combien:
            return
        await asyncio.sleep(0.05)
    raise AssertionError("le geste « non » ne finit pas")


def test_eteinte_par_defaut_un_refus_ne_lance_rien(tmp_path):
    async def scenario():
        s, evenements = _systeme(tmp_path)
        await s.demarrer()
        try:
            await _dire(s, "Prends le coussin")
            await asyncio.sleep(0.3)
            return s.reactions.actif, s.reactions.faites, [e for e in evenements if str(e.conversation or "").startswith(PREFIXE)]
        finally:
            await s.arreter()

    assert asyncio.run(scenario()) == (False, 0, [])


def test_allumee_avec_les_regles_du_projet_le_gardien_demande_un_humain_et_la_reaction_abandonne(tmp_path):
    async def scenario():
        s, evenements = _systeme(tmp_path, **ALLUMEE)
        await s.demarrer()
        try:
            await _dire(s, "Prends le coussin")
            await asyncio.sleep(0.3)
            return s.reactions.faites, s.gardien.demandes_en_attente(), evenements
        finally:
            await s.arreter()

    faites, en_attente, evenements = asyncio.run(scenario())
    assert faites == 0 and _gestes_non(evenements) == [] and en_attente == []  # rien ne part, rien ne traîne à l'écran
    (verdict,) = [e for e in evenements if e.type == "gardien_decision" and str(e.conversation or "").startswith(PREFIXE)]
    assert verdict.donnees["verdict"] == "humain"
    assert any(e.type == "note" and "pas de « non »" in e.donnees.get("texte", "") for e in evenements)


def test_un_refus_fait_faire_non_a_la_tete_par_le_gardien_et_la_prise_si_le_geste_est_permis(tmp_path):
    async def scenario():
        s, evenements = _systeme(tmp_path, geste_permis=True, **ALLUMEE)
        await s.demarrer()
        try:
            assert s.prise.carte().mention_test() == "testé sur faux robot"
            await _dire(s, "Prends le coussin")  # une tête n'a pas de bras : la chaîne dit un refus
            await _fin_des_gestes(evenements, 1)
            await _dire(s, "Regarde devant")  # une demande comprise et faite : pas de « non »
            await asyncio.sleep(0.3)
            return s.reactions.faites, evenements
        finally:
            await s.arreter()

    faites, evenements = asyncio.run(scenario())
    refus = [e for e in evenements if e.type == "reponse_dite" and e.donnees.get("genre") == "refus"]
    assert len(refus) == 1 and faites == 1
    (demarre,) = _gestes_non(evenements)
    (fini,) = _gestes_non(evenements, "action_terminee")
    assert demarre.conversation.startswith(PREFIXE) and demarre.conversation != refus[0].conversation
    assert fini.donnees["statut"] == "reussie"
    # le chemin de tout le monde : le gardien a rendu un verdict pour CETTE réaction, avant que la prise ne démarre
    verdicts = [e for e in evenements if e.type == "gardien_decision" and e.conversation == demarre.conversation]
    assert len(verdicts) == 1 and verdicts[0].donnees["verdict"] == "oui" and verdicts[0].numero < demarre.numero
    assert any(e.type == "note" and e.source == "reactions_tete" for e in evenements)


def test_pas_de_non_pendant_un_arret_d_urgence(tmp_path):
    async def scenario():
        s, evenements = _systeme(tmp_path, geste_permis=True, **ALLUMEE)
        await s.demarrer()
        try:
            await s.prise.arret_urgence()
            await _dire(s, "Prends le coussin")
            await asyncio.sleep(0.3)
            return s.reactions.faites, _gestes_non(evenements)
        finally:
            await s.arreter()

    assert asyncio.run(scenario()) == (0, [])


def test_un_robot_sans_le_geste_non_ne_change_pas(tmp_path):
    async def scenario():
        s, evenements = _systeme(tmp_path, adaptateur="faux_robot", **ALLUMEE)
        await s.demarrer()
        try:
            await _dire(s, "Va à la scène à 5 mètres par seconde")  # le gardien refuse
            await asyncio.sleep(0.3)
            refus = [e for e in evenements if e.type == "reponse_dite" and e.donnees.get("genre") == "refus"]
            return len(refus), s.reactions.faites, [e for e in evenements if str(e.conversation or "").startswith(PREFIXE)]
        finally:
            await s.arreter()

    assert asyncio.run(scenario()) == (1, 0, [])


def test_une_reaction_refusee_ne_relance_rien(tmp_path):
    """Deux refus coup sur coup : le deuxième « non » est refusé par la prise (robot occupé). Pas de boucle, pas de phrase en plus."""
    async def scenario():
        s, evenements = _systeme(tmp_path, geste_permis=True, **ALLUMEE)
        await s.demarrer()
        try:
            await _dire(s, "Prends le coussin")
            await _dire(s, "Prends le coussin")
            await _fin_des_gestes(evenements, 1)
            await asyncio.sleep(0.5)
            return s.reactions.faites, evenements
        finally:
            await s.arreter()

    faites, evenements = asyncio.run(scenario())
    dites = [e for e in evenements if e.type == "reponse_dite"]
    assert faites == 1 and len(_gestes_non(evenements)) == 1
    assert len([e for e in dites if e.donnees.get("genre") == "refus"]) == 2  # les deux refus dits à la personne, rien de plus
    assert not [e for e in dites if str(e.conversation or "").startswith(PREFIXE)]  # la réaction ne parle jamais
    assert any(e.type == "note" and "pas de « non »" in e.donnees.get("texte", "") for e in evenements)


def test_pas_de_non_quand_un_humain_a_la_main_ni_quand_la_personne_a_dit_non_elle_meme():
    """Relecture du 15.11.2026 : la réaction partait même quand un humain commandait par l'écran."""
    from types import SimpleNamespace

    from briques.clinique.reactions_tete import ReactionsDeLaTete

    class _Bus:
        def abonner(self, fonction, type_=None):
            self.fonction = fonction

    carte = SimpleNamespace(capacites=["arreter", "etat", "rejouer_geste"], gestes=["oui", "non"])
    prise = SimpleNamespace(carte=lambda: carte, arret_urgence_actif=False, robot="reachy-mini")

    def reagit(humain=False, **donnees) -> bool:
        async def essai():
            reactions = ReactionsDeLaTete(_Bus(), gardien=None, prise=prise, actif=True, humain_a_la_main=lambda: humain)
            reactions._dire_non = lambda apres: asyncio.sleep(0)  # on regarde seulement si une réaction est préparée
            reactions._sur_reponse(SimpleNamespace(donnees={"genre": "refus", **donnees}, conversation="abc"))
            return bool(reactions._taches)

        return asyncio.run(essai())

    assert reagit() is True
    assert reagit(humain=True) is False
    assert reagit(cle="confirmation_annulee") is False

