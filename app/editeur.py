"""Surface d'édition navigateur — barre + palette de calques insérables.

Voir CLAUDE.md §3 (« Surface d'édition ») : le HTML rendu est retouchable dans
le navigateur via `designMode`, et l'utilisateur peut *ajouter* des éléments.
Ce module produit le fragment (CSS + palette + JS) injecté dans les templates
via `{{ editeur_html | safe }}` — une seule source pour tous les templates.

Trois règles de conception :

1. **La hauteur du document est verrouillée.** Chaque `.page` a une hauteur
   fixe (4 unités de la grille) et `overflow:hidden`. Aucun ajout ne peut donc
   décaler la pagination : tout module inséré est un **calque en position
   absolue**, ancré à la page en coordonnées % (donc fidèle au PDF, quelle que
   soit l'échelle de rendu), déplaçable et redimensionnable à la souris.
2. **Aucune contrainte d'ancrage.** Un calque se pose n'importe où sur la page
   — sur une image, dans une marge, à cheval sur deux blocs.
3. **Toute action est annulable** (historique de snapshots, Ctrl+Z).

Modèle retenu : retouche finale à sens unique. Les calques ne remontent pas
dans `content.yaml` et seront écrasés à la prochaine génération (§2, §7).

Deux blocs de style distincts :
- `#editeur-css`  : chrome de l'éditeur (barre, palette, poignées) — retiré à
  l'enregistrement.
- `#modules-css`  : verrouillage de hauteur + styles des calques — **conservé**
  dans le HTML enregistré, sinon le PDF perdrait les ajouts.
"""
from __future__ import annotations

import re

_SCRIPT_RE = re.compile(r"<script\b.*?</script>", re.IGNORECASE | re.DOTALL)
_HANDLER_RE = re.compile(r"\son\w+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", re.IGNORECASE)


def assainir_html(html: str) -> str:
    """Retire scripts et gestionnaires d'événements du contenu d'un calque.

    Ce contenu est saisi dans le navigateur puis réinjecté à chaque build : il
    passe par ici avant d'être persisté dans `retouches.yaml`, quel que soit le
    chemin d'enregistrement (aperçu du composeur ou HTML autonome).
    """
    return _HANDLER_RE.sub("", _SCRIPT_RE.sub("", html))


# ---------------------------------------------------------------------------
# Catalogue des calques insérables
# ---------------------------------------------------------------------------

_PALETTE_GROUPES = [
    ("Texte", [
        ("paragraphe", "¶ Paragraphe"),
        ("titre", "H Titre"),
        ("liste", "• Liste à puces"),
    ]),
    ("Encadrés", [
        ("encadre-astuce", "💡 Astuce"),
        ("encadre-attention", "⚠️ Attention"),
        ("encadre-info", "ℹ️ Info"),
    ]),
    ("Média & mise en page", [
        ("image", "🖼 Image…"),
        ("etape-compacte", "◧ Image + texte"),
        ("colonnes", "◫ Deux colonnes"),
        ("separateur", "— Séparateur"),
    ]),
    ("Annotations", [
        ("annot-fleche", "➜ Flèche"),
        ("annot-cadre", "▭ Cadre"),
        ("annot-pastille", "① Pastille"),
        ("annot-etiquette", "🏷 Étiquette"),
    ]),
    ("Structure", [
        ("page", "📄 Nouvelle page"),
        ("supprimer", "🗑 Supprimer le calque"),
    ]),
]


def _palette_html() -> str:
    groupes = []
    for titre, modules in _PALETTE_GROUPES:
        boutons = "".join(
            f'<button type="button" data-module="{mid}">{lib}</button>'
            for mid, lib in modules
        )
        groupes.append(
            f'<div class="pal-groupe"><span class="pal-titre">{titre}</span>'
            f'<div class="pal-boutons">{boutons}</div></div>'
        )
    aide = (
        '<p class="pal-aide">Le calque se pose au dernier point cliqué. '
        "Déplacer : poignée ⠿. Redimensionner : poignée ◢. "
        "Annuler : Ctrl+Z.</p>"
    )
    return (
        '<div class="editor-palette" id="editeur-palette" hidden>'
        '<p class="pal-entete">Ajouter un élément</p>'
        + "".join(groupes)
        + aide
        + "</div>"
    )


