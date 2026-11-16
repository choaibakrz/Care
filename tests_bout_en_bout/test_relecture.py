"""Un test par constat de la relecture sécurité du 11.11.2026. Testé sur faux robot.

Chaque test reproduit l'attaque ou la panne trouvée par le relecteur, et vérifie qu'elle ne marche plus.
"""
from __future__ import annotations

import asyncio
import math

import pytest

from briques.b01_prise.actions import ActionDemandee
from briques.b01_prise.raisons import ActionRefusee
from conftest import lancer, robot


def _ticket_du_guichet(s, action):
    """Pour les tests : un ticket signé SANS passer par les vérifications du gardien."""
    return s.gardien._Gardien__guichet.emettre(action, s.prise.robot)


def _scenario(fabrique, carte="humanoide", acceleration=1.0):
    def deco(fonction):
        async def go():
            s = fabrique(carte, acceleration)
            await s.demarrer()
            try:
                await fonction(s)
            finally:
                await s.arreter()

        lancer(go())

    return deco


# --- 1. vitesse 0, NaN, négative ; distance énorme ; force nulle --------------------------------
@pytest.mark.parametrize("parametres,code", [
    ({"lieu": "cuisine", "vitesse": 0}, "valeur_invalide"),
    ({"lieu": "cuisine", "vitesse": math.nan}, "valeur_invalide"),
    ({"lieu": "cuisine", "vitesse": -0.6}, "valeur_invalide"),
    ({"lieu": "cuisine", "vitesse": math.inf}, "valeur_invalide"),
    ({"dx": 500.0}, "au_dessus_du_defaut"),
    ({"dx": math.nan}, "valeur_invalide"),
    ({"lieu": "cuisine", "vitesse": 10 ** 400}, "valeur_invalide"),  # entier géant (contre-relecture)
    ({"dx": 4.9, "dy": 4.9}, "au_dessus_du_defaut"),  # 6,9 m au total (contre-relecture)
])
def test_1_vitesses_et_distances_absurdes_refusees(fabrique_systeme, parametres, code):
    @_scenario(fabrique_systeme)
    async def _(s):
        d, ticket = await s.gardien.verifier(ActionDemandee(nom="se_deplacer", parametres=parametres), s.prise.carte())
        assert d.verdict == "non" and ticket is None and code in [r.code for r in d.raisons]
        # Et même avec un ticket signé (gardien contourné), la prise refuse aussi.
        with pytest.raises(ActionRefusee):
            await s.prise.executer(_ticket_du_guichet(s, ActionDemandee(nom="se_deplacer", parametres=parametres)))


def test_1_phrase_a_zero_metre_par_seconde_refusee(fabrique_systeme):
    @_scenario(fabrique_systeme)
    async def _(s):
        r = await s.chaine.traiter("Va à la cuisine à 0 m/s", "fr")
        assert r.verdict == "non" and r.statut_action is None
        assert not (await s.prise.etat()).en_mouvement


def test_1_la_prise_applique_aussi_les_plafonds_de_securite(fabrique_systeme):
    @_scenario(fabrique_systeme)
    async def _(s):  # 0,6 m/s : permis par la carte, interdit par le plafond de 0,3 m/s
        with pytest.raises(ActionRefusee) as e:
            await s.prise.executer(_ticket_du_guichet(s, ActionDemandee(nom="se_deplacer", parametres={"dx": 1, "vitesse": 0.6})))
        assert e.value.raisons[0].code == "au_dessus_du_defaut"


# --- 2. arrêt d'urgence pendant un réarmement ----------------------------------------------------
def test_2_un_arret_pendant_le_rearmement_n_est_pas_efface(fabrique_systeme):
    @_scenario(fabrique_systeme)
    async def _(s):
        await s.prise.arret_urgence()
        s.simulation.provoquer_panne("lenteur")  # le réarmement prend du temps
        rearmement = asyncio.create_task(s.prise.rearmer())
        await asyncio.sleep(0.05)
        await s.prise.arret_urgence(raison="pendant_le_rearmement")
        assert await rearmement is False
        assert s.prise.arret_urgence_actif and robot(s).arret_urgence_actif
        _, ticket = await s.gardien.verifier(ActionDemandee(nom="se_deplacer", parametres={"dx": 0.2}), s.prise.carte())
        with pytest.raises(ActionRefusee):
            await s.prise.executer(ticket)


# --- 4. coupure courte pendant une action ; « arreter » qui ne fait rien ---------------------------
def test_4_coupure_courte_on_garde_le_fil_sans_arret(fabrique_systeme):
    """0,25 s de coupure (Wi-Fi d'une halle) : la prise patiente, l'action continue, son état reste juste."""
    @_scenario(fabrique_systeme, acceleration=3.0)
    async def _(s):
        _, ticket = await s.gardien.verifier(ActionDemandee(nom="se_deplacer", parametres={"lieu": "table"}), s.prise.carte())
        suivi = await s.prise.executer(ticket)
        await asyncio.sleep(0.3)
        s.simulation.provoquer_panne("perte_liaison")
        await asyncio.sleep(0.25)
        s.simulation.reparer()
        fin = await s.prise.attendre(suivi.id, 20)
        assert fin.statut == "reussie"
        assert not any(e.type == "arret_urgence" for e in s.bus.historique)


