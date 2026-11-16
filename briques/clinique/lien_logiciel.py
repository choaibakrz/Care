"""Le lien entre la clinique en boîte et le faux logiciel administratif (avenant 4, L02 ; seconde moitié).

Trois choses, et rien de plus :
- la clinique branche la page du faux logiciel (qui reste dans son dossier à part), et lui donne l'heure de l'horloge de
  démonstration ;
- chaque message que le faux logiciel écrit est noté dans la boîte noire, avec l'étiquette SIMULÉ : des numéros, pas de nom ;
- « Ouvrir l'assistant » : la page `/clinique/ouvrir` reçoit seulement le numéro du patient et le numéro du séjour.
  On choisit son badge comme d'habitude, et la porte de lecture décide de ce qu'on voit.

DIRE VRAI : notre système LIT ; il n'écrit rien dans le faux logiciel. Le traducteur (`traducteur.py`, L03) lit ses
messages ; la porte de lecture donne alors, en plus du faux dossier, les personnes présentes arrivées par message, avec
les mêmes règles de badges. Ces personnes n'ont que de l'administratif. Tout cela est SIMULÉ.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from faux_logiciel_admin import page as page_du_faux_logiciel
from faux_logiciel_admin.logiciel import ETIQUETTE, VERS_LUI, VERS_NOUS, FauxLogiciel

from .porte import AccesRefuse
from .traducteur import Traducteur

SOURCE = "clinique"
LIEN_FICHE = "/faux-logiciel/fiche"


def lien_vers_la_fiche(patient: str) -> str:
    """Pour l'écran de l'accueil : l'adresse de la fiche dans le faux logiciel. Le numéro seulement, jamais un nom."""
    return f"{LIEN_FICHE}?patient={patient}"


def dessiner_ouverture(clinique, patient: str, sejour: str, badge_id: str | None) -> str:
    from .ecrans import ECRANS, _carte, _e, _mots, lire_ecran

    tete = (f"<p class='ou'>Ouvert depuis le faux logiciel administratif (SIMULÉ) : numéro de patient {_e(patient)}, "
            f"numéro de séjour {_e(sejour)}. Aucun nom n'a été passé.</p>")
    if not badge_id:
        choix = "".join(f"<li><a class='bouton' href=\"/clinique/ouvrir?patient={_e(patient)}&amp;sejour={_e(sejour)}&amp;badge={_e(b.id)}\">"
                        f"{_e(b.libelle)}</a></li>" for b in clinique.badges.values())
        return tete + f"<h2>Choisissez votre badge</h2><ul class='liens'>{choix}</ul><p class='ou'>La porte de lecture décide de ce que ce badge voit.</p>"
    refus = ("<p class='refus'>Refus : ce badge ne donne pas accès à cette personne, ou notre système ne la connaît pas. "
             "Ce refus est noté au journal des accès.</p>")
    if clinique.lecteur_admin is not None:  # pour une personne arrivée par message : le numéro de séjour doit être le sien
        connue = next((p for p in clinique.lecteur_admin().vue() if p["numero_patient"] == patient), None)
        if connue is not None and connue["numero_sejour"] != sejour:
            return tete + refus
    badge = clinique.badges.get(badge_id)
    ecran = next((nom for nom, (_, role, _) in ECRANS.items() if badge is not None and role == badge.role), None)
    if badge is None or ecran is None:
        if badge is not None:  # un badge sans écran (robot, direction, assistant) : la porte note le refus
            try:
                clinique.porte.refuser(badge, "ouvrir depuis le faux logiciel", "ce badge n'a pas d'écran pour une personne")
            except AccesRefuse:
                pass
        return tete + refus
    vue = lire_ecran(clinique, ecran, badge)
    trouve = None if vue["refuse"] else next((p for p in vue["donnees"]["patients"] if p["id"] == patient), None)
    if trouve is None:
        try:
            clinique.porte.patient(badge, patient)  # la porte note elle-même le refus
        except AccesRefuse:
            pass
        return tete + refus
    carte = _carte(trouve, ecran, vue["donnees"]["jour"], _mots("fr"), vue["donnees"].get("listes"), badge.id)
    return (tete + f"<p>Badge : <b>{_e(badge.libelle)}</b> — <a href=\"/clinique/{ecran}?badge={_e(badge.id)}\">tout l'écran</a></p>" + carte
            + "<p class='ou'>Le numéro de séjour est contrôlé pour une personne arrivée par message ; pour les douze patients "
              "du faux dossier, notre système n'a pas de numéro de séjour : il est seulement affiché.</p>")


