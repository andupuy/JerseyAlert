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
    """Va sur la page de l'article pour récupérer infos détaillées via API interne (V3.0 API Call)"""
    try:
        log(f"🔎 Scraping détails: {item_url}")
        
        # Extraire l'ID de l'item depuis l'URL
        import re
        id_match = re.search(r'/items/(\d+)', item_url)
        item_id = id_match.group(1) if id_match else None
        
        if not item_id:
            log("❌ Impossible d'extraire l'ID de l'URL")
            return {"description": "", "photos": [], "brand": "N/A", "size": "N/A", "status": "N/A"}

        # On va sur une page "neutre" (la page d'accueil ou la recherche) pour avoir le contexte de session
        # Pas besoin d'aller sur la page détail lourde, on peut juste fetch l'API
        # Mais pour être sûr d'avoir les cookies, restons sur la page actuelle ou allons sur la home
        # Si on est déjà dans un contexte ouvert, on peut juste faire fetch
        # Le contexte appelant ouvre déjà une page vide, allons sur Vinted Home pour initialiser la session si besoin
        # page.goto("https://www.vinted.fr", wait_until='domcontentloaded') 
        # (Optimisation: on suppose qu'on a déjà les cookies de la recherche précédente)
        
        # Pour être sûr, on va quand même sur la page de l'item (ça génère les cookies spécifiques item)
        page.goto(item_url, wait_until='domcontentloaded', timeout=15000)

        # Récupération des photos (DOM, ça marche toujours bien et c'est joli)
        photos = page.evaluate("""() => {
            const imgs = Array.from(document.querySelectorAll('.item-photo--1 img, .item-photos img'));
            return imgs.map(img => img.src).filter(src => src);
        }""")
        photos = list(dict.fromkeys(photos))

        # APPEL API DIRECT via le navigateur
        log(f"📡 Appel API interne pour l'item {item_id}...")
        api_data = page.evaluate(f"""async () => {{
            try {{
                const response = await fetch('/api/v2/items/{item_id}?localize=false', {{
                    headers: {{
                        'Accept': 'application/json, text/plain, */*'
                    }}
                }});
                if (response.ok) {{
                    return await response.json();
                }}
                return null;
            }} catch (e) {{
                return null;
            }}
        }}""")
        
        description = ""
        brand = "N/A"
        size = "N/A"
        status = "N/A"
        
        if api_data and 'item' in api_data:
            item = api_data['item']
            log("✅ Réponse API reçue !")
            
            description = item.get('description', '')
            brand = item.get('brand_title', 'N/A')
            size = item.get('size_title', 'N/A')
            status = item.get('status', 'N/A') # Parfois c'est status_id, il faut mapper, mais essayons title
            
            # Si status est vide, parfois c'est pas envoyé
            if status == 'N/A' and 'status' in item:
                 # Vinted API change parfois
                 pass
            
        else:
            log("⚠️ API Vinted muette ou erreur")
            # Fallback DOM
            description = page.evaluate("""() => {
                const descEl = document.querySelector('[itemprop="description"]');
                return descEl ? descEl.innerText : '';
            }""")
        
        log(f"✅ Détails finaux: {brand} | {size} | {status}")
        
        return {
            "description": description,
            "photos": photos,
            "brand": brand,
            "size": size,
            "status": status
        }
    except Exception as e:
        log(f"⚠️ Erreur scraping détails (API Mode): {e}")
        return {"description": "", "photos": [], "brand": "N/A", "size": "N/A", "status": "N/A"}

