// app.js — interactions de l'outil de prospection
//  · onglets + progression (recherche simple)
//  · « Relancer » depuis l'historique (préremplit, ne lance pas)
//  · tri / filtre du tableau de résultats
//  · aperçu détaillé d'un contact (modale) + copier le courriel
//  · recherche en lot : progression ligne par ligne (flux NDJSON)

(function () {
  "use strict";

  // ----------------------------------------------------------------
  // Bandeau témoins (informatif — témoins essentiels uniquement)
  // ----------------------------------------------------------------
  (function () {
    var bandeau = document.getElementById("bandeau-cookies");
    if (!bandeau) { return; }
    var vu = false;
    try { vu = localStorage.getItem("cookies-vus") === "1"; } catch (e) { vu = false; }
    if (vu) { return; }
    bandeau.hidden = false;
    var ok = document.getElementById("cookies-ok");
    if (ok) {
      ok.addEventListener("click", function () {
        bandeau.hidden = true;
        try { localStorage.setItem("cookies-vus", "1"); } catch (e) { /* ignore */ }
      });
    }
  })();

  // ----------------------------------------------------------------
  // Révélations douces au scroll (respecte prefers-reduced-motion)
  // ----------------------------------------------------------------
  (function () {
    var cibles = document.querySelectorAll(".reveal");
    if (!cibles.length) { return; }
    var reduit = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduit || !("IntersectionObserver" in window)) {
      cibles.forEach(function (el) { el.classList.add("vu"); });
      return;
    }
    var obs = new IntersectionObserver(function (entrees) {
      entrees.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add("vu"); obs.unobserve(e.target); }
      });
    }, { threshold: 0.12, rootMargin: "0px 0px -8% 0px" });
    cibles.forEach(function (el) { obs.observe(el); });
  })();

  // ----------------------------------------------------------------
  // Utilitaires : mouvement réduit, toasts, chargement, cascade
  // ----------------------------------------------------------------
  var reduitMouvement = !!(window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  var titreOriginal = document.title;

  // Notifications discrètes en bas à droite (confirmations légères).
  function toast(message, type) {
    var zone = document.getElementById("toasts");
    if (!zone) {
      zone = document.createElement("div");
      zone.id = "toasts";
      zone.className = "toasts";
      zone.setAttribute("aria-live", "polite");
      document.body.appendChild(zone);
    }
    var t = document.createElement("div");
    t.className = "toast" + (type ? " toast-" + type : "");
    t.setAttribute("role", "status");
    t.textContent = message;
    zone.appendChild(t);
    requestAnimationFrame(function () { t.classList.add("visible"); });
    setTimeout(function () {
      t.classList.remove("visible");
      setTimeout(function () { if (t.parentNode) { t.parentNode.removeChild(t); } }, 320);
    }, 3600);
  }

  var MESSAGES_ATTENTE = [
    "Analyse en cours…", "Vérification des résultats…",
    "Recoupement des données…", "Presque prêt…",
  ];

  // Remplace la zone de résultats par un squelette de tableau qui « pulse »,
  // avec (optionnellement) des messages génériques rotatifs. Change le titre
  // d'onglet. Retourne une fonction d'arrêt (clear interval + titre d'origine).
  function demarrerChargement(avecMessages) {
    document.title = "🔍 Recherche… · ProspectB2B";
    var zone = document.getElementById("zone-resultats");
    var timer = null;
    if (zone) {
      var lignes = "";
      for (var i = 0; i < 6; i++) {
        lignes += '<div class="sk-ligne">' +
          '<span class="sk" style="width:22%"></span>' +
          '<span class="sk" style="width:15%"></span>' +
          '<span class="sk" style="width:26%"></span>' +
          '<span class="sk" style="width:18%"></span></div>';
      }
      var msg = avecMessages
        ? '<p class="chargement-msg" aria-live="polite">' + MESSAGES_ATTENTE[0] + "</p>" : "";
      zone.innerHTML = '<div class="chargement">' + msg +
        '<div class="sk-table">' + lignes + "</div></div>";
      if (avecMessages && !reduitMouvement) {
        var el = zone.querySelector(".chargement-msg");
        var idx = 0;
        timer = setInterval(function () {
          idx = (idx + 1) % MESSAGES_ATTENTE.length;
          if (el) { el.textContent = MESSAGES_ATTENTE[idx]; }
        }, 2500);
      }
    }
    return function arreter() {
      if (timer) { clearInterval(timer); }
      document.title = titreOriginal;
    };
  }

  // Apparition en cascade des lignes de résultats (sautée si mouvement réduit).
  function animerCascade(bloc) {
    if (reduitMouvement || !bloc) { return; }
    var rows = bloc.querySelectorAll("tbody tr:not(.ligne-plus)");
    Array.prototype.forEach.call(rows, function (tr, i) {
      tr.classList.add("cascade");
      tr.style.transitionDelay = Math.min(i * 55, 660) + "ms";
    });
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        Array.prototype.forEach.call(rows, function (tr) { tr.classList.add("cascade-vu"); });
      });
    });
    setTimeout(function () {
      Array.prototype.forEach.call(rows, function (tr) { tr.style.transitionDelay = ""; });
    }, 1500);
  }

  // Message de valeur (uniquement si au moins un contact a été trouvé).
  function messageValeur(bloc) {
    if (!bloc || bloc.querySelector(".valeur-msg")) { return; }
    var past = bloc.querySelector(".pastille");
    var n = past ? (parseInt(past.textContent, 10) || 0) : 0;
    if (n < 1) { return; }
    var minutes = n * 5;   // estimation prudente : ~5 min / contact à la main
    var p = document.createElement("p");
    p.className = "valeur-msg";
    p.innerHTML = '<svg class="ic-sm" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
      'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
      '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>' +
      '<span>Soit environ <strong>' + minutes + ' min</strong> de recherche manuelle ' +
      'épargnées <span class="muted">(estimation)</span>.</span>';
    var tete = bloc.querySelector(".resultats-tete");
    if (tete && tete.parentNode) { tete.parentNode.insertBefore(p, tete.nextSibling); }
  }

  // ----------------------------------------------------------------
  // Onglets
  // ----------------------------------------------------------------
  function activerOnglet(cible) {
    document.querySelectorAll(".tab").forEach(function (b) {
      b.classList.toggle("actif", b.dataset.cible === cible);
    });
    document.querySelectorAll(".panneau").forEach(function (p) {
      p.hidden = p.id !== cible;
    });
  }
  document.querySelectorAll(".tab").forEach(function (bouton) {
    bouton.addEventListener("click", function () {
      activerOnglet(bouton.dataset.cible);
    });
  });

  // ----------------------------------------------------------------
  // Raccourci « / » : focus sur « Nom de l'entreprise » (hors saisie)
  // ----------------------------------------------------------------
  document.addEventListener("keydown", function (e) {
    var a = document.activeElement;
    var enSaisie = a && (a.tagName === "INPUT" || a.tagName === "TEXTAREA" ||
      a.tagName === "SELECT" || a.isContentEditable);
    if (e.key === "/" && !enSaisie) {
      var champ = document.getElementById("entreprise");
      if (champ) {
        e.preventDefault();
        activerOnglet("onglet-simple");
        champ.focus();
      }
    } else if (e.key === "Escape" && a && a.id === "entreprise") {
      a.blur();
    }
  });

  // ----------------------------------------------------------------
  // Bouton « Renvoyer le courriel » : décompte de 60 s (page confirmation)
  // ----------------------------------------------------------------
  (function () {
    var btn = document.querySelector("button[data-cooldown]");
    if (!btn) { return; }
    var restant = parseInt(btn.dataset.cooldown, 10) || 0;
    if (restant <= 0) { return; }
    var libelle = btn.querySelector(".btn-libelle") || btn;
    var base = libelle.textContent;
    btn.disabled = true;
    (function tic() {
      if (restant <= 0) { btn.disabled = false; libelle.textContent = base; return; }
      libelle.textContent = base + " (" + restant + " s)";
      restant -= 1;
      setTimeout(tic, 1000);
    })();
  })();

  // ----------------------------------------------------------------
  // Progression au submit (recherche simple uniquement : data-loading)
  // ----------------------------------------------------------------
  document.querySelectorAll("form[data-loading]").forEach(function (form) {
    form.addEventListener("submit", function () {
      var bouton = form.querySelector('button[type="submit"]');
      if (bouton) {
        bouton.disabled = true;
        var libelle = bouton.querySelector(".btn-libelle");
        if (libelle) { libelle.textContent = "Recherche en cours…"; }
      }
      // Squelette + messages rotatifs + titre d'onglet (le POST recharge ensuite
      // la page ; le squelette reste visible pendant l'attente serveur).
      demarrerChargement(true);
      toast("Recherche lancée…");
    });
  });

  // ----------------------------------------------------------------
  // « Relancer » : préremplit la recherche simple, sans la lancer
  // ----------------------------------------------------------------
  function definirValeur(id, valeur) {
    var el = document.getElementById(id);
    if (!el) { return; }
    if (el.tagName === "SELECT") {
      var ok = Array.prototype.some.call(el.options, function (o) {
        return o.value === valeur;
      });
      if (ok) { el.value = valeur; }
    } else {
      el.value = valeur;
    }
  }
  document.querySelectorAll(".btn-relancer").forEach(function (bouton) {
    bouton.addEventListener("click", function () {
      definirValeur("entreprise", bouton.dataset.entreprise || "");
      definirValeur("departement", bouton.dataset.departement || "");
      definirValeur("region", bouton.dataset.region || "");
      activerOnglet("onglet-simple");
      var champ = document.getElementById("entreprise");
      if (champ) {
        champ.scrollIntoView({ behavior: "smooth", block: "center" });
        champ.focus();
      }
    });
  });

  // ----------------------------------------------------------------
  // Modale : aperçu détaillé d'un contact
  // ----------------------------------------------------------------
  var modale = document.getElementById("modal-contact");

  function fermerModale() {
    if (!modale) { return; }
    modale.hidden = true;
    document.body.style.overflow = "";
  }
  function ouvrirModale(paires, courriel) {
    if (!modale) { return; }
    var corps = document.getElementById("modal-corps");
    var actions = document.getElementById("modal-actions");
    corps.textContent = "";
    actions.textContent = "";
    paires.forEach(function (p) {
      var dt = document.createElement("dt");
      dt.textContent = p.label;
      var dd = document.createElement("dd");
      dd.textContent = p.valeur ? p.valeur : "—";
      if (!p.valeur) { dd.classList.add("vide"); }
      corps.appendChild(dt);
      corps.appendChild(dd);
    });
    if (courriel) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn";
      btn.textContent = "Copier le courriel";
      btn.addEventListener("click", function () {
        var done = function () {
          btn.textContent = "Copié ✓";
          btn.classList.add("btn-ok");
          setTimeout(function () {
            btn.textContent = "Copier le courriel";
            btn.classList.remove("btn-ok");
          }, 2000);
        };
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(courriel).then(done, function () {});
        } else {
          done();
        }
      });
      actions.appendChild(btn);
    }
    modale.hidden = false;
    document.body.style.overflow = "hidden";
  }
  if (modale) {
    modale.querySelectorAll("[data-fermer]").forEach(function (el) {
      el.addEventListener("click", fermerModale);
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && !modale.hidden) { fermerModale(); }
    });
  }

  // ----------------------------------------------------------------
  // Résultats : filtre, tri, clic -> détail
  // ----------------------------------------------------------------
  function estNombre(v) {
    return v !== "" && !isNaN(parseFloat(v));
  }
  function estOutil(tr) { return tr.classList.contains("ligne-plus"); }

  // Entreprises pour lesquelles « Voir plus » a déjà été utilisé (1 fois max).
  var entreprisesEtendues = {};

  function csrfToken() {
    var el = document.querySelector('input[name="csrf_token"]');
    return el ? el.value : "";
  }
  function colonnesDe(table) {
    return table.tHead ? Array.prototype.map.call(
      table.tHead.rows[0].cells, function (th) { return th.textContent.trim(); }) : [];
  }
  function b64url(str) {
    // base64 url-safe d'une chaîne UTF-8 (compatible avec le décodeur serveur).
    return btoa(unescape(encodeURIComponent(str))).replace(/\+/g, "-").replace(/\//g, "_");
  }

  // Construit une <tr> de contact (mêmes attributs que le rendu serveur).
  function construireLigne(colonnes, ligne, dep, reg) {
    var ent = ligne["Entreprise"] != null ? ligne["Entreprise"] : "";
    return '<tr tabindex="0" data-entreprise="' + echapper(ent) + '"' +
      ' data-departement="' + echapper(dep || "Les deux") + '"' +
      ' data-region="' + echapper(reg || "Toutes") + '">' +
      colonnes.map(function (c, i) {
        var cls = i === 0 ? ' class="cell-entreprise"' : "";
        return "<td" + cls + ">" + echapper(ligne[c] != null ? ligne[c] : "") + "</td>";
      }).join("") + "</tr>";
  }

  // Regroupe visuellement par entreprise selon l'ORDRE COURANT : le nom (col 0)
  // n'apparaît qu'une fois par groupe de lignes consécutives. Ignore les lignes
  // outil (« Voir plus »). La valeur réelle reste dans data-entreprise.
  function regrouper(tbody) {
    if (!tbody) { return; }
    var prec = null, premier = true;
    Array.prototype.forEach.call(tbody.rows, function (tr) {
      if (estOutil(tr) || tr.style.display === "none") { return; }
      var ent = tr.dataset.entreprise != null ? tr.dataset.entreprise
        : (tr.cells[0] ? tr.cells[0].textContent : "");
      var nouveau = ent !== prec;
      if (tr.cells[0]) { tr.cells[0].textContent = nouveau ? ent : ""; }
      tr.classList.toggle("groupe-debut", nouveau && !premier);
      prec = ent; premier = false;
    });
  }

  // Ajoute un bouton « Voir plus » après chaque groupe d'EXACTEMENT 5 contacts
  // (signal probable qu'il en existe d'autres), sauf entreprises déjà étendues.
  function ajouterBoutonsPlus(bloc) {
    var table = bloc.querySelector("table");
    if (!table) { return; }
    var tbody = table.tBodies[0];
    if (!tbody) { return; }
    var nbCol = table.tHead ? table.tHead.rows[0].cells.length : 12;
    Array.prototype.slice.call(tbody.querySelectorAll("tr.ligne-plus"))
      .forEach(function (tr) { tbody.removeChild(tr); });

    var rows = Array.prototype.filter.call(tbody.rows, function (tr) { return !estOutil(tr); });
    var i = 0;
    while (i < rows.length) {
      var ent = rows[i].dataset.entreprise || "";
      var j = i, count = 0;
      while (j < rows.length && (rows[j].dataset.entreprise || "") === ent) { count++; j++; }
      if (count === 5 && ent && !entreprisesEtendues[ent]) {
        var ref = rows[j - 1];
        var dep = rows[i].dataset.departement || "Les deux";
        var reg = rows[i].dataset.region || "Toutes";
        var tr = document.createElement("tr");
        tr.className = "ligne-plus";
        tr.dataset.entreprise = ent; tr.dataset.departement = dep; tr.dataset.region = reg;
        tr.innerHTML = '<td colspan="' + nbCol + '"><button type="button" class="btn-plus">' +
          "Voir plus de contacts pour " + echapper(ent) + "</button></td>";
        if (ref.nextSibling) { tbody.insertBefore(tr, ref.nextSibling); }
        else { tbody.appendChild(tr); }
      }
      i = j;
    }
  }

  function ouvrirDepuisLigne(tr, entetes) {
    var courriel = "";
    var paires = Array.prototype.map.call(tr.cells, function (td, i) {
      var label = entetes[i] || ("Champ " + (i + 1));
      var valeur = td.textContent.trim();
      if (i === 0 && !valeur && tr.dataset.entreprise) { valeur = tr.dataset.entreprise; }
      if (label.toLowerCase().indexOf("courriel") !== -1 && valeur) { courriel = valeur; }
      return { label: label, valeur: valeur };
    });
    ouvrirModale(paires, courriel);
  }

  function valeurTri(tr, idx) {
    if (idx === 0) { return tr.dataset.entreprise != null ? tr.dataset.entreprise : ""; }
    return tr.cells[idx] ? tr.cells[idx].textContent.trim() : "";
  }

  function activerResultats(bloc) {
    if (!bloc) { return; }
    var table = bloc.querySelector("table");
    if (!table) { return; }
    var thead = table.tHead;
    var tbody = table.tBodies[0];
    if (!thead || !tbody) { return; }
    var entetes = colonnesDe(table);

    // Filtre texte en direct (les boutons « Voir plus » sont masqués pendant le filtre)
    var filtre = bloc.querySelector(".filtre-resultats");
    if (filtre) {
      filtre.addEventListener("input", function () {
        var q = filtre.value.trim().toLowerCase();
        Array.prototype.forEach.call(tbody.rows, function (tr) {
          if (estOutil(tr)) { tr.style.display = q ? "none" : ""; return; }
          var foin = (tr.textContent + " " + (tr.dataset.entreprise || "")).toLowerCase();
          tr.style.display = (!q || foin.indexOf(q) !== -1) ? "" : "none";
        });
        regrouper(tbody);
      });
    }

    // Tri au clic sur un en-tête (les lignes outil sont retirées puis recalculées)
    Array.prototype.forEach.call(thead.rows[0].cells, function (th, idx) {
      th.classList.add("triable");
      th.addEventListener("click", function () {
        var asc = th.dataset.sens !== "asc";
        Array.prototype.forEach.call(thead.rows[0].cells, function (c) {
          c.removeAttribute("data-sens");
          c.classList.remove("tri-asc", "tri-desc");
        });
        th.dataset.sens = asc ? "asc" : "desc";
        th.classList.add(asc ? "tri-asc" : "tri-desc");
        Array.prototype.slice.call(tbody.querySelectorAll("tr.ligne-plus"))
          .forEach(function (tr) { tbody.removeChild(tr); });
        var lignes = Array.prototype.slice.call(tbody.rows);
        lignes.sort(function (a, b) {
          var va = valeurTri(a, idx), vb = valeurTri(b, idx);
          var r;
          if (estNombre(va) && estNombre(vb)) { r = parseFloat(va) - parseFloat(vb); }
          else { r = va.localeCompare(vb, "fr", { numeric: true }); }
          return asc ? r : -r;
        });
        lignes.forEach(function (tr) { tbody.appendChild(tr); });
        regrouper(tbody);
        ajouterBoutonsPlus(bloc);
      });
    });

    // Clic sur une ligne -> modale (délégation : gère aussi les lignes ajoutées).
    tbody.addEventListener("click", function (e) {
      if (e.target.closest && e.target.closest(".btn-plus")) { return; }
      var tr = e.target.closest ? e.target.closest("tr") : null;
      if (!tr || estOutil(tr) || !tbody.contains(tr)) { return; }
      ouvrirDepuisLigne(tr, entetes);
    });
    tbody.addEventListener("keydown", function (e) {
      if (e.key !== "Enter" && e.key !== " ") { return; }
      var tr = e.target.closest ? e.target.closest("tr") : null;
      if (!tr || estOutil(tr)) { return; }
      e.preventDefault();
      ouvrirDepuisLigne(tr, entetes);
    });

    // « Voir plus de contacts » : requête d'enrichissement (ne touche pas le quota).
    tbody.addEventListener("click", function (e) {
      var btn = e.target.closest ? e.target.closest(".btn-plus") : null;
      if (!btn) { return; }
      e.preventDefault();
      var tr = btn.closest("tr.ligne-plus");
      var ent = tr.dataset.entreprise;
      var dep = tr.dataset.departement || "Les deux";
      var reg = tr.dataset.region || "Toutes";
      var deja = Array.prototype.filter.call(tbody.rows, function (r) {
        return !estOutil(r) && (r.dataset.entreprise || "") === ent;
      }).length;
      btn.disabled = true;
      btn.textContent = "Chargement…";
      var corps = new URLSearchParams();
      corps.set("csrf_token", csrfToken());
      corps.set("entreprise", ent);
      corps.set("departement", dep);
      corps.set("region", reg);
      corps.set("deja", String(deja));
      fetch("/app/plus-de-contacts", { method: "POST", body: corps })
        .then(function (r) { return r.json(); })
        .then(function (j) {
          entreprisesEtendues[ent] = true;   // une seule requête par entreprise
          if (j.erreur) { btn.disabled = false; btn.textContent = j.erreur; return; }
          var cols = j.colonnes || entetes;
          var nouveaux = j.contacts || [];
          nouveaux.forEach(function (c) {
            var tmp = document.createElement("tbody");
            tmp.innerHTML = construireLigne(cols, c, dep, reg);
            tbody.insertBefore(tmp.firstChild, tr);
          });
          if (tr.parentNode) { tbody.removeChild(tr); }
          regrouper(tbody);
          // met à jour « Y contacts trouvés » (les entreprises ne changent pas)
          var past = bloc.querySelector(".pastille");
          if (past) {
            var reels = nouveaux.filter(function (c) { return c["Prénom"] || c["Courriel"]; }).length;
            past.textContent = String((parseInt(past.textContent, 10) || 0) + reels);
          }
        })
        .catch(function () { btn.disabled = false; btn.textContent = "Réessayer"; });
    });

    // Avant téléchargement : reconstruit `charge` depuis le tableau affiché
    // (inclut donc les contacts ajoutés par « Voir plus »).
    var formDl = bloc.querySelector('form[action="/app/telecharger"]');
    if (formDl) {
      formDl.addEventListener("submit", function () {
        var inp = formDl.querySelector('input[name="charge"]');
        if (!inp) { return; }
        var arr = [];
        Array.prototype.forEach.call(tbody.rows, function (tr) {
          if (estOutil(tr)) { return; }
          var obj = {};
          Array.prototype.forEach.call(tr.cells, function (td, i) {
            var v = td.textContent.trim();
            if (i === 0 && !v && tr.dataset.entreprise) { v = tr.dataset.entreprise; }
            obj[entetes[i] || ("c" + i)] = v;
          });
          arr.push(obj);
        });
        inp.value = b64url(JSON.stringify(arr));
        toast("Export téléchargé");
      });
    }

    regrouper(tbody);
    ajouterBoutonsPlus(bloc);
    animerCascade(bloc);
    messageValeur(bloc);
  }

  // Active les résultats déjà rendus par le serveur (recherche simple, etc.)
  activerResultats(document.querySelector("#zone-resultats .resultats"));

  // ----------------------------------------------------------------
  // Admin : filtre de la liste des comptes
  // ----------------------------------------------------------------
  var filtreComptes = document.getElementById("filtre-comptes");
  if (filtreComptes) {
    var corpsComptes = document.querySelector(".table-admin tbody");
    filtreComptes.addEventListener("input", function () {
      var q = filtreComptes.value.trim().toLowerCase();
      if (!corpsComptes) { return; }
      Array.prototype.forEach.call(corpsComptes.rows, function (tr) {
        tr.style.display = (!q || tr.textContent.toLowerCase().indexOf(q) !== -1)
          ? "" : "none";
      });
    });
  }

  // ----------------------------------------------------------------
  // Confirmation avant actions sensibles (admin, suppression…)
  // ----------------------------------------------------------------
  document.querySelectorAll("form.form-confirmer").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      var msg = form.dataset.confirm || "Confirmer cette action ?";
      if (!window.confirm(msg)) { e.preventDefault(); }
    });
  });

  // ----------------------------------------------------------------
  // Recherche en lot : flux de progression ligne par ligne
  // ----------------------------------------------------------------
  function echapper(t) {
    var d = document.createElement("div");
    d.textContent = t == null ? "" : String(t);
    return d.innerHTML;
  }

  function construireResultats(colonnes, resultats, charge, csrf, nbContacts, nbEntreprises, infosEnt) {
    var bloc = document.createElement("div");
    bloc.className = "resultats";
    infosEnt = infosEnt || {};

    var thead = "<tr>" + colonnes.map(function (c, i) {
      return '<th data-col="' + i + '">' + echapper(c) + "</th>";
    }).join("") + "</tr>";
    var corps = resultats.map(function (ligne) {
      var ent = ligne["Entreprise"] != null ? ligne["Entreprise"] : "";
      var info = infosEnt[ent] || {};
      return construireLigne(colonnes, ligne, info.dep, info.reg);
    }).join("");

    bloc.innerHTML =
      '<div class="resultats-tete">' +
        '<h2><span class="pastille">' + (nbContacts != null ? nbContacts : resultats.length) +
          '</span> contact(s) trouvé(s) <span class="compteur-sec">· ' +
          (nbEntreprises != null ? nbEntreprises : 1) + ' entreprise(s)</span></h2>' +
        '<form method="post" action="/app/telecharger">' +
          '<input type="hidden" name="csrf_token" value="' + echapper(csrf) + '">' +
          '<input type="hidden" name="charge" value="' + echapper(charge) + '">' +
          '<button class="btn" type="submit">Télécharger Excel</button>' +
        "</form>" +
      "</div>" +
      '<div class="resultats-outils">' +
        '<div class="input-wrap">' +
          '<svg class="input-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg>' +
          '<input type="search" class="filtre-resultats" placeholder="Filtrer les résultats…" aria-label="Filtrer les résultats">' +
        "</div>" +
        '<span class="resultats-hint muted">Cliquez une ligne pour le détail · cliquez un en-tête pour trier</span>' +
      "</div>" +
      '<div class="tableau-scroll"><table class="table-resultats"><thead>' +
        thead + "</thead><tbody>" + corps + "</tbody></table></div>";
    return bloc;
  }

  var formLot = document.getElementById("form-lot");
  if (formLot && window.fetch && window.ReadableStream) {
    formLot.addEventListener("submit", function (e) {
      var champFichier = formLot.querySelector('input[type="file"]');
      if (!champFichier || !champFichier.files.length) { return; }  // laisse le navigateur gérer "required"
      e.preventDefault();

      var url = formLot.dataset.flux || "/app/lot/flux";
      var bouton = formLot.querySelector('button[type="submit"]');
      var libelle = bouton ? bouton.querySelector(".btn-libelle") : null;
      var zoneProg = document.getElementById("lot-progress");
      var texte = document.getElementById("lot-progress-texte");
      var compte = document.getElementById("lot-progress-compte");
      var barre = document.getElementById("lot-progress-barre");
      var zoneResultats = document.getElementById("zone-resultats");

      if (bouton) { bouton.disabled = true; }
      if (libelle) { libelle.textContent = "Traitement en cours…"; }
      if (zoneProg) { zoneProg.hidden = false; }
      if (texte) { texte.textContent = "Préparation…"; }
      if (compte) { compte.textContent = ""; }
      if (barre) { barre.style.width = "0%"; }
      if (zoneResultats) { zoneResultats.textContent = ""; }
      demarrerChargement(false);   // squelette dans la zone résultats + titre d'onglet
      toast("Recherche lancée…");

      var reinit = function () {
        if (bouton) { bouton.disabled = false; }
        if (libelle) { libelle.textContent = "Traiter toute la liste"; }
        document.title = titreOriginal;
      };
      var afficherErreur = function (msg) {
        if (zoneProg) { zoneProg.hidden = true; }
        if (zoneResultats) {
          zoneResultats.innerHTML =
            '<div class="alerte alerte-error"><span>' + echapper(msg) + "</span></div>";
        }
        reinit();
      };

      var data = new FormData(formLot);
      fetch(url, { method: "POST", body: data, headers: { "Accept": "application/x-ndjson" } })
        .then(function (rep) {
          var ctype = rep.headers.get("content-type") || "";
          if (!rep.ok || ctype.indexOf("ndjson") === -1) {
            // Erreur renvoyée en JSON (CSRF, quota, CSV invalide…)
            return rep.json().then(function (j) {
              throw new Error(j.erreur || "Traitement impossible.");
            }, function () { throw new Error("Traitement impossible."); });
          }
          var lecteur = rep.body.getReader();
          var decodeur = new TextDecoder();
          var tampon = "";
          var trouves = 0;
          var infosEnt = {};   // entreprise -> {dep, reg} (pour « Voir plus »)

          var traiter = function (obj) {
            if (obj.type === "progress") {
              if (obj.trouve) { trouves += 1; }
              if (obj.entreprise) { infosEnt[obj.entreprise] = { dep: obj.dep, reg: obj.reg }; }
              var pct = obj.total ? Math.round(obj.courante * 100 / obj.total) : 0;
              if (barre) { barre.style.width = pct + "%"; }
              if (texte) {
                texte.textContent = "Traitement " + obj.courante + " / " + obj.total;
              }
              if (compte) {
                compte.textContent = trouves + " avec contact(s)";
              }
            } else if (obj.type === "done") {
              if (texte) { texte.textContent = "Terminé"; }
              if (barre) { barre.style.width = "100%"; }
              if (zoneResultats) {
                zoneResultats.textContent = "";
                if (obj.erreur) {
                  var al = document.createElement("div");
                  al.className = "alerte alerte-warn";
                  al.innerHTML = "<span>" + echapper(obj.erreur) + "</span>";
                  zoneResultats.appendChild(al);
                }
                if (obj.resultats && obj.resultats.length) {
                  var csrf = (formLot.querySelector('[name="csrf_token"]') || {}).value || "";
                  var bloc = construireResultats(obj.colonnes, obj.resultats, obj.charge, csrf,
                                                 obj.nb_contacts, obj.nb_entreprises, infosEnt);
                  zoneResultats.appendChild(bloc);
                  activerResultats(bloc);
                } else if (!obj.erreur) {
                  var info = document.createElement("div");
                  info.className = "alerte alerte-info";
                  info.innerHTML = "<span>Aucun résultat pour ce fichier.</span>";
                  zoneResultats.appendChild(info);
                }
              }
              reinit();
            }
          };

          var pomper = function () {
            return lecteur.read().then(function (res) {
              tampon += decodeur.decode(res.value || new Uint8Array(), { stream: !res.done });
              var lignes = tampon.split("\n");
              tampon = res.done ? "" : lignes.pop();
              lignes.forEach(function (l) {
                l = l.trim();
                if (!l) { return; }
                try { traiter(JSON.parse(l)); } catch (err) { /* ligne partielle */ }
              });
              if (!res.done) { return pomper(); }
            });
          };
          return pomper();
        })
        .catch(function (err) {
          afficherErreur(err && err.message ? err.message : "Traitement impossible.");
        });
    });
  }
})();
