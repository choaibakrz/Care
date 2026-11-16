// Brique 11 — la main humaine dans Chromium (Playwright pour Node, DÉJÀ installé), SANS Internet.
//   node navigateur_main_humaine.js http://127.0.0.1:PORT
// L'écran de l'équipe (« Je prends la main », ordres par boutons, demandes à un humain) et l'écran du jury (bandeau
// « un humain pilote ») sont ouverts en même temps. Toute adresse non locale est bloquée et notée.
// Dernière ligne écrite : un résultat JSON (lu par le test Python). Code 3 : navigateur indisponible (le test saute).
"use strict";

let chromium;
try {
  ({ chromium } = require("playwright"));
} catch (e) {
  console.log(JSON.stringify({ saute: "Playwright pour Node introuvable" }));
  process.exit(3);
}

const [, , base] = process.argv;
const LOCAUX = new Set(["127.0.0.1", "localhost", "[::1]"]);
const journal = { erreurs: [], exterieur: [] };
const verifs = {};

async function ouvrir(navigateur, chemin, options) {
  const contexte = await navigateur.newContext(options);
  const page = await contexte.newPage();
  page.on("pageerror", (e) => journal.erreurs.push(`${chemin} : ${e.message}`));
  page.on("console", (m) => { if (m.type() === "error") journal.erreurs.push(`${chemin} (console) : ${m.text()}`); });
  page.on("dialog", (d) => { journal.erreurs.push(`${chemin} : fenêtre inattendue « ${d.message()} »`); d.dismiss(); });
  await page.route("**/*", (route) => {
    const u = new URL(route.request().url());
    if (LOCAUX.has(u.hostname)) return route.continue();
    journal.exterieur.push(u.href);
    return route.abort();
  });
  await page.goto(base + chemin, { waitUntil: "load" });
  if (chemin === "/jury") await page.waitForFunction(() => document.body.dataset.pret === "1", null, { timeout: 20000 });
  else await page.waitForSelector("#main-humaine #mh-prendre", { state: "attached", timeout: 20000 });
  return { contexte, page };
}

const texteDe = (page, sel) => page.$eval(sel, (el) => el.textContent);
const attendreTexte = (page, sel, morceau, timeout = 20000) =>
  page.waitForFunction(([s, m]) => { const el = document.querySelector(s); return !!el && el.textContent.includes(m); },
    [sel, morceau], { timeout });

async function ordre(page, nom, valeurs) {
  const f = `#mh-ordres form[data-nom="${nom}"]`;
  for (const [champ, v] of Object.entries(valeurs)) {
    const sel = `${f} [name="${champ}"]`;
    if (await page.$eval(sel, (el) => el.tagName) === "SELECT") await page.selectOption(sel, v); else await page.fill(sel, v);
  }
  await page.click(`${f} button`);
}

async function tailles(page) {
  return page.evaluate(() => ({ largeur: document.documentElement.scrollWidth, fenetre_l: innerWidth,
    hauteur: document.documentElement.scrollHeight, fenetre_h: innerHeight }));
}

