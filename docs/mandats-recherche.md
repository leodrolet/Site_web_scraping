# Utiliser les mandats de recherche avec les fichiers de Lyse

## Accès et premier mandat

Se connecter avec un compte administrateur, ouvrir **Mandats**, puis créer un mandat
nommé par exemple « Lyse · Prix d'excellence · Septembre ». Le lien est aussi accessible
depuis le panneau d'administration. L'outil public de recherche conserve son parcours.

Le mandat est privé : seul l'administrateur qui l'a créé peut le consulter ou le modifier.
Le compte administrateur initial est créé avec `setup.py`, comme avant cet ajout.

Dans **Nom, temps de travail et budget**, définir 420 ou 480 minutes. Saisir le total
réellement travaillé au fil des séances; ce total inclut les recherches faites hors du
site et exclut les pauses. Il n'y a pas de chronomètre automatique.

## Importer une liste

Formats acceptés : CSV et Excel `.xlsx`. Un ancien `.xls` doit être converti en `.xlsx`
ou CSV. Les fichiers chiffrés, illisibles et les feuilles contenant des formules sont
refusés avec un message. Pour les formules, copier-coller les **valeurs** dans un nouveau
classeur avant de l'importer. La saisie manuelle reste disponible sur la page du mandat.

Limites : 2 Mo, 2 000 lignes de données, 100 colonnes et 4 000 caractères par cellule.
Pour un classeur à plusieurs feuilles, choisir le numéro de la feuille à importer.
Si le titre du document précède les noms de colonnes, préciser la ligne d'en-tête.

1. **Préparer l'import** lit le fichier et crée un aperçu temporaire. Cela n'ajoute
   aucune organisation au mandat.
2. **Associer les colonnes** propose une correspondance à partir des en-têtes et affiche
   les dix premières lignes. Corriger les choix au besoin. Seule la colonne du nom
   d'organisation est obligatoire. Une colonne ne peut pas servir à deux champs.
3. **Voir l'aperçu et les doublons** montre toutes les lignes normalisées et les erreurs.
4. Choisir le traitement des doublons, puis **Confirmer l'import**. Les lignes invalides
   ne sont exclues qu'après avoir coché la confirmation prévue. Elles pourront être
   saisies manuellement ou réimportées après correction.

Les champs proposés sont : organisation, secteur, pays, région/ville, site web,
prix remporté, notes, liens de sources et construction durable/carbone zéro.
Des en-têtes français et anglais courants sont reconnus; les autres sont associables
manuellement. Les colonnes originales restent consultables sur chaque fiche ajoutée
ou fusionnée, avec le nom du fichier d'origine.

L'aperçu expire après 24 heures. Un import confirmé ne peut pas être rejoué accidentellement.
La copie temporaire du contenu est vidée après confirmation; les valeurs d'origine
conservées dans les fiches restent disponibles.

## Doublons et corrections

La détection compare les noms sans accents, différences de casse, espaces ou ponctuation.
Elle ne fait pas de rapprochement flou : des abréviations, traductions, noms légaux
différents ou filiales peuvent encore nécessiter un examen humain.

Deux noms identiques avec deux pays différents sont conservés séparément. Si le pays
manque sur l'une des lignes, le nom identique est considéré comme un doublon potentiel.
Deux noms différents qui partagent un site ne sont pas fusionnés automatiquement; la
nouvelle fiche est signalée **À vérifier**.

- **Compléter** remplit les champs vides et réunit les prix, sources, notes et indications
  de durabilité. Les valeurs déjà renseignées, contacts et statuts existants sont préservés.
  Les valeurs originales contradictoires restent consultables dans les données du fichier.
- **Ignorer** conserve la fiche existante et n'importe pas la ligne en doublon.

La fiche permet de corriger le nom, le site, la région et les autres données après import.
Une sauvegarde devenue périmée après une modification dans un autre onglet est refusée
pour éviter l'écrasement des données. Recharger la fiche avant de reprendre la modification.

## Effectuer la recherche

Commencer avec le filtre **Les 5 premières (essai)** pour estimer le temps par organisation.
Les tailles servent de repère : environ deux contacts, deux à trois dans une petite
organisation et trois à cinq dans une grande. Il n'y a pas de quota de deux contacts
par fiche; la limite technique est de 100 contacts enregistrés.

La fiche propose des liens préparés pour le site officiel, l'équipe, les communiqués,
les profils professionnels, les responsables Canada/région et la construction durable.
Pour l'enseignement et les organismes publics, les recherches de profils privilégient
communications et partenariats. Les liens ouvrent des recherches publiques dans un autre
onglet; l'application ne parcourt pas les profils ou sites externes automatiquement.

Les fournisseurs configurés dans l'environnement serveur sont facultatifs :

| Fournisseur | Résultat dans le mandat | Limite de l'action |
| --- | --- | --- |
| Hunter | Suggestions de contacts et courriels à vérifier | Une page de recherche par organisation |
| Apollo | Suggestions de personnes; courriel vide s'il n'est pas disponible | Une page de recherche par organisation |
| SerpAPI | Liens de profils publics, affichés comme pistes non vérifiées | Une recherche |

