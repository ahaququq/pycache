#!/usr/bin/env python3
"""Test the download buttons with Chromium headless - full flow test."""
import sys
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

CHROMIUM_BIN = "/usr/bin/chromium"
CHROMEDRIVER_BIN = "/usr/bin/chromedriver"

def main():
    options = Options()
    options.binary_location = CHROMIUM_BIN
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--user-data-dir=/tmp/chromium-test")
    
    service = Service(CHROMEDRIVER_BIN)
    driver = None
    
    try:
        print("Starting Chromium...")
        driver = webdriver.Chrome(service=service, options=options)
        
        # Test full download flow on /info/by-path
        print("\n=== Testing full download flow on /info/by-path ===")
        driver.get("http://localhost/info/by-path")
        time.sleep(3)
        
        # Find a download button for a file that's not cached
        download_buttons = driver.find_elements(By.CSS_SELECTOR, 'button[data-action="download"]')
        print(f"\nFound {len(download_buttons)} download buttons")
        
        if download_buttons:
            btn = download_buttons[0]
            path = btn.get_attribute('data-path')
            print(f"Clicking download for: {path}")
            
            # Click the button
            btn.click()
            print("Clicked download button")
            
            # Wait for notification to appear and track progress
            for i in range(15):  # Wait up to 15 seconds
                time.sleep(1)
                notifications = driver.find_elements(By.CSS_SELECTOR, '.download-notification')
                if notifications:
                    n = notifications[0]
                    classes = n.get_attribute('class') or ''
                    text = n.text[:150]
                    print(f"  [{i+1}s] Notification: {classes} - {text}")
                    
                    if 'completed' in classes or 'failed' in classes:
                        print(f"  Download finished! Final state: {classes}")
                        break
                else:
                    print(f"  [{i+1}s] No notification yet...")
            
            # Check for page reload (table should refresh)
            time.sleep(2)
            print("\nDownload test completed!")
        
        # Test /info/by-source/1 page
        print("\n=== Testing /info/by-source/1 page ===")
        driver.get("http://localhost/info/by-source/1")
        time.sleep(2)
        
        html = driver.page_source
        print(f"Has download buttons: {'data-action=\"download\"' in html}")
        print(f"Has notification container: {'notification-container' in html}")
        
        # Find download buttons on by_source_detail
        download_buttons = driver.find_elements(By.CSS_SELECTOR, 'button[data-action="download"]')
        print(f"Found {len(download_buttons)} download buttons on by_source_detail")
        
        if download_buttons:
            btn = download_buttons[0]
            path = btn.get_attribute('data-path')
            print(f"First button path: {path}")
            
        # Check console logs
        logs = driver.get_log("browser")
        print(f"\nConsole logs ({len(logs)}):")
        for log in logs[-10:]:
            print(f"  [{log['level']}] {log['message'][:200]}")
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if driver:
            driver.quit()
        print("\nDone.")

if __name__ == "__main__":
    main()