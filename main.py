import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from dotenv import load_dotenv
import os
import random
import logging
import json
import platform
import psutil
import shutil
import tempfile
from signals_parser import parse_signal
# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Load environment variables
load_dotenv()

# Configuration
POCKETOPTION_EMAIL = os.getenv('POCKETOPTION_EMAIL')
POCKETOPTION_PASSWORD = os.getenv('POCKETOPTION_PASSWORD')
TELEGRAM_GROUP_URL = ''
BASE_URL = 'https://pocketoption.com/en'
DEMO_MODE = True
MIN_PAYOUT_PERCENTAGE = 50

# Trading variables
martingale_step = 0
trade_amounts = [1, 2, 4]
svg_icon_clicked = False

def kill_chrome_processes():
    """Kill all running Chrome processes"""
    logging.info("Checking for running Chrome processes...")
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            if 'chrome' in proc.info['name'].lower():
                proc.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    time.sleep(2)

def create_temp_profile_copy(profile_path, profile_dir):
    """Create temporary copy of Chrome profile"""
    temp_dir = os.path.join(tempfile.gettempdir(), f"chrome_profile_{int(time.time())}")
    os.makedirs(temp_dir, exist_ok=True)
    essential_files = ['Cookies', 'Login Data', 'Preferences', 'Web Data']
    for file in essential_files:
        source_file = os.path.join(profile_path, profile_dir, file)
        if os.path.exists(source_file):
            try:
                shutil.copy2(source_file, os.path.join(temp_dir, file))
            except Exception as e:
                logging.warning(f"Could not copy {file}: {e}")
    return temp_dir

def get_chrome_profiles():
    """Get Chrome profiles from system"""
    profiles = []
    if platform.system() == "Windows":
        chrome_path = os.path.join(os.environ["LOCALAPPDATA"], "Google", "Chrome", "User Data")
    elif platform.system() == "Darwin":
        chrome_path = os.path.expanduser("~/Library/Application Support/Google/Chrome")
    else:
        chrome_path = os.path.expanduser("~/.config/google-chrome")
    
    try:
        local_state_path = os.path.join(chrome_path, "Local State")
        if os.path.exists(local_state_path):
            with open(local_state_path, 'r', encoding='utf-8') as f:
                local_state = json.load(f)
                if 'profile' in local_state and 'info_cache' in local_state['profile']:
                    profiles.append({"name": "Default", "path": chrome_path, "profile": "Default"})
                    for profile_name, profile_info in local_state['profile']['info_cache'].items():
                        if profile_name != "Default":
                            profiles.append({
                                "name": profile_info.get('name', profile_name),
                                "path": chrome_path,
                                "profile": profile_name
                            })
        if not profiles:
            for item in os.listdir(chrome_path):
                if item.startswith("Profile ") or item == "Default":
                    profiles.append({"name": item, "path": chrome_path, "profile": item})
    except Exception as e:
        logging.error(f"Error getting profiles: {e}")
    return profiles


def close_tutorial(driver):
    try:
        driver.find_element(By.CSS_SELECTOR, '.tutorial-v1__close-icon.js-exit').click()
        logging.info('Closed tutorial')
    except Exception:
        pass

def search_and_select_pair(driver, pair):
    try:
        pair_dropdown = driver.find_element(By.CSS_SELECTOR, '.currencies-block__in .pair-number-wrap')
        pair_dropdown.click()
        time.sleep(0.5)

        search_field = driver.find_element(By.CSS_SELECTOR, '.filters__search-block .search__field')
        search_field.clear()
        search_field.send_keys(pair)
        time.sleep(0.5)

        first_pair = driver.find_element(By.CSS_SELECTOR, '.assets-block__alist .alist__item:first-child')
        first_pair_text = first_pair.text.strip()

        print(first_pair_text)

        if "OTC" in first_pair_text:
            logging.info(f'First pair "{first_pair_text}" contains OTC, selecting second option.')
            print(f'First pair "{first_pair_text}" contains OTC, selecting second option.')
            second_pair = driver.find_element(By.CSS_SELECTOR, '.assets-block__alist .alist__item:nth-child(2)')
            second_pair.click()
        else:
            first_pair.click()

        time.sleep(0.5)

        driver.find_element(By.CSS_SELECTOR, 'body').click()
        time.sleep(0.5)

        logging.info(f'Selected pair: {pair}')
    except Exception as e:
        logging.error(f'Error selecting pair {pair}: {e}')

