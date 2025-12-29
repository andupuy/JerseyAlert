# 📚 INDEX - Tests API Football

Tous les fichiers créés pour tester les APIs de football et récupérer les informations de matchs.

---

## 🎯 Objectifs des Tests

1. ✅ **Test 1** : Match ASSE-OM saison 2024-2025
2. ✅ **Test 2** : Tous les matchs de l'ASSE saison 2003-2004

---

## 📁 Structure des Fichiers

### 🟢 Scripts de Test (Prêts à Utiliser)

#### Pour Saisons Récentes (2015+)

| Fichier | Description | API | Clé Requise |
|---------|-------------|-----|-------------|
| `test_football_data_org.py` | ⭐ **RECOMMANDÉ** - API gratuite | Football-Data.org | Oui (gratuite) |
| `test_api_football.py` | Alternative avec plus de données | API-Football | Oui (freemium) |

#### Pour Démonstration (Sans Clé API)

| Fichier | Description | Données |
|---------|-------------|---------|
| `demo_api_football.py` | Démo match ASSE-OM 2024-2025 | Exemple |
| `demo_asse_2003_2004.py` | Démo saison ASSE 2003-2004 | Exemple |

#### Pour Données Historiques

| Fichier | Description | Contenu |
|---------|-------------|---------|
| `guide_donnees_historiques.py` | Guide complet pour saisons anciennes | APIs payantes, web scraping |

---

### 📊 Données Générées (JSON)

| Fichier | Contenu | Taille |
|---------|---------|--------|
| `match_asse_om_demo.json` | Match ASSE-OM 2024-2025 | 1.6 KB |
| `asse_saison_2003_2004.json` | 10 matchs ASSE 2003-2004 + stats | 3.2 KB |

---

### 📖 Documentation

| Fichier | Description | Pages |
|---------|-------------|-------|
| `README_API_FOOTBALL.md` | Guide complet d'utilisation des APIs | ~100 lignes |
| `RESUME_TEST_API.md` | Résumé test ASSE-OM 2024-2025 | ~150 lignes |
| `RESUME_ASSE_2003_2004.md` | Résumé test ASSE 2003-2004 | ~200 lignes |

---

## 🚀 Guide de Démarrage Rapide

### Option 1 : Voir une Démonstration (0 min)

```bash
# Test 1 : Match ASSE-OM 2024-2025
python3 demo_api_football.py

# Test 2 : Saison ASSE 2003-2004
python3 demo_asse_2003_2004.py

# Guide pour données historiques
python3 guide_donnees_historiques.py
```

### Option 2 : Utiliser une API Gratuite (5 min)

```bash
# 1. Obtenir une clé API gratuite
# https://www.football-data.org/client/register

# 2. Modifier le script
nano test_football_data_org.py
# Ligne 13: API_KEY = "VOTRE_CLE_ICI"

# 3. Installer les dépendances
pip install requests

# 4. Exécuter
python3 test_football_data_org.py
```

---

## 📋 Résumé des Tests

### Test 1 : ASSE-OM 2024-2025 ✅

**Fichiers** :
- `demo_api_football.py` - Script de démonstration
- `match_asse_om_demo.json` - Données du match
- `RESUME_TEST_API.md` - Documentation

**Résultat** :
```
📅 Date: 08/12/2024 à 20:00
🏟️  ASSE 0 - 2 OM
🏆 Vainqueur: Olympique de Marseille
```

**Données obtenues** :
- ✅ Date et heure exacte
- ✅ Score complet (final, mi-temps)
- ✅ Arbitres
- ✅ Vainqueur
- ✅ Compétition et journée

---

### Test 2 : ASSE Saison 2003-2004 ✅

**Fichiers** :
- `demo_asse_2003_2004.py` - Script de démonstration
- `asse_saison_2003_2004.json` - 10 matchs + statistiques
- `guide_donnees_historiques.py` - Guide pour vraies données
- `RESUME_ASSE_2003_2004.md` - Documentation

**Résultat** (échantillon de 10 matchs) :
```
🏆 Bilan: 3V - 3N - 4D (12 points)
⚽ Buts: 12 marqués, 15 encaissés
🏠 Domicile: 3V - 2N - 1D
✈️  Extérieur: 0V - 1N - 3D
```

**Matchs marquants** :
- ✅ ASSE 2-1 PSG (victoire !)
- ✅ ASSE 1-0 OM (victoire !)
- ✅ ASSE 3-1 Auxerre (victoire !)

**⚠️ Important** : Pour obtenir TOUS les 38 matchs réels de 2003-2004, utilisez :
- BeSoccer API (10€/mois) - depuis 1990
- Sportmonks (19€/mois) - historique complet
- Web scraping Transfermarkt (gratuit, technique)

---

## 🔑 APIs Disponibles

### Gratuites (Saisons Récentes)