def extract_items_from_page(page):
    """Extrait les articles de la page Vinted avec une heuristique robuste"""
    try:
        # Attendre que les articles se chargent
        page.wait_for_selector('div[data-testid*="item"]', timeout=10000)
        time.sleep(random.uniform(1, 2))
        
        items = page.evaluate("""
            () => {
                const items = [];
                // Sélecteur générique pour trouver les conteneurs d'articles
                const itemElements = document.querySelectorAll('div[data-testid*="item"], div[class*="feed-grid__item"]');
                
                itemElements.forEach((el) => {
                    try {
                        const link = el.querySelector('a');
                        if (!link) return;
                        
                        const url = link.href;
                        // Extraction ID
                        const idMatch = url.match(/items\\/(\\d+)/);
                        if (!idMatch) return;
                        const itemId = parseInt(idMatch[1]);
                        
                        // Récupération de TOUS les textes visibles dans la carte
                        // On nettoie les doublons et les textes vides
                        const texts = Array.from(el.querySelectorAll('p, h3, h4, span, div'))
                                           .map(e => e.innerText.trim())
                                           .filter(t => t.length > 0 && t.length < 50);
                        const uniqueTexts = [...new Set(texts)];
                        
                        // Heuristique pour deviner les champs
                        let price = 'N/A';
                        let size = 'N/A';
                        let brand = 'N/A';
                        
                        // 1. Le prix contient toujours un symbole monétaire
                        price = uniqueTexts.find(t => t.includes('€') || t.includes('$') || t.includes('£')) || 'N/A';
                        
                        // 2. La taille est souvent courte (S, M, L, XL, XXL, 38, 40, 42...)
                        // Regex simple pour les tailles standards
                        const sizeRegex = /^(XS|S|M|L|XL|XXL|\d{2,3}|Unique)$/i;
                        size = uniqueTexts.find(t => sizeRegex.test(t) && !t.includes('€')) || 'N/A';
                        
                        // 3. La marque est souvent un texte qui n'est ni le prix ni la taille
                        // On prend le texte qui ressemble le plus à une marque (pas 'Vinted', pas 'Nouveau')
                        const ignored = ['vinted', 'nouveau', 'new', 'neuf', '€', 'recommandé', 'boosté'];
                        brand = uniqueTexts.find(t => {
                            const low = t.toLowerCase();
                            return !sizeRegex.test(t) && 
                                   !t.includes('€') && 
                                   !ignored.some(i => low.includes(i));
                        });
                        
                        // Titre : souvent le link title ou une image alt
                        let title = link.getAttribute('title') || '';
                        if (!title) {
                             const img = el.querySelector('img');
                             if (img) title = img.alt;
                        }
                        if (!title) title = 'Article Vinted';

                        const imgEl = el.querySelector('img');
                        const photo = imgEl?.src || '';
                        
                        items.push({
                            id: itemId,
                            title: title,
                            price: price,
                            size: size || 'N/A',
                            brand: brand || 'N/A',
                            url: url,
                            photo: photo
                        });

                    } catch (e) {
                        // Silent error
                    }
                });
                return items;
            }
        """)
        return items
    except Exception as e:
        log(f"❌ Erreur extraction liste: {e}")
        return []

def send_discord_alert(context, item):
    """Envoie une alerte Discord intelligente (fallback liste)"""
    if not DISCORD_WEBHOOK_URL: return

    # 1. On essaie d'avoir les détails riches (Photos + Desc)
    # Mais on ne fait plus confiance au brand/size du scraping détail s'il échoue
    # On garde les infos "liste" (item) comme base solide
    
    details = {"description": "", "photos": [], "brand": "N/A", "size": "N/A", "status": "N/A"}
    try:
        detail_page = context.new_page()
        detail_page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        details = scrape_item_details(detail_page, item['url'])
        detail_page.close()
    except Exception as e:
        log(f"⚠️ Mode Simple (Détails échoués): {e}")

    try:
        # FUSION INTELLIGENTE DES DONNÉES
        # On ne prend la valeur 'details' QUE si elle n'est pas N/A, sinon on garde celle de la liste 'item'
        
        final_brand = details['brand'] if details['brand'] != 'N/A' else item.get('brand', 'N/A')
        final_size = details['size'] if details['size'] != 'N/A' else item.get('size', 'N/A')
        final_status = details['status'] if details['status'] != 'N/A' else "Non spécifié"
        final_price = item.get('price', 'N/A')
        
        # Photos
        photos = details['photos'] if details['photos'] else ([item['photo']] if item.get('photo') else [])
        
        description = details['description']
        if len(description) > 300: description = description[:300] + "..."

        description_text = f"**{final_price}** | Taille: **{final_size}**\nMarque: **{final_brand}**\nÉtat: {final_status}\n\n{description}"

        embed1 = {
            "title": f"🔔 {item.get('title')}",
            "url": item.get('url'),
            "description": description_text,
            "color": 0x09B83E,
            "footer": {"text": f"Vinted Bot • ID: {item.get('id')}"},
            "timestamp": datetime.utcnow().isoformat(),
            "image": {"url": photos[0]} if photos else {}
        }
        
        embeds = [embed1]
        for photo_url in photos[1:4]:
            embeds.append({"url": item.get('url'), "image": {"url": photo_url}})

        payload = {"username": "Vinted ASSE Bot", "avatar_url": "https://images.vinted.net/assets/icon-76x76-precomposed-3e6e4c5f0b8c7e5a5c5e5e5e5e5e5e5e.png", "embeds": embeds}
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        log(f"✅ Alerte envoyée #{item.get('id')}")

    except Exception as e:
        log(f"❌ Erreur Discord: {e}")

def run_bot():
    """Boucle principale du bot"""
    log("🚀 Démarrage du bot Vinted Oracle Cloud - VERSION V4.0 PREMIUM (HEURISTIC MODE)")
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
