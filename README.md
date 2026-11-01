# Fiches anesthésie-réanimation (app iPhone)

Site statique installable (PWA), lisible hors ligne, généré à partir du Word `word/fiches.docx`.

## Mettre à jour les fiches
1. Remplacer `word/fiches.docx` par la nouvelle version du Word (même nom, un seul .docx dans le dossier).
2. Commit + push sur `main` : l'action « Publier les fiches » régénère et publie le site (≈ 3 min).
3. Sur l'iPhone, rouvrir l'app : un bandeau « Nouvelle version » propose la mise à jour.

Le Word fait plus de 25 Mo : l'envoi par le site github.com ne marche pas, utiliser GitHub Desktop
(ou envoyer le fichier à Claude dans le projet).

## Structure attendue du Word
- **Titre 1** = domaine. Correspondance dans `build/build.py` (`H1_MAP`) :
  Anesthésie / Réanimation / Infectiologie → Adulte ; Anesthésie pédiatrique / Réanimation pédiatrique → Pédiatrie.
  Un Titre 1 inconnu apparaît dans une rubrique « Autres ».
- **Titre 2** = chapitre (y compris un Titre 2 placé dans la 1re ligne d'un tableau).
- **Titre 3** = section dans le chapitre (raccourcis dans le sommaire, recherche par section).

## Générer en local
```
python3 build/build.py word/fiches.docx site   # nécessite pandoc, Pillow, LibreOffice
cd site && python3 -m http.server
```
