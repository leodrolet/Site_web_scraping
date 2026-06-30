"""
app.py — Interface Streamlit de l'outil de prospection B2B.

Lancer avec :  streamlit run app.py
"""

from datetime import datetime

import pandas as pd
import streamlit as st

import config
from export import COLONNES, generer_excel
from recherche import ErreurAPI, rechercher_entreprise

st.set_page_config(
    page_title="Outil de prospection B2B",
    page_icon="🔍",
    layout="wide",
)

DEPARTEMENTS = ["Marketing", "Ventes", "Les deux"]
REGIONS = ["Canada", "États-Unis", "Europe", "Toutes"]


# ----------------------------------------------------------------------
# Barre latérale : statut des APIs
# ----------------------------------------------------------------------
def afficher_sidebar():
    st.sidebar.header("État des APIs")
    statuts = config.statut_apis()
    for service, presente in statuts.items():
        if presente:
            st.sidebar.success(f"✅ {service} — clé détectée")
        else:
            st.sidebar.error(f"❌ {service} — clé absente")

    if not any(statuts.values()):
        st.sidebar.warning(
            "Aucune clé API détectée. Copiez le fichier « .env.example » "
            "en « .env » et ajoutez au moins votre clé Hunter.io "
            "(voir le README, étape 3)."
        )
    st.sidebar.divider()
    st.sidebar.caption(
        "Les clés se configurent dans le fichier « .env ». "
        "L'outil teste Hunter.io, puis Apollo.io, puis Google (SerpAPI)."
    )


def afficher_tableau(contacts):
    df = pd.DataFrame(contacts, columns=COLONNES)
    st.dataframe(df, use_container_width=True, hide_index=True)


def bouton_telecharger(contacts, prefixe="prospection"):
    excel = generer_excel(contacts)
    nom = f"{prefixe}_{datetime.now().strftime('%Y-%m-%d_%H%M')}.xlsx"
    st.download_button(
        "📥 Télécharger Excel",
        data=excel,
        file_name=nom,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
    )


# ----------------------------------------------------------------------
# En-tête
# ----------------------------------------------------------------------
st.title("🔍 Outil de prospection B2B")
st.caption("Trouvez les bons contacts marketing et ventes en quelques secondes")

afficher_sidebar()

onglet1, onglet2 = st.tabs(["🔎 Recherche simple", "📋 Recherche en lot"])


# ----------------------------------------------------------------------
# Onglet 1 — Recherche simple
# ----------------------------------------------------------------------
with onglet1:
    st.subheader("Rechercher une entreprise")

    col_a, col_b, col_c = st.columns([2, 1, 1])
    with col_a:
        entreprise = st.text_input("Nom de l'entreprise",
                                    placeholder="Ex : Bell Canada")
    with col_b:
        departement = st.selectbox("Département cible", DEPARTEMENTS, index=2)
    with col_c:
        region = st.selectbox("Région", REGIONS, index=0)

    if st.button("Rechercher", type="primary"):
        if not entreprise.strip():
            st.warning("Veuillez saisir le nom d'une entreprise.")
        else:
            with st.spinner(f"Recherche en cours pour « {entreprise} »…"):
                try:
                    res = rechercher_entreprise(entreprise, departement, region)
                    st.session_state["resultats_simple"] = res["contacts"]
                    st.session_state["avert_simple"] = res["avertissements"]
                except ErreurAPI as e:
                    st.error(f"⛔ {e.message}")
                    st.session_state.pop("resultats_simple", None)
                    st.session_state.pop("avert_simple", None)

    if "resultats_simple" in st.session_state:
        contacts = st.session_state["resultats_simple"]
        for av in st.session_state.get("avert_simple", []):
            st.info(av)
        if contacts:
            st.success(f"{len(contacts)} résultat(s) trouvé(s).")
            afficher_tableau(contacts)
            bouton_telecharger(contacts)


# ----------------------------------------------------------------------
# Onglet 2 — Recherche en lot
# ----------------------------------------------------------------------
with onglet2:
    st.subheader("Traiter une liste d'entreprises")
    st.write(
        "Téléversez un fichier CSV avec les colonnes : "
        "`entreprise`, `departement`, `region`. "
        "Un exemple est fourni : « exemple_entree.csv »."
    )

    fichier = st.file_uploader("Fichier CSV", type=["csv"])

    df_entree = None
    if fichier is not None:
        try:
            df_entree = pd.read_csv(fichier)
            df_entree.columns = [c.lower().strip() for c in df_entree.columns]
        except Exception as e:
            st.error(f"Impossible de lire le fichier CSV : {e}")
            df_entree = None

        if df_entree is not None:
            st.write("Aperçu du fichier :")
            st.dataframe(df_entree.head(), use_container_width=True, hide_index=True)

    if df_entree is not None and st.button("Traiter toute la liste", type="primary"):
        requises = {"entreprise", "departement", "region"}
        if not requises.issubset(set(df_entree.columns)):
            st.error(
                "Le CSV doit contenir les colonnes : "
                "entreprise, departement, region."
            )
        else:
            tous_contacts = []
            avertissements = []
            erreur_bloquante = None
            total = len(df_entree)

            barre = st.progress(0.0, text="Démarrage…")
            zone_tableau = st.empty()

            for i, (_, row) in enumerate(df_entree.iterrows()):
                ent = str(row.get("entreprise", "")).strip()
                dep = str(row.get("departement", "Les deux")).strip() or "Les deux"
                reg = str(row.get("region", "Toutes")).strip() or "Toutes"

                barre.progress((i + 1) / total, text=f"({i + 1}/{total}) {ent}")
                try:
                    res = rechercher_entreprise(ent, dep, reg)
                    tous_contacts.extend(res["contacts"])
                    avertissements.extend(res["avertissements"])
                except ErreurAPI as e:
                    erreur_bloquante = e
                    break

                zone_tableau.dataframe(
                    pd.DataFrame(tous_contacts, columns=COLONNES),
                    use_container_width=True,
                    hide_index=True,
                )

            st.session_state["resultats_lot"] = tous_contacts
            barre.empty()

            if erreur_bloquante is not None:
                st.error(
                    f"⛔ Traitement interrompu : {erreur_bloquante.message} "
                    "Les résultats déjà obtenus restent téléchargeables ci-dessous."
                )

            trouves = sum(
                1 for c in tous_contacts
                if c["Prénom"] or c["Courriel"]
            )
            st.success(
                f"Traitement terminé : {len(tous_contacts)} ligne(s), "
                f"dont {trouves} contact(s) avec données exploitables."
            )

    if "resultats_lot" in st.session_state and st.session_state["resultats_lot"]:
        contacts = st.session_state["resultats_lot"]
        afficher_tableau(contacts)
        bouton_telecharger(contacts, prefixe="prospection_lot")
