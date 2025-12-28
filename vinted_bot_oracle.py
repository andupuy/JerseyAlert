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

def scrape_item_details(page, item_url):
    """Va sur la page de l'article pour récupérer infos détaillées (Stratégie Hybride DOM + Regex)"""
    try:
        log(f"🔎 Scraping détails: {item_url}")
        page.goto(item_url, wait_until='domcontentloaded', timeout=15000)
        
        # 1. Récupération du contenu HTML brut
        html_content = page.content()
        
        # 2. Stratégie Regex (Plus fiable car lit les données brutes JSON cachées)
        import re
        
        brand = 'N/A'
        brand_match = re.search(r'"brand_title":"([^"]+)"', html_content)
        if brand_match: brand = brand_match.group(1)
        
        size = 'N/A'
        size_match = re.search(r'"size_title":"([^"]+)"', html_content)
        if size_match: size = size_match.group(1)
        
        status = 'N/A'
        status_match = re.search(r'"status_title":"([^"]+)"', html_content)
        if status_match: status = status_match.group(1)
        
        description = ''
        desc_match = re.search(r'"description":"([^"]*)"', html_content)
        if desc_match:
            # Nettoyer un peu le JSON escape
            description = desc_match.group(1).replace('\\n', '\n').replace('\\"', '"')

        # 3. Récupération des photos (Le DOM marche bien pour ça)
        photos = page.evaluate("""() => {
            const imgs = Array.from(document.querySelectorAll('.item-photo--1 img, .item-photos img'));
            return imgs.map(img => img.src).filter(src => src);
        }""")
        photos = list(dict.fromkeys(photos))

        # 4. Fallback DOM si le Regex a échoué (Ceinture et bretelles)
        if brand == 'N/A':
             # ... ancien code DOM ...
             pass
        
        log(f"✅ Détails trouvés: {brand} | {size} | {status}")
        
        return {
            "description": description,
            "photos": photos,
            "brand": brand,
            "size": size,
            "status": status
        }
    except Exception as e:
        log(f"⚠️ Erreur scraping détails: {e}")
        return {"description": "", "photos": [], "brand": "N/A", "size": "N/A", "status": "N/A"}

