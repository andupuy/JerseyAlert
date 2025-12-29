# 🔄 Import Automatique via API - Guide Complet

## ✅ Nouvelle Fonctionnalité Ajoutée !

Vous pouvez maintenant **importer automatiquement** tous les matchs d'une équipe pour une saison complète en quelques clics !

---

## 🎯 Comment ça marche ?

### Étape 1 : Obtenir une Clé API Gratuite

1. Allez sur **https://www.football-data.org/client/register**
2. Créez un compte gratuit (email + mot de passe)
3. Confirmez votre email
4. Connectez-vous et copiez votre clé API

**Plan gratuit** :
- ✅ 10 requêtes par minute
- ✅ Données depuis 2015
- ✅ Toutes les grandes ligues européennes
- ✅ Aucune carte bancaire requise

---

### Étape 2 : Importer des Matchs

1. **Cliquez sur le bouton d'import** (icône de téléchargement) dans le header
2. **Remplissez le formulaire** :
   - Clé API (sauvegardée automatiquement)
   - Nom de l'équipe (ex: PSG, OM, ASSE, Lyon...)
   - Saison (2024 pour 2024-2025)
3. **Cliquez sur "Rechercher les matchs"**
4. **Sélectionnez les matchs** que vous avez assisté
5. **Cliquez sur "Importer"**

Les matchs sont ajoutés automatiquement à votre liste !

---

## 📋 Équipes Disponibles

### Ligue 1
- **PSG** / Paris Saint-Germain
- **OM** / Olympique de Marseille / Marseille
- **OL** / Olympique Lyonnais / Lyon
- **ASSE** / AS Saint-Étienne / Saint-Étienne
- **LOSC** / Lille
- **Monaco** / AS Monaco
- **Rennes** / Stade Rennais
- **Nice** / OGC Nice
- **Lens** / RC Lens
- **Nantes** / FC Nantes
- **Strasbourg** / RC Strasbourg

### Premier League
- Manchester United
- Liverpool
- Arsenal
- Chelsea
- Manchester City
- Tottenham

### La Liga
- Real Madrid
- Barcelona
- Atletico Madrid

### Bundesliga
- Bayern Munich
- Borussia Dortmund

### Serie A
- Juventus
- AC Milan
- Inter Milan

*Et bien d'autres...*

---

## 🔍 Exemple d'Utilisation

### Cas 1 : Importer tous les matchs du PSG saison 2023-2024

1. Cliquez sur le bouton d'import
2. Entrez votre clé API
3. Équipe : **PSG**
4. Saison : **2023**
5. Rechercher → Sélectionner tous → Importer

**Résultat** : Tous les matchs du PSG en Ligue 1 2023-2024 sont importés !

### Cas 2 : Importer seulement les matchs de l'ASSE auxquels vous avez assisté

1. Cliquez sur le bouton d'import
2. Équipe : **ASSE**
3. Saison : **2024**
4. Rechercher
5. **Décochez** les matchs auxquels vous n'avez pas assisté
6. Importer seulement ceux que vous avez vus

---

## 📊 Données Importées

Pour chaque match, l'API récupère automatiquement :

- ✅ **Équipes** (domicile et extérieur)
- ✅ **Score** (final, mi-temps)
- ✅ **Date** du match
- ✅ **Compétition** (Ligue 1, Champions League, etc.)
- ✅ **Stade**
- ✅ **Ville et pays**
- ✅ **Affluence** (si disponible)

Vous pouvez ensuite ajouter vos **notes personnelles** en éditant le match.

---

## ⚙️ Fonctionnement Technique

### API Utilisée
**Football-Data.org** - API gratuite et fiable

### Processus d'Import

1. **Requête API** : Récupération de tous les matchs de l'équipe
2. **Filtrage** : Seuls les matchs terminés sont proposés
3. **Conversion** : Les données API sont converties au format Groundhopping
4. **Sélection** : Vous choisissez les matchs à importer
5. **Sauvegarde** : Les matchs sont ajoutés à votre collection locale

### Stockage de la Clé API

- Votre clé API est **sauvegardée localement** dans votre navigateur
- Elle n'est **jamais envoyée** à un serveur tiers
- Elle est **réutilisée** automatiquement pour les prochains imports

---

## 🎯 Cas d'Usage

### Pour les Groundhoppers
Importez rapidement tous les matchs d'une équipe, puis décochez ceux auxquels vous n'avez pas assisté.

### Pour les Supporters
Importez toute la saison de votre équipe favorite en un clic !

### Pour les Collectionneurs
Importez les matchs de plusieurs équipes pour compléter votre collection de stades.

---

## 💡 Astuces

### Astuce 1 : Sauvegarde de la Clé API
Votre clé API est sauvegardée après le premier import. Vous n'avez pas besoin de la re-saisir !

### Astuce 2 : Sélection Multiple
Utilisez "Tout sélectionner" puis décochez les matchs auxquels vous n'avez pas assisté.

### Astuce 3 : Import par Saison
Importez saison par saison pour mieux organiser vos matchs.

### Astuce 4 : Vérification
Après l'import, vérifiez les matchs et ajoutez vos notes personnelles.

---

## ⚠️ Limitations

### API Gratuite
- **10 requêtes/minute** : Attendez 1 minute entre chaque import
- **Données depuis 2015** : Les saisons plus anciennes ne sont pas disponibles
- **Matchs terminés uniquement** : Les matchs à venir ne sont pas importés

### Équipes
- Seules les équipes des **grandes ligues européennes** sont disponibles
- Utilisez le **nom exact** ou le **nom court** (PSG, OM, etc.)

---

## 🔧 Résolution de Problèmes

### Erreur "Clé API invalide"
→ Vérifiez que vous avez copié la clé complète depuis football-data.org

### Erreur "Équipe non trouvée"
→ Utilisez le nom complet (ex: "Paris Saint-Germain") ou le nom court (ex: "PSG")
→ Cliquez sur "Voir la liste complète des équipes"

### Erreur "Limite de requêtes dépassée"
→ Attendez 1 minute avant de faire un nouvel import

### Aucun match trouvé
→ Vérifiez que l'équipe a joué cette saison
→ Les données sont disponibles depuis 2015 seulement

---

## 🚀 Prochaines Améliorations

### Version 2.0 (À venir)
- [ ] Support de plus d'équipes
- [ ] Import de plusieurs équipes en une fois
- [ ] Filtrage par compétition avant import
- [ ] Ajout automatique des notes (ambiance, météo, etc.)
- [ ] Synchronisation avec d'autres APIs

---

## 📖 Documentation API

Pour plus d'informations sur l'API Football-Data.org :
- **Site officiel** : https://www.football-data.org/
- **Documentation** : https://www.football-data.org/documentation/quickstart
- **Inscription** : https://www.football-data.org/client/register

---

## ✅ Résumé

**Avant** : Saisie manuelle de chaque match (5-10 minutes par match)
**Maintenant** : Import automatique de toute une saison en 30 secondes !

**Étapes** :
1. Obtenez une clé API gratuite (1 fois)
2. Cliquez sur le bouton d'import
3. Saisissez équipe + saison
4. Sélectionnez les matchs
5. Importez !

---

**Bon import ! 🚀**

Gagnez du temps et profitez de votre passion pour le football ! ⚽

---

*Créé avec ❤️ pour les passionnés de Groundhopping*
