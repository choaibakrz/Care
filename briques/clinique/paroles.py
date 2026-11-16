"""La parole des soignants (avenant jury, J06 ; J06b-b, réponse de Hiba à Q26 : A).

    /clinique/ce-qu-on-nous-a-dit     la page : les paroles du fichier de l'équipe, ou « Aucune parole recueillie… »

« Avez-vous passé du temps avec des soignants ? » Aujourd'hui, la réponse est non. Cette pièce prépare la place pour
leurs mots, SANS RIEN INVENTER.
- Deux étiquettes pour tout ce qu'un écran dit du travail des gens : DIT PAR UN SOIGNANT, ou HYPOTHÈSE.
- Tant qu'aucune parole n'est recueillie, tout est HYPOTHÈSE.
- Le guide d'entretien est dans docs/projet/GUIDE_ENTRETIEN.md (une page à imprimer).
- Les paroles viennent d'UN fichier, rempli à la main par l'équipe et jamais envoyé vers GitHub
  (`journal/clinique/PAROLES_DES_SOIGNANTS.md`), lu par la pièce de lecture `paroles_fichier.py` : cette page n'ouvre
  aucun fichier elle-même. Tant que l'équipe n'a rien écrit : aucune parole.
- Une parole recueillie ne valide pas une liste de soin : ce que les écrans disent du travail reste HYPOTHÈSE.
On n'écrit jamais ce qu'un soignant « dirait ».
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

ETIQUETTES = ("DIT PAR UN SOIGNANT", "HYPOTHÈSE")
AUCUNE = "Aucune parole recueillie pour l'instant. Ce que nous disons du travail des soignants est une hypothèse."
RAPPEL = "Pas de nom. Pas un mot sur un patient."


def paroles_recueillies() -> int:
    """Le nombre de paroles gardées dans le fichier de l'équipe (lu par paroles_fichier). Pas de fichier : zéro."""
    from . import paroles_fichier

    return len(paroles_fichier.lire()["paroles"])


def etiquette_du_travail() -> str:
    """L'étiquette de ce qu'un écran dit du travail des gens (une liste de soin, l'ordre des gestes) : HYPOTHÈSE.
    Une parole recueillie dit ce qu'UNE personne a dit ; elle ne valide pas la liste. Seule une validation de la liste
    elle-même par des soignants pourrait changer cette étiquette : pas fait."""
    return ETIQUETTES[1]


def mention_hypothese() -> str:
    """La petite phrase à poser sur un écran qui décrit le travail des soignants (une liste de soin, par exemple)."""
    return (f"{etiquette_du_travail()} : cette liste dit ce que nous supposons du travail des soignants ; "
            "aucun soignant ne nous l'a dit.")


def brancher_paroles(app: FastAPI, clinique) -> None:
    from .ecrans import _e, _heure_html, _page

    from . import paroles_fichier

    @app.get("/clinique/ce-qu-on-nous-a-dit", response_class=HTMLResponse)
    async def page_paroles():
        lu = paroles_fichier.lire()
        tete = f"<h1>Ce qu'on nous a dit</h1><span class='heure'>{_heure_html(clinique.horloge.etat())}</span>"
        milieu = (f"<p class='ou'><b>{_e(RAPPEL)}</b></p>"
                  f"{paroles_fichier.dessiner(lu)}"
                  "<article><h3>Deux étiquettes</h3><ul>"
                  f"<li><b>{_e(ETIQUETTES[0])}</b> : une personne qui fait ce travail nous l'a dit, et elle est d'accord pour "
                  "qu'on le cite, sans son nom.</li>"
                  f"<li><b>{_e(ETIQUETTES[1])}</b> : c'est nous qui le supposons. Personne ne nous l'a dit.</li></ul>"
                  f"<p>Paroles recueillies : {len(lu['paroles'])}. Tout ce que nos écrans disent du travail des "
                  f"soignants (les listes de soin, les habitudes, l'ordre des gestes) porte l'étiquette "
                  f"<b>{_e(etiquette_du_travail())}</b>.</p></article>"
                  "<article><h3>Pour recueillir des paroles</h3><p>Le guide d'entretien, dix questions sur une page à imprimer : "
                  "<code>docs/projet/GUIDE_ENTRETIEN.md</code>, à la racine du dépôt. Rien n'est noté sans accord. Les paroles s'écrivent à la main "
                  "dans <code style='overflow-wrap:anywhere'>journal/clinique/PAROLES_DES_SOIGNANTS.md</code>, à partir du modèle "
                  "<code style='overflow-wrap:anywhere'>PAROLES_DES_SOIGNANTS.modele.md</code> ; ce fichier ne part jamais vers GitHub.</p></article>")
        return _page("Clinique — Ce qu'on nous a dit", tete, milieu)