La recherche doit être lancée explicitement pour une organisation. Elle peut consommer
des crédits chez le fournisseur; elle n'ajoute pas de recherches à l'historique public.
Les clés API et les erreurs techniques susceptibles de les révéler restent côté serveur.
Le nombre de pages limité réduit la durée des requêtes sur Vercel (configuration actuelle :
60 secondes); il limite également la couverture des résultats. Aucun traitement complet
du mandat n'est lancé dans une seule requête.

Le nom de l'organisation annoncé par le fournisseur figure dans la note de suggestion.
Vérifier qu'il s'agit de la bonne entreprise. Hunter ne confirme pas la région personnelle.
Le classement par poste ne remplace pas l'évaluation de la pertinence pour ce mandat.

## Vérifier et retenir les contacts

Chaque contact possède un nom, un poste, un département, une région/territoire, une langue
connue, un courriel, des sources, une date, une note et sa provenance. L'organisation est
celle de la fiche. Le nom et le poste peuvent être enregistrés comme piste à vérifier;
les champs absents restent vides.

Pour chaque information, indiquer un lien de preuve dans les sources et préciser dans
la note ce qu'il confirme si les sources diffèrent. Les liens d'identité et de poste
acceptent plusieurs URLs, une par ligne. La source du courriel est un champ distinct.

| Statut | Usage |
| --- | --- |
| Contact à vérifier | Information recueillie ou suggérée, encore à valider |
| Contact vérifié | Poste, liens de preuve et date obligatoires; validation faite par vous |
| Contact écarté | Personne non pertinente; ne peut pas être retenue pour l'export |
| Courriel non trouvé | Champ courriel vide; l'export affiche « non trouvé » |
| Courriel à vérifier | Adresse reçue d'une source, encore à confirmer |
| Courriel trouvé | Adresse disponible et lien de source fiable obligatoire |

L'application vérifie la présence et le format de ces champs, pas la vérité de la source.
Confirmer l'emploi actuel, le rôle, le territoire et la capacité à communiquer en anglais.
Ne pas déduire la langue du pays ni inventer un courriel à partir d'un modèle supposé.
Une suggestion API est toujours **À vérifier**, sans date de vérification et non retenue
par défaut. Les anciens contacts du premier espace « Dossiers » suivent la même règle.

Cocher **Retenir ce contact dans l'export**, puis **Enregistrer ce contact**. Un contact
retenu peut encore être à vérifier : son statut est explicitement exporté. Décocher cette
case pour l'enlever de la sélection sans effacer sa fiche.

## Progression, reprise et remise à Lyse

Enregistrer chaque formulaire avant de quitter la page. Les organisations, contacts et
pistes sont conservés en base, pas uniquement dans le navigateur. Avec JavaScript, un
avertissement signale les formulaires modifiés non enregistrés. Les formulaires et exports
fonctionnent aussi sans JavaScript; seul le filtrage instantané dépend de JavaScript.

Marquer l'organisation **Terminé** lorsque sa recherche est finie. Si aucun contact pertinent
n'a été trouvé, l'indiquer dans les notes et la marquer terminée quand même.

Le tableau affiche le total des organisations (importées et ajoutées manuellement), celles
terminées, celles restantes, les contacts retenus et les fiches qui ont un statut ou des
contacts à vérifier. Une fiche terminée peut encore comporter des contacts à vérifier.

L'export Excel comprend :

1. **Contacts retenus** : uniquement les contacts sélectionnés, une ligne par personne,
   avec leurs sources, langue, région, provenance et statuts de vérification.
2. **Organisations** : toutes les organisations, leurs statuts et notes, incluant celles
   terminées sans contact pertinent. Ce dernier cas est indiqué explicitement.
3. **Bilan** : progression, temps de travail saisi et budget prévu.

Les valeurs externes sont écrites comme texte dans Excel pour empêcher leur interprétation
comme formules. Les URLs sont conservées intégralement dans les cellules.

## Maintenance et vérifications

La migration est additive et idempotente. Elle préserve utilisateurs, mots de passe,
historique, organisations et contacts antérieurs. Les anciennes URLs `/app/dossiers`
redirigent les administrateurs vers les mandats; les anciens formulaires POST sont refusés.
Les anciens dossiers de comptes non administrateurs restent conservés en base et dans
leur export personnel, mais ne sont plus accessibles par les nouvelles routes privées.

`/mes-donnees` inclut les données des mandats appartenant au compte. La suppression d'un
compte par le parcours existant entraîne la suppression de ses mandats, organisations et
aperçus temporaires. En production, `DATABASE_URL` doit toujours pointer vers la base
PostgreSQL persistante; le SQLite temporaire de Vercel ne convient pas à la reprise des mandats.

La suite `tests/test_mandats.py` utilise une base temporaire, des utilisateurs fictifs et
des réponses fournisseurs simulées. Elle couvre les accès, CSRF, import, doublons,
validation, sauvegarde, appels limités, export, migration et suppression en cascade.
Les réponses réelles des fournisseurs, leurs droits de compte et la migration sur la base
PostgreSQL de production doivent être confirmés dans l'environnement de déploiement.
