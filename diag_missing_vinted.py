
import time
from playwright.sync_api import sync_playwright

SEARCH_TEXT = "Maillot Asse"
SEARCH_URL = f"https://www.vinted.fr/catalog?search_text={SEARCH_TEXT.replace(' ', '+')}&order=newest_first"

def extract_items_from_page(page):
    try:
        page.wait_for_selector('div[data-testid*="item"]', timeout=10000)
        time.sleep(2)
        
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
                        
                        items.push({
                            id: itemId,
                            title: rawTitle,
                            url: url
                        });
                    } catch (e) {}
                });
                return items;
            }
        """)
        return items
    except Exception as e:
        print(f"Error extraction: {e}")
        return []

def run_test():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = context.new_page()
        
        print(f"Checking {SEARCH_URL}")
        page.goto(SEARCH_URL, wait_until='domcontentloaded')
        
        items = extract_items_from_page(page)
        print(f"Found {len(items)} items.")
        
        target_id = 8498358511
        found_target = False
        
        for item in items:
            title_low = item.get('title', '').lower()
            synonyms = ["maillot", "jersey", "maglia", "camiseta", "ensemble", "trikot"]
            has_item_kw = any(s in title_low for s in synonyms)
            has_team = any(x in title_low for x in ["asse", "saint etienne", "saint-etienne", "st etienne", "st-etienne", "saint étienne", "saint-étienne", "st étienne", "st-étienne", "sainté"])
            
            is_match = has_item_kw and has_team
            
            if item['id'] == target_id:
                found_target = True
                print(f"🎯 TARGET FOUND: ID={item['id']} Title='{item['title']}' Match={is_match}")
                print(f"   Keywords: has_item_kw={has_item_kw}, has_team={has_team}")
            elif is_match:
                print(f"✨ Other match: ID={item['id']} Title='{item['title']}'")
        
        if not found_target:
            print("❌ Target not found in results.")
            for i, it in enumerate(items[:5]):
                print(f"  {i}: ID={it['id']} Title='{it['title']}'")
                
        browser.close()

if __name__ == "__main__":
    run_test()
