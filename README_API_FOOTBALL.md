# 🔍 Test API Football - ASSE vs OM (Saison 2024-2025)

Ce projet contient des scripts pour tester différentes APIs de football et récupérer les informations des matchs entre deux équipes.

## 📋 Scripts disponibles

### 1. `test_football_data_org.py` ⭐ **RECOMMANDÉ - GRATUIT**

**API utilisée**: [Football-Data.org](https://www.football-data.org/)

**Avantages**:
- ✅ **100% GRATUIT**
- ✅ Pas besoin de carte bancaire
- ✅ 10 requêtes/minute (suffisant pour des tests)
- ✅ Données complètes sur la Ligue 1
- ✅ Simple à configurer

**Comment obtenir une clé API gratuite**:
1. Allez sur: https://www.football-data.org/client/register
2. Créez un compte gratuit (email + mot de passe)
3. Confirmez votre email
4. Connectez-vous et copiez votre clé API
5. Collez la clé dans le script à la ligne: `API_KEY = "VOTRE_CLE_ICI"`

**Utilisation**:
```bash
python test_football_data_org.py
```

---

### 2. `test_api_football.py` (API-Football via RapidAPI)

**API utilisée**: [API-Football](https://www.api-football.com/) via RapidAPI

**Avantages**:
- Plus de données disponibles
- Plus de compétitions (1200+)
- Statistiques détaillées

**Inconvénients**:
- Nécessite un compte RapidAPI
- Plan gratuit limité (100 requêtes/jour)
- Configuration plus complexe

**Comment obtenir une clé API**:
1. Créez un compte sur: https://rapidapi.com/
2. Recherchez "API-Football"
3. Souscrivez au plan gratuit (Basic - $0/mois)
4. Copiez votre clé API RapidAPI
5. Collez la clé dans le script

**Utilisation**:
```bash
python test_api_football.py
```

---

## 🚀 Installation

### Prérequis
- Python 3.7+
- pip

### Installation des dépendances

```bash
pip install requests
```

---

## 📊 Exemple de résultat

Lorsque vous exécutez le script, vous obtiendrez:

```
================================================================================
🔍 RECHERCHE MATCH ASSE - OM (Saison 2024-2025)
================================================================================

✅ 1 match(s) trouvé(s)!

================================================================================
📋 MATCH 1/1
================================================================================

🏆 Compétition: Ligue 1
📅 Date: 08/12/2024 à 21:00
🏟️  Journée: 14
⚽ Statut: FINISHED

🏠 Domicile: AS Saint-Étienne
✈️  Extérieur: Olympique de Marseille

📊 SCORE FINAL: AS Saint-Étienne 0 - 2 Olympique de Marseille
   Mi-temps: 0 - 0

================================================================================

💾 Données complètes sauvegardées dans: match_asse_om_2024_1.json
```

---

## 📁 Fichiers générés

Les scripts génèrent des fichiers JSON contenant toutes les données du match:
- `match_asse_om_2024_1.json` - Données complètes du premier match
- `match_asse_om_2024_2.json` - Données du match retour (si joué)

Ces fichiers contiennent:
- Informations sur les équipes
- Score détaillé (mi-temps, temps réglementaire, prolongations, penalties)
- Arbitres
- Stade
- Date et heure exactes
- Statistiques (selon l'API)

---

## 🔧 Personnalisation

### Rechercher d'autres équipes

Dans `test_football_data_org.py`, modifiez les IDs des équipes:

```python
TEAMS = {
    'ASSE': 1063,  # AS Saint-Étienne
    'OM': 516,     # Olympique de Marseille
    'PSG': 524,    # Paris Saint-Germain
    'OL': 523,     # Olympique Lyonnais
    'LOSC': 521,   # Lille OSC
}

# Puis dans main():
matches = find_matches_between_teams(TEAMS['PSG'], TEAMS['OL'], 2024)
```

### Changer la saison

```python
season = 2023  # Pour la saison 2023-2024
```

---

## ❓ FAQ

### Q: Quelle API choisir?
**R**: Pour commencer, utilisez **Football-Data.org** (gratuit, simple, suffisant pour la Ligue 1)

### Q: Puis-je utiliser ces scripts pour d'autres championnats?
**R**: Oui! Football-Data.org couvre:
- Premier League (Angleterre)
- La Liga (Espagne)
- Bundesliga (Allemagne)
- Serie A (Italie)
- Ligue 1 (France)
- Et plus encore...

### Q: Les données sont-elles en temps réel?
**R**: Oui, les deux APIs fournissent des données en temps réel pendant les matchs.

### Q: Combien de requêtes puis-je faire?
**R**: 
- Football-Data.org: 10 requêtes/minute (gratuit)
- API-Football: 100 requêtes/jour (plan gratuit)

---

## 📞 Support

Si vous rencontrez des problèmes:
1. Vérifiez que votre clé API est correcte
2. Vérifiez votre connexion Internet
3. Consultez la documentation officielle de l'API
4. Vérifiez que vous n'avez pas dépassé la limite de requêtes

---

## 📝 Licence

Ce projet est à usage éducatif et de test. Respectez les conditions d'utilisation des APIs.

---

**Créé pour tester la recherche de matchs ASSE-OM saison 2024-2025** ⚽
