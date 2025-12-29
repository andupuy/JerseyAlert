#!/usr/bin/env python3
"""
Test de l'API Football-Data.org (GRATUITE)
Pour obtenir une clé API gratuite: https://www.football-data.org/client/register
"""

import requests
import json
from datetime import datetime

# Configuration de l'API Football-Data.org (GRATUITE - 10 requêtes/minute)
API_KEY = "YOUR_FREE_API_KEY_HERE"  # Obtenez-la sur https://www.football-data.org/client/register
BASE_URL = "https://api.football-data.org/v4"

headers = {
    'X-Auth-Token': API_KEY
}

# IDs des équipes en Ligue 1
TEAMS = {
    'ASSE': 1063,  # AS Saint-Étienne
    'OM': 516,     # Olympique de Marseille
    'PSG': 524,    # Paris Saint-Germain
    'OL': 523,     # Olympique Lyonnais
    'LOSC': 521,   # Lille OSC
}

# ID de la Ligue 1
LIGUE_1_ID = 2015

def get_team_matches(team_id, season_year):
    """Récupère tous les matchs d'une équipe pour une saison"""
    url = f"{BASE_URL}/teams/{team_id}/matches"
    params = {
        'season': season_year,
        'competitions': LIGUE_1_ID
    }
    
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        if response.status_code == 403:
            print("❌ Erreur 403: Clé API invalide ou non autorisée")
            print("   Obtenez une clé gratuite sur: https://www.football-data.org/client/register")
        else:
            print(f"❌ Erreur HTTP {response.status_code}: {e}")
        return None
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return None

def find_matches_between_teams(team1_id, team2_id, season_year):
    """Trouve tous les matchs entre deux équipes pour une saison"""
    print(f"🔍 Recherche des matchs pour la saison {season_year}...")
    
    data = get_team_matches(team1_id, season_year)
    
    if not data or 'matches' not in data:
        return []
    
    matches = []
    for match in data['matches']:
        home_id = match['homeTeam']['id']
        away_id = match['awayTeam']['id']
        
        if (home_id == team1_id and away_id == team2_id) or \
           (home_id == team2_id and away_id == team1_id):
            matches.append(match)
    
    return matches

def format_date(date_str):
    """Formate une date ISO en format lisible"""
    try:
        dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        return dt.strftime("%d/%m/%Y à %H:%M")
    except:
        return date_str

def display_match_info(match, match_number=1, total_matches=1):
    """Affiche les informations détaillées d'un match"""
    print("\n" + "="*80)
    print(f"📋 MATCH {match_number}/{total_matches}")
    print("="*80)
    
    # Informations générales
    print(f"\n🏆 Compétition: {match['competition']['name']}")
    print(f"📅 Date: {format_date(match['utcDate'])}")
    print(f"🏟️  Journée: {match.get('matchday', 'N/A')}")
    print(f"⚽ Statut: {match['status']}")
    
    # Équipes
    home_team = match['homeTeam']['name']
    away_team = match['awayTeam']['name']
    
    print(f"\n🏠 Domicile: {home_team}")
    print(f"✈️  Extérieur: {away_team}")
    
    # Score
    score = match['score']
    if score['fullTime']['home'] is not None:
        print(f"\n📊 SCORE FINAL: {home_team} {score['fullTime']['home']} - {score['fullTime']['away']} {away_team}")
        
        if score['halfTime']['home'] is not None:
            print(f"   Mi-temps: {score['halfTime']['home']} - {score['halfTime']['away']}")
    else:
        print(f"\n⏳ Match à venir")
    
    # Arbitres
    if match.get('referees'):
        print(f"\n👨‍⚖️ Arbitres:")
        for ref in match['referees']:
            print(f"   - {ref['name']} ({ref['type']})")
    
    print("\n" + "="*80)
    
    return match

def save_match_data(match, filename):
    """Sauvegarde les données du match dans un fichier JSON"""
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(match, f, indent=2, ensure_ascii=False)
    print(f"💾 Données complètes sauvegardées dans: {filename}")

def main():
    print("="*80)
    print("🔍 RECHERCHE MATCH ASSE - OM (Saison 2024-2025)")
    print("="*80)
    print("\nAPI utilisée: Football-Data.org (GRATUITE)")
    print("Limite: 10 requêtes/minute")
    print("-" * 80)
    
    # Vérification de la clé API
    if API_KEY == "YOUR_FREE_API_KEY_HERE":
        print("\n⚠️  ATTENTION: Vous devez d'abord obtenir une clé API gratuite!")
        print("\n📝 Étapes pour obtenir votre clé API:")
        print("   1. Allez sur: https://www.football-data.org/client/register")
        print("   2. Créez un compte gratuit")
        print("   3. Copiez votre clé API")
        print("   4. Remplacez 'YOUR_FREE_API_KEY_HERE' dans ce fichier")
        print("\n✅ Plan gratuit: 10 requêtes/minute, parfait pour des tests!")
        return
    
    # Recherche des matchs
    asse_id = TEAMS['ASSE']
    om_id = TEAMS['OM']
    season = 2024
    
    print(f"\n🔎 Recherche des matchs entre:")
    print(f"   - AS Saint-Étienne (ID: {asse_id})")
    print(f"   - Olympique de Marseille (ID: {om_id})")
    print(f"   - Saison: {season}")
    
    matches = find_matches_between_teams(asse_id, om_id, season)
    
    if matches:
        print(f"\n✅ {len(matches)} match(s) trouvé(s)!\n")
        
        for i, match in enumerate(matches, 1):
            match_data = display_match_info(match, i, len(matches))
            
            # Sauvegarder les données
            filename = f"match_asse_om_{season}_{i}.json"
            save_match_data(match_data, filename)
            
        print("\n" + "="*80)
        print("✅ RECHERCHE TERMINÉE AVEC SUCCÈS!")
        print("="*80)
    else:
        print("\n❌ Aucun match trouvé entre ces deux équipes pour cette saison")
        print("\n💡 Raisons possibles:")
        print("   - Les équipes ne se sont pas encore affrontées cette saison")
        print("   - Une des équipes n'est pas en Ligue 1 cette saison")
        print("   - Problème avec la clé API")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Programme interrompu par l'utilisateur")
    except Exception as e:
        print(f"\n❌ Erreur inattendue: {e}")
        import traceback
        traceback.print_exc()
