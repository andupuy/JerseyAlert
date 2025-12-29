#!/usr/bin/env python3
"""
Guide pour récupérer les VRAIES données de l'ASSE saison 2003-2004
Ce script explique comment utiliser les APIs qui ont des données historiques
"""

import requests
import json

# ============================================================================
# OPTION 1: API-Football (Recommandé pour données historiques)
# ============================================================================

def get_asse_matches_api_football(api_key, season_year):
    """
    Récupère les matchs de l'ASSE via API-Football
    API-Football a des données depuis 2010 environ
    
    Pour 2003-2004, les données peuvent être limitées
    """
    
    BASE_URL = "https://v3.football.api-sports.io"
    
    headers = {
        'x-rapidapi-host': 'v3.football.api-sports.io',
        'x-rapidapi-key': api_key
    }
    
    # ID de l'ASSE dans API-Football
    ASSE_ID = 1063
    
    # Récupérer tous les matchs de l'ASSE pour la saison
    url = f"{BASE_URL}/fixtures"
    params = {
        'team': ASSE_ID,
        'season': season_year
    }
    
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        
        if data.get('response'):
            matches = data['response']
            print(f"✅ {len(matches)} matchs trouvés pour la saison {season_year}")
            return matches
        else:
            print(f"❌ Aucun match trouvé pour la saison {season_year}")
            print(f"   Raison possible: Données historiques non disponibles")
            return []
            
    except requests.exceptions.HTTPError as e:
        print(f"❌ Erreur HTTP: {e}")
        return []
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return []

# ============================================================================
# OPTION 2: Web Scraping (Alternative pour données très anciennes)
# ============================================================================

def get_historical_data_info():
    """
    Informations sur comment obtenir des données historiques de 2003-2004
    """
    
    print("\n" + "="*80)
    print("📚 SOURCES DE DONNÉES HISTORIQUES POUR LA SAISON 2003-2004")
    print("="*80)
    
    sources = [
        {
            "nom": "Transfermarkt",
            "url": "https://www.transfermarkt.com/as-saint-etienne/spielplandatum/verein/618/saison_id/2003",
            "type": "Site Web",
            "avantages": [
                "Données complètes depuis les années 1960",
                "Tous les matchs, buteurs, cartons",
                "Compositions d'équipes",
                "Gratuit"
            ],
            "inconvenients": [
                "Pas d'API officielle",
                "Nécessite du web scraping",
                "Risque de blocage si trop de requêtes"
            ]
        },
        {
            "nom": "Soccerway",
            "url": "https://www.soccerway.com/teams/france/as-saint-etienne/",
            "type": "Site Web",
            "avantages": [
                "Données historiques complètes",
                "Interface claire",
                "Statistiques détaillées"
            ],
            "inconvenients": [
                "Pas d'API",
                "Web scraping nécessaire"
            ]
        },
        {
            "nom": "BeSoccer API",
            "url": "https://www.besoccer.com/api",
            "type": "API Payante",
            "avantages": [
                "Données depuis 1990",
                "API officielle",
                "Données structurées"
            ],
            "inconvenients": [
                "Payant (à partir de 10€/mois)",
                "Nécessite inscription"
            ]
        },
        {
            "nom": "Sportmonks",
            "url": "https://www.sportmonks.com/football-api/",
            "type": "API Payante",
            "avantages": [
                "Données historiques très complètes",
                "Toutes les compétitions",
                "Statistiques avancées"
            ],
            "inconvenients": [
                "Payant (à partir de 19€/mois)",
                "Plan gratuit très limité"
            ]
        },
        {
            "nom": "Wikipedia",
            "url": "https://fr.wikipedia.org/wiki/Saison_2003-2004_de_l%27AS_Saint-%C3%89tienne",
            "type": "Site Web",
            "avantages": [
                "Gratuit",
                "Résumé de la saison",
                "Principaux résultats"
            ],
            "inconvenients": [
                "Données limitées",
                "Pas d'API",
                "Pas de statistiques détaillées"
            ]
        }
    ]
    
    for i, source in enumerate(sources, 1):
        print(f"\n{i}. {source['nom']}")
        print(f"   🔗 {source['url']}")
        print(f"   📋 Type: {source['type']}")
        print(f"   ✅ Avantages:")
        for avantage in source['avantages']:
            print(f"      • {avantage}")
        print(f"   ❌ Inconvénients:")
        for inconvenient in source['inconvenients']:
            print(f"      • {inconvenient}")

