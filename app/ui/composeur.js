/* Composeur — construction d'un content.yaml à la souris (CLAUDE.md, Étape 1).
 *
 * L'état local (`etat`) est la forme de saisie ; `versArticle()` le traduit en
 * la structure exacte de `content.yaml` (le serveur ne connaît que celle-là).
 * Chaque modification redemande l'aperçu au serveur : le rendu affiché est
 * toujours produit par le vrai moteur, jamais réimplémenté ici.
 */

const $ = (sel, racine = document) => racine.querySelector(sel);

let CATALOGUE = [];      // modèles de section (app/modeles.py via /api/catalogue)
let FAMILLES = [];       // regroupement des modèles dans le panneau
let TEMPLATE = null;     // contraintes du template courant
let etat = nouvelEtat();
let compteurSection = 0;

function nouvelEtat() {
  return {
    id: "",
    type: "tutoriel",
    template_id: "tuto-release",
    titre: "",
    resume: "",
    auteur: "",
    prerequis: [],
    sections: [],
  };
}

function layoutDe(id) {
  return CATALOGUE.find((l) => l.id === id);
}

/* --------------------------------------------------------- état → content.yaml */

function versBlocs(section) {
  const layout = layoutDe(section.layout);
  const blocs = [];
  layout.champs.forEach((champ, i) => {
    (section.groupes[i] || []).forEach((entree) => {
      if (champ.type === "image") {
        if (!entree.fichier) return; // image pas encore téléversée
        blocs.push({
          type: "image",
          fichier: entree.fichier,
          legende: entree.legende || null,
          // Réglage fin non exposé dans le formulaire : on le reconduit tel
          // quel pour ne pas l'écraser en rouvrant un content.yaml écrit à la main.
          largeur_mm: entree.largeur_mm ?? null,
          padding_mm: entree.padding_mm ? Number(entree.padding_mm) : null,
        });
      } else if (champ.type === "paragraphe") {
        if (!entree.texte.trim()) return;
        blocs.push({ type: "paragraphe", texte: entree.texte });
      } else if (champ.type === "item") {
        if (!entree.texte.trim()) return;
        blocs.push({ type: "item", texte: entree.texte, icone: entree.icone || null });
      } else if (champ.type === "encadre") {
        if (!entree.texte.trim()) return;
        blocs.push({ type: "encadre", style: entree.style || "astuce", texte: entree.texte });
      }
    });
  });
  return blocs;
}

function versArticle() {
  return {
    id: etat.id,
    type: etat.type,
    template_id: etat.template_id,
    langue: "fr",
    titre: etat.titre,
    resume: etat.resume || null,
    auteur: etat.auteur || "—",
    prerequis: etat.prerequis.filter((p) => p.trim()),
    sections: etat.sections.map((s) => ({
      id: s.id,
      titre: s.titre || null,
      layout: s.layout,
      hauteur: s.hauteur,
      blocs: versBlocs(s),
    })),
    metadonnees_seo: { slug: null, meta_title: null, meta_description: null, mots_cles: [] },
    liens_internes: [],
  };
}

/* --------------------------------------------------------- content.yaml → état */

function groupesVides(layout) {
  return layout.champs.map((champ) =>
    Array.from({ length: champ.mini }, () => entreeVide(champ))
  );
}

function entreeVide(champ) {
  if (champ.type === "image") return { fichier: "", legende: "", largeur_mm: null, padding_mm: null };
  if (champ.type === "item") return { texte: "", icone: "" };
  if (champ.type === "encadre") return { style: "astuce", texte: "" };
  return { texte: "" };
}

function entreeDepuisBloc(bloc) {
  if (bloc.type === "image")
    return {
      fichier: bloc.fichier,
      legende: bloc.legende || "",
      largeur_mm: bloc.largeur_mm ?? null,
      padding_mm: bloc.padding_mm ?? null,
    };
  if (bloc.type === "item") return { texte: bloc.texte, icone: bloc.icone || "" };
  if (bloc.type === "encadre") return { style: bloc.style, texte: bloc.texte };
  return { texte: bloc.texte };
}