_EDITEUR_CSS = """
/* Chrome de l'éditeur — aligné sur l'UI du composeur (app/ui/composeur.css) :
   mêmes gris, même accent, mêmes rayons et ombres. Les jetons sont portés par
   les éléments de chrome plutôt que par `:root`, pour ne pas se mêler aux
   variables de charte du document (--couleur-*), qui, elles, habillent
   l'article rendu. */
.editor-bar, .editor-palette, .editeur-toast {
  --ui-fond: #ffffff;
  --ui-fond-doux: #f6f7f9;
  --ui-fond-actif: #eceef1;
  --ui-bord: #d8dce1;
  --ui-gris: #9aa3ad;
  --ui-texte-doux: #444c55;
  --ui-texte: #1d2229;
  --ui-accent: #2f6df6;
  --ui-danger: #c0392b;
  --ui-rayon: 8px;
  --ui-ombre: 0 1px 2px rgba(20, 25, 32, .08), 0 4px 12px rgba(20, 25, 32, .06);
  font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  color: var(--ui-texte);
}

.editor-bar {
  display: flex; position: fixed; top: 12px; right: 12px; gap: 8px; z-index: 9999;
}
.editor-bar button {
  font: 500 13px/1.45 inherit; padding: 7px 12px; cursor: pointer;
  border: 1px solid var(--ui-bord); border-radius: var(--ui-rayon);
  background: var(--ui-fond); color: var(--ui-texte); box-shadow: var(--ui-ombre);
}
.editor-bar button:hover { background: var(--ui-fond-doux); }
.editor-bar button.on { background: var(--ui-accent); border-color: var(--ui-accent); color: #fff; }
.editor-bar button.on:hover { filter: brightness(1.06); }
.editor-bar button[disabled] { opacity: .45; cursor: default; }

/* Palette : carte posée sous la barre, même colonne à droite. */
.editor-palette {
  position: fixed; top: 54px; right: 12px; width: 226px; z-index: 9999;
  background: var(--ui-fond); border: 1px solid var(--ui-bord);
  border-radius: 10px; padding: 12px; box-shadow: var(--ui-ombre);
  max-height: calc(100vh - 76px); overflow: auto;
}
.editor-palette[hidden] { display: none; }
.pal-entete {
  font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em;
  color: var(--ui-texte-doux); margin: 0 0 10px;
}
.pal-groupe { margin-bottom: 12px; }
.pal-groupe:last-of-type { margin-bottom: 6px; }
.pal-titre {
  display: block; font-size: 10px; text-transform: uppercase; letter-spacing: .05em;
  color: var(--ui-gris); margin-bottom: 5px;
}
.pal-boutons { display: flex; flex-wrap: wrap; gap: 5px; }
.editor-palette button {
  font: 400 12px/1.35 inherit; padding: 5px 9px; cursor: pointer; text-align: left;
  border: 1px solid var(--ui-bord); border-radius: 6px;
  background: var(--ui-fond); color: var(--ui-texte);
}
.editor-palette button:hover { background: var(--ui-fond-doux); border-color: var(--ui-accent); color: var(--ui-accent); }
.editor-palette button[data-module="supprimer"]:hover {
  background: #fdecea; border-color: var(--ui-danger); color: var(--ui-danger);
}
.pal-aide {
  margin: 0; padding-top: 10px; border-top: 1px solid var(--ui-fond-actif);
  font-size: 10px; line-height: 1.4; color: var(--ui-gris);
}

/* Repère du point de pose (dernier clic dans la page). Écran uniquement. */
.pose-repere {
  position: absolute; width: 9px; height: 9px; margin: -5px 0 0 -5px;
  border-radius: 999px; border: 2px solid var(--couleur-lisere);
  background: rgba(255, 255, 255, .7); z-index: 8; pointer-events: none;
}

/* --- Chrome de manipulation des calques (mode édition uniquement) --------- */
body.mode-edition .calque { outline: 1px dashed rgba(20, 25, 32, .18); }
body.mode-edition .calque.selection { outline: 2px solid #2f6df6; }
.calque-outils { position: absolute; top: -11px; left: -11px; display: none; gap: 3px; z-index: 9; }
body.mode-edition .calque:hover > .calque-outils,
body.mode-edition .calque.selection > .calque-outils { display: flex; }
.calque-outils span {
  width: 19px; height: 19px; border-radius: 6px; background: #fff;
  border: 1px solid #d8dce1; box-shadow: 0 1px 2px rgba(20, 25, 32, .12);
  font: 11px/17px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  text-align: center; color: #444c55;
}
.calque-grip { cursor: move; }
.calque-fermer { cursor: pointer; }
.calque-fermer:hover { background: #fdecea; border-color: #c0392b; color: #c0392b; }
.calque-poignee {
  position: absolute; width: 11px; height: 11px; border-radius: 999px;
  background: #fff; border: 2px solid #2f6df6;
  cursor: nwse-resize; z-index: 9; display: none;
}
body.mode-edition .calque:hover > .calque-poignee,
body.mode-edition .calque.selection > .calque-poignee { display: block; }
.calque-poignee[data-role="pointe"] { cursor: crosshair; border-color: var(--couleur-annotation); }

/* Retour d'enregistrement (écrasement du HTML + régénération du PDF). */
.editeur-toast {
  position: fixed; bottom: 14px; right: 14px; max-width: 420px; z-index: 10000;
  padding: 10px 13px; border-radius: var(--ui-rayon); border: 1px solid var(--ui-bord);
  background: var(--ui-fond); font-size: 13px; line-height: 1.4;
  box-shadow: var(--ui-ombre);
}
.editeur-toast.toast-ok { background: #eef8ef; border-color: #b6ddb9; }
.editeur-toast.toast-ko { background: #fdecea; border-color: #e3b2ab; }

@media print {
  .editor-bar, .editor-palette, .pose-repere, .editeur-toast { display: none !important; }
}
"""