async function verifier(navigateur) {
  const equipe = await ouvrir(navigateur, "/", { viewport: { width: 1280, height: 900 } });
  const jury = await ouvrir(navigateur, "/jury", { viewport: { width: 1280, height: 720 } });
  const e = equipe.page, j = jury.page;
  verifs.bandeau_avant = await j.$eval("#bandeau-pilote", (el) => el.hidden);
  verifs.ordres_caches_avant = await e.$eval("#mh-ordres", (el) => el.hidden);

  // Sans prénom : la page le demande (rien n'est envoyé).
  await e.click("#mh-prendre");
  await attendreTexte(e, "#mh-reponse", "prénom");
  await e.fill("#mh-qui", "Hiba");
  await e.click("#mh-prendre");
  await attendreTexte(e, "#mh-etat", "Hiba a la main");
  verifs.etat_equipe = await texteDe(e, "#mh-etat");

  // Une AUTRE tablette (sans le jeton) : pas d'ordres, seulement « Libérer la main ».
  const autre = await ouvrir(navigateur, "/", { viewport: { width: 1280, height: 900 } });
  await attendreTexte(autre.page, "#mh-etat", "sur une autre tablette");
  verifs.autre_liberer_visible = await autre.page.$eval("#mh-liberer", (el) => !el.hidden);
  verifs.autre_ordres_caches = await autre.page.$eval("#mh-ordres", (el) => el.hidden);
  verifs.autre_rendre_cache = await autre.page.$eval("#mh-rendre", (el) => el.hidden);
  await autre.contexte.close();

  // Le jury le dit clairement : bandeau « un humain pilote » + qui.
  await j.waitForSelector("#bandeau-pilote", { state: "visible", timeout: 10000 });
  await j.waitForTimeout(300);
  verifs.jury_1280_avec_bandeau = await tailles(j);  // grand écran : le bandeau ne fait pas défiler la page
  verifs.pilote_titre = await texteDe(j, "#pilote-titre");
  verifs.pilote_qui = await texteDe(j, "#pilote-qui");
  verifs.pilote_detail = await texteDe(j, "#pilote-detail");

  // Un ordre par bouton : il passe par le gardien, le jury le montre comme un ordre de l'humain.
  await ordre(e, "se_deplacer", { lieu: "table" });
  await attendreTexte(e, "#mh-reponse", "Le gardien a dit oui");
  verifs.reponse_ok = await texteDe(e, "#mh-reponse");
  await attendreTexte(j, "#pan-entendu .principal", "Ordre de l'humain qui pilote (Hiba)");
  verifs.jury_entendu = await texteDe(j, "#pan-entendu .principal");
  await attendreTexte(j, "#pan-faire .second", "réussi");

  // Trop rapide : refusé, et l'explication du gardien s'affiche.
  await ordre(e, "se_deplacer", { lieu: "", dx: "1", vitesse: "2" });
  await attendreTexte(e, "#mh-reponse", "Refusé");
  verifs.reponse_refus = await texteDe(e, "#mh-reponse");

  // Une phrase à la tablette pendant la main humaine : réponse polie, rien ne part.
  await e.fill("#texte", "Va à la cuisine");
  await e.click("#formulaire button");
  await attendreTexte(j, "#st-robot .l1 .txt", "Un humain pilote");
  verifs.jury_robot = await texteDe(j, "#st-robot .l1 .txt");

  // Le gardien demande un humain (objet fragile) : la demande s'affiche, on l'accepte.
  await ordre(e, "saisir", { objet: "tasse" });
  await attendreTexte(e, "#mh-reponse", "accord d'un humain");
  await e.waitForSelector("#dh-liste .dh-demande", { timeout: 10000 });
  verifs.demande = await texteDe(e, "#dh-liste .dh-demande");
  await e.click("#dh-liste .dh-demande .dh-oui");
  await attendreTexte(e, "#dh-reponse", "Accepté");
  verifs.reponse_demande = await texteDe(e, "#dh-reponse");
  await e.waitForSelector("#dh-liste .dh-vide", { timeout: 10000 });

  // Apprendre un mot.
  await e.click("#demandes-humain summary");
  await e.fill("#dh-mot", "frigo");
  await e.selectOption("#dh-langue", "fr");
  await e.selectOption("#dh-sens", "cuisine");
  await e.click("#dh-apprendre button");
  await attendreTexte(e, "#dh-reponse", "Appris");
  await attendreTexte(e, "#dh-mots", "« frigo » (fr) = cuisine");

  // La fiche du jury compte les ordres de l'humain.
  await attendreTexte(j, "#f-humain-d", "ordre(s) de l'humain");
  verifs.fiche_humain = await texteDe(j, "#f-humain");
  verifs.fiche_humain_d = await texteDe(j, "#f-humain-d");
  await attendreTexte(j, "#f-reussites-d", "par l'humain");
  verifs.fiche_reussites_d = await texteDe(j, "#f-reussites-d");

  // Rendre la main : tout comme avant, le bandeau du jury disparaît.
  await e.click("#mh-rendre");
  await attendreTexte(e, "#mh-etat", "écoute la voix");
  await j.waitForSelector("#bandeau-pilote", { state: "hidden", timeout: 10000 });
  verifs.bandeau_apres = true;
  verifs.ordres_caches_apres = await e.$eval("#mh-ordres", (el) => el.hidden);
  await equipe.contexte.close();
  await jury.contexte.close();

  // Téléphone : les boutons de la main humaine ne font pas défiler de côté.
  const tel = await ouvrir(navigateur, "/", { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  await tel.page.fill("#mh-qui", "Luca");
  await tel.page.click("#mh-prendre");
  await attendreTexte(tel.page, "#mh-etat", "Luca a la main");
  await tel.page.waitForSelector("#mh-ordres form", { state: "visible", timeout: 10000 });
  verifs.telephone = await tailles(tel.page);
  await tel.page.click("#mh-rendre");
  await attendreTexte(tel.page, "#mh-etat", "écoute la voix");
  await tel.contexte.close();
}

(async () => {
  let navigateur;
  try {
    navigateur = await chromium.launch({ args: ["--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost, EXCLUDE 127.0.0.1"] });
  } catch (e) {
    console.log(JSON.stringify({ saute: `Chromium ne démarre pas : ${String(e.message).split("\n")[0]}` }));
    process.exit(3);
  }
  let ok = true;
  try {
    await verifier(navigateur);
  } catch (e) {
    ok = false;
    journal.erreurs.push(`script : ${String(e.message).split("\n").slice(0, 12).join(" ")}`);
  } finally {
    await navigateur.close();
  }
  console.log(JSON.stringify({ ok, ...journal, verifs }));
  process.exit(ok ? 0 : 1);
})();
