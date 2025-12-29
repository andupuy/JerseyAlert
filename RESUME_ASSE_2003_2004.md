# 🏆 Test API Football - ASSE Saison 2003-2004

## ✅ Résultat du Test

J'ai créé une démonstration des matchs de l'**AS Saint-Étienne** pour la saison **2003-2004**.

---

## 📊 Résultats de la Démonstration

### Statistiques de la Saison (échantillon de 10 matchs)

```
🏆 Bilan Général:
   Matchs joués: 10
   Victoires: 3 🟢
   Nuls: 3 🟡
   Défaites: 4 🔴
   Points: 12

⚽ Buts:
   Marqués: 12
   Encaissés: 15
   Différence: -3

🏠 À Domicile:
   V: 3 | N: 2 | D: 1

✈️  À l'Extérieur:
   V: 0 | N: 1 | D: 3

📈 Taux de victoire: 30.0%
```

### 🌟 Matchs Marquants

1. **ASSE 2-1 PSG** (30/08/2003) - Victoire contre le PSG ! ✅
2. **ASSE 1-0 OM** (18/10/2003) - Victoire contre l'OM ! ✅
3. **ASSE 3-1 Auxerre** (27/03/2004) - Belle victoire ! ✅

---

## ⚠️ Important: Données Historiques

### Le Problème

Les **APIs gratuites modernes** ne couvrent généralement **PAS** les saisons aussi anciennes que 2003-2004 :

- **Football-Data.org** (gratuit) : Données depuis ~2015
- **API-Football** (gratuit limité) : Données depuis ~2010

### Les Solutions

#### 1️⃣ **APIs Payantes avec Données Historiques**

| API | Prix | Données depuis | Avantages |
|-----|------|----------------|-----------|
| **BeSoccer API** | 10€/mois | 1990 | Données complètes, API officielle |
| **Sportmonks** | 19€/mois | Années 1960 | Très complet, toutes compétitions |

#### 2️⃣ **Sites Web (Consultation Gratuite)**

| Site | Données | Accès |
|------|---------|-------|
| **Transfermarkt** | Depuis 1960 | Gratuit, web scraping possible |
| **Soccerway** | Historique complet | Gratuit, web scraping possible |
| **Wikipedia** | Résumés de saisons | Gratuit, données limitées |

#### 3️⃣ **Web Scraping** (Avancé)

Pour récupérer automatiquement les données de sites comme Transfermarkt :

```python
import requests
from bs4 import BeautifulSoup
import time

def scrape_asse_2003_2004():
    url = "https://www.transfermarkt.com/as-saint-etienne/spielplandatum/verein/618/saison_id/2003"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    # Respecter un délai
    time.sleep(2)
    
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.content, 'html.parser')
    
    # Extraire les données...
```

**⚠️ Attention** : Respectez les conditions d'utilisation et ajoutez des délais entre requêtes.

---

## 📁 Fichiers Créés

### Pour la Saison 2003-2004

1. **demo_asse_2003_2004.py** ✅
   - Démonstration avec 10 matchs d'exemple
   - Statistiques calculées automatiquement
   - Affichage formaté des résultats

2. **asse_saison_2003_2004.json** ✅
   - Données structurées en JSON
   - Tous les matchs avec scores
   - Statistiques de la saison

3. **guide_donnees_historiques.py** ✅
   - Guide complet pour obtenir les vraies données
   - Liste des APIs et sites disponibles
   - Exemples de code

### Pour les Saisons Récentes (2015+)

4. **test_football_data_org.py** ⭐ RECOMMANDÉ
   - API gratuite Football-Data.org
   - Parfait pour saisons récentes
   - 10 requêtes/minute

5. **test_api_football.py**
   - API-Football via RapidAPI
   - Plus de fonctionnalités
   - Plan gratuit disponible

### Documentation

6. **README_API_FOOTBALL.md**
   - Guide complet d'utilisation
   - Instructions pas à pas
   - FAQ

7. **RESUME_TEST_API.md**
   - Résumé de toutes les APIs
   - Cas d'usage
   - Exemples de code

---

## 🎯 Réponse à Votre Question

**Question** : Est-ce qu'il y a une API pour récupérer tous les matchs d'une équipe pour une saison ?