function depuisBlocs(layout, blocs) {
  // Répartit les blocs existants dans les groupes du modèle, dans l'ordre des
  // champs déclarés. Les blocs d'un content.yaml écrit à la main peuvent être
  // plus nombreux que prévu : le surplus rejoint le dernier groupe du même
  // type (au-delà de son maximum) plutôt que d'être perdu au ré-enregistrement.
  const restants = [...blocs];
  const groupes = layout.champs.map((champ) => {
    const pris = [];
    while (pris.length < champ.maxi) {
      const idx = restants.findIndex((b) => b.type === champ.type);
      if (idx === -1) break;
      pris.push(entreeDepuisBloc(restants.splice(idx, 1)[0]));
    }
    return pris;
  });
  restants.forEach((bloc) => {
    const i = layout.champs.map((c) => c.type).lastIndexOf(bloc.type);
    if (i !== -1) groupes[i].push(entreeDepuisBloc(bloc));
  });
  layout.champs.forEach((champ, i) => {
    while (groupes[i].length < champ.mini) groupes[i].push(entreeVide(champ));
  });
  return groupes;
}

function chargerArticle(contenu) {
  apercuArticleId = apercuArticleIdAttendu = null;
  etat = {
    id: contenu.id,
    type: contenu.type,
    template_id: contenu.template_id,
    titre: contenu.titre || "",
    resume: contenu.resume || "",
    auteur: contenu.auteur || "",
    prerequis: contenu.prerequis || [],
    sections: (contenu.sections || []).map((s) => {
      const layout = layoutDe(s.layout);
      return {
        id: s.id,
        titre: s.titre || "",
        layout: s.layout,
        hauteur: s.hauteur || (layout ? layout.defaut : 1),
        groupes: layout ? depuisBlocs(layout, s.blocs || []) : [],
        ouverte: false,
      };
    }),
  };
  compteurSection = etat.sections.length;
  rendreTout();
}

/* ------------------------------------------------------------------ réseau */

async function api(url, options) {
  const rep = await fetch(url, options);
  if (!rep.ok) {
    const corps = await rep.json().catch(() => ({}));
    const detail = corps.detail;
    throw new Error(Array.isArray(detail) ? detail.join(" · ") : detail || rep.statusText);
  }
  return rep.json();
}

/* ------------------------------------------------------------------ aperçu */

let minuteurApercu = null;
let generationApercu = 0;
// Tutoriel dont l'aperçu est actuellement affiché. Il ne suit `etat.id` qu'une
// fois le nouveau document *chargé* : entre les deux, le document à l'écran est
// encore celui du tutoriel précédent, et ses calques ne doivent surtout pas
// être attribués au suivant (voir calquesDeLApercu).
let apercuArticleId = null;
let apercuArticleIdAttendu = null;

function planifierApercu() {
  marquerModifie();
  clearTimeout(minuteurApercu);
  if (enAnnotation()) {
    // On repasse régulièrement : l'aperçu reprend dès la sortie du mode édition.
    $("#etat-apercu").textContent = "aperçu figé pendant l'annotation";
    minuteurApercu = setTimeout(planifierApercu, 1500);
    return;
  }
  $("#etat-apercu").textContent = "mise à jour…";
  minuteurApercu = setTimeout(rafraichirApercu, 350);
}

/** Vrai quand le mode édition de la surface d'annotation est actif : on ne
 *  remplace alors pas le document affiché, sinon les calques posés et non
 *  encore enregistrés seraient perdus au moindre caractère saisi. */
function enAnnotation() {
  const doc = $("#apercu").contentDocument;
  return !!doc && !!doc.body && doc.body.classList.contains("mode-edition");
}

async function rafraichirApercu() {
  if (!etat.id) {
    $("#etat-apercu").textContent = "en attente d'un titre";
    return;
  }
  if (enAnnotation()) {
    $("#etat-apercu").textContent = "aperçu figé pendant l'annotation";
    return;
  }
  const gen = ++generationApercu;
  const articleId = etat.id;
  try {
    const res = await api(`/api/articles/${articleId}/apercu`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // On renvoie les calques du document courant : une annotation posée mais
      // pas encore enregistrée survit ainsi au rafraîchissement.
      body: JSON.stringify({ article: versArticle(), calques: calquesDeLApercu() }),
    });
    if (gen !== generationApercu) return; // une frappe plus récente a pris la main
    if (enAnnotation()) {
      // L'utilisateur est passé en annotation pendant la requête : on ne
      // remplace pas le document sous ses doigts.
      marquerModifie();
      planifierApercu();
      return;
    }
    apercuArticleId = null;
    apercuArticleIdAttendu = articleId;
    $("#apercu").srcdoc = res.html;
    afficherAvertissements(res.avertissements);
    $("#etat-apercu").textContent = "";
  } catch (err) {
    if (gen !== generationApercu) return;
    $("#etat-apercu").textContent = "";
    afficherAvertissements([String(err.message)], "erreur");
  }
}