def set_trade_time(driver, expiry_time):
    global svg_icon_clicked
    try:
        if not DEMO_MODE and not svg_icon_clicked:
            try:
                svg_icon = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, 'svg[data-src*="exp-mode-2.svg"]'))
                )
                svg_icon.click()
                time.sleep(0.5)
                logging.info("Clicked on the SVG icon to enable manual time input.")
                svg_icon_clicked = True 
            except Exception as e:
                logging.error(f"Failed to click SVG icon: {e}")

        time_dropdown = driver.find_element(By.CSS_SELECTOR, '.block--expiration-inputs .control__value')
        time_dropdown.click()
        time.sleep(0.5)

        predefined_times = ['M1', 'M3', 'M5', 'M30', 'H1', 'H4']
        if expiry_time in predefined_times:
            time_button = driver.find_element(By.XPATH, f"//div[contains(@class, 'dops__timeframes-item') and text()='{expiry_time}']")
            time_button.click()
            logging.info(f'Set trade time to {expiry_time}')
        else:
            hours_input = driver.find_element(By.CSS_SELECTOR, '.trading-panel-modal__in .rw:nth-child(1) input')
            minutes_input = driver.find_element(By.CSS_SELECTOR, '.trading-panel-modal__in .rw:nth-child(2) input')
            seconds_input = driver.find_element(By.CSS_SELECTOR, '.trading-panel-modal__in .rw:nth-child(3) input')

            hours, minutes, seconds = expiry_time.split(':')
            hours_input.clear()
            hours_input.send_keys(hours)
            minutes_input.clear()
            minutes_input.send_keys(minutes)
            seconds_input.clear()
            seconds_input.send_keys(seconds)
            logging.info(f'Manually set trade time to {expiry_time}')

        driver.find_element(By.CSS_SELECTOR, 'body').click()
        time.sleep(0.5)
    except Exception as e:
        logging.error(f'Error setting trade time: {e}')

def set_trade_amount(driver, amount):
    global svg_icon_clicked
    try:    
        if not svg_icon_clicked:
            try:
                currency_icon = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, 'svg.currency-icon--usd'))
                )
                currency_icon.click()
                time.sleep(0.5)
                logging.info("Converted trade amount from USD to percentage.")
                svg_icon_clicked = True 
            except Exception as e:
                logging.error(f"Failed to convert trade amount to percentage: {e}")

        amount_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '.value__val input'))
        )

        amount_input.click()  
        amount_input.send_keys(Keys.CONTROL + "a")  
        amount_input.send_keys(Keys.BACKSPACE) 

        amount_input.send_keys(str(amount))
        logging.info(f'Trade amount set to {amount}%')

        driver.find_element(By.CSS_SELECTOR, 'body').click()
        time.sleep(0.5)

    except Exception as e:
        logging.error(f'Error setting trade amount: {e}')

def check_payout(driver):
    try:
        payout_element = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '.value__val-start'))
        )
        payout_text = payout_element.text.strip()  
        
        payout_value = payout_text.split('+')[-1].replace('%', '').strip()
        
        payout = float(payout_value)
        logging.info(f'Payout: {payout}%')
        return payout >= MIN_PAYOUT_PERCENTAGE
    except Exception as e:
        logging.error(f'Error checking payout: {e}')
        return False

def execute_trade(driver, action):
    try:
        if action == "CALL":
            call_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, '.btn-call'))
            )
            call_button.click()
            logging.info('CALL trade executed')
        elif action == "PUT":
            put_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, '.btn-put'))
            )
            put_button.click()
            logging.info('PUT trade executed')

        time.sleep(random.uniform(0.5, 1.5))
    except Exception as e:
        logging.error(f'Error executing trade: {e}')
        
def parse_telegram_message(driver, msg_element):
    script = """
    var elements = arguments[0].querySelectorAll('img');
    var result = {};
    for (var i = 0; i < elements.length; i++) {
        var img = elements[i];
        var alt = img.getAttribute('alt');
        if (['📊', '🕓', '⏳', '🟢', '🔴'].includes(alt)) {
            var nextSibling = img.nextSibling;
            var text = '';
            while (nextSibling && nextSibling.nodeType === Node.TEXT_NODE) {
                text += nextSibling.textContent.trim();
                nextSibling = nextSibling.nextSibling;
            }
            result[alt] = text;
        }
    }
    return result;
    """
    emoji_data = driver.execute_script(script, msg_element)
    pair = emoji_data.get('📊', '').strip()
    expiry_time = emoji_data.get('⏳', '').strip()
    action = (emoji_data.get('🟢', '') or emoji_data.get('🔴', '')).strip().upper()
    return pair, expiry_time, action


def get_last_processed_id():
    with open("data.json", "r") as f:
        data = json.load(f)
        return data.get("last_processed_id", 0)
    
def save_last_processed_id(last_processed_id):
    with open("data.json", "w") as f:
        json.dump({"last_processed_id": last_processed_id}, f)

