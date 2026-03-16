import os
import time
import requests
from datetime import datetime
from playwright.sync_api import sync_playwright

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
# On ne touche pas au vrai fichier d'état pour ne pas corrompre le bot principal
VFA_URL = "https://www.vintagefootballarea.com/collections/asse?sort_by=created-descending"

def log(message):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] [TEST-VFA] {message}", flush=True)

def send_vfa_discord_alert(item):
    """Envoie une alerte pour un article Vintage Football Area"""
    if not DISCORD_WEBHOOK_URL:
        log("⚠️ Pas de Webhook Discord, l'alerte ne sera pas envoyée.")
        return

    embed = {
        "title": f"🆕 {item['title']} - Vintage Football Area",
        "url": item['url'],
        "description": f"**Prix: {item['price']}**\n\n[TEST] Nouveauté détectée sur Vintage Football Area !",
        "color": 0x008000,
        "image": {"url": item['image']},
        "footer": {"text": f"VFA Bot Test • ID: {item['id']}"},
        "timestamp": datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
    }

    payload = {
        "content": f"📢 [TEST] Nouveau maillot ASSE dispo sur Vintage Football Area !\n{item['title']}",
        "embeds": [embed],
        "username": "Vintage Football Bot",
        "avatar_url": "https://www.vintagefootballarea.com/cdn/shop/files/favicon-32x32_32x32.png"
    }
    
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        log(f"✅ Alerte VFA envoyée: {item['title']}")
    except Exception as e:
        log(f"❌ Erreur envoi Discord VFA: {e}")

def run_test():
    log(f"🚀 Lancement test unitaire VFA sur : {VFA_URL}")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = context.new_page()
        
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
                # On prend le tout premier (le plus récent)
                target = items[0]
                log(f"🎯 Article cible détecté : {target['title']} (ID: {target['id']})")
                send_vfa_discord_alert(target)
            else:
                log("❌ Aucun article trouvé sur la page.")
                
        except Exception as e:
            log(f"❌ Erreur pendant le test : {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    run_test()