// `ton` : "info" (ce qu'il reste à compléter), "erreur", "succes".
function afficherAvertissements(messages, ton = "info") {
  const zone = $("#avertissements");
  zone.classList.toggle("erreur", ton === "erreur");
  zone.classList.toggle("succes", ton === "succes");
  if (!messages || !messages.length) {
    zone.hidden = true;
    zone.innerHTML = "";
    return;
  }
  const entetes = {
    info: "À compléter avant enregistrement",
    erreur: "Erreur",
    succes: "Tutoriel enregistré et généré",
  };
  zone.hidden = false;
  zone.innerHTML =
    `<strong>${entetes[ton]}</strong><ul>` +
    messages.map((m) => `<li>${echapper(m)}</li>`).join("") +
    "</ul>";
}

function echapper(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

/* ---------------------------------------------------------------- en-tête */

function brancherEntete() {
  const lier = (sel, cle) => {
    const champ = $(sel);
    champ.addEventListener("input", () => {
      etat[cle] = champ.value;
      if (cle === "titre") majIdSiNouveau();
      planifierApercu();
    });
  };
  lier("#f-titre", "titre");
  lier("#f-resume", "resume");
  lier("#f-auteur", "auteur");

  // Quitter le champ titre crée le tutoriel sur disque : à partir de là, tout
  // est enregistré automatiquement (voir sauvegarderAuto).
  $("#f-titre").addEventListener("change", () => {
    if (etat.titre.trim()) sauvegarderAuto();
  });

  $("#btn-prerequis").addEventListener("click", () => {
    etat.prerequis.push("");
    rendrePrerequis();
    planifierApercu();
  });
}

let idFige = false; // l'id suit le titre tant que l'article n'a pas été enregistré

async function majIdSiNouveau() {
  if (idFige || !etat.titre.trim()) return;
  const res = await api(`/api/id-propose?titre=${encodeURIComponent(etat.titre)}`);
  etat.id = res.id;
  $("#article-id").textContent = res.id;
}

function rendrePrerequis() {
  const zone = $("#liste-prerequis");
  zone.innerHTML = "";
  etat.prerequis.forEach((valeur, i) => {
    const ligne = document.createElement("div");
    ligne.className = "ligne-prerequis";
    const input = document.createElement("input");
    input.type = "text";
    input.value = valeur;
    input.placeholder = "Être connecté à l'application";
    input.addEventListener("input", () => {
      etat.prerequis[i] = input.value;
      planifierApercu();
    });
    const suppr = document.createElement("button");
    suppr.textContent = "×";
    suppr.title = "Retirer";
    suppr.addEventListener("click", () => {
      etat.prerequis.splice(i, 1);
      rendrePrerequis();
      planifierApercu();
    });
    ligne.append(input, suppr);
    zone.append(ligne);
  });
}

/* -------------------------------------------------------------- catalogue */

const POIDS_LIBELLES = { 1: "¼ de page", 2: "½ page", 3: "¾ de page", 4: "Page entière" };
let ongletPoids = 2;

function ouvrirCatalogue() {
  rendreOngletsPoids();
  rendreGrilleModeles();
  $("#modale").hidden = false;
}

function rendreOngletsPoids() {
  const zone = $("#onglets-poids");
  zone.innerHTML = "";
  [1, 2, 3, 4].forEach((h) => {
    const n = CATALOGUE.filter((m) => m.hauteurs.includes(h)).length;
    const onglet = document.createElement("button");
    onglet.className = "onglet" + (h === ongletPoids ? " actif" : "");
    onglet.setAttribute("role", "tab");
    onglet.setAttribute("aria-selected", h === ongletPoids ? "true" : "false");
    onglet.innerHTML =
      `<span class="onglet-poids">Poids ${h}</span>` +
      `<span class="onglet-detail">${POIDS_LIBELLES[h]} · ${n} modèles</span>`;
    onglet.addEventListener("click", () => {
      ongletPoids = h;
      rendreOngletsPoids();
      rendreGrilleModeles();
    });
    zone.append(onglet);
  });
}

function rendreGrilleModeles() {
  const grille = $("#grille-layouts");
  grille.innerHTML = "";
  grille.dataset.poids = ongletPoids;
  FAMILLES.forEach((famille) => {
    const modeles = CATALOGUE.filter(
      (m) => m.famille === famille.id && m.hauteurs.includes(ongletPoids)
    );
    if (!modeles.length) return;
    const titre = document.createElement("h3");
    titre.className = "famille";
    titre.textContent = famille.libelle;
    grille.append(titre);
    modeles.forEach((modele) => {
      const carte = document.createElement("button");
      carte.className = "carte-layout";
      carte.innerHTML =
        `<div class="cadre-wire">${modele.wireframes[ongletPoids]}</div>` +
        `<span class="nom">${echapper(modele.libelle)}</span>` +
        `<span class="desc">${echapper(modele.description)}</span>` +
        `<span class="desc champs">${echapper(resumeChamps(modele))}</span>`;
      carte.addEventListener("click", () => {
        ajouterSection(modele, ongletPoids);
        fermerCatalogue();
      });
      grille.append(carte);
    });
  });
}

function fermerCatalogue() {
  $("#modale").hidden = true;
}

function resumeChamps(layout) {
  const noms = { image: "image", paragraphe: "texte", item: "élément", encadre: "encart" };
  return layout.champs
    .map((c) => {
      const nb = c.mini === c.maxi ? `${c.mini}` : `${c.mini}–${c.maxi}`;
      return `${nb} ${noms[c.type]}${c.maxi > 1 ? "s" : ""}`;
    })
    .join(" · ");
}

/* --------------------------------------------------------------- sections */

function ajouterSection(layout, hauteur) {
  compteurSection += 1;
  etat.sections.push({
    id: `sec-${compteurSection}`,
    titre: "",
    layout: layout.id,
    hauteur: layout.hauteurs.includes(hauteur) ? hauteur : layout.defaut,
    groupes: groupesVides(layout),
    ouverte: true,
  });
  rendreSections();
  planifierApercu();
  const cartes = document.querySelectorAll(".carte-section");
  cartes[cartes.length - 1]?.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function rendreSections() {
  const zone = $("#liste-sections");
  zone.innerHTML = "";
  etat.sections.forEach((section, index) => zone.append(carteSection(section, index)));
  majCompteurPages();
}

function majCompteurPages() {
  // Même règle que app/pagination.py : 4 unités par page, l'en-tête en occupe 1.
  let pages = 1;
  let reste = 4 - 1;
  etat.sections.forEach((s) => {
    const h = s.hauteur;
    if (reste - h < 0) {
      pages += 1;
      reste = 4;
    }
    reste -= h;
  });
  const n = etat.sections.length;
  $("#compteur-pages").textContent = `${n} section${n > 1 ? "s" : ""} · ${pages} page${pages > 1 ? "s" : ""}`;
}

function carteSection(section, index) {
  const layout = layoutDe(section.layout);
  const carte = document.createElement("div");
  carte.className = "carte-section" + (section.ouverte ? " active" : "");

  const entete = document.createElement("div");
  entete.className = "carte-entete";
  if (!layout) {
    // Modèle inconnu du catalogue (content.yaml écrit à la main) : on
    // l'affiche sans formulaire plutôt que de faire échouer tout le composeur.
    entete.innerHTML =
      `<span class="nom">${echapper(section.titre || section.layout)}</span>` +
      `<span class="poids">modèle inconnu</span>`;
    carte.append(entete);
    return carte;
  }
  entete.innerHTML =
    `<span class="mini-wire">${layout.wireframes[section.hauteur] || ""}</span>` +
    `<span class="nom">${echapper(section.titre || layout.libelle)}</span>` +
    `<span class="poids">${section.hauteur}/4</span>`;

  const outils = document.createElement("div");
  outils.className = "carte-outils";
  outils.append(
    bouton("↑", "Monter", () => deplacerSection(index, -1)),
    bouton("↓", "Descendre", () => deplacerSection(index, 1)),
    bouton("🗑", "Supprimer la section", () => supprimerSection(index), "suppr")
  );
  entete.append(outils);
  entete.addEventListener("click", (ev) => {
    if (ev.target.closest(".carte-outils")) return;
    section.ouverte = !section.ouverte;
    rendreSections();
  });
  carte.append(entete);

  if (section.ouverte) carte.append(corpsSection(section, layout));
  return carte;
}

function bouton(texte, titre, action, classe = "") {
  const b = document.createElement("button");
  b.type = "button";
  b.textContent = texte;
  b.title = titre;
  if (classe) b.className = classe;
  b.addEventListener("click", (ev) => {
    ev.stopPropagation();
    action();
  });
  return b;
}

function deplacerSection(index, sens) {
  const cible = index + sens;
  if (cible < 0 || cible >= etat.sections.length) return;
  const [s] = etat.sections.splice(index, 1);
  etat.sections.splice(cible, 0, s);
  rendreSections();
  planifierApercu();
}

function supprimerSection(index) {
  etat.sections.splice(index, 1);
  rendreSections();
  planifierApercu();
}

function corpsSection(section, layout) {
  const corps = document.createElement("div");
  corps.className = "carte-corps";

  // Poids : on peut agrandir ou réduire une section sans la recréer, parmi
  // les poids où son modèle existe.
  const poids = document.createElement("div");
  poids.className = "choix-poids";
  poids.innerHTML = '<span class="label">Poids</span>';
  [1, 2, 3, 4].forEach((h) => {
    const b = bouton(`${h}/4`, POIDS_LIBELLES[h], () => {
      section.hauteur = h;
      rendreSections();
      planifierApercu();
    }, h === section.hauteur ? "actif" : "");
    b.disabled = !layout.hauteurs.includes(h);
    if (b.disabled) b.title = "Ce modèle n'existe pas dans ce poids";
    poids.append(b);
  });
  corps.append(poids);

  const label = document.createElement("label");
  label.textContent = "Titre de la section";
  const input = document.createElement("input");
  input.type = "text";
  input.value = section.titre;
  input.placeholder = "1 - Ouvrir le menu Identité";
  input.addEventListener("input", () => {
    section.titre = input.value;
    $(".nom", corps.parentElement).textContent = section.titre || layout.libelle;
    planifierApercu();
  });
  label.append(input);
  corps.append(label);

  layout.champs.forEach((champ, i) => corps.append(groupeChamp(section, champ, i)));
  return corps;
}

function groupeChamp(section, champ, i) {
  const groupe = document.createElement("div");
  groupe.className = "groupe";
  const entrees = section.groupes[i] || (section.groupes[i] = []);

  const titre = document.createElement("div");
  titre.className = "titre-groupe";
  const nb = champ.maxi > 1 ? ` (${entrees.length}/${champ.maxi})` : "";
  const facultatif = champ.mini === 0 ? " — facultatif" : "";
  titre.innerHTML = `<span>${echapper(champ.libelle)}${nb}${facultatif}</span>`;
  if (entrees.length < champ.maxi) {
    titre.append(
      bouton("+ Ajouter", `Ajouter : ${champ.libelle}`, () => {
        entrees.push(entreeVide(champ));
        rendreSections();
      }, "lien")
    );
  }
  groupe.append(titre);

  entrees.forEach((entree, j) => {
    const bloc = document.createElement("div");
    bloc.className = "entree";
    if (champ.type === "image") bloc.append(champImage(champ, entree));
    else if (champ.type === "item") bloc.append(champItem(entree));
    else bloc.append(champTexte(champ, entree));
    if (entrees.length > champ.mini) {
      bloc.append(
        bouton("×", "Retirer", () => {
          entrees.splice(j, 1);
          rendreSections();
          planifierApercu();
        }, "retirer")
      );
    }
    groupe.append(bloc);
  });
  return groupe;
}

/** Zone de texte + barre d'outils (gras, lien). Le texte reste du Markdown
 *  léger : c'est ce qu'écrit content.yaml et ce que lit le moteur. */
function zoneTexte(valeur, placeholder, surSaisie) {
  const enveloppe = document.createElement("div");
  enveloppe.className = "zone-texte";
  const zone = document.createElement("textarea");
  zone.value = valeur;
  zone.placeholder = placeholder;
  zone.addEventListener("input", () => surSaisie(zone.value));

  const outils = document.createElement("div");
  outils.className = "outils-texte";
  const entourer = (avant, apres) => {
    const { selectionStart: a, selectionEnd: b, value: v } = zone;
    zone.value = v.slice(0, a) + avant + v.slice(a, b) + apres + v.slice(b);
    zone.focus();
    zone.setSelectionRange(a + avant.length, b + avant.length);
    surSaisie(zone.value);
  };
  outils.append(
    bouton("G", "Gras : **texte**", () => entourer("**", "**"), "outil gras"),
    bouton("🔗 Lien", "Lien internet : [texte](https://…)", () => {
      const url = window.prompt("Adresse du lien (http:// ou https://)", "https://");
      if (url === null) return;
      if (!/^https?:\/\/\S+$/.test(url.trim())) {
        afficherAvertissements(["Seuls les liens internet (http:// ou https://) sont acceptés."], "erreur");
        return;
      }
      const { selectionStart: a, selectionEnd: b, value: v } = zone;
      const libelle = v.slice(a, b) || url.trim();
      zone.value = v.slice(0, a) + `[${libelle}](${url.trim()})` + v.slice(b);
      zone.focus();
      surSaisie(zone.value);
    }, "outil"),
    bouton("1.", "Liste numérotée : « 1. » en début de ligne", () => entourer("\n1. ", ""), "outil"),
    bouton("•", "Liste à puces : « - » en début de ligne", () => entourer("\n- ", ""), "outil")
  );
  enveloppe.append(outils, zone);
  return enveloppe;
}

function champTexte(champ, entree) {
  const enveloppe = document.createElement("div");

  if (champ.type === "encadre") {
    const choix = document.createElement("select");
    [["astuce", "✓ Astuce"], ["attention", "! Attention"], ["info", "i Info"]].forEach(([v, l]) => {
      choix.append(new Option(l, v, false, entree.style === v));
    });
    choix.addEventListener("change", () => {
      entree.style = choix.value;
      planifierApercu();
    });
    enveloppe.append(choix);
  }

  const placeholder =
    champ.type === "encadre"
      ? "L'intervention est archivée."
      : "Texte du paragraphe. **gras**, listes « - » ou « 1. », liens [texte](https://…).";
  enveloppe.append(
    zoneTexte(entree.texte, placeholder, (v) => {
      entree.texte = v;
      planifierApercu();
    })
  );
  return enveloppe;
}

/** Téléverse un fichier dans assets/ et renvoie son chemin relatif. */
async function televerser(fichier) {
  const donnees = new FormData();
  donnees.append("fichier", fichier);
  const res = await api(
    `/api/articles/${etat.id}/assets?template_id=${encodeURIComponent(etat.template_id)}`,
    { method: "POST", body: donnees }
  );
  return res.fichier;
}

/** Vignette + bouton de choix de fichier, partagés par images et icônes. */
function selecteurFichier(cheminActuel, surChoix, libelle = "Choisir une image…") {
  const enveloppe = document.createElement("div");
  enveloppe.className = "selecteur";
  const vignette = document.createElement("div");
  vignette.className = "vignette";
  if (cheminActuel) {
    const img = document.createElement("img");
    img.src = `/vault/articles/${etat.id}/${cheminActuel}`;
    vignette.append(img);
  } else {
    vignette.textContent = "aucune";
  }
  const input = document.createElement("input");
  input.type = "file";
  input.accept = "image/*";
  const choisir = bouton(cheminActuel ? "Remplacer…" : libelle, "Téléverser", () => input.click());
  const nom = document.createElement("div");
  nom.className = "nom-fichier";
  nom.textContent = cheminActuel || "";
  input.addEventListener("change", async () => {
    const fichier = input.files[0];
    if (!fichier) return;
    nom.textContent = "envoi…";
    try {
      surChoix(await televerser(fichier));
    } catch (err) {
      nom.textContent = "";
      afficherAvertissements([String(err.message)], "erreur");
    }
  });
  return { vignette, choisir, nom, input };
}

function champImage(champ, entree) {
  const boite = document.createElement("div");
  boite.className = "uploader" + (entree.fichier ? " pleine" : "");
  const { vignette, choisir, nom, input } = selecteurFichier(entree.fichier, (chemin) => {
    entree.fichier = chemin;
    rendreSections();
    planifierApercu();
  });

  const corps = document.createElement("div");
  corps.className = "corps";
  corps.append(choisir, nom);

  if (champ.legende) {
    const legende = document.createElement("input");
    legende.type = "text";
    legende.value = entree.legende || "";
    legende.placeholder = "Légende affichée sous l'image";
    legende.addEventListener("input", () => {
      entree.legende = legende.value;
      planifierApercu();
    });
    corps.append(legende);
  }

  if (champ.padding) {
    // Padding : marge intérieure de la boîte image. L'image, qui remplit sa
    // boîte sans déformation, rétrécit d'autant — la mise en page ne bouge pas.
    const ligne = document.createElement("label");
    ligne.className = "reglage-padding";
    ligne.innerHTML = "<span>Padding</span>";
    const curseur = document.createElement("input");
    curseur.type = "range";
    curseur.min = "0";
    curseur.max = "30";
    curseur.step = "1";
    curseur.value = entree.padding_mm || 0;
    const valeur = document.createElement("output");
    valeur.textContent = `${curseur.value} mm`;
    curseur.addEventListener("input", () => {
      entree.padding_mm = Number(curseur.value) || null;
      valeur.textContent = `${curseur.value} mm`;
      planifierApercu();
    });
    ligne.append(curseur, valeur);
    corps.append(ligne);
  }

  boite.append(vignette, corps, input);
  return boite;
}

function champItem(entree) {
  const boite = document.createElement("div");
  boite.className = "uploader item" + (entree.icone ? " pleine" : "");
  const { vignette, choisir, input } = selecteurFichier(entree.icone, (chemin) => {
    entree.icone = chemin;
    rendreSections();
    planifierApercu();
  }, "Icône…");
  const corps = document.createElement("div");
  corps.className = "corps";
  const ligneIcone = document.createElement("div");
  ligneIcone.className = "ligne-icone";
  ligneIcone.append(choisir);
  if (entree.icone) {
    ligneIcone.append(bouton("Retirer l'icône", "Retirer l'icône", () => {
      entree.icone = "";
      rendreSections();
      planifierApercu();
    }, "lien"));
  }
  corps.append(
    ligneIcone,
    zoneTexte(entree.texte, "Dictée vocale", (v) => {
      entree.texte = v;
      planifierApercu();
    })
  );
  boite.append(vignette, corps, input);
  return boite;
}

/* --------------------------------------------------- sauvegarde auto */

/** Vrai si l'aperçu du tutoriel courant a été retouché depuis son affichage
 *  (calque posé, déplacé, supprimé). Sert à ne pas perdre une annotation en
 *  changeant de tutoriel : la pose d'un calque, elle, ne passe pas par le
 *  formulaire et ne marque donc rien comme modifié. */
function apercuRetouche() {
  if (apercuArticleId !== etat.id) return false;
  const fen = $("#apercu").contentWindow;
  try {
    return !!fen && typeof fen.retouchesTouchees === "function" && fen.retouchesTouchees();
  } catch {
    return false;
  }
}

/** Annotations posées dans l'aperçu, au format `retouches.yaml`.
 *  `null` = aperçu pas encore rendu : on ne touche alors pas aux retouches
 *  existantes (les envoyer vides les effacerait). */
function calquesDeLApercu() {
  // L'aperçu affiche-t-il bien le tutoriel courant ? Sinon (changement de
  // tutoriel en cours), ses calques appartiennent au précédent.
  if (apercuArticleId !== etat.id) return null;
  const fen = $("#apercu").contentWindow;
  if (!fen || typeof fen.collecterCalques !== "function") return null;
  try {
    return fen.collecterCalques();
  } catch {
    return null; // document pas (encore) accessible
  }
}

const PERIODE_SAUVEGARDE_MS = 30000;
let modifie = false;
let sauvegardeEnCours = false;
let chargementEnCours = false;

function marquerModifie() {
  // Ouvrir un tutoriel n'est pas le modifier : sans ce garde-fou, le simple
  // affichage déclencherait une réécriture de content.yaml au tour suivant.
  if (!chargementEnCours) modifie = true;
}

function etatSauvegarde(texte) {
  $("#etat-sauvegarde").textContent = texte;
}

/** Écrit `content.yaml` sans exiger un tutoriel complet (une saisie en cours
 *  l'est rarement) et régénère le HTML quand c'est possible — sans PDF, trop
 *  lent pour un enregistrement de fond. Le PDF est produit par le bouton
 *  « Enregistrer & générer ». */
async function sauvegarderAuto() {
  if (sauvegardeEnCours || !etat.id || !etat.titre.trim()) return;
  sauvegardeEnCours = true;
  modifie = false;
  try {
    const res = await api(`/api/articles/${etat.id}/enregistrer?auto=1`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ article: versArticle(), calques: calquesDeLApercu() }),
    });
    const heure = new Date().toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
    etatSauvegarde(`enregistré à ${heure}`);
    if (!idFige) {
      // Premier enregistrement : l'identifiant ne suit plus le titre.
      idFige = true;
      await chargerListeArticles();
      $("#choix-article").value = etat.id;
    }
    if (res.avertissements && res.avertissements.length) {
      afficherAvertissements(res.avertissements);
    }
  } catch (err) {
    modifie = true; // à retenter au prochain tour
    etatSauvegarde("enregistrement auto en échec");
    afficherAvertissements([String(err.message)], "erreur");
  } finally {
    sauvegardeEnCours = false;
  }
}

