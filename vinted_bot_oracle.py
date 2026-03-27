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
VFA_STATE_FILE = "last_seen_vfa_id.txt"
VFA_URL = "https://www.vintagefootballarea.com/collections/asse?sort_by=created-descending"
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

def load_last_vfa_id():
    """Charge le dernier ID VFA vu"""
    if os.path.exists(VFA_STATE_FILE):
        try:
            with open(VFA_STATE_FILE, "r") as f:
                return int(f.read().strip())
        except:
            pass
    return 0

def save_last_vfa_id(item_id):
    """Sauvegarde le dernier ID VFA vu"""
    with open(VFA_STATE_FILE, "w") as f:
        f.write(str(item_id))

def send_vfa_discord_alert(item):
    """Envoie une alerte pour un article Vintage Football Area"""
    if not DISCORD_WEBHOOK_URL: return

    embed = {
        "title": f"🆕 {item['title']} - Vintage Football Area",
        "url": item['url'],
        "description": f"**Prix: {item['price']}**\n\nNouveauté détectée sur Vintage Football Area !",
        "color": 0x008000,
        "image": {"url": item['image']},
        "footer": {"text": f"VFA Bot • ID: {item['id']}"},
        "timestamp": datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
    }

    payload = {
        "content": f"📢 Nouveau maillot ASSE dispo sur Vintage Football Area !\n{item['title']}",
        "embeds": [embed],
        "username": "Vintage Football Bot",
        "avatar_url": "https://www.vintagefootballarea.com/cdn/shop/files/favicon-32x32_32x32.png"
    }
    
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        log(f"✅ Alerte VFA envoyée: {item['title']}")
    except Exception as e:
        log(f"❌ Erreur envoi Discord VFA: {e}")

def check_vfa_site(page, last_id, is_initial=False):
    """Scrape Vintage Football Area pour les nouveautés"""
    log(f"🔎 Check VFA: {VFA_URL}")
    try:
        page.goto(VFA_URL, wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)
        
        items = page.evaluate("""
            () => {
                const results = [];
                const products = document.querySelectorAll('.product-block');
                products.forEach(el => {
                    const id = el.getAttribute('data-product-id');
                    const titleEl = el.querySelector('.title');
                    const priceEl = el.querySelector('.price');
                    const linkEl = el.querySelector('a.product-link');
                    const imgEl = el.querySelector('img');
                    
                    if (id && titleEl && priceEl && linkEl) {
                        let imgSrc = imgEl ? imgEl.src : '';
                        if (imgEl && imgEl.srcset) {
                            const sources = imgEl.srcset.split(',').map(s => s.trim().split(' ')[0]);
                            if (sources.length > 0) imgSrc = sources[sources.length - 1];
                        }
                        if (imgSrc.startsWith('//')) imgSrc = 'https:' + imgSrc;

                        results.push({
                            id: parseInt(id),
                            title: titleEl.innerText.trim(),
                            price: priceEl.innerText.trim(),
                            url: linkEl.href,
                            image: imgSrc
                        });
                    }
                });
                return results;
            }
        """)
        
        if items:
            new_items = [it for it in items if it['id'] > last_id]
            if new_items:
                if is_initial:
                    log(f"✨ Initialisation VFA accomplie ({len(new_items)} articles indexés)")
                else:
                    log(f"🆕 {len(new_items)} nouveaux maillots VFA détectés !")
                    for it in reversed(new_items):
                        send_vfa_discord_alert(it)
                return max(last_id, max(it['id'] for it in new_items))
        return last_id
    except Exception as e:
        log(f"❌ Erreur scraping VFA: {e}")
        return last_id