# Verrouillage de hauteur + styles des calques : conservés dans le HTML
# enregistré (c'est ce bloc qui porte le rendu des ajouts au PDF).
_MODULES_CSS = """
/* --- Hauteur du document verrouillée --------------------------------------
   Une page = exactement 4 unités de la grille, jamais plus. `overflow:hidden`
   garantit qu'aucun ajout (calque ou saisie) ne peut décaler la pagination :
   ce qui dépasse est rogné, pas repoussé. `position:relative` fait de la page
   le repère des coordonnées % des calques. */
.page { position: relative; overflow: hidden; }
/* Repère des calques ancrés à une section : ils suivent leur section d'une
   régénération à l'autre, même si la pagination change. */
.sec { position: relative; }
@media screen { .page { height: 297mm; } }
@media print { .page { height: calc(var(--unit-height) * 4); } }

/* --- Calques : tout ajout est hors flux ----------------------------------
   Position et taille en % de la page → rendu identique à l'écran et au PDF. */
.calque { position: absolute; z-index: 2; line-height: 1.2; }
.calque > :last-child { margin-bottom: 0; }
.calque img { width: 100%; height: auto; display: block; max-height: none; }
.calque figure.image { margin: 0; }

.calque-colonnes { display: table; width: 100%; table-layout: fixed; border-spacing: 4mm 0; }
.calque-colonnes .mod-col { display: table-cell; vertical-align: top; }
.calque-separateur {
  border-top: 2px solid var(--couleur-lisere); border-radius: 999px; height: 0;
}

/* Image + liseré + texte, repris du design-system des templates. */
.calque-ec { display: table; width: 100%; }
.calque-ec .ec-image { display: table-cell; width: 45%; vertical-align: middle; padding-right: 5mm; }
.calque-ec .ec-textwrap { display: table-cell; vertical-align: middle; }
.calque-ec .ec-textinner { display: table; }
.calque-ec .ec-lisere {
  display: table-cell; width: 4px; background: var(--couleur-lisere); border-radius: 999px;
}
.calque-ec .ec-text { display: table-cell; vertical-align: middle; padding-left: 4mm; }

/* --- Annotations ----------------------------------------------------------
   Couleur sémantique fixe (une annotation signale, indépendamment de la
   marque — même logique que les encadrés), surchargeable plus tard par la
   charte via --couleur-annotation. */
:root { --couleur-annotation: #e5322d; }
/* Flèche en CSS pur (hampe + pointe en bordures) et non en SVG : WeasyPrint
   ne résout pas `currentColor` dans un SVG inline, la flèche sortait noire. */
.calque-fleche {
  transform-origin: 0 50%; height: 1.4mm; border-radius: 999px;
  background: var(--couleur-annotation);
}
.calque-fleche::after {
  content: ""; position: absolute; right: -1mm; top: -1.5mm;
  border-left: 3.5mm solid var(--couleur-annotation);
  border-top: 2.2mm solid transparent; border-bottom: 2.2mm solid transparent;
}
.calque-cadre { border: 2px solid var(--couleur-annotation); border-radius: 2px; }
.calque-pastille {
  width: 6.5mm; height: 6.5mm; margin: -3.25mm 0 0 -3.25mm; border-radius: 999px;
  background: var(--couleur-annotation); color: #fff; text-align: center;
  font: 700 10pt/6.5mm "Inter", sans-serif;
}
.calque-etiquette {
  background: #fff; border: 1.5px solid var(--couleur-annotation);
  border-radius: 3px; padding: 1mm 2mm; color: var(--couleur-texte);
  font: 400 9pt/1.25 "Inter", sans-serif;
}
"""

