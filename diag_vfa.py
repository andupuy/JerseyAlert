
import os
import time
from playwright.sync_api import sync_playwright

VFA_URL = "https://www.vintagefootballarea.com/collections/asse?sort_by=created-descending"
VFA_STATE_FILE = "last_seen_vfa_id.txt"

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")

def load_last_vfa_id():
    if os.path.exists(VFA_STATE_FILE):
        try:
            with open(VFA_STATE_FILE, "r") as f:
                content = f.read().strip()
                log(f"Loading state from file: '{content}'")
                return int(content)
        except Exception as e:
            log(f"Error loading state: {e}")
    return 0

def check_vfa_site(page, last_id):
    log(f"🔎 Checking VFA: {VFA_URL}")
    log(f"Last ID known: {last_id}")
    try:
        page.goto(VFA_URL, wait_until="domcontentloaded", timeout=30000)
        time.sleep(3) # Wait for JS scripts to run
        
        # Check if products are visible
        count = page.evaluate("() => document.querySelectorAll('.product-block').length")
        log(f"Items found on page: {count}")
        
        items = page.evaluate("""
            () => {
                const results = [];
                const products = document.querySelectorAll('.product-block');
                products.forEach(el => {
                    const id = el.getAttribute('data-product-id');
                    const titleEl = el.querySelector('.title');
                    const priceEl = el.querySelector('.price');
                    
                    if (id && titleEl && priceEl) {
                        results.push({
                            id: parseInt(id),
                            title: titleEl.innerText.trim(),
                            price: priceEl.innerText.trim()
                        });
                    }
                });
                return results;
            }
        """)
        
        if items:
            log(f"Extracted {len(items)} items with data.")
            for it in items[:3]:
                log(f"Item: {it['title']} (ID: {it['id']})")
            
            new_items = [it for it in items if it['id'] > last_id]
            if new_items:
                log(f"🆕 FOUND {len(new_items)} NEW ITEMS!")
                for it in new_items:
                    log(f"MATCH: {it['title']} - ID: {it['id']} - Price: {it['price']}")
                return max(last_id, max(it['id'] for it in new_items))
            else:
                log("No new items (all IDs <= last_id)")
        else:
            log("No items found in extraction (selector issue?)")
            # Debug DOM
            html_snippet = page.evaluate("() => document.querySelector('.collection-matrix')?.innerHTML?.substring(0, 500)")
            log(f"HTML Snippet: {html_snippet}")
            
        return last_id
    except Exception as e:
        log(f"❌ Error during check: {e}")
        return last_id

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = context.new_page()
        
        last_id = load_last_vfa_id()
        new_id = check_vfa_site(page, last_id)
        
        if new_id > last_id:
            log(f"SUCCESS: New ID {new_id} found. Ready to update state file.")
        else:
            log("FINISHED: No updates.")
            
        browser.close()

if __name__ == "__main__":
    run()
