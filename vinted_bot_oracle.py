#!/usr/bin/env python3
"""
Vinted Bot V11.28 - NICKEL STABLE + AUTO-LOCK
- Restauration EXACTE du moteur V10.6 (Descriptions, Photos, Vitesse)
- Système de LOCK pour empêcher les alertes en triple (Un seul bot actif)
- Anti-Repost (Signature Vendeur+Titre+Prix)
"""

import os
import sys
import time
import random
import requests
import signal
import gc
import json
from datetime import datetime
from playwright.sync_api import sync_playwright

# Configuration
PRIORITY_QUERIES = ["Maillot Asse", "Maillot Saint-Etienne", "Maillot St Etienne"]
SECONDARY_QUERIES = ["Jersey Asse", "Jersey Saint-Etienne", "Maglia Asse", "Camiseta Asse", "Ensemble Asse", "Trikot Asse"]
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

STATE_FILE = "last_seen_id.txt"
SIGNATURES_FILE = "sent_signatures.json"
LOCK_FILE = "bot.lock"

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

def save_last_seen_id(item_id):
    with open(STATE_FILE, "w") as f: f.write(str(item_id))

def clean_text(text):
    if not text: return ""
    import re
    text = re.sub(r'(?i)enlevé\s*!?', '', text)
    text = re.sub(r'(?i)nouveau\s*!?', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def scrape_item_details(page, item_url):
    """Moteur détail V10.6 (NICKEL)"""
    try:
        import re
        id_match = re.search(r'/items/(\d+)', item_url)
        item_id = id_match.group(1) if id_match else None
        if not item_id: return {"description": "", "photos": [], "brand": "N/A", "size": "N/A", "status": "N/A"}
        
        page.goto(item_url, wait_until='domcontentloaded', timeout=15000)
        photos = page.evaluate("() => Array.from(document.querySelectorAll('.item-photo--1 img, .item-photos img')).map(img => img.src).filter(src => src)")
        
        api_data = page.evaluate(f"""async () => {{
            try {{
                const r = await fetch('/api/v2/items/{item_id}?localize=false');
                return r.ok ? await r.json() : null;
            }} catch(e) {{ return null; }}
        }}""")
        
        brand, size, status, description = "N/A", "N/A", "N/A", ""
        if api_data and 'item' in api_data:
            it = api_data['item']
            description = it.get('description', '')
            brand = it.get('brand_title', 'N/A')
            size = it.get('size_title', 'N/A')
            status = it.get('status', 'N/A')
        else:
            description = page.evaluate("() => document.querySelector('[itemprop=\"description\"]')?.innerText || ''")
            
        return {"description": description, "photos": list(dict.fromkeys(photos)), "brand": brand, "size": size, "status": status}
    except: return {"description": "", "photos": [], "brand": "N/A", "size": "N/A", "status": "N/A"}

def extract_items_from_page(page):
    """Moteur liste V10.6 (NICKEL)"""
    try:
        page.wait_for_selector('div[data-testid*="item"]', timeout=10000)
        time.sleep(random.uniform(1, 1.5))
        return page.evaluate("""() => {
            const items = [];
            const els = document.querySelectorAll('div[data-testid*="item"], div[class*="feed-grid__item"]');
            els.forEach(el => {
                const a = el.querySelector('a'); if (!a) return;
                const url = a.href; const id = parseInt(url.match(/items\\/(\\d+)/)?.[1] || 0); if (!id) return;
                
                let rawT = a.getAttribute('title') || el.querySelector('img')?.alt || '';
                let price = 'N/A', size = 'N/A', brand = 'N/A', title = rawT;
                
                if (rawT.includes('marque:')) {
                    title = rawT.split(',')[0].trim();
                    const b = rawT.match(/marque:\\s*([^,]+)/i); if (b) brand = b[1].trim();
                    const s = rawT.match(/taille:\\s*([^,]+)/i); if (s) size = s[1].trim();
                }
                const ts = Array.from(el.querySelectorAll('p, h3, h4, span, div')).map(e => e.innerText.trim()).filter(t => t);
                price = ts.find(t => t.includes('€')) || 'N/A';
                if (size === 'N/A') {
                    const r = /^(XS|S|M|L|XL|XXL|\\d{2,3}|Unique)$/i;
                    size = ts.find(t => r.test(t) && !t.includes('€')) || 'N/A';
                }
                
                const sellerEl = el.querySelector('h4, [class*="seller"], [data-testid*="seller-name"]');
                const seller = sellerEl ? sellerEl.innerText.trim() : "Inconnu";

                items.push({ id: id, title: title, price: price, size: size, brand: brand, url: url, photo: el.querySelector('img')?.src || '', seller: seller });
            });
            return items;
        }""")
    except: return []

def send_discord_alert(context, item):
    if not DISCORD_WEBHOOK_URL: return
    try:
        dp = context.new_page(); d = scrape_item_details(dp, item['url']); dp.close()
        final_brand = d['brand'] if d['brand'] != 'N/A' else item['brand']
        final_size = d['size'] if d['size'] != 'N/A' else item['size']
        final_desc = clean_text(d['description'])
        
        # Formatage du message iPhone/Montre
        clean_title = item['title'].split(',')[0].strip()
        desc_preview = final_desc[:1000] + "..." if len(final_desc) > 1000 else (final_desc if final_desc else "Pas de description")

        payload = {
            "content": f"@everyone | {clean_title}\\n💰 {item['price']} | 📏 {final_size} | 👤 {item['seller']}\\n📝 {desc_preview}",
            "avatar_url": "https://images.vinted.net/assets/icon-76x76-precomposed-3e6e4c5f0b8c7e5a5c5e5e5e5e5e5e5e.png",
            "embeds": [{
                "title": f"🔔 {clean_title}", "url": item['url'], "color": 0x09B83E,
                "description": f"**{item['price']}** | Taille: **{final_size}**\\nMarque: **{final_brand}**\\n\\nVendeur: **{item['seller']}**\\n\\n{final_desc[:300]}...",
                "image": {"url": d['photos'][0] if d['photos'] else item['photo']},
                "footer": {"text": f"Vinted Sniper V11.28 • ID: {item['id']}"}, 
                "timestamp": datetime.utcnow().isoformat() + 'Z'
            }]
        }
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10); log(f"✅ Alerte envoyée #{item['id']}")
    except: pass

