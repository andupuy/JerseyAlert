import requests
import json

# Configuration de l'API
API_KEY = "YOUR_API_KEY_HERE"  # À remplacer par votre clé API
BASE_URL = "https://v3.football.api-sports.io"

headers = {
    'x-rapidapi-host': 'v3.football.api-sports.io',
    'x-rapidapi-key': API_KEY
}

def get_team_id(team_name):
    """Récupère l'ID d'une équipe par son nom"""
    url = f"{BASE_URL}/teams"
    params = {
        'search': team_name,
        'country': 'France'
    }
    
    response = requests.get(url, headers=headers, params=params)
    data = response.json()
    
    if data['response']:
        team = data['response'][0]
        print(f"✓ Équipe trouvée: {team['team']['name']} (ID: {team['team']['id']})")
        return team['team']['id']
    return None

def get_fixtures_between_teams(team1_id, team2_id, season):
    """Récupère tous les matchs entre deux équipes pour une saison donnée"""
    url = f"{BASE_URL}/fixtures"
    
    # Requête pour les matchs de l'équipe 1 contre l'équipe 2
    params = {
        'team': team1_id,
        'season': season,
        'league': 61  # Ligue 1 ID
    }
    
    response = requests.get(url, headers=headers, params=params)
    data = response.json()
    
    # Filtrer pour trouver les matchs contre l'équipe 2
    matches = []
    if data['response']:
        for fixture in data['response']:
            home_team_id = fixture['teams']['home']['id']
            away_team_id = fixture['teams']['away']['id']
            
            if (home_team_id == team1_id and away_team_id == team2_id) or \
               (home_team_id == team2_id and away_team_id == team1_id):
                matches.append(fixture)
    
    return matches

def display_match_info(match):
    """Affiche les informations détaillées d'un match"""
    print("\n" + "="*80)
    print("📅 INFORMATIONS DU MATCH")
    print("="*80)
    
    # Informations générales
    fixture = match['fixture']
    teams = match['teams']
    goals = match['goals']
    score = match['score']
    
    print(f"\n🏆 Compétition: {match['league']['name']} - {match['league']['round']}")
    print(f"📍 Stade: {fixture['venue']['name']}, {fixture['venue']['city']}")
    print(f"📅 Date: {fixture['date']}")
    print(f"⚽ Statut: {fixture['status']['long']}")
    
    print(f"\n🏠 Équipe domicile: {teams['home']['name']}")
    print(f"✈️  Équipe extérieur: {teams['away']['name']}")
    
    if goals['home'] is not None:
        print(f"\n📊 SCORE FINAL: {teams['home']['name']} {goals['home']} - {goals['away']} {teams['away']['name']}")
        
        # Score à la mi-temps
        if score['halftime']['home'] is not None:
            print(f"   Mi-temps: {score['halftime']['home']} - {score['halftime']['away']}")
        
        # Score en prolongation si applicable
        if score['extratime']['home'] is not None:
            print(f"   Prolongations: {score['extratime']['home']} - {score['extratime']['away']}")
        
        # Tirs au but si applicable
        if score['penalty']['home'] is not None:
            print(f"   Tirs au but: {score['penalty']['home']} - {score['penalty']['away']}")
    else:
        print(f"\n⏳ Match à venir")
    
    print("\n" + "="*80)

def main():
    print("🔍 Recherche du match ASSE - OM (Saison 2024-2025)")
    print("-" * 80)
    
    # Recherche des IDs des équipes
    print("\n1️⃣ Recherche de l'AS Saint-Étienne...")
    asse_id = get_team_id("Saint-Etienne")
    
    print("\n2️⃣ Recherche de l'Olympique de Marseille...")
    om_id = get_team_id("Marseille")
    
    if not asse_id or not om_id:
        print("❌ Erreur: Impossible de trouver les équipes")
        return
    
    # Recherche des matchs
    print(f"\n3️⃣ Recherche des matchs entre ASSE (ID: {asse_id}) et OM (ID: {om_id}) pour la saison 2024...")
    matches = get_fixtures_between_teams(asse_id, om_id, 2024)
    
    if matches:
        print(f"\n✅ {len(match(es))} match(s) trouvé(s)!")
        for i, match in enumerate(matches, 1):
            print(f"\n--- Match {i}/{len(matches)} ---")
            display_match_info(match)
            
            # Sauvegarder les données complètes dans un fichier JSON
            filename = f"match_asse_om_{i}.json"
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(match, f, indent=2, ensure_ascii=False)
            print(f"\n💾 Données complètes sauvegardées dans: {filename}")
    else:
        print("\n❌ Aucun match trouvé entre ces deux équipes pour cette saison")

if __name__ == "__main__":
    try:
        main()
    except requests.exceptions.RequestException as e:
        print(f"\n❌ Erreur de connexion à l'API: {e}")
    except KeyError as e:
        print(f"\n❌ Erreur de format de données: {e}")
        print("Vérifiez que votre clé API est valide et que vous avez accès à l'API")
    except Exception as e:
        print(f"\n❌ Erreur inattendue: {e}")