def check_vfa_site_with_context(context, last_id, is_initial=False):
    """Gère l'ouverture de page et le check VFA"""
    try:
        vfa_page = context.new_page()
        # On ne bloque pas agressivement ici au cas où le site serait sensible
        res = check_vfa_site(vfa_page, last_id, is_initial)
        vfa_page.close()
        return res
    except Exception as e:
        log(f"⚠️ Erreur lors du check VFA context: {e}")
        return last_id

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
        # FUSION ET NETTOYAGE (V8.4 TOTAL CLEAN)
        price_raw = item.get('price', 'N/A')
        brand_raw = details['brand'] if details['brand'] != 'N/A' else item.get('brand', 'N/A')
        size_raw = details['size'] if details['size'] != 'N/A' else item.get('size', 'N/A')
        status_raw = details['status'] if details['status'] not in ['N/A', 'Non spécifié'] else item.get('status', 'Non spécifié')
        desc_raw = details['description']
        
        # Photos
        photos = details['photos'] if details['photos'] else ([item['photo']] if item.get('photo') else [])
        
        # Nettoyage radical
        final_title = clean_text(item.get('title'))
        final_brand = clean_text(brand_raw)
        final_price = clean_text(price_raw)
        final_size = clean_text(size_raw)
        final_status = clean_text(status_raw)
        final_desc = clean_text(desc_raw)
        
        if len(final_desc) > 300: final_desc = final_desc[:300] + "..."

        description_text = f"**{final_price}** | Taille: **{final_size}**\nMarque: **{final_brand}**\nÉtat: {final_status}\n\n{final_desc}"
        
        # Un dernier coup de balai sur l'ensemble du bloc au cas où
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

        # NETTOYAGE DU TITRE (enlever les infos redondantes de Vinted)
        import re
        clean_title = re.sub(r'\s*·.*$', '', final_title)  # Enlève tout après le "·"
        clean_title = re.sub(r'\d+[,\.]\d+\s*€.*$', '', clean_title)  # Enlève les prix
        clean_title = clean_title.strip()
        if not clean_title:
            clean_title = "Maillot ASSE"

        # EXTRAIT DE DESCRIPTION (COMPLÈTE jusqu'à 1000 caractères)
        desc_preview = final_desc[:1000] if final_desc else "Pas de description"
        if len(final_desc) > 1000:
            desc_preview += "..."

        # TEXTE DE NOTIFICATION (Pour montres et écrans verrouillés)
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
    os._exit(1) # Sortie brutale pour forcer Railway à relancer