def brancher_faux_logiciel(app, clinique, protege: list, bus=None) -> None:
    from fastapi.responses import HTMLResponse

    from .ecrans import _page

    def heure() -> dict[str, Any]:
        etat = clinique.horloge.etat()
        return {"jour": etat["jour"], "heure": etat["heure"]}

    clinique.faux_logiciel = FauxLogiciel(heure=heure)
    clinique.messages_du_faux_logiciel = []
    lecteurs: dict[str, Traducteur] = {}

    def lecteur() -> Traducteur:
        """Le traducteur du dossier de messages du faux logiciel. Il LIT seulement ; chaque appel lit ce qui est nouveau."""
        dossier = Path(clinique.faux_logiciel.dossier) / VERS_NOUS
        if str(dossier) not in lecteurs:
            lecteurs.clear()
            lecteurs[str(dossier)] = Traducteur(dossier)
        actuel = lecteurs[str(dossier)]
        actuel.lire()
        return actuel

    clinique.lecteur_admin = lecteur
    if clinique.papiers is not None:  # la pré-admission (L04) : l'assistant prépare, une personne de l'accueil valide
        from .ecrans_pre_admission import brancher_pre_admission
        from .pre_admission import PreAdmissions

        pre_admissions = PreAdmissions(clinique.papiers, clinique.carnet, Path(clinique.faux_logiciel.dossier) / VERS_LUI,
                                       clinique.horloge, bus=bus)

        def pre() -> PreAdmissions:
            pre_admissions.dossier = Path(clinique.faux_logiciel.dossier) / VERS_LUI  # la seule chose qui part vers le faux logiciel
            pre_admissions.marquer_les_admises(lecteur())  # une admission revenue ? le carnet marque la proposition « admise »
            return pre_admissions

        clinique.pre_admissions = pre
        brancher_pre_admission(app, clinique, protege)
    clinique.porte.vue_admin = lambda: lecteur().vue()  # la porte donne la vue administrative, avec ses règles de badges

    async def apres_message(message: dict[str, Any]) -> None:
        note = {"quoi": "message_du_faux_logiciel", "etiquette": ETIQUETTE, "sorte": message["sorte"], "nom": message["nom"],
                "fichier": Path(message["fichier"]).name, "numero_patient": message["numero_patient"],
                "numero_sejour": message["numero_sejour"]}
        clinique.messages_du_faux_logiciel.append(note)
        if bus is not None:
            await bus.emettre("note", SOURCE, **note)
            await lecteur().noter_dans_la_boite(bus)  # le message vient d'être lu par le traducteur : c'est noté aussi
        if clinique.pre_admissions is not None:
            clinique.pre_admissions()  # la boucle : une admission qui répond à une pré-admission validée

    def pied() -> str:
        actuel = lecteur()
        return f"Côté clinique en boîte : {actuel.texte_du_delai()} — {actuel.compte()['texte']}."

    page_du_faux_logiciel.brancher(app, lambda: clinique.faux_logiciel, protege, lien_assistant="/clinique/ouvrir",
                                   apres_message=apres_message, pied=pied,
                                   apres_zero=lambda: clinique.pre_admissions and clinique.pre_admissions().remettre_a_zero())

    @app.get("/clinique/ouvrir", response_class=HTMLResponse)
    async def page_ouvrir(patient: str, sejour: str = "", badge: str | None = None):
        return _page("Clinique — Ouvrir depuis le faux logiciel", "<h1>Ouvrir l'assistant</h1>",
                     dessiner_ouverture(clinique, patient[:12], sejour[:12], badge), "")
