// Brique 11 — La main humaine, sur l'écran de l'équipe. Aucun fichier venu d'Internet.
// Chargé APRÈS ecran.js (brique 13) : réutilise api() (code d'équipe demandé une fois, gardé dans ce navigateur).
// Deux encadrés : « La main humaine » (je prends / je rends la main, ordres par boutons) et « Demandes à un humain »
// (accepter / refuser une demande du gardien, apprendre un mot, vote du public). Chaque ordre passe par le gardien.
"use strict";
(() => {
  const $m = (s, r = document) => r.querySelector(s);
  const lireMem = (cle) => { try { return localStorage.getItem(cle) || ""; } catch (e) { return ""; } };
  const garderMem = (cle, v) => { try { localStorage.setItem(cle, v); } catch (e) { /* tant pis */ } };
  const heure = (iso) => { try { return new Date(iso).toLocaleTimeString(); } catch (e) { return ""; } };

  // ------------------------------------------------------------ les deux encadrés (modèle fixe, sans donnée)
  const main = document.createElement("section");
  main.id = "main-humaine";
  main.className = "mh";
  main.innerHTML = `
    <h2>La main humaine</h2>
    <div id="mh-etat" class="mh-etat" role="status">…</div>
    <div id="mh-consigne" class="mh-consigne" hidden><strong>Le chef de démonstration demande qu'un humain prenne la main :</strong>
      <span></span></div>
    <div class="mh-ligne">
      <label class="mh-prenom">Votre prénom <input id="mh-qui" maxlength="40" autocomplete="off" placeholder="ex. Hiba"></label>
      <button type="button" id="mh-prendre" class="mh-gros">Je prends la main</button>
      <button type="button" id="mh-rendre" class="mh-gros" hidden>Je rends la main</button>
      <button type="button" id="mh-fait" class="mh-gros" hidden>Fait — je rends la main</button>
      <button type="button" id="mh-paspu" hidden>Pas pu — je rends la main</button>
      <button type="button" id="mh-liberer" hidden>Libérer la main</button>
    </div>
    <p class="mh-aide">Pendant la main humaine, la voix, la tablette et les agents ne commandent plus le robot :
      ils reçoivent « un humain pilote ». « Stop » et ARRÊT marchent toujours. Chaque bouton passe par le gardien.</p>
    <div id="mh-ordres" class="mh-ordres" hidden></div>
    <p id="mh-reponse" class="mh-reponse" aria-live="polite"></p>`;

  const aides = document.createElement("section");
  aides.id = "demandes-humain";
  aides.className = "mh";
  aides.innerHTML = `
    <h2>Demandes à un humain</h2>
    <ul id="dh-liste" class="dh-liste"><li class="dh-vide">Aucune demande en attente.</li></ul>
    <p id="dh-reponse" class="mh-reponse" aria-live="polite"></p>
    <details class="dh-mot"><summary>Apprendre un mot au robot (« frigo » = cuisine)</summary>
      <form id="dh-apprendre" class="mh-form">
        <input id="dh-mot" maxlength="40" placeholder="frigo" aria-label="Le mot">
        <select id="dh-langue" aria-label="Langue du mot"></select>
        <span>veut dire</span>
        <select id="dh-sens" aria-label="Ce que le mot veut dire"></select>
        <button>Apprendre</button>
      </form>
      <p id="dh-mots" class="mh-aide"></p>
    </details>
    <div id="dh-votes" hidden><h3>Vote du public</h3><div id="dh-votes-liste"></div></div>`;

  const cote = $m("main .cote");
  if (cote) cote.prepend(main, aides); else document.body.append(main, aides);

  let etatMH = null;
  let cleOrdres = "";
  let cleDemandes = null;  // null : à reconstruire au prochain état
  let finDemandes = {};  // numéro → heure de fin (ms, horloge de ce navigateur)

  // Le jeton remis à CETTE tablette quand elle prend la main : exigé pour donner des ordres et rendre la main.
  let jeton = lireMem("jeton_main_humaine");
  const garderJeton = (j) => { jeton = j || ""; garderMem("jeton_main_humaine", jeton); };

  $m("#mh-qui").value = lireMem("prenom_pilote");
  $m("#mh-qui").addEventListener("change", (e) => garderMem("prenom_pilote", e.target.value.trim()));
  const qui = () => $m("#mh-qui").value.trim();

  function dire(id, texte, classe) {
    const p = $m(id);
    p.textContent = texte || "";
    p.className = `mh-reponse ${classe || ""}`;
  }
  function erreur(r) {
    if (!r) return "pas de réponse du serveur";
    if (typeof r.detail === "string") return r.detail;
    if (Array.isArray(r.detail)) return "une précision n'est pas valable (" + r.detail.map((d) => (d.loc || []).slice(-1)[0]).join(", ") + ")";
    return "";
  }

  // ------------------------------------------------------------ prendre et rendre
  async function prendre() {
    if (!qui()) { dire("#mh-reponse", "Écrivez d'abord votre prénom (ou un rôle) : il est noté dans la boîte noire.", "non"); $m("#mh-qui").focus(); return; }
    garderMem("prenom_pilote", qui());
    const r = await api("/api/main_humaine/prendre", { qui: qui() });
    if (r && r.qui && r.jeton) {
      garderJeton(r.jeton);
      dire("#mh-reponse", `${r.qui} a la main (le robot s'arrête d'abord). La voix et les agents ne commandent plus le robot.`, "ok");
      montrer(r);
    } else dire("#mh-reponse", erreur(r) || "refusé", "non");
  }
  async function rendre(fait, forcer) {
    const corps = { qui: qui(), jeton };
    if (fait !== undefined) corps.fait = fait;
    if (forcer) corps.forcer = true;
    const r = await api("/api/main_humaine/rendre", corps);
    if (r && r.qui === null) {
      garderJeton("");
      dire("#mh-reponse", forcer ? "Main libérée (noté dans la boîte noire) : le robot écoute de nouveau la voix et les agents."
        : "Main rendue : le robot écoute de nouveau la voix et les agents.", "ok");
      montrer(r);
    } else dire("#mh-reponse", erreur(r) || "refusé", "non");
  }
  // « Libérer la main » (la tablette du pilote est perdue ou éteinte) : deux clics, pour ne pas le faire par erreur.
  const liberer = $m("#mh-liberer");
  liberer.addEventListener("click", () => {
    if (liberer.dataset.arme !== "1") {
      liberer.dataset.arme = "1";
      liberer.textContent = "Confirmer : libérer la main (noté)";
      setTimeout(() => { liberer.dataset.arme = ""; liberer.textContent = "Libérer la main"; }, 5000);
      return;
    }
    liberer.dataset.arme = ""; liberer.textContent = "Libérer la main";
    rendre(undefined, true);
  });
  $m("#mh-prendre").addEventListener("click", prendre);
  $m("#mh-rendre").addEventListener("click", () => rendre());
  $m("#mh-fait").addEventListener("click", () => rendre(true));
  $m("#mh-paspu").addEventListener("click", () => rendre(false));

  // ------------------------------------------------------------ les ordres par boutons
  function champ(p, nomAction) {
    if (p.choix) {
      const s = document.createElement("select");
      s.name = p.nom; s.setAttribute("aria-label", p.nom);
      const vide = !p.obligatoire || nomAction === "se_deplacer";
      if (vide) s.append(new Option(`${p.nom} : —`, ""));
      for (const c of p.choix) s.append(new Option(c.texte, c.valeur));
      return s;
    }
    const i = document.createElement("input");
    i.name = p.nom;
    i.type = p.type === "nombre" ? "number" : "text";
    if (p.type === "nombre") { i.step = "any"; i.inputMode = "decimal"; i.className = "mh-nombre"; }
    else i.maxLength = 200;
    i.placeholder = p.nom + (p.unite ? ` (${p.unite})` : "");
    i.title = p.explication || p.nom;
    i.setAttribute("aria-label", i.placeholder);
    return i;
  }
  function construireOrdres(actions) {
    const boite = $m("#mh-ordres");
    boite.replaceChildren();
    for (const a of actions) {
      const f = document.createElement("form");
      f.className = `mh-form mh-action${a.nom === "arreter" ? " mh-arreter" : ""}`;
      f.dataset.nom = a.nom;
      const t = document.createElement("span");
      t.className = "mh-nom"; t.textContent = a.texte;
      f.append(t);
      for (const p of a.parametres) f.append(champ(p, a.nom));
      const b = document.createElement("button");
      b.textContent = a.nom === "arreter" ? "S'arrêter" : "Envoyer";
      f.append(b);
      f.addEventListener("submit", (ev) => { ev.preventDefault(); envoyer(f); });
      boite.append(f);
    }
  }
  async function envoyer(f) {
    const parametres = {};
    for (const el of f.querySelectorAll("input, select")) {
      const v = el.value.trim();
      if (v === "") continue;
      parametres[el.name] = el.type === "number" ? Number(v) : v;
    }
    const langue = ($m("#langue") && $m("#langue").value) || null;
    dire("#mh-reponse", "… envoyé au gardien", "");
    const r = await api("/api/main_humaine/ordre", { nom: f.dataset.nom, parametres, qui: qui(), langue, jeton });
    if (!r || !r.sorte) { dire("#mh-reponse", erreur(r) || "refusé", "non"); return; }
    const robot = (r.reponses || []).join(" ");
    if (r.sorte === "parti") dire("#mh-reponse", `✔ Le gardien a dit oui : ${r.action_texte}. Le robot : « ${robot} »`, "ok");
    else if (r.sorte === "humain") dire("#mh-reponse", `✋ Le gardien demande l'accord d'un humain (n° ${r.numero_demande || "?"}) : voir « Demandes à un humain ». ${robot}`, "attention");
    else if (r.sorte === "oublie") dire("#mh-reponse", "· Rien n'est parti : la main a changé, ou un « stop » est passé pendant la vérification.", "non");
    else dire("#mh-reponse", `⛔ Refusé : ${r.action_texte}. ${robot}`, "non");
  }

  // ------------------------------------------------------------ demandes à un humain
  function construireDemandes(demandes) {
    const ul = $m("#dh-liste");
    ul.replaceChildren();
    finDemandes = {};
    if (!demandes.length) {
      const li = document.createElement("li"); li.className = "dh-vide"; li.textContent = "Aucune demande en attente.";
      ul.append(li); return;
    }
    for (const d of demandes) {
      finDemandes[d.numero] = Date.now() + (d.reste_s || 0) * 1000;
      const li = document.createElement("li");
      li.className = "dh-demande"; li.dataset.numero = d.numero;
      const quoi = document.createElement("strong"); quoi.textContent = d.action_texte;
      const pourquoi = document.createElement("span"); pourquoi.className = "dh-pourquoi"; pourquoi.textContent = d.raisons_texte;
      const detail = document.createElement("span"); detail.className = "dh-detail";
      detail.textContent = `demandé par ${d.demandeur_texte} · n° ${d.numero} · `;
      const reste = document.createElement("span"); reste.className = "dh-reste"; detail.append(reste);
      const oui = document.createElement("button"); oui.textContent = "Accepter"; oui.className = "dh-oui";
      const non = document.createElement("button"); non.textContent = "Refuser"; non.className = "dh-non";
      oui.addEventListener("click", () => repondre(d.numero, true));
      non.addEventListener("click", () => repondre(d.numero, false));
      const boutons = document.createElement("span"); boutons.className = "dh-boutons"; boutons.append(oui, non);
      li.append(quoi, pourquoi, detail, boutons);
      ul.append(li);
    }
    compteARebours();
  }
  function compteARebours() {
    for (const li of document.querySelectorAll("#dh-liste .dh-demande")) {
      const s = Math.max(0, Math.round((finDemandes[li.dataset.numero] - Date.now()) / 1000));
      $m(".dh-reste", li).textContent = s > 0 ? `reste ${s} s` : "trop ancienne";
    }
  }
  async function repondre(numero, accepte) {
    const r = await api("/api/aide/repondre", { numero, accepte, qui: qui() || "écran" });
    if (r && r.ok && r.resultat) {
      const res = r.resultat;
      const robot = (res.reponses || []).join(" ");
      if (!accepte) dire("#dh-reponse", `Refusé par un humain. ${robot}`, "");
      else if (res.verdict === "oui") dire("#dh-reponse", `Accepté ; le gardien a tout revérifié : oui. Le robot : « ${robot} »`, "ok");
      else dire("#dh-reponse", `Accepté, mais le gardien a revérifié et refuse : ${robot}`, "non");
    } else dire("#dh-reponse", erreur(r) || "Demande trop ancienne, ou effacée par un « stop » : rien n'est parti.", "non");
    cleDemandes = null; rafraichirMH();
  }

  // ------------------------------------------------------------ apprendre un mot, vote du public
  function remplirChoix(select, paires) {
    if (select.options.length) return;
    for (const [v, t] of paires) select.append(new Option(t, v));
  }
  $m("#dh-apprendre").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const mot = $m("#dh-mot").value.trim();
    if (!mot) return;
    const r = await api("/api/aide/apprendre", { mot, langue: $m("#dh-langue").value, sens: $m("#dh-sens").value, qui: qui() || "écran" });
    if (r && r.ok) { dire("#dh-reponse", `Appris : « ${r.mot.mot} » veut dire ${r.mot.sens}.`, "ok"); $m("#dh-mot").value = ""; }
    else dire("#dh-reponse", `Mot refusé : ${erreur(r)}`, "non");
    rafraichirMH();
  });
  function construireVotes(votes) {
    const boite = $m("#dh-votes-liste");
    boite.replaceChildren();
    for (const v of votes) {
      const f = document.createElement("form"); f.className = "mh-form dh-vote";
      const q = document.createElement("strong"); q.textContent = v.question; f.append(q);
      for (const [id, c] of Object.entries(v.choix || {})) {
        const l = document.createElement("label"); l.textContent = c.texte + " ";
        const n = document.createElement("input"); n.type = "number"; n.min = "0"; n.step = "1"; n.value = "0"; n.name = id; n.className = "mh-nombre";
        l.append(n); f.append(l);
      }
      const b = document.createElement("button"); b.textContent = "Appliquer le vote"; f.append(b);
      f.addEventListener("submit", async (ev) => {
        ev.preventDefault();
        const resultats = {};
        for (const n of f.querySelectorAll("input")) resultats[n.name] = parseInt(n.value || "0", 10) || 0;
        const r = await api("/api/gardien/vote", { vote: v.id, resultats, qui: "vote du public" });
        if (r && r.ok) dire("#dh-reponse", r.change ? `Vote appliqué : ${r.phrase}` : "Égalité : rien ne change.", "ok");
        else dire("#dh-reponse", `Vote refusé : ${erreur(r)}`, "non");
      });
      boite.append(f);
    }
  }

  // ------------------------------------------------------------ montrer l'état
  function montrer(e) {
    etatMH = { ...(etatMH || {}), ...e };
    e = etatMH;
    const a = !!e.qui;
    const moi = a && !!e.a_moi;  // cette tablette a-t-elle la main (son jeton) ?
    if (!a && jeton) garderJeton("");  // la main a été rendue ou libérée ailleurs : ce jeton ne sert plus
    const etat = $m("#mh-etat");
    if (a) {
      etat.textContent = `👤 ${e.qui} a la main ${moi ? "" : "sur une autre tablette "}depuis ${heure(e.depuis)} ` +
        `(${Math.round(e.duree_s || 0)} s, ${e.ordres} ordre(s)). ` +
        "La voix, la tablette et les agents ne commandent plus le robot (sauf « stop »).";
    } else if (e.annoncee) {
      etat.textContent = `Main humaine annoncée par le chef de démonstration : ${e.annoncee.qui} (la voix n'est pas coupée).`;
    } else {
      etat.textContent = "Le robot écoute la voix, la tablette et les agents (toujours sous le gardien).";
    }
    etat.className = `mh-etat${a ? " actif" : ""}`;
    main.classList.toggle("actif", a);
    const c = $m("#mh-consigne");
    c.hidden = !e.consigne;
    if (e.consigne) $m("span", c).textContent = e.consigne.texte;
    $m("#mh-prendre").hidden = a;
    $m("#mh-rendre").hidden = !moi || !!e.consigne;
    $m("#mh-fait").hidden = !moi || !e.consigne;
    $m("#mh-paspu").hidden = !moi || !e.consigne;
    $m("#mh-liberer").hidden = !a || moi;
    $m("#mh-ordres").hidden = !moi;
    if (e.actions) {
      const cle = JSON.stringify(e.actions);
      if (cle !== cleOrdres) { cleOrdres = cle; construireOrdres(e.actions); }
    }
    if (e.demandes) {
      const cle = e.demandes.map((d) => d.numero).join(",");
      if (cle !== cleDemandes) { cleDemandes = cle; construireDemandes(e.demandes); }
    }
    if (e.langues) remplirChoix($m("#dh-langue"), Object.entries(e.langues));
    if (e.sens_possibles) remplirChoix($m("#dh-sens"), e.sens_possibles.map((s) => [s.valeur, s.texte]));
    if (e.mots_appris) {
      $m("#dh-mots").textContent = e.mots_appris.length
        ? "Mots appris : " + e.mots_appris.map((m) => `« ${m.mot} » (${m.langue}) = ${m.sens}`).join(" · ") : "Aucun mot appris pour l'instant.";
    }
    const votes = e.vote_public && (e.votes || []).length;
    $m("#dh-votes").hidden = !votes;
    if (votes && !$m("#dh-votes-liste").children.length) construireVotes(e.votes);
  }

  async function rafraichirMH() {
    try {
      const r = await fetch("/api/main_humaine", { headers: { "X-Jeton-Main": jeton || "" } });
      if (r.ok) montrer(await r.json());
    } catch (e) { /* le serveur redémarre */ }
  }
  rafraichirMH();
  setInterval(rafraichirMH, 1000);
  setInterval(compteARebours, 1000);
})();