# ============================================================================
# OPTION 3: Exemple de Web Scraping (Transfermarkt)
# ============================================================================

def example_web_scraping():
    """
    Exemple de code pour scraper Transfermarkt
    ATTENTION: Respectez les conditions d'utilisation du site
    """
    
    print("\n" + "="*80)
    print("💻 EXEMPLE DE WEB SCRAPING (Transfermarkt)")
    print("="*80)
    
    code_example = '''
import requests
from bs4 import BeautifulSoup
import time

def scrape_asse_season_2003_2004():
    """
    Exemple de scraping pour récupérer les matchs de l'ASSE 2003-2004
    """
    
    url = "https://www.transfermarkt.com/as-saint-etienne/spielplandatum/verein/618/saison_id/2003"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        # Respecter un délai entre les requêtes
        time.sleep(2)
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Trouver le tableau des matchs
        matches_table = soup.find('table', class_='items')
        
        if matches_table:
            matches = []
            rows = matches_table.find_all('tr', class_=['odd', 'even'])
            
            for row in rows:
                # Extraire les données de chaque match
                # (Le code exact dépend de la structure HTML)
                pass
            
            return matches
        
    except Exception as e:
        print(f"Erreur: {e}")
        return []

# IMPORTANT: Respectez les conditions d'utilisation
# - Ajoutez des délais entre les requêtes (time.sleep)
# - Ne faites pas trop de requêtes
# - Vérifiez le fichier robots.txt du site
'''
    
    print("\n⚠️  AVERTISSEMENT:")
    print("   - Le web scraping doit respecter les conditions d'utilisation des sites")
    print("   - Ajoutez toujours des délais entre les requêtes")
    print("   - Vérifiez le fichier robots.txt")
    print("   - Préférez les APIs officielles quand c'est possible")
    
    print("\n📝 Code d'exemple:")
    print(code_example)

# ============================================================================
# MAIN
# ============================================================================

def main():
    print("="*80)
    print("🔍 GUIDE: Récupérer les matchs de l'ASSE saison 2003-2004")
    print("="*80)
    
    print("\n⚠️  PROBLÈME: Les APIs gratuites modernes n'ont généralement pas")
    print("   de données aussi anciennes que 2003-2004")
    
    print("\n💡 SOLUTIONS DISPONIBLES:")
    
    # Afficher les sources de données
    get_historical_data_info()
    
    # Afficher l'exemple de web scraping
    example_web_scraping()
    
    print("\n" + "="*80)
    print("🎯 RECOMMANDATIONS")
    print("="*80)
    
    print("\n1️⃣  Pour un usage personnel/éducatif:")
    print("   → Utilisez Wikipedia ou Transfermarkt (consultation manuelle)")
    
    print("\n2️⃣  Pour un projet nécessitant une API:")
    print("   → BeSoccer API (10€/mois) - Données depuis 1990")
    print("   → Sportmonks (19€/mois) - Données historiques complètes")
    
    print("\n3️⃣  Pour un projet de web scraping:")
    print("   → Transfermarkt (gratuit mais nécessite du code)")
    print("   → Respectez les conditions d'utilisation")
    print("   → Ajoutez des délais entre les requêtes")
    
    print("\n4️⃣  Alternative: Saisons plus récentes")
    print("   → Football-Data.org: Données depuis 2015 (GRATUIT)")
    print("   → API-Football: Données depuis 2010 (Plan gratuit disponible)")
    
    print("\n" + "="*80)
    print("📦 FICHIERS UTILES")
    print("="*80)
    
    print("\n✅ Fichiers créés pour vous:")
    print("   • demo_asse_2003_2004.py - Démonstration avec échantillon")
    print("   • asse_saison_2003_2004.json - Données d'exemple")
    
    print("\n📝 Pour tester avec des données réelles récentes:")
    print("   • test_football_data_org.py - API gratuite (saisons 2015+)")
    print("   • test_api_football.py - API-Football (saisons 2010+)")
    
    print("\n" + "="*80)
    print("✅ GUIDE TERMINÉ")
    print("="*80)
    
    print("\n❓ Besoin d'aide?")
    print("   - Pour des saisons récentes (2015+): Utilisez Football-Data.org")
    print("   - Pour des données historiques: Considérez BeSoccer API ou Sportmonks")
    print("   - Pour un usage ponctuel: Consultez Transfermarkt ou Wikipedia")

if __name__ == "__main__":
    main()
