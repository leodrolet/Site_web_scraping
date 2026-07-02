// app.js — interactions de l'outil de prospection
//  · onglets + progression (recherche simple)
//  · « Relancer » depuis l'historique (préremplit, ne lance pas)
//  · tri / filtre du tableau de résultats
//  · aperçu détaillé d'un contact (modale) + copier le courriel
//  · recherche en lot : progression ligne par ligne (flux NDJSON)

(function () {
  "use strict";

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
  // Progression au submit (recherche simple uniquement : data-loading)
  // ----------------------------------------------------------------
  document.querySelectorAll("form[data-loading]").forEach(function (form) {
    form.addEventListener("submit", function () {
      var bouton = form.querySelector('button[type="submit"]');
      var prog = form.querySelector(".progress");
      if (bouton) {
        bouton.disabled = true;
        var libelle = bouton.querySelector(".btn-libelle");
        if (libelle) { libelle.textContent = "Recherche en cours…"; }
      }
      if (prog) { prog.hidden = false; }
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
          btn.textContent = "Courriel copié ✓";
          setTimeout(function () { btn.textContent = "Copier le courriel"; }, 1800);
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

  // Regroupe visuellement les lignes par entreprise selon l'ORDRE COURANT :
  // le nom (colonne 0) n'est affiché que sur la 1re ligne de chaque groupe de
  // lignes consécutives, avec une séparation avant chaque nouveau groupe.
  // La valeur réelle reste dans data-entreprise (tri, filtre, modale).
  function regrouper(tbody) {
    if (!tbody) { return; }
    var prec = null, premier = true;
    Array.prototype.forEach.call(tbody.rows, function (tr) {
      if (tr.style.display === "none") { return; }
      var ent = tr.dataset.entreprise != null ? tr.dataset.entreprise
        : (tr.cells[0] ? tr.cells[0].textContent : "");
      var nouveau = ent !== prec;
      if (tr.cells[0]) { tr.cells[0].textContent = nouveau ? ent : ""; }
      tr.classList.toggle("groupe-debut", nouveau && !premier);
      prec = ent; premier = false;
    });
  }

  function valeurTri(tr, idx) {
    // Colonne 0 = Entreprise : on lit data-entreprise (la cellule peut être vidée).
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
    var entetes = Array.prototype.map.call(
      thead.rows[0].cells, function (th) { return th.textContent.trim(); });

    // Filtre texte en direct (inclut le nom d'entreprise même s'il est masqué)
    var filtre = bloc.querySelector(".filtre-resultats");
    if (filtre) {
      filtre.addEventListener("input", function () {
        var q = filtre.value.trim().toLowerCase();
        Array.prototype.forEach.call(tbody.rows, function (tr) {
          var foin = (tr.textContent + " " + (tr.dataset.entreprise || "")).toLowerCase();
          tr.style.display = (!q || foin.indexOf(q) !== -1) ? "" : "none";
        });
        regrouper(tbody);
      });
    }

    // Tri au clic sur un en-tête
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
        var lignes = Array.prototype.slice.call(tbody.rows);
        lignes.sort(function (a, b) {
          var va = valeurTri(a, idx), vb = valeurTri(b, idx);
          var r;
          if (estNombre(va) && estNombre(vb)) {
            r = parseFloat(va) - parseFloat(vb);
          } else {
            r = va.localeCompare(vb, "fr", { numeric: true });
          }
          return asc ? r : -r;
        });
        lignes.forEach(function (tr) { tbody.appendChild(tr); });
        regrouper(tbody);
      });
    });

    // Clic sur une ligne -> modale détaillée (repli sur data-entreprise si masqué)
    Array.prototype.forEach.call(tbody.rows, function (tr) {
      tr.classList.add("cliquable");
      var ouvrir = function () {
        var courriel = "";
        var paires = Array.prototype.map.call(tr.cells, function (td, i) {
          var label = entetes[i] || ("Champ " + (i + 1));
          var valeur = td.textContent.trim();
          if (i === 0 && !valeur && tr.dataset.entreprise) { valeur = tr.dataset.entreprise; }
          if (label.toLowerCase().indexOf("courriel") !== -1 && valeur) {
            courriel = valeur;
          }
          return { label: label, valeur: valeur };
        });
        ouvrirModale(paires, courriel);
      };
      tr.addEventListener("click", ouvrir);
      tr.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); ouvrir(); }
      });
    });

    // Normalise l'affichage groupé (idempotent avec le rendu serveur).
    regrouper(tbody);
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

  function construireResultats(colonnes, resultats, charge, csrf, nbContacts, nbEntreprises) {
    var bloc = document.createElement("div");
    bloc.className = "resultats";

    var thead = "<tr>" + colonnes.map(function (c, i) {
      return '<th data-col="' + i + '">' + echapper(c) + "</th>";
    }).join("") + "</tr>";
    var corps = resultats.map(function (ligne) {
      var ent = ligne["Entreprise"] != null ? ligne["Entreprise"] : "";
      return '<tr tabindex="0" data-entreprise="' + echapper(ent) + '">' + colonnes.map(function (c, i) {
        var cls = i === 0 ? ' class="cell-entreprise"' : "";
        return "<td" + cls + ">" + echapper(ligne[c] != null ? ligne[c] : "") + "</td>";
      }).join("") + "</tr>";
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

      var reinit = function () {
        if (bouton) { bouton.disabled = false; }
        if (libelle) { libelle.textContent = "Traiter toute la liste"; }
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

          var traiter = function (obj) {
            if (obj.type === "progress") {
              if (obj.trouve) { trouves += 1; }
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
                                                 obj.nb_contacts, obj.nb_entreprises);
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
