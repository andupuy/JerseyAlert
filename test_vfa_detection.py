
import time
from playwright.sync_api import sync_playwright

VFA_URL = "https://www.vintagefootballarea.com/collections/asse?sort_by=created-descending"

def check_vfa_site(page, last_id):
    print(f"🔎 Check VFA: {VFA_URL}")
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
            print(f"Total items found: {len(items)}")
            new_items = [it for it in items if it['id'] > last_id]
            for it in items[:5]:
                print(f"Item on page: ID={it['id']} Title={it['title']}")
            
            if new_items:
                print(f"🆕 {len(new_items)} nouveaux maillots VFA détectés !")
                for it in reversed(new_items):
                    print(f"ALERT: {it['title']} (ID: {it['id']})")
                return max(last_id, max(it['id'] for it in new_items))
            else:
                print("No new items found.")
        return last_id
    except Exception as e:
        print(f"❌ Erreur scraping VFA: {e}")
        return last_id

def run_test():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        
        # Le dernier ID dans le fichier était 9935227683144
        last_id = 9935227683144
        print(f"Running test with last_id = {last_id}")
        check_vfa_site(page, last_id)
        browser.close()

if __name__ == "__main__":
    run_test()
