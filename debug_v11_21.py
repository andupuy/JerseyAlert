import os
import sys
import time
import requests
import re
from playwright.sync_api import sync_playwright

def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}")

def get_search_url(query, color_id=None):
    url = f"https://www.vinted.fr/catalog?search_text={query.replace(' ', '+')}&order=newest_first"
    if color_id: url += f"&color_ids[]={color_id}"
    return url

def extract_items_from_page(page):
    try:
        page.wait_for_selector('div[data-testid*="item"]', timeout=15000)
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
                        const sellerEl = el.querySelector('h4[class*="Text"], [class*="seller"], [data-testid*="seller-name"]');
                        const seller = sellerEl ? sellerEl.innerText.trim() : "Inconnu";
                        let rawTitle = link.getAttribute('title') || '';
                        let title = rawTitle;
                        const texts = Array.from(el.querySelectorAll('p, h3, h4, span, div')).map(e => e.innerText.trim()).filter(t => t);
                        const price = texts.find(t => t.includes('€') || t.includes('$')) || 'N/A';
                        items.push({
                            id: itemId, title: title, price: price, url: url, seller: seller
                        });
                    } catch (e) {}
                });
                return items;
            }
        """)
    except Exception as e:
        log(f"Extraction error: {e}")
        return []

def test_debug():
    query = "Maillot Asse"
    log(f"Testing query: {query}")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        
        page = context.new_page()
        url = get_search_url(query)
        log(f"Going to: {url}")
        
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            log("Page loaded. Inspecting content...")
            
            # Print page title to check for Cloudflare
            log(f"Page Title: {page.title()}")
            
            if "Vinted" not in page.title() and "Catalogue" not in page.title():
                log("⚠️ Possible block or different page title.")
            
            items = extract_items_from_page(page)
            log(f"Found {len(items)} items.")
            
            for it in items[:5]:
                log(f"- [{it['id']}] {it['title']} | {it['price']} | {it['seller']}")
                
                # Check filtering logic
                low_t = it['title'].lower()
                team_kw = ["asse", "saint etienne", "saint-etienne", "st etienne", "st-etienne", "sainté", "sainte", "as st", "as saint", "vert"]
                wear_kw = ["maillot", "jersey", "maglia", "camiseta", "trikot", "ensemble", "reproduction"]
                
                has_team = any(k in low_t for k in team_kw)
                has_wear = any(k in low_t for k in wear_kw)
                
                log(f"  Match Team: {has_team} | Match Wear: {has_wear}")
                
        except Exception as e:
            log(f"Scraping failed: {e}")
            # Save screenshot if it failed
            page.screenshot(path="debug_screenshot.png")
            log("Screenshot saved to debug_screenshot.png")
            with open("debug_page.html", "w", encoding="utf-8") as f:
                f.write(page.content())
            log("HTML saved to debug_page.html")
            
        browser.close()

if __name__ == "__main__":
    test_debug()
