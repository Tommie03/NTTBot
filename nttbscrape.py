#!/usr/bin/env python3
"""
Improved NTTB Tournament Scraper
Handles cookie banners properly and extracts complete tournament data
"""

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, WebDriverException
import time
import json
import sqlite3
from datetime import datetime, timedelta
import os
import logging
import hashlib
import re
import argparse

# Flask imports (optional for API mode)
try:
    from flask import Flask, jsonify, render_template_string
    import schedule
    import threading
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False

# Set up logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('nttb_scraper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class NTTBTournamentScraper:
    def __init__(self, db_path='tournaments.db'):
        self.base_url = "https://nttb.toernooi.nl"
        self.db_path = db_path
        self.setup_database()
        
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'nl-NL,nl;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
        }
        
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.tournaments_data = []

    def setup_database(self):
        """Create database tables for storing tournament data"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tournaments (
                id TEXT PRIMARY KEY,
                tournament_id TEXT,
                name TEXT NOT NULL,
                location TEXT,
                date TEXT,
                start_date TEXT,
                end_date TEXT,
                categories TEXT,
                registration_available BOOLEAN,
                registration_url TEXT,
                registration_deadline TEXT,
                registration_status TEXT,
                tournament_url TEXT,
                participant_count INTEGER,
                entry_fee TEXT,
                contact_info TEXT,
                source TEXT,
                extraction_method TEXT,
                raw_data TEXT,
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                hash TEXT,
                is_active BOOLEAN DEFAULT 1
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS scrape_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                tournaments_found INTEGER,
                status TEXT,
                error_message TEXT
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("Database setup completed")

    def scrape_tournaments(self):
        """Main scraping method - uses Selenium for reliable cookie handling"""
        logger.info("Starting tournament scrape...")
        
        try:
            # Use Selenium exclusively - handles cookies and dynamic content
            if self._scrape_with_selenium():
                tournaments = self.tournaments_data
                saved_count = self._save_tournaments_to_db(tournaments)
                self._log_scrape_attempt(saved_count, "success", "Used selenium method")
                logger.info(f"Successfully scraped and saved {saved_count} tournaments")
                return True
            else:
                logger.error("Selenium scraping failed")
                self._log_scrape_attempt(0, "failed", "Selenium failed")
                return False
            
        except Exception as e:
            error_msg = f"Scraping error: {str(e)}"
            logger.error(error_msg)
            self._log_scrape_attempt(0, "error", error_msg)
            return False

    def _scrape_with_selenium(self):
        """Scrape using Selenium with proper cookie handling"""
        logger.info("Scraping with Selenium...")
        
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument(f'--user-agent={self.headers["User-Agent"]}')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        
        driver = None
        all_tournaments = []
        
        try:
            driver = webdriver.Chrome(options=chrome_options)
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            # Load base page
            logger.info(f"Loading: {self.base_url}")
            driver.get(self.base_url)
            time.sleep(3)
            
            # Handle cookie banner FIRST
            if self._handle_cookie_banner(driver):
                logger.info("Cookie banner handled successfully")
                time.sleep(2)  # Wait for page to refresh after accepting cookies
            
            # Now scrape upcoming tournaments
            logger.info("Navigating to upcoming tournaments...")
            upcoming_tournaments = self._scrape_upcoming_tab(driver)
            if upcoming_tournaments:
                all_tournaments.extend(upcoming_tournaments)
            
            # Scrape recent tournaments
            logger.info("Navigating to recent tournaments...")
            recent_tournaments = self._scrape_recent_tab(driver)
            if recent_tournaments:
                all_tournaments.extend(recent_tournaments)
            
            if all_tournaments:
                unique_tournaments = self._remove_duplicate_tournaments(all_tournaments)
                self.tournaments_data = unique_tournaments
                logger.info(f"Total unique tournaments: {len(unique_tournaments)}")
                return True
            else:
                logger.error("No tournaments found")
                # Save debug HTML
                with open('debug_page.html', 'w', encoding='utf-8') as f:
                    f.write(driver.page_source)
                logger.info("Saved debug HTML to debug_page.html")
                return False
                
        except WebDriverException as e:
            logger.error(f"Selenium error: {e}")
            return False
        finally:
            if driver:
                driver.quit()
    
    def _handle_cookie_banner(self, driver):
        """Handle cookie banner with multiple strategies"""
        logger.info("Looking for cookie banner...")
        
        # Wait a moment for banner to appear
        time.sleep(2)
        
        # Try different cookie accept button selectors
        accept_selectors = [
            # Cookiebot (common on Dutch sites)
            "//a[@id='CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll']",
            "//a[@id='CybotCookiebotDialogBodyButtonAccept']",
            "//button[@id='CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll']",
            "//button[@id='CybotCookiebotDialogBodyButtonAccept']",
            
            # Generic selectors
            "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'accept')]",
            "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'accepteren')]",
            "//a[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'accept')]",
            "//a[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'accepteren')]",
            
            # By class
            "//button[contains(@class, 'accept')]",
            "//a[contains(@class, 'accept')]",
        ]
        
        for selector in accept_selectors:
            try:
                element = WebDriverWait(driver, 3).until(
                    EC.element_to_be_clickable((By.XPATH, selector))
                )
                
                # Scroll into view and click
                driver.execute_script("arguments[0].scrollIntoView(true);", element)
                time.sleep(0.5)
                element.click()
                
                logger.info(f"Clicked cookie accept button with selector: {selector}")
                return True
                
            except TimeoutException:
                continue
            except Exception as e:
                logger.debug(f"Failed with selector {selector}: {e}")
                continue
        
        logger.warning("No cookie banner found or could not click accept button")
        return False
    
    def _scrape_upcoming_tab(self, driver):
        """Scrape upcoming tournaments tab"""
        try:
            # Try to find and click upcoming tab
            tab_selectors = [
                "//a[contains(@href, '#TabUpcoming')]",
                "//button[contains(text(), 'Upcoming')]",
                "//a[contains(text(), 'Komende')]",
            ]
            
            for selector in tab_selectors:
                try:
                    tab = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.XPATH, selector))
                    )
                    tab.click()
                    logger.info("Clicked upcoming tab")
                    time.sleep(3)
                    break
                except:
                    continue
            
            # Scroll to load all content
            self._scroll_to_load_all(driver)
            
            # Parse tournaments
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            tournaments = self._parse_tournaments(soup, "upcoming")
            logger.info(f"Found {len(tournaments)} upcoming tournaments")
            return tournaments
            
        except Exception as e:
            logger.error(f"Error scraping upcoming tab: {e}")
            return []
    
    def _scrape_recent_tab(self, driver):
        """Scrape recent tournaments tab"""
        try:
            # Try to find and click recent tab
            tab_selectors = [
                "//a[contains(@href, '#TabRecent')]",
                "//button[contains(text(), 'Recent')]",
                "//a[contains(text(), 'Recente')]",
            ]
            
            for selector in tab_selectors:
                try:
                    tab = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.XPATH, selector))
                    )
                    tab.click()
                    logger.info("Clicked recent tab")
                    time.sleep(3)
                    break
                except:
                    continue
            
            # Scroll to load all content
            self._scroll_to_load_all(driver)
            
            # Parse tournaments
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            tournaments = self._parse_tournaments(soup, "recent")
            logger.info(f"Found {len(tournaments)} recent tournaments")
            return tournaments
            
        except Exception as e:
            logger.error(f"Error scraping recent tab: {e}")
            return []
    
    def _scroll_to_load_all(self, driver):
        """Scroll page to load all lazy-loaded content"""
        logger.info("Scrolling to load all content...")
        
        last_height = driver.execute_script("return document.body.scrollHeight")
        scroll_attempts = 0
        max_scrolls = 5
        
        while scroll_attempts < max_scrolls:
            # Scroll to bottom
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            
            # Check if new content loaded
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            
            last_height = new_height
            scroll_attempts += 1
        
        logger.info(f"Finished scrolling ({scroll_attempts} times)")

    def _parse_tournaments(self, soup, source):
        """Parse tournament data from HTML with improved selectors"""
        tournaments = []
        
        # CRITICAL: Filter out cookie consent elements
        # Find all list items but exclude those with cookie-related content
        all_list_items = soup.find_all('li', class_='list__item')
        
        tournament_elements = [
            elem for elem in all_list_items
            if elem.find('h4', class_='media__title')  # Must have tournament title
            and not elem.find('input', type='checkbox')  # No checkboxes (cookie consent)
            and not elem.find('div', class_='ad')  # No ads
            and 'cookie' not in elem.get_text().lower()[:100]  # No "cookie" in first part of text
        ]
        
        logger.info(f"Found {len(tournament_elements)} valid tournament elements (filtered from {len(all_list_items)} total)")
        
        for i, element in enumerate(tournament_elements):
            try:
                tournament_data = self._extract_tournament_details(element, i, source)
                if tournament_data and tournament_data.get('name'):
                    tournaments.append(tournament_data)
            except Exception as e:
                logger.warning(f"Error parsing tournament {i}: {e}")
                continue
        
        logger.info(f"Successfully parsed {len(tournaments)} tournaments from {source}")
        return tournaments

    def _extract_tournament_details(self, element, index, source):
        """Extract detailed tournament information with improved extraction"""
        tournament = {
            'id': f'tournament_{source}_{index}_{int(time.time())}',
            'extraction_method': 'nttb_scraper_v2',
            'timestamp': datetime.now().isoformat(),
            'source': source
        }
        
        try:
            # Extract name and URL
            title_element = element.find('h4', class_='media__title')
            if title_element:
                # Get tournament name
                name_span = title_element.find('span', class_='nav-link__value')
                if name_span:
                    tournament['name'] = name_span.get_text(strip=True)
                
                # Get tournament URL
                title_link = title_element.find('a', href=True)
                if title_link:
                    href = title_link['href']
                    if href.startswith('/'):
                        tournament['tournament_url'] = self.base_url + href
                    else:
                        tournament['tournament_url'] = href
                    
                    if 'id=' in href:
                        tournament['tournament_id'] = href.split('id=')[1].split('&')[0]
            
            # Extract location and date from subheadings
            subheadings = element.find_all('small', class_='media__subheading')
            
            if len(subheadings) >= 1:
                # First subheading contains location
                location_span = subheadings[0].find('span', class_='nav-link__value')
                if location_span:
                    location_text = location_span.get_text(strip=True)
                    
                    # Parse location from text like "NTTB | Rotterdam"
                    if '|' in location_text:
                        tournament['location'] = location_text.split('|')[1].strip()
                    else:
                        tournament['location'] = location_text
            
            if len(subheadings) >= 2:
                # Second subheading contains date
                date_subheading = subheadings[1]
                time_elements = date_subheading.find_all('time', datetime=True)
                
                if len(time_elements) == 1:
                    tournament['date'] = time_elements[0].get_text(strip=True)
                    tournament['start_date'] = time_elements[0].get('datetime')
                elif len(time_elements) >= 2:
                    date1 = time_elements[0].get_text(strip=True)
                    date2 = time_elements[1].get_text(strip=True)
                    tournament['date'] = f"{date1} t/m {date2}"
                    tournament['start_date'] = time_elements[0].get('datetime')
                    tournament['end_date'] = time_elements[1].get('datetime')
            
            # Extract categories
            categories = []
            tag_lists = element.find_all('ul', class_='list--inline')
            for tag_list in tag_lists:
                tags = tag_list.find_all('span', class_=['tag', 'tag-duo'])
                for tag in tags:
                    tag_text = tag.get_text(strip=True)
                    if tag_text and len(tag_text) > 1:
                        categories.append(tag_text)
            
            tournament['categories'] = json.dumps(categories) if categories else None
            
            # Extract registration info
            self._extract_registration_info(element, tournament)
            
            # Create hash
            hash_string = f"{tournament.get('name', '')}{tournament.get('start_date', '')}{tournament.get('location', '')}"
            tournament['hash'] = hashlib.md5(hash_string.encode()).hexdigest()
            
            return tournament
            
        except Exception as e:
            logger.error(f"Error extracting tournament details: {e}")
            return None

    def _extract_registration_info(self, element, tournament):
        """Extract registration information"""
        tournament['registration_available'] = False
        
        # Look for registration links
        reg_links = element.find_all('a', href=True)
        for link in reg_links:
            href = link.get('href', '')
            text = link.get_text().lower()
            
            if any(keyword in text for keyword in ['inschrijv', 'register', 'aanmeld', 'sign up']):
                tournament['registration_available'] = True
                
                if href:
                    if href.startswith('/'):
                        tournament['registration_url'] = self.base_url + href
                    elif href.startswith('http'):
                        tournament['registration_url'] = href
                
                # Check if registration is closed
                if any(closed in text for closed in ['gesloten', 'closed', 'vol', 'full']):
                    tournament['registration_status'] = 'closed'
                    tournament['registration_available'] = False
                
                break

    def _remove_duplicate_tournaments(self, tournaments):
        """Remove duplicate tournaments based on name, date, and location"""
        seen = {}
        unique = []
        
        for tournament in tournaments:
            if not isinstance(tournament, dict) or not tournament.get('name'):
                continue
            
            key = (
                tournament.get('name', '').strip().lower(),
                tournament.get('start_date', '').strip(),
                tournament.get('location', '').strip().lower()
            )
            
            if key not in seen:
                seen[key] = tournament
                unique.append(tournament)
        
        logger.info(f"Removed {len(tournaments) - len(unique)} duplicates")
        return unique

    def _save_tournaments_to_db(self, tournaments):
        """Save tournaments to database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        saved_count = 0
        
        for tournament in tournaments:
            cursor.execute("SELECT id FROM tournaments WHERE hash = ? AND is_active = 1", 
                         (tournament.get('hash'),))
            
            if cursor.fetchone():
                # Update existing
                cursor.execute('''
                    UPDATE tournaments SET 
                    name = ?, location = ?, date = ?, start_date = ?, end_date = ?,
                    categories = ?, registration_available = ?, registration_url = ?,
                    registration_deadline = ?, registration_status = ?, tournament_url = ?,
                    source = ?, extraction_method = ?, scraped_at = CURRENT_TIMESTAMP
                    WHERE hash = ? AND is_active = 1
                ''', (
                    tournament.get('name'), tournament.get('location'), tournament.get('date'),
                    tournament.get('start_date'), tournament.get('end_date'),
                    tournament.get('categories'), tournament.get('registration_available', False),
                    tournament.get('registration_url'), tournament.get('registration_deadline'),
                    tournament.get('registration_status'), tournament.get('tournament_url'),
                    tournament.get('source'), tournament.get('extraction_method'), 
                    tournament.get('hash')
                ))
            else:
                # Insert new
                cursor.execute('''
                    INSERT INTO tournaments 
                    (id, tournament_id, name, location, date, start_date, end_date,
                     categories, registration_available, registration_url, registration_deadline,
                     registration_status, tournament_url, source, extraction_method, hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    tournament.get('id'), tournament.get('tournament_id'), tournament.get('name'),
                    tournament.get('location'), tournament.get('date'), tournament.get('start_date'),
                    tournament.get('end_date'), tournament.get('categories'),
                    tournament.get('registration_available', False), tournament.get('registration_url'),
                    tournament.get('registration_deadline'), tournament.get('registration_status'),
                    tournament.get('tournament_url'), tournament.get('source'),
                    tournament.get('extraction_method'), tournament.get('hash')
                ))
                saved_count += 1
        
        conn.commit()
        conn.close()
        return saved_count

    def _log_scrape_attempt(self, tournaments_found, status, error_message=None):
        """Log scraping attempt"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO scrape_log (tournaments_found, status, error_message)
            VALUES (?, ?, ?)
        ''', (tournaments_found, status, error_message))
        conn.commit()
        conn.close()

    def get_active_tournaments(self):
        """Get all active tournaments from database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, tournament_id, name, location, date, start_date, end_date,
                   categories, registration_available, registration_url,
                   registration_deadline, registration_status, tournament_url,
                   participant_count, entry_fee, contact_info, source, scraped_at
            FROM tournaments 
            WHERE is_active = 1 
            ORDER BY start_date ASC, scraped_at DESC
        ''')
        
        tournaments = []
        for row in cursor.fetchall():
            tournament = {
                'id': row[0], 'tournament_id': row[1], 'name': row[2], 'location': row[3],
                'date': row[4], 'start_date': row[5], 'end_date': row[6],
                'categories': json.loads(row[7]) if row[7] else [],
                'registration_available': bool(row[8]), 'registration_url': row[9],
                'registration_deadline': row[10], 'registration_status': row[11],
                'tournament_url': row[12], 'participant_count': row[13],
                'entry_fee': row[14], 'contact_info': row[15], 'source': row[16],
                'scraped_at': row[17]
            }
            tournaments.append(tournament)
        
        conn.close()
        return tournaments

    def cleanup_old_tournaments(self, days_old=14):
        """Remove old tournaments"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cutoff_date = datetime.now() - timedelta(days=days_old)
        one_week_ago = (datetime.now() - timedelta(days=7)).isoformat()
        
        cursor.execute('''
            UPDATE tournaments 
            SET is_active = 0 
            WHERE scraped_at < ? 
            OR (end_date IS NOT NULL AND end_date < ?)
            OR (start_date IS NOT NULL AND end_date IS NULL AND start_date < ?)
        ''', (cutoff_date.isoformat(), one_week_ago, one_week_ago))
        
        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()
        
        if deleted_count > 0:
            logger.info(f"Marked {deleted_count} old tournaments as inactive")

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='NTTB Tournament Scraper')
    parser.add_argument('--mode', choices=['scrape', 'test'], default='scrape',
                       help='Mode: scrape (save to db) or test (show first 5)')
    args = parser.parse_args()

    scraper = NTTBTournamentScraper()

    if args.mode == 'scrape':
        logger.info("Running tournament scrape...")
        success = scraper.scrape_tournaments()
        
        if success:
            tournaments = scraper.get_active_tournaments()
            print(f"\nSuccessfully scraped {len(tournaments)} tournaments!")
            print(f"Data saved to: {scraper.db_path}")
            
            # Show first 5 as preview
            print("\nFirst 5 tournaments:")
            for t in tournaments[:5]:
                print(f"\n  {t['name']}")
                print(f"  Location: {t['location']}")
                print(f"  Date: {t['date']}")
                if t['registration_available']:
                    print(f"  Registration: OPEN")
        else:
            print("\nScraping failed. Check logs for details.")
            print("Debug HTML saved to debug_page.html")
    
    elif args.mode == 'test':
        logger.info("Running test scrape (showing first 5 tournaments)...")
        success = scraper.scrape_tournaments()
        
        if success and scraper.tournaments_data:
            print(f"\nFound {len(scraper.tournaments_data)} tournaments")
            print("\nFirst 5:")
            for t in scraper.tournaments_data[:5]:
                print(f"\n{t.get('name', 'No name')}")
                print(f"  Location: {t.get('location', 'Unknown')}")
                print(f"  Date: {t.get('date', 'TBD')}")
                print(f"  Categories: {t.get('categories', 'None')}")

if __name__ == '__main__':
    main()