def run_bot():
    """Boucle principale du bot V10.5 SNIPER"""
    log("🚀 Démarrage du bot V10.5 SNIPER")
    
    log(f"⚡ Mode Sniper : Réactivité maximale + International toutes les 20 min")
    
    if not DISCORD_WEBHOOK_URL:
        log("⚠️ ALERTE : DISCORD_WEBHOOK_URL n'est pas configuré ! Le bot ne pourra rien envoyer.")
    else:
        log("✅ Discord Webhook configuré.")
    
    # Initialisation
    seen_ids = set()
    last_secondary_check = 0
    last_green_check = 0
    
    log("🚀 Phase d'initialisation rapide...")
    last_seen_id = load_last_seen_id()
    last_seen_vfa_id = load_last_vfa_id()
    
    # On n'active l'initialisation silencieuse QUE si c'est le premier lancement absolu (ID=0)
    # Sinon, on veut les alertes dès le premier cycle après un redémarrage.
    is_initial_cycle = (last_seen_id == 0)
    is_initial_vfa_cycle = (last_seen_vfa_id == 0)
    
    log(f"📊 État initial: Vinted={last_seen_id}, VFA={last_seen_vfa_id}")
    last_vfa_check = 0

    try:
        while True:
            # 1. Gestion des heures (Paris UTC+1)
            import datetime as dt
            current_hour = (dt.datetime.utcnow().hour + 1) % 24
            if current_hour >= 1 and current_hour < 7:
                log(f"🌙 Mode Veille Silencieuse activé ({current_hour}h).")
                time.sleep(600)
                continue

            # 2. DÉMARRAGE MOTEUR (Watchdog activé)
            try:
                # On arme le Watchdog pour 5 minutes (300s) au lieu de 180s
                # Playwright peut être lent sur les machines chargées
                signal.signal(signal.SIGALRM, watchdog_handler)
                signal.alarm(300) 

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

                    # OPTIMISATION (ÉCONOMIE D'ÉNERGIE) : Bloquer images/CSS/Polices
                    def block_aggressively(route):
                        if route.request.resource_type in ["image", "stylesheet", "font", "media"]:
                            route.abort()
                        else:
                            route.continue_()
                    
                    context.route("**/*", block_aggressively)

                    # Détermination des recherches
                    current_cycle_queries = [] # On va remplir dynamiquement
                    now = time.time()
                    
                    # 1. Requêtes Prioritaires (Toujours)
                    queries_to_run = [(q, None) for q in PRIORITY_QUERIES]
                    
                    # 2. Triple Scan Vert (Toutes les 5 min) sur les 3 prioritaires
                    if (now - last_green_check) > 300:
                        log("☘️ Mode Triple Scan Vert (Priority + Filter 10)")
                        for q in PRIORITY_QUERIES:
                            queries_to_run.append((q, 10))
                        last_green_check = now
                        
                    # 3. Requêtes Secondaires (Toutes les 20 min)
                    if (now - last_secondary_check) > 1200:
                        log("🌍 Mode Cycle Complet (International)")
                        for q in SECONDARY_QUERIES:
                            queries_to_run.append((q, None))
                        last_secondary_check = now

                    log(f"\n" + "🚀" + "="*50)
                    log(f"⚡ Scan V9.3 : {len(queries_to_run)} requêtes")

                    for query_data in queries_to_run:
                        query, color = query_data
                        try:
                            # 1. Ouverture page NEUVE
                            page = context.new_page()
                            page.set_default_timeout(20000)
                            
                            # 2. Blocage ressources (RAM optimisée)
                            page.route("**/*", lambda route: route.abort() if route.request.resource_type in ["image", "media", "font", "stylesheet"] else route.continue_())
                            
                            # 3. Navigation Ultra-Rapide (Commit mode)
                            log(f"🔎 Check: '{query}'{' [VERTE]' if color else ''}")
                            try:
                                page.goto(get_search_url(query, color), wait_until='commit', timeout=20000)
                                # On attend explicitement un élément pour confirmer le chargement
                                page.wait_for_selector('div[data-testid*="item"]', timeout=10000)
                                
                                items = extract_items_from_page(page)
                                
                                if items:
                                    new_found = []
                                    for item in items:
                                        if item['id'] not in seen_ids and item['id'] > (last_seen_id - 100000):
                                            new_found.append(item)
                                            seen_ids.add(item['id'])
                                    
                                    if is_initial_cycle:
                                        log(f"✨ Initialisation: {len(new_found)} items trouvés.")
                                        if new_found:
                                            last_seen_id = max(last_seen_id, max(x['id'] for x in new_found))
                                    elif new_found:
                                        log(f"🆕 {len(new_found)} nouvelles pépites détectées !")
                                        new_found.sort(key=lambda x: x['id'])
                                        for item in new_found:
                                            title_low = item.get('title', '').lower()
                                            synonyms = ["maillot", "jersey", "maglia", "camiseta", "ensemble", "trikot"]
                                            has_item_kw = any(s in title_low for s in synonyms)
                                            has_team = any(x in title_low for x in ["asse", "saint etienne", "saint-etienne", "st etienne", "st-etienne", "saint étienne", "saint-étienne", "st étienne", "st-étienne", "sainté"])
                                            
                                            # 🎯 MATCH : (Maillot + Club) OU (Scan Vert + Club)
                                            if (has_item_kw and has_team) or (color == 10 and has_team):
                                                log(f"🎯 MATCH : '{item.get('title')}'")
                                                
                                                # On envoie l'alerte même au premier cycle, mais on limite à 10 items
                                                # pour éviter de spammer si on relance le bot après un moment.
                                                if not is_initial_cycle or (is_initial_cycle and len(new_found) <= 10):
                                                    send_discord_alert(context, item)
                                                else:
                                                    log(f"⏩ Skip alerte (Initial Cycle & {len(new_found)} items > 10)")
                                            
                                            last_seen_id = max(last_seen_id, max(x['id'] for x in new_found))
                                            save_last_seen_id(last_seen_id)
                            finally:
                                page.close()

                            time.sleep(random.uniform(1, 2))
                        except Exception as e:
                            log(f"⚠️ Erreur locale sur '{query}': {e}")
                    
                    # 3. CHECK VFA (Priorité revue à la hausse)
                    if (now - last_vfa_check) > 300:
                        try:
                            log("🔎 Passage check VFA...")
                            new_vfa_id = check_vfa_site_with_context(context, last_seen_vfa_id, is_initial_vfa_cycle)
                            if new_vfa_id > last_seen_vfa_id:
                                last_seen_vfa_id = new_vfa_id
                                save_last_vfa_id(last_seen_vfa_id)
                                log(f"✅ State VFA mis à jour : {last_seen_vfa_id}")
                            
                            is_initial_vfa_cycle = False
                            last_vfa_check = now
                        except Exception as e:
                            log(f"⚠️ Erreur lors du check VFA: {e}")

                    # 4. Requêtes Secondaires Vinted (Plus loin dans la boucle car plus risquées)
                    if (now - last_secondary_check) > 1200:
                        log("🌍 Mode Cycle Complet (International)")
                        # On réutilise queries_to_run qui a été calculé au début du cycle
                        # Mais wait, queries_to_run contient déjà tout si c'est le moment.
                        # En fait, la logique au début de la boucle remplissait queries_to_run.
                        # Je vais simplifier : tout ce qui est dans queries_to_run est déjà traité.
                        # Je vais juste mettre à jour le timer ici.
                        last_secondary_check = now

                    browser.close()
                
                # Désactivation du Watchdog après succès du cycle
                signal.alarm(0)
            except Exception as e:
                log(f"🚨 Bug moteur Playwright : {e}. Redémarrage au prochain cycle.")
                signal.alarm(0)

            # 3. Entretien du Cache
            is_initial_cycle = False
            if len(seen_ids) > 2000:
                seen_ids_list = sorted(list(seen_ids), reverse=True)
                seen_ids = set(seen_ids_list[:1500])

            # 4. Sommeil
            log(f"⏳ Cycle {datetime.now().strftime('%H:%M:%S')} terminé. Repos 10s...")
            time.sleep(10)

    except KeyboardInterrupt:
        log("\n⛔ Arrêt du bot demandé")
    finally:
        log("👋 Bot éteint proprement")

if __name__ == "__main__":
    run_bot()
