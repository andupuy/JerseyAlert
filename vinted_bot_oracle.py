#!/usr/bin/env python3
"""
Vinted Bot V11.21 - SNIPER ULTIME (ANTI-REPOST & ANTI-BLIND)
- Signature automatique intelligente (Vendeur + Titre + Prix)
- Mémoire d'éléphant (10 000 signatures)
- Correction bug boucle : processe TOUTES les nouvelles annonces d'un coup
- Restauration parsing robuste (V10.6 Nickel)
"""

import os
import sys
import time
import random
import requests
import signal
import gc
import json
import re
from datetime import datetime
from playwright.sync_api import sync_playwright

# Configuration
PRIORITY_QUERIES = ["Maillot Asse", "Maillot Saint-Etienne", "Maillot St Etienne"]
SECONDARY_QUERIES = ["Jersey Asse", "Jersey Saint-Etienne", "Maglia Asse", "Camiseta Asse", "Ensemble Asse", "Trikot Asse"]
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

STATE_FILE = "last_seen_id.txt"
SIGNATURES_FILE = "sent_signatures.json"

def log(message):
    timestamp = datetime.now().strftime('%H:%M:%S')
    print(f"[{timestamp}] {message}", flush=True)

def load_json(filename, default):
    if os.path.exists(filename):
        try:
            with open(filename, "r") as f: return json.load(f)
        except: pass
    return default

def save_json(filename, data):
    try:
        with open(filename, "w") as f: json.dump(data, f)
    except: pass

def load_last_seen_id():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f: return int(f.read().strip())
        except: pass
    return 0