def send_discord_alert(context, item):
    """Envoie une alerte Discord"""
    if not DISCORD_WEBHOOK_URL: return

    # Scraping détails
    details = {"description": "", "photos": [], "brand": "N/A", "size": "N/A", "status": "N/A"}
    try:
        detail_page = context.new_page()
        detail_page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        details = scrape_item_details(detail_page, item['url'])
        detail_page.close()
    except Exception as e:
        log(f"❌ Impossible de récupérer les détails: {e}")

    try:
        title = item.get('title', 'Nouvel article')
        price = item.get('price', 'N/A')
        url = item.get('url', '')
        item_id = item.get('id', 'N/A')
        
        # On utilise les infos précises du scraping
        brand = details['brand'] if details['brand'] != 'N/A' else item.get('brand', 'N/A')
        size = details['size'] if details['size'] != 'N/A' else item.get('size', 'N/A')
        status = details['status']
        
        photos = details['photos'] if details['photos'] else ([item['photo']] if item.get('photo') else [])
        description = details['description']

        if len(description) > 300: description = description[:300] + "..."

        description_text = f"**{price}** | Taille: **{size}**\nMarque: **{brand}**\nÉtat: {status}\n\n{description}"

        embed1 = {
            "title": f"🔔 {title}",
            "url": url,
            "description": description_text,
            "color": 0x09B83E,
            "footer": {"text": f"Vinted Bot • ID: {item_id}"},
            "timestamp": datetime.utcnow().isoformat(),
            "image": {"url": photos[0]} if photos else {}
        }
        
        embeds = [embed1]
        for photo_url in photos[1:4]:
            embeds.append({"url": url, "image": {"url": photo_url}})

        payload = {"username": "Vinted ASSE Bot", "avatar_url": "https://images.vinted.net/assets/icon-76x76-precomposed-3e6e4c5f0b8c7e5a5c5e5e5e5e5e5e5e.png", "embeds": embeds}
        
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        log(f"✅ Alerte envoyée #{item_id}")

    except Exception as e:
        log(f"❌ Erreur Discord: {e}")

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
    log("🚀 Démarrage du bot Vinted Oracle Cloud - VERSION V2.4 PREMIUM (JSON/REGEX STRATEGY)")
    log(f"🔍 Recherche: '{SEARCH_TEXT}'")
    log(f"⏱️  Intervalle: {CHECK_INTERVAL_MIN}-{CHECK_INTERVAL_MAX}s")
    
    last_seen_id = load_last_seen_id()
    seen_ids = set() # Cache pour éviter les doublons
    log(f"📌 Dernier ID vu: {last_seen_id}")
    
    with sync_playwright() as p:
        # Lancer le navigateur en mode headless optimisé
        browser = p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage', # Indispensable sur Docker/Railway
                '--disable-blink-features=AutomationControlled',
                '--disable-gpu' # Économie RAM
            ]
        )
        
        # Créer un contexte avec un user agent réaliste
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1280, 'height': 720}, # Résolution plus petite = moins de RAM
            locale='fr-FR',
            timezone_id='Europe/Paris'
        )
        
        # Bloquer les ressources inutiles pour économiser la RAM et la bande passante
        def block_resources(route):
            if route.request.resource_type in ["image", "media", "font", "stylesheet"]:
                # On laisse passer les images Vinted si on est sur une page détail, sinon on bloque
                # Mais pour la recherche, on bloque tout
                route.abort()
            else:
                route.continue_()

        # Initialisation intelligente (Anti-Spam au redémarrage)
        if last_seen_id == 0:
            log("🚀 Premier lancement (ou redémarrage Railway). Initialisation du dernier ID...")
            try:
                page = context.new_page()
                # On bloque tout pour l'init, c'est juste pour avoir l'ID
                page.route("**/*", block_resources) 
                
                page.goto(VINTED_SEARCH_URL, wait_until='domcontentloaded', timeout=30000)
                items = extract_items_from_page(page)
                if items:
                    last_seen_id = max(item['id'] for item in items)
                    for item in items:
                        seen_ids.add(item['id'])
                    
                    save_last_seen_id(last_seen_id)
                    log(f"✅ Initialisé ! {len(seen_ids)} articles ajoutés au cache.")
                    log("🤫 Pas d'alerte pour les articles déjà en ligne.")
                else:
                    log("⚠️ Aucun article trouvé pour l'initialisation.")
                page.close()
            except Exception as e:
                log(f"❌ Erreur lors de l'initialisation: {e}")

        log("✅ Navigateur initialisé (Mode Éco)")
        
        iteration = 0

        
        try:
            while True:
                # Gestion des heures de sommeil
                current_hour = datetime.now().hour
                if current_hour >= 23 or current_hour < 8:
                    log("🌙 Il est tard. Arrêt planifié pour économiser les crédits Railway.")
                    log("💤 Le bot va crasher volontairement.")
                    sys.exit(1)

                iteration += 1
                log(f"\n{'='*50}")
                log(f"🔄 Vérification #{iteration}")
                
                # NOUVEAU: On crée une page fraîche à CHAQUE vérification
                # C'est la seule façon de garantir 0 fuite mémoire sur le long terme
                page = context.new_page()
                page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
                
                # On bloque les images/css pour la recherche (ça va 2x plus vite)
                page.route("**/*", block_resources)

                try:
                    # Charger la page de recherche
                    page.goto(VINTED_SEARCH_URL, wait_until='domcontentloaded', timeout=30000)
                    
                    # Extraire les articles
                    items = extract_items_from_page(page)
                    
                    # On ferme la page tout de suite pour libérer la RAM
                    page.close()
                    
                    if items:
                        log(f"📦 {len(items)} articles trouvés")
                        
                        # Filtrer les VRAIS nouveaux articles
                        new_items = []
                        for item in items:
                            if item['id'] not in seen_ids:
                                new_items.append(item)
                                seen_ids.add(item['id'])
                        
                        # Nettoyer cache
                        if len(seen_ids) > 200:
                             seen_ids_list = list(seen_ids)
                             seen_ids = set(seen_ids_list[-100:])

                        if new_items:
                            log(f"🆕 {len(new_items)} nouveaux articles!")
                            new_items.sort(key=lambda x: x['id'])
                            
                            for item in new_items:
                                # send_discord_alert crée sa propre page pour les détails
                                send_discord_alert(context, item)
                                time.sleep(1)
                            
                            if new_items:
                                save_last_seen_id(max(item['id'] for item in new_items))

                        else:
                            log("😴 Aucun nouvel article (doublons filtrés)")
                    else:
                        log("⚠️  Aucun article trouvé (possible problème de scraping)")
                    
                except Exception as e:
                    log(f"❌ Erreur lors de la vérification: {e}")
                    # En cas d'erreur, on s'assure que la page est fermée
                    try: page.close()
                    except: pass
                
                # Attendre un délai aléatoire
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
