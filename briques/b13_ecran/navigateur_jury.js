// Brique 13 — ouvrir /jury dans Chromium (Playwright pour Node, DÉJÀ installé), SANS Internet, et vérifier l'écran.
//   node navigateur_jury.js http://127.0.0.1:8000 verifier
//   node navigateur_jury.js http://127.0.0.1:8000 capture capture_jury.png
// Le navigateur n'a le droit d'ouvrir que des adresses locales : toute autre demande est bloquée et notée.
// Dernière ligne écrite : un résultat JSON (lu par le test Python). Code 3 : navigateur indisponible (le test saute).
"use strict";

let chromium;
try {
  ({ chromium } = require("playwright"));
} catch (e) {
  console.log(JSON.stringify({ saute: "Playwright pour Node introuvable" }));
  process.exit(3);
}

const [, , base, mode = "verifier", fichier] = process.argv;
const LOCAUX = new Set(["127.0.0.1", "localhost", "[::1]"]);
const journal = { erreurs: [], exterieur: [] };
const verifs = {};

async function ouvrir(navigateur, chemin, options) {
  const contexte = await navigateur.newContext(options);
  const page = await contexte.newPage();
  page.on("pageerror", (e) => journal.erreurs.push(`${chemin} : ${e.message}`));
  page.on("console", (m) => { if (m.type() === "error") journal.erreurs.push(`${chemin} (console) : ${m.text()}`); });
  await page.route("**/*", (route) => {
    const u = new URL(route.request().url());
    if (LOCAUX.has(u.hostname)) return route.continue();
    journal.exterieur.push(u.href);
    return route.abort();
  });
  await page.goto(base + chemin, { waitUntil: "load" });
  if (chemin === "/jury") await page.waitForFunction(() => document.body.dataset.pret === "1", null, { timeout: 20000 });
  return { contexte, page };
}

const texteDe = (page, sel) => page.$eval(sel, (el) => el.textContent);
const attendreTexte = (page, sel, morceau, timeout = 20000) =>
  page.waitForFunction(([s, m]) => { const el = document.querySelector(s); return !!el && el.textContent.includes(m); },
    [sel, morceau], { timeout });

async function dire(page, texte, langue) {
  await page.selectOption("#langue-dite", langue);
  await page.fill("#texte", texte);
  await page.click("#ecrire button[type=submit]");
}

async function tailles(page) {
  return page.evaluate(() => ({
    largeur: document.documentElement.scrollWidth, hauteur: document.documentElement.scrollHeight,
    fenetre_l: innerWidth, fenetre_h: innerHeight,
  }));
}

async function verifier(navigateur) {
  const { contexte, page } = await ouvrir(navigateur, "/jury", { viewport: { width: 1920, height: 1080 } });
  await page.selectOption("#langue2", "de");
  await dire(page, "Va à la cuisine", "fr");
  await attendreTexte(page, "#st-personne .l1 .txt", "Va à la cuisine");
  await attendreTexte(page, "#st-robot .l1 .txt", "cuisine");
  await attendreTexte(page, "#st-robot .l2 .txt", "Küche");  // deuxième langue : la même phrase, redite en allemand
  await attendreTexte(page, "#st-personne .l2 .txt", "traduction indisponible hors ligne");
  await attendreTexte(page, "#f-demandes", "1");
  await attendreTexte(page, "#f-reussites", "1");
  verifs.sous_titre_personne = await texteDe(page, "#st-personne .l1 .txt");
  verifs.sous_titre_robot = await texteDe(page, "#st-robot .l1 .txt");
  verifs.sous_titre_robot_de = await texteDe(page, "#st-robot .l2 .txt");
  verifs.sous_titre_personne_de = await texteDe(page, "#st-personne .l2 .txt");
  verifs.compris = await texteDe(page, "#pan-compris .principal");
  verifs.fiche_demandes = await texteDe(page, "#f-demandes");
  verifs.fiche_reussites = await texteDe(page, "#f-reussites");
  verifs.mention = await texteDe(page, "#f-mention");
  verifs.mention_haut = await texteDe(page, "#mention-haut");
  verifs.tailles_1920 = await tailles(page);
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.waitForTimeout(200);
  verifs.tailles_1280 = await tailles(page);

  // Le bouton « Internet coupé » : la page le dit en grand, et tout continue.
  await page.click("#b-internet");
  await page.waitForSelector("#bandeau-internet", { state: "visible", timeout: 10000 });
  await dire(page, "Regarde la table", "fr");
  await attendreTexte(page, "#st-robot .l1 .txt", "table");
  await attendreTexte(page, "#preuve-internet", "1 demande");
  verifs.bandeau_internet = await texteDe(page, "#bandeau-internet");
  verifs.tailles_1280_coupe = await tailles(page);
  await page.click("#b-internet");
  await page.waitForSelector("#bandeau-internet", { state: "hidden", timeout: 10000 });
  verifs.internet_retabli = true;

  // Le mode silence : pictogrammes en grand.
  await page.click("#b-silence");
  await page.waitForFunction(() => document.body.classList.contains("silence"), null, { timeout: 10000 });
  verifs.silence = true;
  await page.click("#b-silence");
  await page.waitForFunction(() => !document.body.classList.contains("silence"), null, { timeout: 10000 });
  await contexte.close();

  // Clair et sombre.
  for (const schema of ["light", "dark"]) {
    const o = await ouvrir(navigateur, "/jury", { viewport: { width: 1280, height: 720 }, colorScheme: schema });
    verifs[`fond_${schema}`] = await o.page.evaluate(() => getComputedStyle(document.body).backgroundColor);
    await o.contexte.close();
  }
  // Largeur de téléphone : pas de défilement de côté, ni pour /jury ni pour la page de l'équipe.
  for (const chemin of ["/jury", "/"]) {
    const o = await ouvrir(navigateur, chemin, { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
    await o.page.waitForTimeout(300);
    verifs[`telephone_${chemin === "/" ? "equipe" : "jury"}`] = await tailles(o.page);
    await o.contexte.close();
  }
}

async function capture(navigateur) {
  const { contexte, page } = await ouvrir(navigateur, "/jury", { viewport: { width: 1600, height: 900 }, deviceScaleFactor: 2,
    colorScheme: "light" });
  await page.selectOption("#langue2", "fr");
  await dire(page, "Va à la cuisine", "fr");
  await attendreTexte(page, "#f-reussites", "1");
  await page.click("#b-internet");
  await page.waitForSelector("#bandeau-internet", { state: "visible", timeout: 10000 });
  await dire(page, "Geh zur Bühne mit 4 Meter pro Sekunde", "de");
  await attendreTexte(page, "#st-robot .l2 .txt", "limite de sécurité");
  await attendreTexte(page, "#f-refus", "1");
  await page.waitForTimeout(1200);
  await page.screenshot({ path: fichier });
  verifs.capture = fichier;
  await page.click("#b-internet");  // on rend Internet avant de partir
  await page.waitForSelector("#bandeau-internet", { state: "hidden", timeout: 10000 });
  await contexte.close();
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
    if (mode === "capture") await capture(navigateur); else await verifier(navigateur);
  } catch (e) {
    ok = false;
    journal.erreurs.push(`script : ${String(e.message).split("\n").slice(0, 3).join(" ")}`);
  } finally {
    await navigateur.close();
  }
  console.log(JSON.stringify({ ok, ...journal, verifs }));
  process.exit(ok ? 0 : 1);
})();