function demarrerSauvegardeAuto() {
  setInterval(() => {
    if (modifie) sauvegarderAuto();
  }, PERIODE_SAUVEGARDE_MS);
}

/* -------------------------------------------------------- enregistrement */

async function enregistrer() {
  if (!etat.id) {
    afficherAvertissements(["Donne d'abord un titre au tutoriel."], "erreur");
    return;
  }
  const btn = $("#btn-enregistrer");
  btn.disabled = true;
  btn.textContent = "Génération…";
  try {
    const res = await api(`/api/articles/${etat.id}/enregistrer`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ article: versArticle(), calques: calquesDeLApercu() }),
    });
    if (!res.ok) {
      afficherAvertissements(res.erreurs, "erreur");
    } else {
      idFige = true;
      modifie = false;
      etatSauvegarde("enregistré et généré");
      const messages = [`content.yaml et HTML écrits — ${res.html}`];
      if (res.pdf) messages.push(`PDF : ${res.pdf}`);
      if (res.pdf_erreur) messages.push(`PDF non généré : ${res.pdf_erreur}`);
      afficherAvertissements(messages, "succes");
      await chargerListeArticles();
      $("#choix-article").value = etat.id;
    }
  } catch (err) {
    afficherAvertissements([String(err.message)], "erreur");
  } finally {
    btn.disabled = false;
    btn.textContent = "Enregistrer & générer";
  }
}