def watchdog_handler(signum, frame):
    log("🚨 WATCHDOG ! Redémarrage..."); os._exit(1)

def run_bot():
    # --- SÉCURITÉ ANTI-TRIPLE (VERROU) ---
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, "r") as f: pid = int(f.read().strip())
            os.kill(pid, 0) # On vérifie si le bot tourne vraiment
            log("🚫 Instance déjà active. Extinction de celle-ci pour éviter les doublons."); sys.exit(0)
        except: pass
    with open(LOCK_FILE, "w") as f: f.write(str(os.getpid()))

    log("🚀 Restauration V11.28 NICKEL (Stability + Fix Triple)")
    seen_ids = set(); last_green = 0; last_sec = 0; is_warm = True 
    last_id = load_last_seen_id()
    sent_signatures = set(load_json(SIGNATURES_FILE, []))

    try:
        while True:
            try:
                signal.signal(signal.SIGALRM, watchdog_handler); signal.alarm(180)
                with sync_playwright() as p:
                    b = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'])
                    ctx = b.new_context(user_agent='Mozilla/5.0', locale='fr-FR')
                    ctx.route("**/*", lambda r: r.abort() if r.request.resource_type in ["image", "stylesheet", "font", "media"] else r.continue_())
                    
                    now = time.time()
                    q_run = [(q, None) for q in PRIORITY_QUERIES]
                    if (now - last_green) > 300:
                        for q in PRIORITY_QUERIES: q_run.append((q, 10))
                        last_green = now
                    if (now - last_sec) > 1200:
                        for q in SECONDARY_QUERIES: q_run.append((q, None))
                        last_sec = now

                    log(f"⚡ Scan V10.6 Exact : {len(q_run)} requêtes")
                    c_max = last_id
                    for q, col in q_run:
                        try:
                            page = ctx.new_page(); log(f"🔎 Check: {q}")
                            page.goto(f"https://www.vinted.fr/catalog?search_text={q.replace(' ', '+')}&order=newest_first" + (f"&color_ids[]={col}" if col else ""), wait_until='commit', timeout=20000)
                            items = extract_items_from_page(page)
                            for it in items:
                                if it['id'] in seen_ids: continue
                                seen_ids.add(it['id'])
                                if it['id'] > last_id:
                                    if it['id'] > c_max: c_max = it['id']
                                    if not is_warm:
                                        # ANTI-REPOST (Signature)
                                        sig = f"{it['seller']}_{it['title']}_{it['price']}"
                                        if sig in sent_signatures: continue
                                        
                                        tl = it['title'].lower()
                                        if any(x in tl for x in ["asse", "saint etienne", "st etienne", "sainté", "vert"]) or col == 10:
                                            send_discord_alert(ctx, it)
                                            sent_signatures.add(sig)
                                            if len(sent_signatures) > 3000: sent_signatures.remove(next(iter(sent_signatures)))
                                            save_json(SIGNATURES_FILE, list(sent_signatures))
                            page.close()
                        except: pass
                    b.close()
                    if c_max > last_id: last_id = c_max; save_last_seen_id(last_id)
                signal.alarm(0)
            except: signal.alarm(0)
            is_warm = False
            if len(seen_ids) > 2000: seen_ids = set(sorted(list(seen_ids), reverse=True)[:1500])
            log("⏳ Cycle terminé. Repos 10s..."); time.sleep(10)
    finally:
        if os.path.exists(LOCK_FILE): os.remove(LOCK_FILE)

if __name__ == "__main__":
    run_bot()