_SCRIPT = r"""
(function () {
  var PLACEHOLDER = "Saisir le texte…";
  // Endpoint d'écrasement, injecté au build (app/serveur.py). Conservé dans le
  // fichier écrit : un HTML rouvert sait toujours où s'enregistrer.
  var API_ENREGISTREMENT = "__API_ENREGISTREMENT__";
  // Mode « aperçu du composeur » : le document affiché pointe vers /vault en
  // http:// et son texte vient du formulaire. On ne persiste donc pas le DOM
  // — on n'envoie que les calques, et le serveur régénère output/article.html
  // depuis content.yaml + retouches.yaml (chemins locaux, PDF correct).
  var REGENERER = __REGENERER__;

  // ---------------------------------------------------------------------
  // Catalogue : contenu HTML, largeur/hauteur par défaut (% de la page) et
  // capacité de redimensionnement. `texte:true` = le clic sert à éditer, le
  // déplacement passe alors par la poignée ⠿.
  // ---------------------------------------------------------------------
  var CALQUES = {
    paragraphe:  { html: '<p class="corps">' + PLACEHOLDER + "</p>", w: 45, texte: true },
    titre:       { html: '<h2 class="titre-2" style="margin:0">Titre</h2>', w: 50, texte: true },
    liste:       { html: '<ul class="corps" style="margin:0"><li>Premier point</li><li>Deuxième point</li></ul>', w: 40, texte: true },
    "encadre-astuce":    { html: encadre("astuce", "Astuce : "), w: 45, texte: true },
    "encadre-attention": { html: encadre("attention", "Attention : "), w: 45, texte: true },
    "encadre-info":      { html: encadre("info", "Info : "), w: 45, texte: true },
    colonnes: {
      cls: "calque-colonnes", w: 60, texte: true,
      html: '<div class="mod-col"><p class="corps">Colonne de gauche</p></div>' +
            '<div class="mod-col"><p class="corps">Colonne de droite</p></div>',
    },
    "etape-compacte": {
      cls: "calque-ec", w: 55, texte: true,
      html: '<div class="ec-image"><figure class="image">' + imgVide() + "</figure></div>" +
            '<div class="ec-textwrap"><div class="ec-textinner"><div class="ec-lisere"></div>' +
            '<div class="ec-text"><p class="corps">' + PLACEHOLDER + "</p></div></div></div>",
    },
    separateur: { cls: "calque-separateur", html: "", w: 40, redim: "largeur" },
    image: { html: "", w: 30, texte: false },  // contenu injecté après choix du fichier
    "annot-fleche":  { cls: "calque-fleche", html: "", w: 20, redim: "fleche" },
    "annot-cadre":   { cls: "calque-cadre", html: "", w: 25, h: 15, redim: "boite" },
    "annot-pastille": { cls: "calque-pastille", html: "", redim: "non" },
    "annot-etiquette": { cls: "calque-etiquette", html: '<span class="calque-texte">Annotation</span>', w: 18, texte: true },
  };

  function encadre(style, prefixe) {
    return '<div class="encadre encadre-' + style + '" style="margin:0">' +
      '<p class="encadre-texte">' + prefixe + PLACEHOLDER + "</p></div>";
  }

  // Cadre gris 16/10 en SVG inline : aucun fichier externe, le HTML enregistré
  // reste autonome.
  function imgVide() {
    var svg =
      "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 160 100'>" +
      "<rect width='160' height='100' fill='%23eee' stroke='%23bbb'/>" +
      "<text x='80' y='54' font-family='sans-serif' font-size='9' fill='%23888' " +
      "text-anchor='middle'>image</text></svg>";
    return "<img src=\"data:image/svg+xml;utf8," + svg + "\" alt=\"\">";
  }

  function el(html) {
    var d = document.createElement("div");
    d.innerHTML = html.trim();
    return d.firstElementChild;
  }

  // ---------------------------------------------------------------------
  // Historique : snapshots des pages. Couvre les calques ET la frappe (par
  // rafales), pour que Ctrl+Z ait un comportement homogène.
  // ---------------------------------------------------------------------
  var histo = [];
  var MAX_HISTO = 60;

  function etatPages() {
    return Array.prototype.map.call(document.querySelectorAll(".page"), function (p) {
      return p.outerHTML;
    }).join("");
  }

  function memoriser() {
    histo.push(etatPages());
    if (histo.length > MAX_HISTO) histo.shift();
    majBoutonAnnuler();
  }

  // Exposée : le composeur s'en sert pour ne pas quitter un tutoriel en
  // laissant tomber des annotations posées mais pas encore enregistrées.
  window.retouchesTouchees = function () {
    return histo.length > 0;
  };

  function annuler() {
    if (!histo.length) return;
    var html = histo.pop();
    document.querySelectorAll(".page").forEach(function (p) { p.remove(); });
    var tmp = document.createElement("div");
    tmp.innerHTML = html;
    var ref = document.body.firstChild;
    while (tmp.firstChild) document.body.insertBefore(tmp.firstChild, ref);
    selection = null;
    majBoutonAnnuler();
  }

  function majBoutonAnnuler() {
    var b = document.getElementById("btn-annuler");
    if (b) b.disabled = histo.length === 0;
  }
  window.annulerAction = annuler;

  // Frappe : un snapshot par rafale (600 ms d'inactivité = nouvelle rafale).
  var derniereFrappe = 0;
  document.addEventListener("beforeinput", function () {
    var t = Date.now();
    if (t - derniereFrappe > 600) memoriser();
    derniereFrappe = t;
  });

  document.addEventListener("keydown", function (ev) {
    if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "z") {
      ev.preventDefault();
      annuler();
    }
  });

  // ---------------------------------------------------------------------
  // Pose des calques
  // ---------------------------------------------------------------------
  var pose = null;      // { hote, x, y } — dernier point cliqué (section ou page)
  var selection = null; // calque sélectionné

  // Hôte d'un calque : la SECTION sous le point de pose si elle existe, sinon
  // la page. Ancrer à la section rend la retouche solidaire de son contenu :
  // si un changement de charte déplace la section, le calque la suit (voir
  // CLAUDE.md §3 et retouches.yaml).
  function hoteCourant() {
    if (pose && document.body.contains(pose.hote)) return pose.hote;
    var page = document.querySelector(".page:last-of-type");
    return page ? (page.querySelector(".sec:last-of-type") || page) : null;
  }

  function selectionner(calque) {
    document.querySelectorAll(".calque.selection").forEach(function (c) {
      c.classList.remove("selection");
    });
    selection = calque;
    if (calque) calque.classList.add("selection");
  }

  function creer(id, contenuHtml) {
    var def = CALQUES[id];
    var hote = hoteCourant();
    if (!hote) return null;
    memoriser();

    var c = document.createElement("div");
    c.className = "calque " + (def.cls || "calque-" + id);
    c.setAttribute("contenteditable", def.texte ? "true" : "false");
    // Attributs persistés dans retouches.yaml : ils suffisent à ré-équiper le
    // calque (poignées, mode de déplacement) après une régénération.
    c.dataset.texte = def.texte ? "oui" : "non";
    c.dataset.redim = def.redim || "boite";
    c.innerHTML = contenuHtml !== undefined ? contenuHtml : def.html;

    // Pastille : numérotation automatique par page.
    if (id === "annot-pastille") {
      var pg = hote.closest(".page") || hote;
      c.textContent = pg.querySelectorAll(".calque-pastille").length + 1;
    }

    var p = pose && pose.hote === hote ? pose : { x: 20, y: 20 };
    c.style.left = p.x.toFixed(2) + "%";
    c.style.top = p.y.toFixed(2) + "%";
    if (def.w) c.style.width = def.w + "%";
    if (def.h) c.style.height = def.h + "%";
    if (id === "annot-fleche") c.style.transform = "translateY(-50%) rotate(0deg)";

    outiller(c);
    hote.appendChild(c);
    selectionner(c);
    c.scrollIntoView({ block: "center", behavior: "smooth" });
    return c;
  }

  // Chrome de manipulation : barrette ⠿/✕ + poignée de redimensionnement.
  // Retiré du HTML enregistré, et re-posé au chargement sur les calques
  // rétablis depuis retouches.yaml (voir equiperCalquesExistants).
  function outiller(c) {
    var outils = el('<span class="calque-outils" contenteditable="false">' +
      '<span class="calque-grip" title="Déplacer">⠿</span>' +
      '<span class="calque-fermer" title="Supprimer">✕</span></span>');
    c.appendChild(outils);
    var redim = c.dataset.redim || "boite";
    if (redim === "non") return;
    var role = redim === "fleche" ? "pointe" : (redim === "largeur" ? "largeur" : "boite");
    var h = el('<span class="calque-poignee" data-role="' + role + '" contenteditable="false"></span>');
    if (role === "pointe") { h.style.right = "-6px"; h.style.top = "calc(50% - 5px)"; }
    else if (role === "largeur") { h.style.right = "-6px"; h.style.top = "-5px"; h.style.cursor = "ew-resize"; }
    else { h.style.right = "-6px"; h.style.bottom = "-6px"; }
    c.appendChild(h);
  }

  // Calques rétablis depuis retouches.yaml : le HTML généré porte leurs
  // attributs (data-texte, data-redim) mais pas le chrome de manipulation.
  function equiperCalquesExistants() {
    document.querySelectorAll(".calque").forEach(function (c) {
      if (!c.querySelector(":scope > .calque-outils")) outiller(c);
    });
  }

  // Représentation structurée des calques, envoyée au serveur pour être
  // persistée dans retouches.yaml (source des retouches, hors content.yaml).
  // Exposée : le composeur récupère les calques de l'aperçu au moment
  // d'« Enregistrer & générer » (app/ui/composeur.js).
  window.collecterCalques = collecterCalques;

  function collecterCalques() {
    var pages = Array.prototype.slice.call(document.querySelectorAll(".page"));
    return Array.prototype.map.call(document.querySelectorAll(".calque"), function (c) {
      var clone = c.cloneNode(true);
      clone.querySelectorAll(".calque-outils, .calque-poignee").forEach(function (e) { e.remove(); });
      var parent = c.parentElement;
      var sec = parent && parent.classList.contains("sec") ? parent : null;
      return {
        ancre_section: sec ? sec.id : null,
        page: Math.max(0, pages.indexOf(c.closest(".page"))),
        classes: c.className.replace(/\s*selection\s*/, " ").trim(),
        style: c.getAttribute("style") || "",
        texte: c.dataset.texte === "oui",
        redim: c.dataset.redim || "boite",
        html: clone.innerHTML,
      };
    });
  }

  function supprimerCalque() {
    if (!selection || !document.body.contains(selection)) return;
    memoriser();
    selection.remove();
    selection = null;
  }

  function imageDepuisFichier() {
    var input = document.createElement("input");
    input.type = "file";
    input.accept = "image/*";
    input.onchange = function () {
      var f = input.files && input.files[0];
      if (!f) return;
      var reader = new FileReader();
      reader.onload = function () {
        // Data URI : le HTML enregistré reste autonome (pas de fichier lié).
        var c = creer("image",
          '<figure class="image"><img alt=""><figcaption class="legende">Légende</figcaption></figure>');
        if (c) c.querySelector("img").src = reader.result;
      };
      reader.readAsDataURL(f);
    };
    input.click();
  }

  function nouvellePage() {
    memoriser();
    var p = el('<div class="page"></div>');
    var h = hoteCourant();
    var ref = h ? (h.closest(".page") || h) : null;
    if (ref) ref.after(p); else document.body.insertBefore(p, document.body.firstChild);
    p.scrollIntoView({ block: "center", behavior: "smooth" });
  }

  // ---------------------------------------------------------------------
  // Déplacement / redimensionnement / rotation
  // Coordonnées en % de l'HÔTE du calque (sa section, ou la page) : un calque
  // déplacé reste exprimé dans le repère qui le suivra à la régénération.
  // ---------------------------------------------------------------------
  var drag = null;

  function pct(v, total) { return Math.max(0, Math.min(100, (v / total) * 100)); }

  document.addEventListener("mousedown", function (ev) {
    if (document.designMode !== "on") return;
    if (ev.target.closest(".editor-bar, .editor-palette")) return;

    var calque = ev.target.closest(".calque");
    if (!calque) {
      // Clic dans le document : mémorise le point de pose du prochain calque,
      // exprimé dans le repère de la section cliquée (à défaut, de la page).
      var hote = ev.target.closest(".sec") || ev.target.closest(".page");
      selectionner(null);
      if (hote) {
        var pr = hote.getBoundingClientRect();
        pose = { hote: hote, x: pct(ev.clientX - pr.left, pr.width), y: pct(ev.clientY - pr.top, pr.height) };
        marquerPose();
      }
      return;
    }
    selectionner(calque);
    if (ev.target.closest(".calque-fermer")) { supprimerCalque(); ev.preventDefault(); return; }

    var poignee = ev.target.closest(".calque-poignee");
    var mode = poignee ? poignee.dataset.role
      : (ev.target.closest(".calque-grip") || calque.dataset.texte !== "oui" ? "move" : null);
    if (!mode) return;  // calque de texte : le clic sert à éditer

    var r = calque.parentElement.getBoundingClientRect();
    // Snapshot pris maintenant mais empilé au premier déplacement réel : un
    // simple clic de sélection ne doit pas créer d'étape d'annulation.
    drag = {
      mode: mode, calque: calque, rect: r, avant: etatPages(),
      dx: ev.clientX - (r.left + (parseFloat(calque.style.left) / 100) * r.width),
      dy: ev.clientY - (r.top + (parseFloat(calque.style.top) / 100) * r.height),
    };
    ev.preventDefault();
  });

  document.addEventListener("mousemove", function (ev) {
    if (!drag) return;
    if (drag.avant) {
      histo.push(drag.avant);
      if (histo.length > MAX_HISTO) histo.shift();
      drag.avant = null;
      majBoutonAnnuler();
    }
    var r = drag.rect, c = drag.calque;
    var l = (parseFloat(c.style.left) / 100) * r.width;
    var t = (parseFloat(c.style.top) / 100) * r.height;

    if (drag.mode === "move") {
      c.style.left = pct(ev.clientX - drag.dx - r.left, r.width).toFixed(2) + "%";
      c.style.top = pct(ev.clientY - drag.dy - r.top, r.height).toFixed(2) + "%";
    } else if (drag.mode === "boite" || drag.mode === "largeur") {
      c.style.width = Math.max(2, pct(ev.clientX - r.left - l, r.width)).toFixed(2) + "%";
      if (drag.mode === "boite" && c.style.height) {
        c.style.height = Math.max(2, pct(ev.clientY - r.top - t, r.height)).toFixed(2) + "%";
      }
    } else if (drag.mode === "pointe") {
      // La flèche part de son ancre (transform-origin: 0 50%) : la poignée
      // fixe à la fois sa longueur et son angle.
      var vx = ev.clientX - (r.left + l), vy = ev.clientY - (r.top + t);
      var angle = (Math.atan2(vy, vx) * 180) / Math.PI;
      c.style.width = Math.max(3, pct(Math.sqrt(vx * vx + vy * vy), r.width)).toFixed(2) + "%";
      c.style.transform = "translateY(-50%) rotate(" + angle.toFixed(1) + "deg)";
    }
    ev.preventDefault();
  });

  document.addEventListener("mouseup", function () { drag = null; });

  function marquerPose() {
    document.querySelectorAll(".pose-repere").forEach(function (e) { e.remove(); });
    if (!pose) return;
    var m = el('<span class="pose-repere" contenteditable="false"></span>');
    m.style.left = pose.x + "%";
    m.style.top = pose.y + "%";
    pose.hote.appendChild(m);
  }

  // ---------------------------------------------------------------------
  // Barre
  // ---------------------------------------------------------------------
  window.toggleEdit = function (btn) {
    var on = document.designMode !== "on";
    document.designMode = on ? "on" : "off";
    btn.classList.toggle("on", on);
    btn.textContent = on ? "✏️ Édition activée" : "✏️ Mode édition";
    document.getElementById("editeur-palette").hidden = !on;
    document.body.classList.toggle("mode-edition", on);
    if (!on) { selectionner(null); document.querySelectorAll(".pose-repere").forEach(function (e) { e.remove(); }); }
  };

  // Écrase output/article.html et régénère le PDF via le service local
  // (app/serveur.py). Pas de « enregistrer sous » : même fichier, même nom.
  // Le chrome de l'éditeur est CONSERVÉ dans le fichier écrit — il est masqué
  // à l'impression et WeasyPrint n'exécute pas de script, donc le PDF reste
  // propre et le fichier écrasé reste rouvrable et ré-éditable.
  window.enregistrerHTML = function (btn) {
    document.designMode = "off";
    document.body.classList.remove("mode-edition");
    var edit = document.getElementById("btn-edit");
    edit.classList.remove("on");
    edit.textContent = "✏️ Mode édition";
    document.getElementById("editeur-palette").hidden = true;
    selectionner(null);

    var calques = collecterCalques();
    var clone = document.documentElement.cloneNode(true);
    // État transitoire de la session + chrome de manipulation : le fichier
    // écrit doit être identique à ce que produira une régénération.
    clone.querySelectorAll(
      ".pose-repere, .editeur-toast, .calque-outils, .calque-poignee"
    ).forEach(function (e) { e.remove(); });
    clone.querySelectorAll(".selection").forEach(function (e) { e.classList.remove("selection"); });
    clone.querySelector("body").classList.remove("mode-edition");

    if (btn) { btn.disabled = true; btn.textContent = "⏳ Enregistrement…"; }
    fetch(API_ENREGISTREMENT, {
      method: "POST",
      headers: { "Content-Type": "application/json;charset=utf-8" },
      body: JSON.stringify({
        html: "<!DOCTYPE html>\n" + clone.outerHTML,
        calques: calques,
        regenerer: REGENERER,
      }),
    })
      .then(function (r) {
        return r.json().then(function (d) {
          if (!r.ok) throw new Error(d.detail || r.status);
          return d;
        });
      })
      .then(function (d) {
        var quoi = REGENERER ? "Document régénéré" : "HTML écrasé";
        toast(d.pdf_erreur
          ? quoi + ". PDF non régénéré : " + d.pdf_erreur
          : quoi + ", PDF régénéré, " + d.calques + " calque(s) enregistré(s).",
          !d.pdf_erreur);
      })
      .catch(function (err) {
        toast(
          "Enregistrement impossible (" + err.message + "). Le service local " +
          "tourne-t-il ? → python -m app.cli serve", false
        );
      })
      .finally(function () {
        if (btn) { btn.disabled = false; btn.textContent = "💾 Enregistrer HTML"; }
      });
  };

  function toast(message, ok) {
    var t = el('<div class="editeur-toast"></div>');
    t.classList.add(ok ? "toast-ok" : "toast-ko");
    t.textContent = message;
    document.body.appendChild(t);
    setTimeout(function () { t.remove(); }, ok ? 4000 : 9000);
  }

  // ---------------------------------------------------------------------
  // Palette
  // ---------------------------------------------------------------------
  document.addEventListener("DOMContentLoaded", function () {
    majBoutonAnnuler();
    equiperCalquesExistants();
    document.getElementById("editeur-palette").addEventListener("click", function (ev) {
      var btn = ev.target.closest("button[data-module]");
      if (!btn) return;
      var id = btn.dataset.module;
      if (id === "image") return imageDepuisFichier();
      if (id === "page") return nouvellePage();
      if (id === "supprimer") return supprimerCalque();
      if (CALQUES[id]) creer(id);
    });
  });
})();
"""