def test_4_coupure_longue_action_perdue_de_vue_arret(fabrique_systeme):
    @_scenario(fabrique_systeme)
    async def _(s):
        _, ticket = await s.gardien.verifier(ActionDemandee(nom="se_deplacer", parametres={"lieu": "cuisine"}), s.prise.carte())
        suivi = await s.prise.executer(ticket)
        await asyncio.sleep(0.3)
        s.simulation.provoquer_panne("perte_liaison")
        await asyncio.sleep(1.4)
        s.simulation.reparer()
        fin = await s.prise.attendre(suivi.id, 3)
        await asyncio.sleep(0.3)
        assert fin.statut == "echouee"  # arrêté par son chien de garde, ou déclaré perdu par la prise
        assert not (await s.prise.etat()).en_mouvement, "le robot ne doit pas continuer seul"
        assert any(e.type == "arret_urgence" and e.donnees["raison"] == "action_perdue_de_vue" for e in s.bus.historique) \
            or "chien" in (fin.code_erreur or "")


def test_4_arreter_arrete_vraiment_le_robot(fabrique_systeme):
    @_scenario(fabrique_systeme)
    async def _(s):
        _, ticket = await s.gardien.verifier(ActionDemandee(nom="se_deplacer", parametres={"lieu": "cuisine"}), s.prise.carte())
        await s.prise.executer(ticket)
        await asyncio.sleep(0.3)
        r = await s.chaine.traiter("Stop !", "fr")
        assert r.statut_action == "reussie"
        avant = (await s.prise.etat()).position
        await asyncio.sleep(0.3)
        apres = await s.prise.etat()
        assert not apres.en_mouvement and apres.position == avant


# --- 5. « arreter » avec une précision en trop -----------------------------------------------------
def test_5_arreter_avec_des_precisions_n_est_jamais_refuse(fabrique_systeme):
    @_scenario(fabrique_systeme)
    async def _(s):
        _, ticket = await s.gardien.verifier(ActionDemandee(nom="se_deplacer", parametres={"lieu": "cuisine"}), s.prise.carte())
        await s.prise.executer(ticket)
        await asyncio.sleep(0.2)
        d, t = await s.gardien.verifier(ActionDemandee(nom="arreter", parametres={"raison": "danger"}), s.prise.carte())
        assert d.verdict == "oui"
        await s.prise.executer(t)
        # même un ticket signé avec des précisions inconnues ne bloque pas l'arrêt
        await s.prise.executer(_ticket_du_guichet(s, ActionDemandee(nom="arreter", parametres={"pourquoi": "x"})))
        await asyncio.sleep(0.2)
        assert not (await s.prise.etat()).en_mouvement


# --- 6. modifier l'action après la vérification ------------------------------------------------------
def test_6_modifier_l_action_apres_coup_ne_change_rien(fabrique_systeme):
    @_scenario(fabrique_systeme, acceleration=5.0)
    async def _(s):
        depart = (await s.prise.etat()).position
        _, ticket = await s.gardien.verifier(ActionDemandee(nom="se_deplacer", parametres={"dx": 0.2}), s.prise.carte())
        suivi = await s.prise.executer(ticket)
        suivi.action.parametres.update(dx=3.0, vitesse=0.6)
        ticket.action.parametres.update(dx=3.0, vitesse=0.6)
        fin = await s.prise.attendre(suivi.id, 10)
        arrivee = (await s.prise.etat()).position
        assert fin.statut == "reussie"
        assert math.dist((depart["x"], depart["y"]), (arrivee["x"], arrivee["y"])) < 0.25


# --- 8. deux actions longues en même temps -------------------------------------------------------------
def test_8_une_seule_action_longue_a_la_fois(fabrique_systeme):
    @_scenario(fabrique_systeme)
    async def _(s):
        _, t1 = await s.gardien.verifier(ActionDemandee(nom="se_deplacer", parametres={"lieu": "cuisine"}), s.prise.carte())
        await s.prise.executer(t1)
        _, t2 = await s.gardien.verifier(ActionDemandee(nom="se_deplacer", parametres={"lieu": "entree"}), s.prise.carte())
        with pytest.raises(ActionRefusee) as e:
            await s.prise.executer(t2)
        assert e.value.raisons[0].code == "robot_occupe"
        r = await s.chaine.traiter("Go to the door", "en")
        assert "busy" in r.reponses[-1]


def test_8_deux_demarrages_simultanes_un_seul_passe(fabrique_systeme):
    """Contre-relecture : deux executer() lancés en même temps, réseau lent. La prise seule doit trancher."""
    @_scenario(fabrique_systeme)
    async def _(s):
        s.simulation.provoquer_panne("lenteur")
        _, t1 = await s.gardien.verifier(ActionDemandee(nom="se_deplacer", parametres={"lieu": "cuisine"}), s.prise.carte())
        _, t2 = await s.gardien.verifier(ActionDemandee(nom="se_deplacer", parametres={"lieu": "entree"}), s.prise.carte())
        r = await asyncio.gather(s.prise.executer(t1), s.prise.executer(t2), return_exceptions=True)
        refus = [x for x in r if isinstance(x, ActionRefusee)]
        assert len(refus) == 1 and refus[0].raisons[0].code == "robot_occupe"  # refusé par la PRISE, pas par le robot