def main():
    global martingale_step

    profiles = get_chrome_profiles()
    if not profiles:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))
    else:
        print("\nAvailable Chrome Profiles:")
        for i, p in enumerate(profiles):
            print(f"{i+1}. {p['name']}")
        
        while True:
            try:
                selection = int(input("\nSelect profile number: ")) - 1
                if 0 <= selection < len(profiles):
                    selected_profile = profiles[selection]
                    break
            except ValueError:
                pass

        kill_chrome_processes()
        chrome_options = Options()
        chrome_options.add_argument(f"user-data-dir={selected_profile['path']}")
        chrome_options.add_argument(f"profile-directory={selected_profile['profile']}")
        chrome_options.add_argument("--remote-debugging-port=9222")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        
        try:
            driver = webdriver.Chrome(
                service=Service(ChromeDriverManager().install()),
                options=chrome_options
            )
        except Exception:
            temp_profile = create_temp_profile_copy(selected_profile['path'], selected_profile['profile'])
            chrome_options.add_argument(f"user-data-dir={temp_profile}")
            driver = webdriver.Chrome(
                service=Service(ChromeDriverManager().install()),
                options=chrome_options
            )

    # Open Pocket Option
    driver.get('https://pocketoption.com/en/cabinet/try-demo/' if DEMO_MODE else 'https://pocketoption.com/en/cabinet/')
    time.sleep(5)
    close_tutorial(driver)

    # Open Telegram
    driver.execute_script("window.open('');")
    driver.switch_to.window(driver.window_handles[1])
    driver.get(TELEGRAM_GROUP_URL)
    logging.info("Opened Telegram")
    time.sleep(10)

    # last_processed_id = 0
    last_processed_id = get_last_processed_id()
    try:
        initial_msgs = WebDriverWait(driver, 20).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, '.Message[data-message-id]'))
        )
        if initial_msgs:
            last_processed_id = max(int(msg.get_attribute('data-message-id')) for msg in initial_msgs)
    except Exception as e:
        logging.warning(f"Initial message load failed: {e}")

    while True:
        try:
            driver.switch_to.window(driver.window_handles[1])
            time.sleep(15)
            messages = WebDriverWait(driver, 20).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, '.Message[data-message-id]'))
            )
            
            new_messages = []
            for msg in messages:
                msg_id = int(msg.get_attribute('data-message-id'))
                if msg_id > last_processed_id:
                    new_messages.append(msg)
            
            for msg in new_messages:
                msg_id = int(msg.get_attribute('data-message-id'))
                try:
                # if True:
                    print("new signal")
                    print(msg.get_attribute('innerText'))

                    # pair, expiry_time, action = parse_telegram_message(driver, msg)
                    pair, expiry_time, action = parse_signal(msg.get_attribute('innerText'))

                    if pair is None:
                        logging.error('Invalid signal format')
                        save_last_processed_id(msg_id)
                        continue

                    
                    # Validate signal
                    if not pair or not expiry_time or not action:
                        logging.error('Invalid signal format')
                        save_last_processed_id(msg_id)
                        continue

                    logging.info(f"New signal: {pair} {expiry_time} {action}")
                    
                    driver.switch_to.window(driver.window_handles[0])
                    time.sleep(2)
                    
                    # Trading logic
                    close_tutorial(driver)
                    search_and_select_pair(driver, pair)
                    
                    close_tutorial(driver)
                    set_trade_time(driver, expiry_time)
                    
                    # Martingale logic
                    if martingale_step < len(trade_amounts):
                        trade_amount = trade_amounts[martingale_step]
                        close_tutorial(driver)
                        set_trade_amount(driver, amount=trade_amount)
                    else:
                        logging.info('Martingale sequence complete. Resetting and waiting for the next signal.')
                        martingale_step = 0
                        continue

                    # Payout check
                    if not check_payout(driver):
                        logging.info('Payout below minimum threshold. Skipping trade.')
                        continue

                    # Execute trade
                    close_tutorial(driver)
                    execute_trade(driver, action)
                    
                    # Increment Martingale step only if the trade was successful
                    martingale_step += 1
                    
                    # Reset Martingale step after the sequence is complete
                    if martingale_step >= len(trade_amounts):
                        logging.info('Martingale sequence complete. Resetting and waiting for the next signal.')
                        martingale_step = 0
                    
                    last_processed_id = msg_id
                    save_last_processed_id(last_processed_id)
                    time.sleep(5)
                    
                except Exception as e:
                    logging.error(f"Message processing failed: {e}")
                    driver.switch_to.window(driver.window_handles[0])

            if new_messages:
                last_processed_id = max(int(msg.get_attribute('data-message-id')) for msg in new_messages)
                save_last_processed_id(last_processed_id)
            
            driver.switch_to.window(driver.window_handles[0])
            time.sleep(10)
        
        except Exception as e:
            logging.error(f"Main loop error: {e}")
            time.sleep(10)
            driver.switch_to.window(driver.window_handles[0])

if __name__ == '__main__':
    main()