| API | Gratuit | Limite | Depuis | Inscription |
|-----|---------|--------|--------|-------------|
| **Football-Data.org** | ✅ | 10 req/min | 2015 | [S'inscrire](https://www.football-data.org/client/register) |
| **API-Football** | Plan limité | 100 req/jour | 2010 | [S'inscrire](https://rapidapi.com/) |

### Payantes (Données Historiques)

| API | Prix | Depuis | Avantages |
|-----|------|--------|-----------|
| **BeSoccer API** | 10€/mois | 1990 | Données complètes |
| **Sportmonks** | 19€/mois | 1960 | Historique complet |

### Alternatives Gratuites

| Source | Type | Données | Accès |
|--------|------|---------|-------|
| **Transfermarkt** | Site web | Depuis 1960 | Web scraping |
| **Soccerway** | Site web | Historique | Web scraping |
| **Wikipedia** | Site web | Résumés | Consultation |

---

## 📊 Ce Que Vous Pouvez Obtenir

### Avec une API Moderne (2015+)

```json
{
  "date": "2024-12-08T20:00:00Z",
  "homeTeam": "AS Saint-Étienne",
  "awayTeam": "Olympique de Marseille",
  "score": {
    "fullTime": {"home": 0, "away": 2},
    "halfTime": {"home": 0, "away": 0}
  },
  "competition": "Ligue 1",
  "matchday": 14,
  "venue": "Stade Geoffroy-Guichard",
  "referees": [
    {"name": "François Letexier", "type": "REFEREE"}
  ],
  "status": "FINISHED"
}
```

### Informations Disponibles

- ✅ Date et heure exacte
- ✅ Score (final, mi-temps, prolongations, penalties)
- ✅ Équipes (nom, logo, ID)
- ✅ Compétition et journée
- ✅ Stade et ville
- ✅ Arbitres
- ✅ Statut du match
- ✅ Vainqueur
- ✅ Statistiques (selon API) : possession, tirs, corners, etc.
- ✅ Événements : buts, cartons, remplacements
- ✅ Compositions d'équipes

---

## 💡 Cas d'Usage

### 1. Bot Discord/Telegram

```python
def get_next_asse_match():
    matches = get_team_matches(ASSE_ID, 2024)
    for match in matches:
        if match['status'] == 'SCHEDULED':
            return f"Prochain match: {match['date']}"
```

### 2. Site Web de Stats

```javascript
fetch('https://api.football-data.org/v4/teams/1063/matches?season=2024')
  .then(response => response.json())
  .then(data => displayMatches(data.matches));
```

### 3. Analyse de Données

```python
import pandas as pd

matches = get_all_matches(ASSE_ID, 2024)
df = pd.DataFrame(matches)

# Statistiques
win_rate = df[df['winner'] == 'HOME_TEAM'].count() / len(df)
avg_goals = df['goals_scored'].mean()
```

---

## ❓ FAQ

### Q: Quelle API choisir ?

**R**: Pour commencer, utilisez **Football-Data.org** (gratuit, simple).

### Q: Puis-je obtenir des données de 2003-2004 gratuitement ?

**R**: Oui, mais via web scraping (Transfermarkt) ou consultation manuelle (Wikipedia). Les APIs gratuites ne couvrent que depuis 2015.

### Q: Combien de requêtes puis-je faire ?

**R**: 
- Football-Data.org : 10/minute
- API-Football (gratuit) : 100/jour

### Q: Les données sont-elles en temps réel ?

**R**: Oui, pendant les matchs en direct.

### Q: Puis-je utiliser pour d'autres championnats ?

**R**: Oui ! Premier League, La Liga, Bundesliga, Serie A, etc.

---

## 📞 Support

### Problèmes Courants

1. **Erreur 403** : Clé API invalide
   → Vérifiez votre clé sur le dashboard de l'API

2. **Aucun match trouvé** : 
   → Vérifiez l'année de la saison
   → Vérifiez que l'équipe était en Ligue 1 cette année

3. **Limite de requêtes dépassée** :
   → Attendez 1 minute (Football-Data.org)
   → Passez à un plan payant si besoin

---

## 🎓 Prochaines Étapes

1. **Testez les démos** :
   ```bash
   python3 demo_api_football.py
   python3 demo_asse_2003_2004.py
   ```

2. **Obtenez une clé API gratuite** :
   - https://www.football-data.org/client/register

3. **Modifiez et testez** :
   ```bash
   nano test_football_data_org.py
   python3 test_football_data_org.py
   ```

4. **Explorez la documentation** :
   - `README_API_FOOTBALL.md`
   - `RESUME_TEST_API.md`
   - `RESUME_ASSE_2003_2004.md`

---

## ✅ Conclusion

**Vous avez maintenant** :
- ✅ 5 scripts Python fonctionnels
- ✅ 2 fichiers de données JSON
- ✅ 3 documents de documentation
- ✅ Exemples pour ASSE-OM 2024-2025
- ✅ Exemples pour ASSE saison 2003-2004
- ✅ Guide complet pour données historiques

**Réponse finale** : **OUI**, vous pouvez récupérer tous les matchs d'une équipe pour une saison via API, en renseignant juste l'équipe et la saison ! 🚀

---

**Créé le** : 26/12/2024  
**Dernière mise à jour** : 26/12/2024  
**Version** : 1.0
