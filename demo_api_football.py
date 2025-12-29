#!/usr/bin/env python3
"""
DÉMONSTRATION - Simulation du résultat de recherche ASSE-OM
Ce script simule ce que vous obtiendriez avec une vraie clé API
"""

import json
from datetime import datetime

def simulate_match_data():
    """Simule les données d'un match ASSE-OM"""
    return {
        "area": {
            "id": 2081,
            "name": "France",
            "code": "FRA",
            "flag": "https://crests.football-data.org/FRA.svg"
        },
        "competition": {
            "id": 2015,
            "name": "Ligue 1",
            "code": "FL1",
            "type": "LEAGUE",
            "emblem": "https://crests.football-data.org/FL1.png"
        },
        "season": {
            "id": 2024,
            "startDate": "2024-08-16",
            "endDate": "2025-05-18",
            "currentMatchday": 16
        },
        "id": 123456,
        "utcDate": "2024-12-08T20:00:00Z",
        "status": "FINISHED",
        "matchday": 14,
        "stage": "REGULAR_SEASON",
        "group": None,
        "lastUpdated": "2024-12-08T22:05:00Z",
        "homeTeam": {
            "id": 1063,
            "name": "AS Saint-Étienne",
            "shortName": "ASSE",
            "tla": "STE",
            "crest": "https://crests.football-data.org/1063.png"
        },
        "awayTeam": {
            "id": 516,
            "name": "Olympique de Marseille",
            "shortName": "Marseille",
            "tla": "OLM",
            "crest": "https://crests.football-data.org/516.png"
        },
        "score": {
            "winner": "AWAY_TEAM",
            "duration": "REGULAR",
            "fullTime": {
                "home": 0,
                "away": 2
            },
            "halfTime": {
                "home": 0,
                "away": 0
            }
        },
        "odds": {
            "msg": "Activate Odds-Package in User-Panel to retrieve odds."
        },
        "referees": [
            {
                "id": 57001,
                "name": "François Letexier",
                "type": "REFEREE",
                "nationality": "France"
            },
            {
                "id": 57002,
                "name": "Cyril Gringore",
                "type": "ASSISTANT_REFEREE_N1",
                "nationality": "France"
            },
            {
                "id": 57003,
                "name": "Mehdi Rahmouni",
                "type": "ASSISTANT_REFEREE_N2",
                "nationality": "France"
            }
        ]
    }

def format_date(date_str):
    """Formate une date ISO en format lisible"""
    try:
        dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        return dt.strftime("%d/%m/%Y à %H:%M")
    except:
        return date_str

def display_match_info(match):
    """Affiche les informations détaillées d'un match"""
    print("\n" + "="*80)
    print("📋 INFORMATIONS DU MATCH")
    print("="*80)
    
    # Informations générales
    print(f"\n🏆 Compétition: {match['competition']['name']}")
    print(f"🌍 Pays: {match['area']['name']}")
    print(f"📅 Date: {format_date(match['utcDate'])}")
    print(f"🏟️  Journée: {match.get('matchday', 'N/A')}")
    print(f"⚽ Statut: {match['status']}")
    
    # Équipes
    home_team = match['homeTeam']['name']
    away_team = match['awayTeam']['name']
    
    print(f"\n🏠 Domicile: {home_team} ({match['homeTeam']['tla']})")
    print(f"✈️  Extérieur: {away_team} ({match['awayTeam']['tla']})")
    
    # Score
    score = match['score']
    if score['fullTime']['home'] is not None:
        home_score = score['fullTime']['home']
        away_score = score['fullTime']['away']
        
        print(f"\n📊 SCORE FINAL: {home_team} {home_score} - {away_score} {away_team}")
        
        if score['halfTime']['home'] is not None:
            print(f"   Mi-temps: {score['halfTime']['home']} - {score['halfTime']['away']}")
        
        # Vainqueur
        winner = score.get('winner')
        if winner == 'HOME_TEAM':
            print(f"   🏆 Vainqueur: {home_team}")
        elif winner == 'AWAY_TEAM':
            print(f"   🏆 Vainqueur: {away_team}")
        else:
            print(f"   🤝 Match nul")
    else:
        print(f"\n⏳ Match à venir")
    
    # Arbitres
    if match.get('referees'):
        print(f"\n👨‍⚖️ Arbitres:")
        for ref in match['referees']:
            role = {
                'REFEREE': 'Arbitre principal',
                'ASSISTANT_REFEREE_N1': 'Assistant 1',
                'ASSISTANT_REFEREE_N2': 'Assistant 2',
                'FOURTH_OFFICIAL': 'Quatrième arbitre'
            }.get(ref['type'], ref['type'])
            print(f"   - {ref['name']} ({role})")
    
    print("\n" + "="*80)

def main():
    print("="*80)
    print("🎬 DÉMONSTRATION - Recherche Match ASSE - OM (Saison 2024-2025)")
    print("="*80)
    print("\n⚠️  Ceci est une SIMULATION avec des données d'exemple")
    print("Pour des données réelles, utilisez test_football_data_org.py avec une clé API")
    print("-" * 80)
    
    # Simulation des données
    print("\n🔍 Simulation de la recherche...")
    print("   - AS Saint-Étienne (ID: 1063)")
    print("   - Olympique de Marseille (ID: 516)")
    print("   - Saison: 2024-2025")
    
    match = simulate_match_data()
    
    print(f"\n✅ 1 match trouvé!")
    
    # Affichage des informations
    display_match_info(match)
    
    # Sauvegarde des données
    filename = "match_asse_om_demo.json"
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(match, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Données complètes sauvegardées dans: {filename}")
    
    print("\n" + "="*80)
    print("✅ DÉMONSTRATION TERMINÉE!")
    print("="*80)
    
    print("\n📝 PROCHAINES ÉTAPES:")
    print("   1. Obtenez une clé API gratuite sur: https://www.football-data.org/client/register")
    print("   2. Modifiez test_football_data_org.py avec votre clé")
    print("   3. Exécutez: python test_football_data_org.py")
    print("\n💡 Avec une vraie clé API, vous obtiendrez:")
    print("   - Données en temps réel")
    print("   - Tous les matchs de la saison")
    print("   - Statistiques détaillées")
    print("   - Informations sur les buteurs, cartons, etc.")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Erreur: {e}")
        import traceback
        traceback.print_exc()
