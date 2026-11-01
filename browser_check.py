"""Read a job page with verified TLS using the Playwright WebKit container."""
import json
import sys
from playwright.sync_api import sync_playwright

url = sys.argv[1]
with sync_playwright() as playwright:
    browser = playwright.webkit.launch(headless=True)
    try:
        page = browser.new_page()
        response = page.goto(url, wait_until='domcontentloaded', timeout=25000)
        page.wait_for_timeout(1000)
        body = page.locator('body').inner_text(timeout=10000)
        lowered = body.lower()
        markers = ['job has expired', 'job you are trying to view has expired', 'no longer accepting applications', 'this job is no longer available', 'this vacancy has closed', 'job is no longer available']
        buttons = page.get_by_role('button').all_inner_texts()
        links = page.get_by_role('link').all_inner_texts()
        result = {
            'status': response.status if response else None,
            'url': page.url,
            'title': page.title(),
            'closed_message': next((phrase for phrase in markers if phrase in lowered), None),
            'apply_controls': [label.strip() for label in buttons + links if 'apply' in label.lower()][:8],
            'body_excerpt': ' '.join(body.split())[:350],
        }
        print(json.dumps(result))
    finally:
        browser.close()
