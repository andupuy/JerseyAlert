#!/usr/bin/env python3
"""
Vinted Bot optimisé pour Oracle Cloud
- Utilise Playwright pour éviter la détection
- Délais aléatoires pour paraître humain
- Gestion robuste des erreurs
- Notifications Discord
"""

import os
import sys
import time
import random
import requests
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# Configuration
SEARCH_TEXT = "Maillot Asse"
VINTED_SEARCH_URL = f"https://www.vinted.fr/catalog?search_text={SEARCH_TEXT.replace(' ', '+')}&order=newest_first"
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
STATE_FILE = "last_seen_id.txt"
CHECK_INTERVAL_MIN = 10  # secondes minimum entre checks
CHECK_INTERVAL_MAX = 20  # secondes maximum entre checks

def log(message):
    """Log avec timestamp"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {message}", flush=True)

def load_last_seen_id():
    """Charge le dernier ID vu depuis le fichier"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return int(f.read().strip())
        except:
            pass
    return 0

def save_last_seen_id(item_id):
    """Sauvegarde le dernier ID vu"""
    with open(STATE_FILE, "w") as f:
        f.write(str(item_id))

def send_discord_alert(item):
    """Envoie une alerte Discord pour un nouvel article"""
    if not DISCORD_WEBHOOK_URL:
        log("⚠️  Pas de webhook Discord configuré")
        return

    try:
        # Extraction des données
        title = item.get('title', 'Nouvel article')
        price = item.get('price', 'N/A')
        size = item.get('size', 'N/A')
        brand = item.get('brand', 'N/A')
        url = item.get('url', '')
        photo_url = item.get('photo', '')
        item_id = item.get('id', 'N/A')

        # Construction de l'embed Discord
        embed = {
            "title": f"🔔 {title}",
            "url": url,
            "description": f"**{price}** | Taille: **{size}**\nMarque: {brand}",
            "color": 0x09B83E,  # Vert Vinted
            "footer": {"text": f"Vinted Bot • ID: {item_id}"},
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        if photo_url:
            embed["thumbnail"] = {"url": photo_url}

        payload = {
            "username": "Vinted ASSE Bot",
            "avatar_url": "https://images.vinted.net/assets/icon-76x76-precomposed-3e6e4c5f0b8c7e5a5c5e5e5e5e5e5e5e.png",
            "embeds": [embed]
        }
        
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        response.raise_for_status()
        log(f"✅ Alerte envoyée pour l'article #{item_id}")

    except Exception as e:
        log(f"❌ Erreur lors de l'envoi Discord: {e}")

def extract_items_from_page(page):
    """Extrait les articles de la page Vinted avec Playwright"""
    try:
        # Attendre que les articles se chargent
        page.wait_for_selector('div[data-testid*="item"]', timeout=10000)
        
        # Petit délai aléatoire pour paraître humain
        time.sleep(random.uniform(1, 2))
        
        # Extraire les données des articles via JavaScript
        items = page.evaluate("""
            () => {
                const items = [];
                const itemElements = document.querySelectorAll('div[data-testid*="item"]');
                
                itemElements.forEach((el, index) => {
                    try {
                        const link = el.querySelector('a[href*="/items/"]');
                        if (!link) return;
                        
                        const url = link.href;
                        const itemId = parseInt(url.match(/items\\/(\\d+)/)?.[1] || '0');
                        
                        const title = el.querySelector('h3, [class*="title"]')?.textContent?.trim() || '';
                        const priceEl = el.querySelector('[class*="price"]');
                        const price = priceEl?.textContent?.trim() || 'N/A';
                        
                        const sizeEl = el.querySelector('[class*="size"]');
                        const size = sizeEl?.textContent?.trim() || 'N/A';
                        
                        const brandEl = el.querySelector('[class*="brand"]');
                        const brand = brandEl?.textContent?.trim() || 'N/A';
                        
                        const imgEl = el.querySelector('img');
                        const photo = imgEl?.src || '';
                        
                        if (itemId > 0) {
                            items.push({
                                id: itemId,
                                title: title,
                                price: price,
                                size: size,
                                brand: brand,
                                url: url,
                                photo: photo
                            });
                        }
                    } catch (e) {
                        console.error('Error parsing item:', e);
                    }
                });
                
                return items;
            }
        """)
        
        return items
        
    except PlaywrightTimeout:
        log("⚠️  Timeout lors du chargement de la page")
        return []
    except Exception as e:
        log(f"❌ Erreur lors de l'extraction: {e}")
        return []

def run_bot():
    """Boucle principale du bot"""
    log("🚀 Démarrage du bot Vinted Oracle Cloud")
    log(f"🔍 Recherche: '{SEARCH_TEXT}'")
    log(f"⏱️  Intervalle: {CHECK_INTERVAL_MIN}-{CHECK_INTERVAL_MAX}s")
    
    last_seen_id = load_last_seen_id()
    log(f"📌 Dernier ID vu: {last_seen_id}")
    
    with sync_playwright() as p:
        # Lancer le navigateur en mode headless
        browser = p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled'
            ]
        )
        
        # Créer un contexte avec un user agent réaliste
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='fr-FR',
            timezone_id='Europe/Paris'
        )
        
        page = context.new_page()
        
        # Masquer le fait qu'on utilise Playwright
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)
        
        log("✅ Navigateur initialisé")
        
        iteration = 0
        
        try:
            while True:
                # Gestion des heures de sommeil (Économie Railway)
                # De 23h00 à 08h00, le bot s'arrête COMPLÈTEMENT pour économiser les crédits
                current_hour = datetime.now().hour
                if current_hour >= 23 or current_hour < 8:
                    log("🌙 Il est tard. Arrêt planifié pour économiser les crédits Railway.")
                    log("💤 Le bot va crasher volontairement pour arrêter le conteneur.")
                    sys.exit(1) # Quitter avec erreur pour forcer l'arrêt


                iteration += 1
                log(f"\n{'='*50}")
                log(f"🔄 Vérification #{iteration}")
                
                try:
                    # Charger la page de recherche
                    page.goto(VINTED_SEARCH_URL, wait_until='domcontentloaded', timeout=30000)
                    
                    # Extraire les articles
                    items = extract_items_from_page(page)
                    
                    if items:
                        log(f"📦 {len(items)} articles trouvés")
                        
                        # Filtrer les nouveaux articles
                        new_items = [item for item in items if item['id'] > last_seen_id]
                        
                        if new_items:
                            log(f"🆕 {len(new_items)} nouveaux articles!")
                            
                            # Trier par ID croissant pour envoyer dans l'ordre
                            new_items.sort(key=lambda x: x['id'])
                            
                            for item in new_items:
                                send_discord_alert(item)
                                # Petit délai entre les notifications
                                time.sleep(1)
                            
                            # Mettre à jour le dernier ID vu
                            last_seen_id = max(item['id'] for item in items)
                            save_last_seen_id(last_seen_id)
                            log(f"💾 Dernier ID sauvegardé: {last_seen_id}")
                        else:
                            log("😴 Aucun nouvel article")
                    else:
                        log("⚠️  Aucun article trouvé (possible problème de scraping)")
                    
                except Exception as e:
                    log(f"❌ Erreur lors de la vérification: {e}")
                
                # Attendre un délai aléatoire avant la prochaine vérification
                wait_time = random.uniform(CHECK_INTERVAL_MIN, CHECK_INTERVAL_MAX)
                log(f"⏳ Prochaine vérification dans {wait_time:.1f}s")
                time.sleep(wait_time)
                
        except KeyboardInterrupt:
            log("\n⛔ Arrêt du bot demandé")
        finally:
            browser.close()
            log("👋 Bot arrêté proprement")

if __name__ == "__main__":
    run_bot()
