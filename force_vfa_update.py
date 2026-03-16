
import os
import time
import requests
from datetime import datetime
from playwright.sync_api import sync_playwright

# RÉCUPÉRATION DU WEBHOOK (On cherche partout)
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
VFA_URL = "https://www.vintagefootballarea.com/collections/asse?sort_by=created-descending"
VFA_STATE_FILE = "last_seen_vfa_id.txt"

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")

def send_vfa_discord_alert(item):
    if not DISCORD_WEBHOOK_URL:
        log("⚠️ ERREUR : DISCORD_WEBHOOK_URL non trouvé dans l'environnement.")
        return False

    embed = {
        "title": f"🆕 {item['title']} - Vintage Football Area",
        "url": item['url'],
        "description": f"**Prix: {item['price']}**\n\n[FORCE UPDATE] Nouveauté détectée !",
        "color": 0x008000,
        "image": {"url": item['image']},
        "footer": {"text": f"VFA Bot • ID: {item['id']}"},
        "timestamp": datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
    }

    payload = {
        "content": f"📢 [FORCE] Nouveau maillot ASSE sur Vintage Football Area !\n{item['title']}",
        "embeds": [embed],
        "username": "Vintage Football Bot",
        "avatar_url": "https://www.vintagefootballarea.com/cdn/shop/files/favicon-32x32_32x32.png"
    }
    
    try:
        r = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        if r.status_code == 204 or r.status_code == 200:
            log(f"✅ Alerte envoyée pour : {item['title']}")
            return True
        else:
            log(f"❌ Erreur Discord (Status {r.status_code}): {r.text}")
            return False
    except Exception as e:
        log(f"❌ Erreur envoi Discord : {e}")
        return False

def force_update():
    log("🚀 FORÇAGE DE LA MISE À JOUR VFA...")
    
    if not DISCORD_WEBHOOK_URL:
        log("❌ Impossible de continuer sans Webhook.")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        try:
            # Charger le dernier ID connu
            last_id = 0
            if os.path.exists(VFA_STATE_FILE):
                with open(VFA_STATE_FILE, "r") as f:
                    last_id = int(f.read().strip())
            
            log(f"Dernier ID connu : {last_id}")
            page.goto(VFA_URL, wait_until="domcontentloaded")
            time.sleep(3)
            
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
                    log(f"🔥 {len(new_items)} nouveaux articles à traiter.")
                    # Inverser pour envoyer du plus vieux au plus récent
                    for it in reversed(new_items):
                        success = send_vfa_discord_alert(it)
                        if success:
                            # Mettre à jour le fichier d'état au fur et à mesure
                            with open(VFA_STATE_FILE, "w") as f:
                                f.write(str(it['id']))
                    log("✨ Mise à jour forcée terminée.")
                else:
                    log("✅ Aucun nouvel article trouvé (déjà à jour).")
            else:
                log("❌ Aucun article extrait de la page.")
                
        except Exception as e:
            log(f"❌ Erreur fatale : {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    force_update()
