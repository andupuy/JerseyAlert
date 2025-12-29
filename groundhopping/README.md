# ⚽ Groundhopping Tracker

Application mobile de suivi des matchs de football auxquels vous avez assisté.

## 🎯 Fonctionnalités

### ✅ Gestion des Matchs
- **Ajout de matchs** : Enregistrez facilement chaque match auquel vous assistez
- **Détails complets** : Équipes, score, date, stade, ville, pays, affluence
- **Notes personnelles** : Ajoutez vos impressions et anecdotes
- **Suppression** : Gérez votre liste de matchs

### 📊 Statistiques Complètes
- **Vue d'ensemble** : Total de matchs, stades, pays, buts vus
- **Top stades** : Classement des stades les plus visités
- **Pays visités** : Liste de tous les pays où vous avez vu des matchs
- **Records** : Match le plus prolifique, moyennes, etc.

### 🔍 Recherche et Filtres
- **Recherche** : Trouvez rapidement un match par équipe, stade ou ville
- **Filtres** : Par compétition (Ligue 1, Coupe, Europe, etc.)
- **Tri** : Matchs classés du plus récent au plus ancien

### 📱 Application Mobile
- **Progressive Web App** : Installable sur votre téléphone
- **Mode hors-ligne** : Fonctionne sans connexion internet
- **Stockage local** : Vos données restent sur votre appareil
- **Interface moderne** : Design dark mode avec animations fluides

---

## 🚀 Installation

### Option 1 : Utilisation Directe
1. Ouvrez `index.html` dans votre navigateur
2. L'application fonctionne immédiatement !

### Option 2 : Installation sur Mobile (PWA)
1. Ouvrez l'application dans votre navigateur mobile (Chrome, Safari, etc.)
2. Cliquez sur "Ajouter à l'écran d'accueil"
3. L'application s'installe comme une app native !

### Option 3 : Serveur Local
```bash
# Avec Python
python3 -m http.server 8000

# Avec Node.js
npx http-server

# Puis ouvrez: http://localhost:8000/groundhopping/
```

---

## 📖 Guide d'Utilisation

### Ajouter un Match

1. Cliquez sur le bouton **+** (en bas à droite)
2. Remplissez le formulaire :
   - **Équipes** : Domicile et extérieur
   - **Score** : Résultat final
   - **Date** : Date du match
   - **Compétition** : Ligue 1, Coupe, etc.
   - **Stade** : Nom du stade
   - **Ville et Pays** : Localisation
   - **Affluence** : Nombre de spectateurs (optionnel)
   - **Notes** : Vos impressions (optionnel)
3. Cliquez sur **Enregistrer**

### Voir les Détails d'un Match

1. Cliquez sur une carte de match dans la liste
2. Une fenêtre s'ouvre avec tous les détails
3. Vous pouvez supprimer le match depuis cette fenêtre

### Consulter les Statistiques

1. Cliquez sur l'icône **📊** en haut à droite
2. Consultez :
   - Statistiques générales
   - Top des stades visités
   - Pays visités
   - Match record (plus de buts)

### Rechercher et Filtrer

- **Recherche** : Tapez dans la barre de recherche (équipe, stade, ville)
- **Filtres** : Cliquez sur les boutons (Tous, Ligue 1, Coupe, Europe)

---

## 🎨 Captures d'Écran

### Écran Principal
- Liste de vos matchs avec scores
- Statistiques en un coup d'œil
- Recherche et filtres

### Ajout de Match
- Formulaire complet et intuitif
- Validation des données
- Sauvegarde instantanée

### Détails du Match
- Informations complètes
- Notes personnelles
- Option de suppression

### Statistiques
- Vue d'ensemble de votre parcours
- Top stades et pays
- Records personnels

---

## 💾 Stockage des Données

### LocalStorage
- Toutes vos données sont stockées localement dans votre navigateur
- **Aucune connexion internet requise** après le premier chargement
- **Vos données restent privées** (aucun serveur externe)

### Sauvegarde
Pour sauvegarder vos données :
1. Ouvrez la console du navigateur (F12)
2. Tapez : `localStorage.getItem('groundhopping_matches')`
3. Copiez le résultat et sauvegardez-le dans un fichier texte

### Restauration
Pour restaurer vos données :
1. Ouvrez la console du navigateur (F12)
2. Tapez : `localStorage.setItem('groundhopping_matches', 'VOTRE_SAUVEGARDE')`
3. Rechargez la page

---

## 🎯 Cas d'Usage

### Pour les Groundhoppers
- Suivez votre progression dans la visite des stades
- Gardez une trace de chaque match
- Partagez vos statistiques avec d'autres passionnés

### Pour les Supporters
- Enregistrez tous les matchs de votre équipe favorite
- Revivez les meilleurs moments
- Suivez votre fidélité au stade

### Pour les Collectionneurs
- Complétez votre "collection" de stades
- Visitez tous les stades de Ligue 1
- Explorez les stades européens

---

## 🛠️ Technologies Utilisées

- **HTML5** : Structure sémantique
- **CSS3** : Design moderne avec variables CSS, gradients, animations
- **JavaScript (Vanilla)** : Logique applicative sans framework
- **LocalStorage API** : Stockage des données
- **PWA** : Progressive Web App pour installation mobile
- **Responsive Design** : Optimisé pour mobile et desktop

---

## 📊 Données d'Exemple

L'application inclut 3 matchs d'exemple au premier lancement :
- ASSE 1-0 OM (Stade Geoffroy-Guichard)
- PSG 3-1 ASSE (Parc des Princes)
- OL 2-2 ASSE (Groupama Stadium)

Vous pouvez les supprimer et ajouter vos propres matchs !

---

## 🔮 Fonctionnalités Futures

### Version 2.0 (Prévue)
- [ ] Import/Export des données (JSON, CSV)
- [ ] Intégration API Football pour auto-complétion
- [ ] Photos de matchs
- [ ] Carte interactive des stades visités
- [ ] Partage sur réseaux sociaux
- [ ] Statistiques avancées (graphiques)
- [ ] Mode clair/sombre
- [ ] Multi-langues

### Idées en Réflexion
- Synchronisation cloud (optionnelle)
- Comparaison avec d'autres groundhoppers
- Défis et achievements
- Timeline des matchs
- Prédictions de prochains matchs

---

## 🤝 Contribution

Cette application est open source ! N'hésitez pas à :
- Signaler des bugs
- Proposer des améliorations
- Ajouter des fonctionnalités
- Partager vos retours

---

## 📝 Licence

MIT License - Libre d'utilisation et de modification

---

## 🎉 Bon Groundhopping !

Profitez de chaque match et gardez une trace de vos meilleurs souvenirs footballistiques ! ⚽

---

**Créé avec ❤️ pour les passionnés de football**