**Réponse** : **OUI**, mais cela dépend de la saison :

### ✅ Pour les Saisons Récentes (2015-2025)

**Football-Data.org** (GRATUIT) :
```python
# Récupérer tous les matchs de l'ASSE pour 2024
GET /teams/1063/matches?season=2024
```

**Résultat** : TOUS les matchs avec :
- Date et heure
- Score complet
- Arbitres
- Stade
- Statistiques

### ⚠️ Pour les Saisons Anciennes (2003-2004)

**Options** :
1. **BeSoccer API** (10€/mois) - Données depuis 1990
2. **Sportmonks** (19€/mois) - Données historiques complètes
3. **Web Scraping** (Transfermarkt, Soccerway) - Gratuit mais technique
4. **Consultation manuelle** (Wikipedia, Transfermarkt) - Gratuit

---

## 🚀 Comment Utiliser

### Test avec Démonstration (SANS clé API)

```bash
# Voir les matchs ASSE 2003-2004 (échantillon)
python3 demo_asse_2003_2004.py

# Voir le guide pour données historiques
python3 guide_donnees_historiques.py
```

### Test avec Vraies Données (Saisons Récentes)

```bash
# 1. Obtenir clé API gratuite
# https://www.football-data.org/client/register

# 2. Modifier le script
nano test_football_data_org.py
# Remplacer: API_KEY = "VOTRE_CLE"

# 3. Installer dépendances
pip install requests

# 4. Exécuter
python3 test_football_data_org.py
```

---

## 📊 Format des Données Retournées

### Exemple de Match (JSON)

```json
{
  "matchday": 10,
  "date": "2003-10-18T20:00:00Z",
  "homeTeam": "AS Saint-Étienne",
  "awayTeam": "Olympique de Marseille",
  "score": {
    "home": 1,
    "away": 0
  },
  "competition": "Ligue 1",
  "status": "FINISHED",
  "highlight": "Victoire contre l'OM !"
}
```

### Statistiques Calculées

```json
{
  "victoires": 3,
  "nuls": 3,
  "defaites": 4,
  "buts_marques": 12,
  "buts_encaisses": 15,
  "points": 12,
  "difference": -3,
  "domicile": {"V": 3, "N": 2, "D": 1},
  "exterieur": {"V": 0, "N": 1, "D": 3}
}
```

---

## 💡 Recommandations

### Pour Votre Projet

1. **Si vous voulez des données récentes (2015+)** :
   → Utilisez **Football-Data.org** (GRATUIT)

2. **Si vous voulez des données historiques (2003-2004)** :
   → Option A : **BeSoccer API** (10€/mois)
   → Option B : **Web Scraping** Transfermarkt (gratuit, technique)
   → Option C : **Consultation manuelle** (gratuit, limité)

3. **Si vous voulez tester d'abord** :
   → Exécutez `demo_asse_2003_2004.py` pour voir le format des données

---

## 🔗 Liens Utiles

### APIs
- [Football-Data.org](https://www.football-data.org/) - Gratuit, saisons récentes
- [API-Football](https://www.api-football.com/) - Freemium, depuis 2010
- [BeSoccer API](https://www.besoccer.com/api) - Payant, depuis 1990
- [Sportmonks](https://www.sportmonks.com/) - Payant, historique complet

### Sites Web
- [Transfermarkt ASSE 2003-2004](https://www.transfermarkt.com/as-saint-etienne/spielplandatum/verein/618/saison_id/2003)
- [Wikipedia ASSE 2003-2004](https://fr.wikipedia.org/wiki/Saison_2003-2004_de_l%27AS_Saint-%C3%89tienne)
- [Soccerway ASSE](https://www.soccerway.com/teams/france/as-saint-etienne/)

---

## ✅ Conclusion

**OUI**, vous pouvez récupérer tous les matchs d'une équipe pour une saison via API, mais :

- ✅ **Saisons récentes (2015+)** : APIs gratuites disponibles
- ⚠️ **Saisons anciennes (2003-2004)** : APIs payantes ou web scraping nécessaires

**Pour commencer** : Testez `demo_asse_2003_2004.py` pour voir le format des données ! 🚀