/* ------------------------------------------------------------ chargement */

async function chargerCatalogue(templateId) {
  const res = await api(`/api/catalogue?template_id=${encodeURIComponent(templateId)}`);
  CATALOGUE = res.modeles;
  FAMILLES = res.familles;
  TEMPLATE = res.template;
}

const VALEUR_NOUVEAU = "__nouveau__";

async function chargerListeArticles() {
  const liste = await api("/api/articles");
  const choix = $("#choix-article");
  choix.innerHTML = "";
  choix.append(new Option("+ Nouveau tutoriel", VALEUR_NOUVEAU));
  liste.forEach((a) => choix.append(new Option(`${a.titre} (${a.sections} sect.)`, a.id)));
  choix.value = etat.id || VALEUR_NOUVEAU;
}

function nouveauTutoriel() {
  etat = nouvelEtat();
  compteurSection = 0;
  idFige = false;
  modifie = false;
  apercuArticleId = apercuArticleIdAttendu = null;
  etatSauvegarde("");
  $("#choix-article").value = VALEUR_NOUVEAU;
  rendreTout();
  $("#f-titre").focus();
}

function rendreTout() {
  chargementEnCours = true;
  $("#f-titre").value = etat.titre;
  $("#f-resume").value = etat.resume;
  $("#f-auteur").value = etat.auteur;
  $("#article-id").textContent = etat.id || "nouveau tutoriel";
  rendrePrerequis();
  rendreSections();
  planifierApercu();
  chargementEnCours = false;
}

