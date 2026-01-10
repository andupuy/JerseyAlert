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
import signal
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# Configuration
# Configuration des recherches
PRIORITY_QUERIES = ["Maillot Asse", "Maillot Saint-Etienne", "Maillot St Etienne"]
SECONDARY_QUERIES = ["Jersey Asse", "Jersey Saint-Etienne", "Maglia Asse", "Camiseta Asse", "Ensemble Asse", "Trikot Asse"]
# Liste combinée pour l'initialisation
SEARCH_QUERIES = PRIORITY_QUERIES + SECONDARY_QUERIES

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
STATE_FILE = "last_seen_id.txt"
CHECK_INTERVAL_MIN = 10
CHECK_INTERVAL_MAX = 20

def clean_text(text):
    """Nettoyage radical des parasites Vinted (Enlevé, Nouveau, etc)"""
    if not text: return ""
    import re
    # Supprime les badges publicitaires et parasites
    text = re.sub(r'(?i)enlevé\s*!?', '', text)
    text = re.sub(r'(?i)nouveau\s*!?', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def get_search_url(query, color_id=None):
    url = f"https://www.vinted.fr/catalog?search_text={query.replace(' ', '+')}&order=newest_first"
    if color_id:
        url += f"&color_ids[]={color_id}"
    return url

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
            status = item.get('status', 'N/A')
            
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
    """Extrait les articles avec Parsing Intelligent du Titre (V5.0)"""
    try:
        # Note: on ne remet pas de wait_for_selector ici car il est fait avant l'appel
        items = page.evaluate("""
            () => {
                const items = [];
                const itemElements = document.querySelectorAll('div[data-testid*="item"], div[class*="feed-grid__item"]');
                
                itemElements.forEach((el) => {
                    try {
                        const link = el.querySelector('a');
                        if (!link) return;
                        
                        const url = link.href;
                        const idMatch = url.match(/items\\/(\\d+)/);
                        if (!idMatch) return;
                        const itemId = parseInt(idMatch[1]);
                        
                        let rawTitle = link.getAttribute('title') || '';
                        if (!rawTitle) {
                             const img = el.querySelector('img');
                             if (img) rawTitle = img.alt;
                        }
                        
                        let price = 'N/A';
                        let size = 'N/A';
                        let brand = 'N/A';
                        let status = 'Non spécifié';
                        let title = rawTitle;

                        if (rawTitle.includes('marque:') || rawTitle.includes('taille:')) {
                            title = rawTitle.split(',')[0].trim();
                            const brandMatch = rawTitle.match(/marque:\\s*([^,]+)/i);
                            if (brandMatch) brand = brandMatch[1].trim();
                            const sizeMatch = rawTitle.match(/taille:\\s*([^,]+)/i);
                            if (sizeMatch) size = sizeMatch[1].trim();
                            const statusMatch = rawTitle.match(/état:\\s*([^,]+)/i);
                            if (statusMatch) status = statusMatch[1].trim();
                        }
                        
                        const texts = Array.from(el.querySelectorAll('p, h3, h4, span, div'))
                                           .map(e => e.innerText.trim())
                                           .filter(t => t.length > 0);
                        texts.push(el.innerText.trim());
                        
                        const uniqueTexts = [...new Set(texts)];
                        price = uniqueTexts.find(t => t.includes('€') || t.includes('$')) || 'N/A';
                        
                        if (size === 'N/A') {
                            const sizeRegex = /^(XS|S|M|L|XL|XXL|\\d{2,3}|Unique)$/i;
                            size = uniqueTexts.find(t => sizeRegex.test(t) && !t.includes('€')) || 'N/A';
                        }

                        if (status === 'Non spécifié') {
                            const statusKeywords = [
                                "neuf avec étiquette", "neuf sans étiquette", "neuf",
                                "très bon état", "très bon", "bon état", "satisfaisant", 
                                "jamais porté", "porté"
                            ];
                            const stateText = uniqueTexts.find(t => 
                                statusKeywords.some(kw => t.toLowerCase().includes(kw))
                            );
                            if (stateText) {
                                const lowState = stateText.toLowerCase();
                                const found = statusKeywords.find(kw => lowState.includes(kw));
                                if (found) {
                                    status = found.charAt(0).toUpperCase() + found.slice(1);
                                }
                            }
                        }

                        if (brand === 'N/A' || brand.toLowerCase().includes('enlevé')) {
                             const ignored = ['vinted', 'enlevé', 'nouveau', 'neuf', '€', 'recommandé', 'boosté', 'protection', 'avis', 'favori'];
                             const potentialBrand = uniqueTexts.find(t => {
                                 const low = t.toLowerCase();
                                 if (t.length < 2 || t.length > 25) return false;
                                 if (ignored.some(i => low.includes(i))) return false;
                                 if (/(neuf|état|porté|taille|size)/i.test(low)) return false;
                                 if (/^(XS|S|M|L|XL|XXL|[0-9]{2})$/i.test(t)) return false;
                                 if (t.includes('€')) return false;
                                 return true;
                             });
                             if (potentialBrand) brand = potentialBrand;
                        }

                        title = title.replace(/enlevé/gi, '').replace(/nouveau/gi, '').replace(/!/g, '').replace(/\\s*,\\s*$/, '').trim();
                        title = title.replace(/\\s{2,}/g, ' ');
                        if (!title || title.length < 3) title = 'Maillot ASSE';

                        const imgEl = el.querySelector('img');
                        const photo = imgEl?.src || '';
                        
                        items.push({
                            id: itemId,
                            title: title,
                            price: price,
                            size: size,
                            brand: brand,
                            status: status,
                            url: url,
                            photo: photo
                        });

                    } catch (e) {
                         // Silent
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

    details = {"description": "", "photos": [], "brand": "N/A", "size": "N/A", "status": "N/A"}
    try:
        detail_page = context.new_page()
        detail_page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        details = scrape_item_details(detail_page, item['url'])
        detail_page.close()
    except Exception as e:
        log(f"⚠️ Mode Simple (Détails échoués): {e}")

    try:
        # FUSION ET NETTOYAGE
        price_raw = item.get('price', 'N/A')
        brand_raw = details['brand'] if details['brand'] != 'N/A' else item.get('brand', 'N/A')
        size_raw = details['size'] if details['size'] != 'N/A' else item.get('size', 'N/A')
        status_raw = details['status'] if details['status'] not in ['N/A', 'Non spécifié'] else item.get('status', 'Non spécifié')
        desc_raw = details['description']
        
        photos = details['photos'] if details['photos'] else ([item['photo']] if item.get('photo') else [])
        
        final_title = clean_text(item.get('title'))
        final_brand = clean_text(brand_raw)
        final_price = clean_text(price_raw)
        final_size = clean_text(size_raw)
        final_status = clean_text(status_raw)
        final_desc = clean_text(desc_raw)
        
        if len(final_desc) > 300: final_desc = final_desc[:300] + "..."

        description_text = f"**{final_price}** | Taille: **{final_size}**\nMarque: **{final_brand}**\nÉtat: {final_status}\n\n{final_desc}"
        description_text = description_text.replace("  ", " ").strip()

        if not final_title: final_title = "Nouvel article ASSE"

        embed1 = {
            "title": f"🔔 {final_title}",
            "url": item.get('url'),
            "description": description_text,
            "color": 0x09B83E,
            "footer": {"text": f"Vinted Bot • ID: {item.get('id')}"},
            "timestamp": datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
        }
        
        if photos:
            embed1["image"] = {"url": photos[0]}

        embeds = [embed1]
        for photo_url in photos[1:4]:
            embeds.append({"url": item.get('url'), "image": {"url": photo_url}})

        import re
        clean_title = re.sub(r'\s*·.*$', '', final_title)
        clean_title = re.sub(r'\d+[,\.]\d+\s*€.*$', '', clean_title)
        clean_title = clean_title.strip()
        if not clean_title: clean_title = "Maillot ASSE"

        desc_preview = final_desc[:1000] if final_desc else "Pas de description"
        if len(final_desc) > 1000: desc_preview += "..."

        notif_text = f"""@everyone | {clean_title}
💰 {final_price} | 📏 {final_size} | 🏷️ {final_brand}
📝 {desc_preview}"""

        payload = {
            "content": notif_text,
            "username": "Vinted ASSE Bot", 
            "avatar_url": "https://images.vinted.net/assets/icon-76x76-precomposed-3e6e4c5f0b8c7e5a5c5e5e5e5e5e5e5e.png", 
            "embeds": embeds
        }
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        log(f"✅ Alerte envoyée #{item.get('id')}")

    except Exception as e:
        log(f"❌ Erreur Discord: {e}")

def watchdog_handler(signum, frame):
    """Tue le bot si un cycle prend trop de temps (Freeze detection)"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] 🚨 WATCHDOG: Bot figé depuis trop longtemps ! Redémarrage forcé...", flush=True)
    os._exit(1)

def run_bot():
    """Boucle principale du bot V11.0 PERSISTENT SNIPER"""
    log("🚀 Démarrage du bot V11.0 PERSISTENT SNIPER")
    
    log(f"⚡ Mode Sniper : Réactivité maximale + International toutes les 20 min")
    
    # Initialisation
    seen_ids = set()
    last_secondary_check = 0
    last_green_check = 0
    cycle_count = 0  # Compteur pour redémarrage préventif
    
    log("🚀 Phase d'initialisation rapide...")
    is_initial_cycle = True
    last_seen_id = load_last_seen_id()

    try:
        while True:
            # 1. Gestion des heures (Paris UTC+1)
            import datetime as dt
            current_hour = (dt.datetime.utcnow().hour + 1) % 24
            if current_hour >= 1 and current_hour < 7:
                log(f"🌙 Mode Veille Silencieuse activé ({current_hour}h).")
                time.sleep(600)
                continue

            # 2. DÉMARRAGE MOTEUR PERSISTANT
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
                )
                context = browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    viewport={'width': 1280, 'height': 720},
                    locale='fr-FR',
                    timezone_id='Europe/Paris'
                )

                # OPTIMISATION GREEN ENERGY
                def block_aggressively(route):
                    if route.request.resource_type in ["image", "stylesheet", "font", "media"]:
                        route.abort()
                    else:
                        route.continue_()
                context.route("**/*", block_aggressively)

                # BOUCLE DE CYCLES PERSISTANTS (Redémarrage toutes les 30 itérations)
                while cycle_count < 30:
                    try:
                        # On arme le Watchdog pour chaque cycle
                        signal.signal(signal.SIGALRM, watchdog_handler)
                        signal.alarm(240) # 4 minutes max par cycle complet

                        now = time.time()
                        queries_to_run = [(q, None) for q in PRIORITY_QUERIES]
                        
                        if (now - last_green_check) > 300:
                            log("☘️ Mode Triple Scan Vert")
                            for q in PRIORITY_QUERIES:
                                queries_to_run.append((q, 10))
                            last_green_check = now
                            
                        if (now - last_secondary_check) > 1200:
                            log("🌍 Mode Cycle Complet (International)")
                            for q in SECONDARY_QUERIES:
                                queries_to_run.append((q, None))
                            last_secondary_check = now

                        log(f"\n🚀 Cycle {cycle_count+1}/30 | {len(queries_to_run)} requêtes")

                        for query_data in queries_to_run:
                            query, color = query_data
                            page = None
                            try:
                                page = context.new_page()
                                url = get_search_url(query, color)
                                
                                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                                page.wait_for_selector('div[data-testid*="item"]', timeout=10000)
                                items = extract_items_from_page(page)
                                
                                new_found = []
                                for item in items:
                                    if item['id'] not in seen_ids:
                                        seen_ids.add(item['id'])
                                        if not is_initial_cycle and item['id'] > last_seen_id:
                                            new_found.append(item)
                                            send_discord_alert(context, item)
                                
                                if new_found:
                                    last_seen_id = max(last_seen_id, max(x['id'] for x in new_found))
                                    save_last_seen_id(last_seen_id)

                            except Exception as e:
                                log(f"⚠️ Erreur locale '{query}': {e}")
                            finally:
                                if page:
                                    page.close()
                                time.sleep(random.uniform(1, 2))

                        # Fin de cycle réussi
                        cycle_count += 1
                        is_initial_cycle = False
                        signal.alarm(0) # Désarme le watchdog

                        # Cache maintenance
                        if len(seen_ids) > 2000:
                            seen_ids_list = sorted(list(seen_ids), reverse=True)
                            seen_ids = set(seen_ids_list[:1500])

                        log(f"⏳ Repos 15s...")
                        time.sleep(15)

                    except Exception as e:
                        log(f"🚨 Bug cycle : {e}")
                        signal.alarm(0)
                        break

                log("🔄 Redémarrage préventif du navigateur pour la RAM...")
                browser.close()
                cycle_count = 0

    except KeyboardInterrupt:
        log("\n⛔ Arrêt du bot demandé")
    except Exception as e:
        log(f"🚨 Erreur fatale run_bot: {e}")
    finally:
        log("👋 Bot éteint proprement")

if __name__ == "__main__":
    run_bot()