def clean_text(text):
    if not text: return ""
    text = re.sub(r'(?i)enlevé\s*!?', '', text)
    text = re.sub(r'(?i)nouveau\s*!?', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def get_search_url(query, color_id=None):
    url = f"https://www.vinted.fr/catalog?search_text={query.replace(' ', '+')}&order=newest_first"
    if color_id: url += f"&color_ids[]={color_id}"
    return url

def scrape_item_details(page, item_url):
    """Extraction riche via API interne et DOM"""
    try:
        page.goto(item_url, wait_until='domcontentloaded', timeout=15000)
        time.sleep(1)
        
        photos = page.evaluate("""() => {
            const imgs = Array.from(document.querySelectorAll('.item-photo--1 img, .item-photos img'));
            return imgs.map(img => img.src).filter(src => src && src.includes('images.vinted'));
        }""")
        
        desc = page.evaluate("() => document.querySelector('[itemprop=\"description\"]')?.innerText || ''")
        
        id_match = re.search(r'/items/(\d+)', item_url)
        item_id = id_match.group(1) if id_match else None
        
        brand, size, status = "N/A", "N/A", "N/A"
        if item_id:
            api_data = page.evaluate(f"""async () => {{
                try {{
                    const r = await fetch('/api/v2/items/{item_id}?localize=false');
                    return r.ok ? await r.json() : null;
                }} catch(e) {{ return null; }}
            }}""")
            if api_data and 'item' in api_data:
                it = api_data['item']
                brand = it.get('brand_title', 'N/A')
                size = it.get('size_title', 'N/A')
                status = it.get('status', 'N/A')

        return {"description": desc, "photos": photos, "brand": brand, "size": size, "status": status}
    except:
        return {"description": "", "photos": [], "brand": "N/A", "size": "N/A", "status": "N/A"}

def extract_items_from_page(page):
    """Le moteur d'extraction robuste de la V10.6"""
    try:
        page.wait_for_selector('div[data-testid*="item"]', timeout=10000)
        return page.evaluate("""
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
                        
                        // Vendeur (important pour Signature)
                        const sellerEl = el.querySelector('h4[class*="Text"], [class*="seller"], [data-testid*="seller-name"]');
                        const seller = sellerEl ? sellerEl.innerText.trim() : "Inconnu";
                        
                        let rawTitle = link.getAttribute('title') || '';
                        let price = 'N/A';
                        let size = 'N/A';
                        let brand = 'N/A';
                        let status = 'Non spécifié';
                        let title = rawTitle;

                        if (rawTitle.includes('marque:') || rawTitle.includes('taille:')) {
                            title = rawTitle.split(',')[0].trim();
                            const bm = rawTitle.match(/marque:\\s*([^,]+)/i); if (bm) brand = bm[1].trim();
                            const sm = rawTitle.match(/taille:\\s*([^,]+)/i); if (sm) size = sm[1].trim();
                            const stm = rawTitle.match(/état:\\s*([^,]+)/i); if (stm) status = stm[1].trim();
                        }
                        
                        const texts = Array.from(el.querySelectorAll('p, h3, h4, span, div')).map(e => e.innerText.trim()).filter(t => t);
                        price = texts.find(t => t.includes('€') || t.includes('$')) || 'N/A';
                        
                        if (size === 'N/A') {
                            const sizeRegex = /^(XS|S|M|L|XL|XXL|\\d{2,3}|Unique)$/i;
                            size = texts.find(t => sizeRegex.test(t) && !t.includes('€')) || 'N/A';
                        }

                        if (!title || title.length < 3) title = 'Maillot ASSE';
                        const photo = el.querySelector('img')?.src || '';
                        
                        items.push({
                            id: itemId, title: title, price: price, size: size,
                            brand: brand, status: status, url: url, photo: photo, seller: seller,
                            signature: seller + "_" + title + "_" + price
                        });
                    } catch (e) {}
                });
                return items;
            }
        """)
    except: return []

def send_discord_alert(context, item):
    if not DISCORD_WEBHOOK_URL: return
    try:
        p = context.new_page()
        d = scrape_item_details(p, item['url'])
        p.close()
        
        f_desc = clean_text(d['description'])
        desc_preview = f_desc[:1000] + "..." if len(f_desc) > 1000 else (f_desc if f_desc else "Pas de description")
        
        # Nettoyage Titre
        c_title = item['title'].split(',')[0].split('·')[0].strip()
        c_title = re.sub(r'\d+[.,]\d+\s*€.*$', '', c_title).strip()
        if not c_title: c_title = "Maillot ASSE"

        # Marque/Taille fusionnée (si possible)
        final_brand = d['brand'] if d['brand'] != 'N/A' else item['brand']
        final_size = d['size'] if d['size'] != 'N/A' else item['size']

        payload = {
            "content": f"@everyone | {c_title}\n💰 {item['price']} | 📏 {final_size} | 🏷️ {final_brand} | 👤 {item['seller']}\n📝 {desc_preview}",
            "embeds": [{
                "title": f"🔔 {c_title}", "url": item['url'], "color": 0x09B83E,
                "description": f"**{item['price']}** | Taille: **{final_size}**\nVendeur: **{item['seller']}**\n\n{f_desc[:300]}...",
                "image": {"url": d['photos'][0] if d['photos'] else (item['photo'] if item['photo'] else "")},
                "footer": {"text": "Vinted Bot • Anti-Repost Actif"},
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }]
        }
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        log(f"✅ Alerte envoyée: {item['title']} (#{item['id']})")
    except Exception as e: log(f"❌ Erreur Alert: {e}")

def watchdog_handler(signum, frame):
    log("🚨 WATCHDOG ! Redémarrage..."); os._exit(1)

def run_bot():
    log("🚀 Démarrage SNIPER V11.21 (Anti-Repost + Fix Boucle)")
    
    # Init
    last_id = load_last_seen_id()
    sent_signatures = set(load_json(SIGNATURES_FILE, []))
    
    seen_ids = set()
    initialized_queries = set()
    last_green_check = 0
    last_secondary_check = 0
    
    is_initial_run = (last_id == 0)
    log(f"🔄 Reprise d'activité (Dernier ID : {last_id})")

    while True:
        try:
            gc.collect()
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'])
                context = browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    viewport={'width': 1280, 'height': 720},
                    locale='fr-FR'
                )
                
                def block(route):
                    if route.request.resource_type in ["image", "stylesheet", "font", "media"]: route.abort()
                    else: route.continue_()
                context.route("**/*", block)

                now = time.time()
                queries = [(q, None) for q in PRIORITY_QUERIES]
                if now - last_green_check > 300:
                    queries += [(q, 10) for q in PRIORITY_QUERIES]; last_green_check = now
                if now - last_secondary_check > 1200:
                    queries += [(q, None) for q in SECONDARY_QUERIES]; last_secondary_check = now

                log(f"\n🚀 "+ "="*40)
                log(f"⚡ Scan : {len(queries)} requêtes")
                signal.signal(signal.SIGALRM, watchdog_handler); signal.alarm(300)

                temp_last_id = last_id # On stocke le max du cycle ici

                for q, c in queries:
                    q_key = f"{q}_{c}"
                    try:
                        log(f"🔎 Check: '{q}'{' [VERT]' if c else ''}")
                        page = context.new_page()
                        page.goto(get_search_url(q, c), wait_until="domcontentloaded", timeout=25000)
                        items = extract_items_from_page(page)
                        
                        if items: log(f"   ∟ {len(items)} articles trouvés")
                        
                        is_new_query = q_key not in initialized_queries
                        for it in items:
                            if it['id'] in seen_ids: continue
                            seen_ids.add(it['id'])
                            
                            if it['id'] > last_id:
                                # Update global max (mais sans casser la boucle)
                                if it['id'] > temp_last_id: temp_last_id = it['id']

                                # VERIFICATION SIGNATURE
                                sig = it['signature']
                                if sig in sent_signatures:
                                    continue
                                
                                # FILTRES CLUB (V11.16+)
                                low_t = it['title'].lower()
                                team_kw = ["asse", "saint etienne", "saint-etienne", "st etienne", "st-etienne", "sainté", "sainte", "as st", "as saint", "vert"]
                                wear_kw = ["maillot", "jersey", "maglia", "camiseta", "trikot", "ensemble", "reproduction"]
                                
                                if any(k in low_t for k in team_kw) and (any(k in low_t for k in wear_kw) or c == 10):
                                    # Alerte seulement si ce n'est pas le tour de chauffe
                                    if not (is_initial_run and is_new_query):
                                        send_discord_alert(context, it)
                                        sent_signatures.add(sig)
                                        # Gestion taille signatures (10000 max)
                                        if len(sent_signatures) > 10000:
                                            sent_signatures.remove(next(iter(sent_signatures)))
                                        save_json(SIGNATURES_FILE, list(sent_signatures))
                        
                        initialized_queries.add(q_key)
                        page.close()
                    except Exception as e: log(f"⚠️ Erreur {q}: {e}")

                browser.close()
                signal.alarm(0)
                
                # Mise à jour finale du last_id
                if temp_last_id > last_id:
                    last_id = temp_last_id
                    with open(STATE_FILE, "w") as f: f.write(str(last_id))

                # Nettoyage cache IDs
                if len(seen_ids) > 2000:
                    ids_sorted = sorted(list(seen_ids), reverse=True)
                    seen_ids = set(ids_sorted[:1500])

                log(f"⏳ Cycle terminé. Repos 10s...")
                time.sleep(10)

        except Exception as e:
            log(f"🚨 Bug global : {e}"); time.sleep(20)

if __name__ == "__main__":
    run_bot()