# --- 9. la fiche ne se remet jamais à zéro ---------------------------------------------------------------
def test_9_la_fiche_tient_apres_des_milliers_d_evenements(fabrique_systeme):
    @_scenario(fabrique_systeme)
    async def _(s):
        await s.chaine.traiter("Regarde la table", "fr")
        for i in range(6000):
            await s.bus.emettre("note", "test", texte=str(i))
        f = s.compteur.fiche()
        assert f.demandes == 1 and f.reussites == 1
        assert len(s.bus.historique) <= s.bus.taille_max_historique


# --- 10. écoute peu sûre comptée comme « non compris » ----------------------------------------------------
def test_10_ecoute_peu_sure_comptee(fabrique_systeme):
    @_scenario(fabrique_systeme)
    async def _(s):
        r = await s.chaine.traiter("Va à la cuisine", "fr", confiance_ecoute=0.2)
        assert r.decision.genre == "inconnu" and r.statut_action is None
        assert s.compteur.fiche().par_langue["fr"].non_comprises == 1


# --- 11. panne provoquée comptée une fois, à part ----------------------------------------------------------
def test_11_panne_provoquee_comptee_a_part(fabrique_systeme):
    from fastapi.testclient import TestClient

    from briques.b13_ecran.serveur import creer_app

    import time

    s = fabrique_systeme()
    s.reglages["ecran"]["code_equipe"] = "code-de-test"
    with TestClient(creer_app(s)) as client:
        client.post("/api/panne", json={"nom": "refus"}, headers={"X-Code-Equipe": "code-de-test"})
        f = client.get("/api/fiche").json()
        assert f["pannes_provoquees"] == 1 and f["pannes"] == 0  # « refus » ne se voit pas tant qu'on n'agit pas
        client.post("/api/panne", json={"nom": "perte_liaison"}, headers={"X-Code-Equipe": "code-de-test"})
        time.sleep(2.5)  # la prise constate la perte de liaison (délai de réponse 2 s)
        f = client.get("/api/fiche").json()
        assert f["pannes_provoquees"] == 2 and f["pannes"] == 1  # une provoquée, une constatée : chacune une fois
        assert client.post("/api/rearmer", headers={"X-Code-Equipe": "code-de-test"}).json()["ok"] is False  # liaison coupée : pas d'erreur 500


# --- 12. arrêt d'urgence sans effet : on le voit -------------------------------------------------------------
def test_12_arret_d_urgence_sans_effet_est_signale(fabrique_systeme):
    @_scenario(fabrique_systeme)
    async def _(s):
        _, ticket = await s.gardien.verifier(ActionDemandee(nom="se_deplacer", parametres={"lieu": "cuisine"}), s.prise.carte())
        await s.prise.executer(ticket)
        s.simulation.provoquer_panne("arret_ignore")
        await s.prise.arret_urgence()
        await asyncio.sleep(0.7)
        alerte = [e for e in s.bus.historique if e.type == "panne" and e.donnees.get("quoi") == "arret_urgence_non_confirme"]
        assert alerte and "PHYSIQUE" in alerte[0].donnees["consigne"]



# --- contre-relecture : déconnexion, double comptage, rebond DNS --------------------------------------
def test_deconnexion_arrete_le_chien_de_garde_meme_liaison_coupee(fabrique_systeme):
    async def go():
        s = fabrique_systeme()
        await s.demarrer()
        s.simulation.provoquer_panne("perte_liaison")
        await s.arreter()
        await asyncio.sleep(0.05)
        assert robot(s)._chien.cancelled() or robot(s)._chien.done()

    lancer(go())


def test_un_appui_un_arret_compte(fabrique_systeme):
    @_scenario(fabrique_systeme)
    async def _(s):
        _, ticket = await s.gardien.verifier(ActionDemandee(nom="se_deplacer", parametres={"lieu": "cuisine"}), s.prise.carte())
        await s.prise.executer(ticket)
        await asyncio.sleep(0.2)
        s.simulation.provoquer_panne("perte_liaison")
        await s.prise.arret_urgence()
        await asyncio.sleep(1.5)
        assert s.compteur.fiche().arrets_urgence == 1


def test_rebond_dns_refuse_sans_code(fabrique_systeme):
    from fastapi.testclient import TestClient

    from briques.b13_ecran.serveur import creer_app

    s = fabrique_systeme()
    s.reglages["ecran"]["code_equipe"] = "code-de-test"
    with TestClient(creer_app(s), client=("127.0.0.1", 5000)) as client:
        assert client.post("/api/rearmer", headers={"host": "site-pirate.example"}).status_code == 403
        assert client.post("/api/rearmer", headers={"host": "localhost:8000"}).status_code == 200
