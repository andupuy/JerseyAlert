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
# Configuration des recherches
PRIORITY_QUERIES = ["Maillot Asse", "Maillot Saint-Etienne", "Maillot St Etienne"]
SECONDARY_QUERIES = ["Jersey Asse", "Jersey Saint-Etienne", "Maglia Asse", "Camiseta Asse"]
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

def get_search_url(query):
    return f"https://www.vinted.fr/catalog?search_text={query.replace(' ', '+')}&order=newest_first"

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
    """Extrait les articles avec Parsing Intelligent du Titre (V5.0)"""
    try:
        page.wait_for_selector('div[data-testid*="item"]', timeout=10000)
        time.sleep(random.uniform(1, 2))
        
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
                        
                        // RECUPERATION DU TITRE COMPLET (contient souvent marque, taille, état)
                        let rawTitle = link.getAttribute('title') || '';
                        if (!rawTitle) {
                             const img = el.querySelector('img');
                             if (img) rawTitle = img.alt;
                        }
                        
                        // Valeurs par défaut
                        let price = 'N/A';
                        let size = 'N/A';
                        let brand = 'N/A';
                        let status = 'Non spécifié';
                        let title = rawTitle; // Par défaut on prend tout

                        // ANALYSE DU TITRE (Parsing V5.0)
                        // Exemple: "Maillot, marque: Nike, taille: L, état: Très bon état, 20,00 €"
                        if (rawTitle.includes('marque:') || rawTitle.includes('taille:')) {
                            
                            // Nettoyage du titre (on garde le début avant la première virgule souvent)
                            title = rawTitle.split(',')[0].trim();
                            
                            // Extraction par Regex JS
                            const brandMatch = rawTitle.match(/marque:\\s*([^,]+)/i);
                            if (brandMatch) brand = brandMatch[1].trim();
                            
                            const sizeMatch = rawTitle.match(/taille:\\s*([^,]+)/i);
                            if (sizeMatch) size = sizeMatch[1].trim();
                            
                            const statusMatch = rawTitle.match(/état:\\s*([^,]+)/i);
                            if (statusMatch) status = statusMatch[1].trim();
                        }
                        
                        // Récupération de TOUS les textes (morceaux + bloc complet)
                        const texts = Array.from(el.querySelectorAll('p, h3, h4, span, div'))
                                           .map(e => e.innerText.trim())
                                           .filter(t => t.length > 0);
                        
                        // On ajoute le texte brut complet de l'élément pour voir les lignes concaténées
                        texts.push(el.innerText.trim());
                        
                        const uniqueTexts = [...new Set(texts)];
                        price = uniqueTexts.find(t => t.includes('€') || t.includes('$')) || 'N/A';
                        
                        // Si le parsing titre a échoué pour certains champs, on tente l'heuristique
                        if (size === 'N/A') {
                            const sizeRegex = /^(XS|S|M|L|XL|XXL|\d{2,3}|Unique)$/i;
                            size = uniqueTexts.find(t => sizeRegex.test(t) && !t.includes('€')) || 'N/A';
                        }

                        // 4. Heuristique "État" ULTIME (V6.3)
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

                        // 5. Heuristique "Marque" de secours (V6.3 Ultra-Strict)
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

                        // 6. Nettoyage final du Titre (V8.2 AGRESSIF)
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
        final_status = details['status'] if details['status'] not in ['N/A', 'Non spécifié'] else item.get('status', 'Non spécifié')
        final_price = item.get('price', 'N/A')
        
        # Photos
        photos = details['photos'] if details['photos'] else ([item['photo']] if item.get('photo') else [])
        
        # Nettoyage final avant envoi (V8.2)
        final_title = clean_text(item.get('title'))
        final_brand = clean_text(final_brand)
        final_desc = clean_text(details['description'])
        if len(final_desc) > 300: final_desc = final_desc[:300] + "..."

        description_text = f"**{final_price}** | Taille: **{final_size}**\nMarque: **{final_brand}**\nÉtat: {final_status}\n\n{final_desc}"

        embed1 = {
            "title": f"🔔 {final_title}",
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
    log("🚀 Démarrage du bot Vinted Oracle Cloud - VERSION V8.3 FINAL")
    log(f"⚡ Priorité : {len(PRIORITY_QUERIES)} requêtes rapides toutes les ~30s")
    log(f"🌍 Secondaire : {len(SECONDARY_QUERIES)} requêtes internationales toutes les 20 min")
    
    last_seen_id = load_last_seen_id()
    seen_ids = set() # Cache pour éviter les doublons
    last_secondary_check = 0 # Timestamp pour le cycle de 20 min
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
        log("🚀 Phase d'initialisation (remplissage du cache sans alertes)...")
        try:
            page = context.new_page()
            page.route("**/*", block_resources) 
            
            for query in SEARCH_QUERIES:
                for attempt in range(2): # 2 tentatives en cas de lag
                    try:
                        log(f"📥 Pré-chargement ({attempt+1}/2) : '{query}'...")
                        page.goto(get_search_url(query), wait_until='domcontentloaded', timeout=30000)
                        items = extract_items_from_page(page)
                        if items:
                            for item in items:
                                seen_ids.add(item['id'])
                                if item['id'] > last_seen_id:
                                    last_seen_id = item['id']
                            break # Succès, on passe au suivant
                        time.sleep(2)
                    except:
                        continue
            
            save_last_seen_id(last_seen_id)
            log(f"✅ Initialisé ! {len(seen_ids)} articles en mémoire. Dernier ID : {last_seen_id}")
            page.close()
        except Exception as e:
            log(f"❌ Erreur lors de l'initialisation: {e}")

        log("✅ Navigateur prêt. Lancement du mode Sniper...")
        
        try:
            while True:
                # Gestion des heures de sommeil (Heure de Paris UTC+1)
                import datetime as dt
                # Railway est souvent en UTC, on ajoute 1h pour Paris
                current_hour = (dt.datetime.utcnow().hour + 1) % 24
                if current_hour >= 1 and current_hour < 7:
                    if 'is_sleeping' not in locals() or not is_sleeping:
                        log(f"🌙 Mode Veille Silencieuse activé ({current_hour}h). Plus d'emails de crash !")
                        is_sleeping = True
                    
                    time.sleep(600) # Dort 10 minutes
                    continue 
                
                is_sleeping = False # Réveil !

                # Détermination des recherches à effectuer pour ce cycle
                current_cycle_queries = list(PRIORITY_QUERIES)
                
                # On ajoute les recherches secondaires toutes les 20 minutes (1200 secondes)
                now = time.time()
                is_full_cycle = (now - last_secondary_check) > 1200
                if is_full_cycle:
                    log("🌍 Mode Cycle Complet : Inclusion des recherches internationales")
                    current_cycle_queries += SECONDARY_QUERIES
                    last_secondary_check = now

                log(f"\n" + "🚀" + "="*50)
                log(f"⚡ Cycle de scan (X{len(current_cycle_queries)})")
                
                for current_query in current_cycle_queries:
                    try:
                        page = context.new_page()
                        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
                        page.route("**/*", block_resources)
                        
                        log(f"🔎 Check: '{current_query}'")
                        page.goto(get_search_url(current_query), wait_until='domcontentloaded', timeout=20000)
                        
                        items = extract_items_from_page(page)
                        page.close()

                        if items:
                            new_found = []
                            for item in items:
                                # LE DOUBLE VERROU SOUPLE (Anti-Oublis V8.2)
                                # On accepte les IDs jusqu'à 100k en arrière (marge de sécurité)
                                if item['id'] not in seen_ids and item['id'] > (last_seen_id - 100000):
                                    new_found.append(item)
                                    seen_ids.add(item['id'])
                            
                            if new_found:
                                log(f"🆕 {len(new_found)} nouvelles pépites détectées !")
                                new_found.sort(key=lambda x: x['id'])
                                
                                for item in new_found:
                                    title_low = item.get('title', '').lower()
                                    # FILTRE STRICT (V8.3)
                                    synonyms = ["maillot", "jersey", "maglia", "camiseta"]
                                    has_item_kw = any(s in title_low for s in synonyms)
                                    has_team = any(x in title_low for x in ["asse", "saint etienne", "saint-etienne", "st etienne"])
                                    
                                    if has_item_kw and has_team:
                                        log(f"🎯 MATCH : '{item.get('title')}'")
                                        send_discord_alert(context, item)
                                    else:
                                        log(f"⏭️  Ignoré : '{item.get('title')}'")
                                
                                # Mise à jour du dernier ID vu
                                current_max = max(item['id'] for item in new_found)
                                if current_max > last_seen_id:
                                    last_seen_id = current_max
                                    save_last_seen_id(last_seen_id)
                        
                        # Petite pause
                        time.sleep(1)

                    except Exception as e:
                        log(f"⚠️ Erreur sur '{current_query}': {e}")
                        try: page.close()
                        except: pass
                
                # Cache maintenance (V8.2 : 2000 items pour éviter tout doublon)
                if len(seen_ids) > 2000:
                    seen_ids_list = sorted(list(seen_ids), reverse=True)
                    seen_ids = set(seen_ids_list[:1500]) # On garde les 1500 plus récents

                # Pause de 10s avant le prochain cycle complet
                log(f"⏳ Cycle terminé. Pause de 10s...")
                time.sleep(10)
                
        except KeyboardInterrupt:
            log("\n⛔ Arrêt du bot demandé")
        finally:
            browser.close()
            log("👋 Bot arrêté proprement")

if __name__ == "__main__":
    run_bot()