def modules_css_html() -> str:
    """Styles des calques et verrou de hauteur des pages, seuls.

    Indispensables au *rendu* des annotations — donc aussi dans un HTML produit
    sans barre d'édition (production). Sans eux, une pastille posée sur une
    capture retombe en simple texte dans le flux de la section.
    """
    return f'<style id="modules-css">{_MODULES_CSS}</style>'


def editeur_html(
    article_id: str,
    port: int | None = None,
    api_url: str | None = None,
    regenerer: bool = False,
    avec_enregistrement: bool = True,
) -> str:
    """Fragment injecté en fin de `<body>` : styles, barre, palette, script.

    `article_id` cible l'endpoint d'écrasement du service local : le bouton
    « Enregistrer HTML » réécrit output/article.html du même article et
    relance la conversion PDF (voir app/serveur.py).

    `api_url` (avec `regenerer=True`) sert l'aperçu du composeur : le document
    affiché y est un rendu de travail (URL http://, texte piloté par le
    formulaire), donc seuls les calques sont persistés — le serveur reconstruit
    ensuite l'artefact depuis `content.yaml` + `retouches.yaml`.

    `avec_enregistrement=False` retire le bouton « Enregistrer HTML » : dans le
    composeur, c'est « Enregistrer & générer » qui écrit la source *et* les
    calques. Le HTML autonome, lui, le garde — c'est sa seule façon de
    persister une retouche.
    """
    from app.serveur_config import PORT_DEFAUT

    api = api_url or f"http://127.0.0.1:{port or PORT_DEFAUT}/articles/{article_id}/html"
    script = _SCRIPT.replace("__API_ENREGISTREMENT__", api).replace(
        "__REGENERER__", "true" if regenerer else "false"
    )
    enregistrer = (
        '<button onclick="enregistrerHTML(this)">💾 Enregistrer HTML</button>'
        if avec_enregistrement
        else ""
    )
    return (
        f'<style id="editeur-css">{_EDITEUR_CSS}</style>\n'
        f"{modules_css_html()}\n"
        '<div class="editor-bar">'
        '<button id="btn-edit" onclick="toggleEdit(this)">✏️ Mode édition</button>'
        '<button id="btn-annuler" onclick="annulerAction()" disabled>↩ Annuler</button>'
        f"{enregistrer}"
        "</div>\n"
        f"{_palette_html()}\n"
        f"<script>{script}</script>"
    )