/** Le zoom s'applique aux pages *dans* le document (variable --apercu-zoom,
 *  voir app/renderer.py) et non à l'<iframe> : la barre d'édition et la palette
 *  d'annotations restent donc lisibles, à droite du volet. */
function appliquerZoom() {
  const doc = $("#apercu").contentDocument;
  if (!doc) return;
  doc.documentElement.style.setProperty("--apercu-zoom", $("#f-zoom").value / 100);
}

async function demarrer() {
  await chargerCatalogue("tuto-release");
  await chargerListeArticles();

  brancherEntete();
  $("#btn-ajouter-section").addEventListener("click", ouvrirCatalogue);
  $("#btn-enregistrer").addEventListener("click", enregistrer);
  $("#choix-article").addEventListener("change", async (ev) => {
    // Enregistrer ce qui reste en attente avant de changer de tutoriel —
    // saisie du formulaire comme annotations posées dans l'aperçu.
    if (modifie || apercuRetouche()) await sauvegarderAuto();
    if (ev.target.value === VALEUR_NOUVEAU) return nouveauTutoriel();
    const contenu = await api(`/api/articles/${ev.target.value}/content`);
    await chargerCatalogue(contenu.template_id);
    idFige = true;
    modifie = false;
    etatSauvegarde("");
    chargerArticle(contenu);
  });
  document.querySelectorAll("[data-fermer]").forEach((el) => el.addEventListener("click", fermerCatalogue));
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") fermerCatalogue();
  });
  $("#f-zoom").addEventListener("input", appliquerZoom);
  $("#apercu").addEventListener("load", () => {
    apercuArticleId = apercuArticleIdAttendu;
    appliquerZoom();
  });

  appliquerZoom();
  demarrerSauvegardeAuto();
  rendreTout();
}

demarrer();
