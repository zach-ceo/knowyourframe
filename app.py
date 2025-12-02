#!/usr/bin/env python3

"""
Tekken 8 Frame Data Quiz - Flask Backend
Scrapes data on startup and caches to JSON file
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import json
import time
import re
import threading
import os
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service

app = Flask(__name__)
CORS(app)

CHARACTERS = [
    'alisa', 'anna', 'armor-king', 'asuka', 'azucena', 'bryan', 'claudio',
    'clive', 'devil-jin', 'dragunov', 'eddy', 'fahkumram', 'feng', 'heihachi',
    'hwoarang', 'jack-8', 'jin', 'jun', 'kazuya', 'king', 'kuma', 'lars',
    'law', 'lee', 'leo', 'leroy', 'lidia', 'lili', 'nina', 'panda', 'paul',
    'raven', 'reina', 'shaheen', 'steve', 'victor', 'xiaoyu', 'yoshimitsu', 'zafina'
]

CACHE_FILE = 'moves_cache.json'
CACHE_METADATA = 'cache_metadata.json'

# Global state
cache_data = {
    'moves': [],
    'last_updated': None,
    'is_scraping': False,
    'progress': 0,
    'current_character': ''
}


def load_cache():
    """Load cached move data from file"""
    global cache_data
    
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r') as f:
                data = json.load(f)
                if isinstance(data, list):
                    cache_data['moves'] = data
                elif isinstance(data, dict) and 'moves' in data:
                    cache_data['moves'] = data['moves']
                else:
                    cache_data['moves'] = []
            
            if os.path.exists(CACHE_METADATA):
                with open(CACHE_METADATA, 'r') as f:
                    metadata = json.load(f)
                    cache_data['last_updated'] = metadata.get('last_updated')
            
            print(f"✓ Loaded {len(cache_data['moves'])} moves from cache")
            return True
        except Exception as e:
            print(f"✗ Error loading cache: {e}")
            return False
    return False


def save_cache():
    """Save move data to cache file"""
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump(cache_data['moves'], f, indent=2)
        
        metadata = {
            'last_updated': datetime.now().isoformat(),
            'total_moves': len(cache_data['moves']),
            'characters': len(set(m['character'] for m in cache_data['moves']))
        }
        with open(CACHE_METADATA, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        cache_data['last_updated'] = metadata['last_updated']
        print(f"✓ Saved {len(cache_data['moves'])} moves to cache")
        return True
    except Exception as e:
        print(f"✗ Error saving cache: {e}")
        return False


def create_driver():
    """Create a Chrome WebDriver"""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        return driver
    except Exception as e:
        print(f"✗ Error creating WebDriver: {e}")
        return None


def extract_moves_from_page(driver, character):
    """Extract moves from current page"""
    moves = []
    
    try:
        time.sleep(0.5)
        move_divs = driver.find_elements(By.XPATH, "//div[contains(@class, 'move')]")
        
        for move_div in move_divs:
            try:
                text = move_div.text.strip()
                if not text:
                    continue
                
                lines = text.split('\n')
                if len(lines) < 2:
                    continue
                
                move_notation = lines[0].strip()
                
                on_block = 0
                on_hit = 0
                move_name = move_notation
                frame_data = []
                
                for line in lines:
                    line = line.strip()
                    if re.match(r'^[+-]\d+$', line):
                        frame_data.append(int(line))
                
                if len(frame_data) >= 2:
                    on_block = frame_data[-2]
                    on_hit = frame_data[-1]
                
                for line in lines[1:]:
                    if line and not re.match(r'^[+-]?\d+', line) and len(line) > 1:
                        move_name = line
                        break
                
                video_url = ""
                try:
                    video_elem = move_div.find_element(By.TAG_NAME, "video")
                    video_url = video_elem.get_attribute("src")
                except:
                    pass
                
                if not video_url:
                    video_url = f"https://okizeme.b-cdn.net/{character}/{move_notation.replace('/', '').replace('+', '%2B')}.mp4"
                
                move = {
                    "character": character.replace('-', ' ').title(),
                    "move": move_notation,
                    "name": move_name[:50],
                    "onBlock": on_block,
                    "onHit": on_hit,
                    "videoUrl": video_url
                }
                
                moves.append(move)
            except Exception as e:
                continue
        
        return moves
    except Exception as e:
        return moves


def scrape_character_all_pages(driver, character):
    """Scrape all pages for a character"""
    all_moves = []
    seen_moves = set()
    page = 1
    consecutive_no_new_moves = 0
    last_page_count = 0
    
    while page <= 100:
        try:
            url = f"https://okizeme.gg/database/{character}?page={page}"
            driver.get(url)
            time.sleep(0.6)
            
            move_divs = driver.find_elements(By.XPATH, "//div[contains(@class, 'move')]")
            
            if not move_divs:
                break
            
            moves = extract_moves_from_page(driver, character)
            
            if not moves:
                break
            
            new_moves_this_page = 0
            for move in moves:
                move_key = (move['move'], move['onBlock'], move['onHit'])
                if move_key not in seen_moves:
                    seen_moves.add(move_key)
                    all_moves.append(move)
                    new_moves_this_page += 1
            
            if new_moves_this_page == 0 and len(moves) == last_page_count:
                consecutive_no_new_moves += 1
                if consecutive_no_new_moves >= 2:
                    break
            else:
                consecutive_no_new_moves = 0
            
            last_page_count = len(moves)
            page += 1
            time.sleep(0.2)
        except Exception as e:
            print(f"  Error on page {page}: {e}")
            break
    
    return all_moves


def scrape_all_characters_background():
    """Background task to scrape all characters"""
    global cache_data
    
    cache_data['is_scraping'] = True
    cache_data['progress'] = 0
    cache_data['moves'] = []
    
    driver = create_driver()
    if not driver:
        cache_data['is_scraping'] = False
        return
    
    try:
        for idx, character in enumerate(CHARACTERS):
            cache_data['current_character'] = character
            cache_data['progress'] = int((idx / len(CHARACTERS)) * 100)
            
            print(f"[{idx+1}/{len(CHARACTERS)}] Scraping {character}...")
            moves = scrape_character_all_pages(driver, character)
            
            if moves:
                cache_data['moves'].extend(moves)
                print(f"  → Found {len(moves)} unique moves")
            
            time.sleep(0.3)
    
    finally:
        driver.quit()
        save_cache()
        cache_data['is_scraping'] = False
        cache_data['progress'] = 100
        cache_data['current_character'] = ''


@app.route('/api/characters', methods=['GET'])
def get_characters():
    """Get list of available characters"""
    return jsonify({'characters': CHARACTERS})


@app.route('/api/moves/<character>', methods=['GET'])
def get_moves_for_character(character):
    """Get moves for a specific character from cache"""
    try:
        print(f"\n{'='*60}")
        print(f"REQUEST RECEIVED for character: {character}")
        print(f"Raw character param: '{character}'")
        
        character_display = character.replace('-', ' ').title()
        print(f"Converted to: '{character_display}'")
        
        available_chars = set(m['character'] for m in cache_data['moves'])
        print(f"Available in cache: {available_chars}")
        
        character_moves = [m for m in cache_data['moves'] if m['character'] == character_display]
        print(f"Found {len(character_moves)} moves")
        print(f"{'='*60}\n")
        
        if not character_moves:
            return jsonify({'error': 'Character not found or no moves cached'}), 404
        
        return jsonify({
            'character': character_display,
            'moves': character_moves,
            'total': len(character_moves)
        })
    except Exception as e:
        print(f"ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/all-moves', methods=['GET'])
def get_all_moves():
    """Get all cached moves"""
    if not cache_data['moves']:
        return jsonify({'error': 'No moves cached'}), 404
    
    return jsonify({
        'moves': cache_data['moves'],
        'total': len(cache_data['moves']),
        'characters': len(set(m['character'] for m in cache_data['moves'])),
        'last_updated': cache_data['last_updated']
    })


@app.route('/api/cache-status', methods=['GET'])
def get_cache_status():
    """Get cache status"""
    return jsonify({
        'is_scraping': cache_data['is_scraping'],
        'progress': cache_data['progress'],
        'current_character': cache_data['current_character'],
        'total_moves': len(cache_data['moves']),
        'last_updated': cache_data['last_updated'],
        'characters_count': len(set(m['character'] for m in cache_data['moves']))
    })


@app.route('/api/rescrape', methods=['POST'])
def rescrape():
    """Trigger a full rescrape of all characters"""
    if cache_data['is_scraping']:
        return jsonify({'error': 'Already scraping'}), 400
    
    thread = threading.Thread(target=scrape_all_characters_background)
    thread.daemon = True
    thread.start()
    
    return jsonify({'status': 'Rescraping started'})


@app.before_request
def before_request():
    """Called before each request"""
    pass


if __name__ == '__main__':
    print("=" * 60)
    print("🥊 Tekken 8 Frame Data Quiz - Backend")
    print("=" * 60)
    
    if load_cache() and len(cache_data['moves']) > 0:
        print(f"✓ Ready with {len(cache_data['moves'])} cached moves\n")
    else:
        print("\n⚠️  No cache found or cache is empty. Starting initial scrape...")
        print("This will take several minutes on first run.\n")
        scrape_all_characters_background()
    
    print("Endpoints:")
    print("  GET  /api/characters         - List all characters")
    print("  GET  /api/moves/character>  - Get moves for character")
    print("  GET  /api/all-moves          - Get all cached moves")
    print("  GET  /api/cache-status       - Get cache status")
    print("  POST /api/rescrape           - Trigger full rescrape")
    print("\nRunning on http://0.0.0.0:5000\n")
    
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)

