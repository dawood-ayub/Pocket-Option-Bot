import time
import threading
import queue
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
import os
import random
import logging
import json
import platform
import psutil
import shutil
import tempfile


TELEGRAM_GROUP_URL = '#' #enter telegram web group url here
BASE_URL = 'https://pocketoption.com/en'
DEMO_MODE = True
MIN_PAYOUT_PERCENTAGE = 50


martingale_step = 0
trade_amounts = [1, 2, 4]
svg_icon_clicked = False

trade_signal_queue = queue.Queue()

def kill_chrome_processes():
    logging.info("Checking for running Chrome processes...")
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            if 'chrome' in proc.info['name'].lower():
                proc.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    time.sleep(2)

def create_temp_profile_copy(profile_path, profile_dir):
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

        # Check if any pairs are found
        pairs = driver.find_elements(By.CSS_SELECTOR, '.assets-block__alist .alist__item')
        if not pairs:
            logging.info(f'Pair {pair} not found.')
            driver.find_element(By.CSS_SELECTOR, 'body').click()  
            return False

        first_pair = pairs[0]
        first_pair_text = first_pair.text.strip()
        if "OTC" in first_pair_text:
            logging.info(f'First pair "{first_pair_text}" contains OTC, checking second option.')
            if len(pairs) > 1:
                second_pair = pairs[1]
                second_pair_text = second_pair.text.strip()
                if "OTC" not in second_pair_text:
                    if 'alist__item--no-active' not in second_pair.get_attribute('class') and 'alist__item--no-hover' not in second_pair.get_attribute('class'):
                        second_pair.click()
                        logging.info(f'Selected pair: {second_pair_text}')
                        time.sleep(0.5)
                        driver.find_element(By.CSS_SELECTOR, 'body').click()
                        time.sleep(0.5)
                        return True
                    else:
                        logging.info(f'Second pair "{second_pair_text}" is disabled.')
                else:
                    logging.info(f'Second pair "{second_pair_text}" also contains OTC. Pair {pair} not available.')
            else:
                logging.info(f'Only OTC pair available. Pair {pair} not available.')
            driver.find_element(By.CSS_SELECTOR, 'body').click()  
            return False
        else:
            if 'alist__item--no-active' not in first_pair.get_attribute('class') and 'alist__item--no-hover' not in first_pair.get_attribute('class'):
                first_pair.click()
                logging.info(f'Selected pair: {first_pair_text}')
                time.sleep(0.5)
                driver.find_element(By.CSS_SELECTOR, 'body').click()
                time.sleep(0.5)
                return True
            else:
                logging.info(f'Pair {pair} is disabled.')
                driver.find_element(By.CSS_SELECTOR, 'body').click() 
                return False

    except Exception as e:
        logging.error(f'Error selecting pair {pair}: {e}')
        return False


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

def check_trade_result(driver, pair, action):
    try:
        logging.info("Attempting to click on the 'Closed' tab...")
        closed_tab = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, '.divider ul li:nth-child(2) a'))
        )
        closed_tab.click()
        logging.info("Clicked on the 'Closed' tab.")
        time.sleep(2)

        logging.info("Fetching all closed trades...")
        closed_trades = driver.find_elements(By.CSS_SELECTOR, '.deals-list__item')
        logging.info(f"Found {len(closed_trades)} closed trades.")

        for trade in closed_trades:
            try:
                trade_pair_element = trade.find_element(By.CSS_SELECTOR, '.deals-list__item-short > .item-row:nth-child(1) div a:nth-child(2)')
                trade_pair = trade_pair_element.text.replace('/', '')  

                trade_action_element = trade.find_element(By.CSS_SELECTOR, '.deals-list__item-short > .item-row:nth-child(2) div i')
                trade_action = trade_action_element.get_attribute('class')

                trade_result_element = trade.find_element(By.CSS_SELECTOR, '.deals-list__item-short > .item-row:nth-child(2) div.centered')
                trade_result = trade_result_element.text

                logging.info(f"Checking trade: Pair={trade_pair}, Action={trade_action}, Result={trade_result}")

                if (trade_pair == pair) and ('fa-arrow-up' in trade_action if action == "CALL" else 'fa-arrow-down' in trade_action):
                    logging.info(f"Found matching trade for {pair} {action}.")
                    if trade_result == "$0":
                        logging.info(f"Trade for {pair} {action} was a loss. Proceeding with Martingale.")
                        return False
                    else:
                        logging.info(f"Trade for {pair} {action} was a success. Resetting Martingale.")
                        return True
            except Exception as e:
                logging.error(f"Error parsing trade result: {e}")
                continue

        logging.info(f"No matching trade found for {pair} {action}.")
        return False
    except Exception as e:
        logging.error(f"Error checking trade result: {e}")
        return False

def telegram_checking_loop(driver, trade_signal_queue):
    last_processed_id = 0
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
                    pair, expiry_time, action = parse_telegram_message(driver, msg)
                    
                    if not pair or not expiry_time or not action:
                        logging.error('Invalid signal format')
                        continue

                    logging.info(f"New signal: {pair} {expiry_time} {action}")
                    
                    trade_signal_queue.put((pair, expiry_time, action))
                    
                    last_processed_id = msg_id
                    time.sleep(5)
                    
                except Exception as e:
                    logging.error(f"Message processing failed: {e}")
                    driver.switch_to.window(driver.window_handles[0])

            if new_messages:
                last_processed_id = max(int(msg.get_attribute('data-message-id')) for msg in new_messages)
            
            driver.switch_to.window(driver.window_handles[0])
            time.sleep(10)
        
        except Exception as e:
            logging.error(f"Telegram checking loop error: {e}")
            time.sleep(10)
            driver.switch_to.window(driver.window_handles[0])

def trade_execution_loop(driver, trade_signal_queue):
    while True:
        try:
            pair, expiry_time, action = trade_signal_queue.get()

            trade_thread = threading.Thread(target=execute_trade_thread, args=(driver, pair, expiry_time, action))
            trade_thread.daemon = True
            trade_thread.start()

        except Exception as e:
            logging.error(f"Trade execution loop error: {e}")
            time.sleep(10)

def execute_trade_thread(driver, pair, expiry_time, action):
    global martingale_step

    try:
        driver.switch_to.window(driver.window_handles[0])
        time.sleep(2)
        
        # Trading logic
        close_tutorial(driver)
        if not search_and_select_pair(driver, pair):
            logging.info(f'Pair {pair} not available or disabled. Skipping trade.')
            return
        
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
            return

        # Payout check
        if not check_payout(driver):
            logging.info('Payout below minimum threshold. Skipping trade.')
            return

        # Execute trade
        close_tutorial(driver)
        execute_trade(driver, action)
        
        # Wait for trade to complete
        time.sleep(int(expiry_time.replace('M', '')) * 60)

        # Check trade result
        if not check_trade_result(driver, pair, action):
            martingale_step += 1
            # Re-execute the trade with the new amount
            if martingale_step < len(trade_amounts):
                logging.info(f"Re-executing trade with {trade_amounts[martingale_step]}% amount.")
                execute_trade_thread(driver, pair, expiry_time, action)
            else:
                logging.info('Martingale sequence complete. Resetting and waiting for the next signal.')
                martingale_step = 0
        else:
            martingale_step = 0
        
    except Exception as e:
        logging.error(f"Trade execution thread error: {e}")


def main():
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

    # Start the Telegram checking thread
    telegram_thread = threading.Thread(target=telegram_checking_loop, args=(driver, trade_signal_queue))
    telegram_thread.daemon = True
    telegram_thread.start()

    # Start the trade execution thread
    trade_execution_thread = threading.Thread(target=trade_execution_loop, args=(driver, trade_signal_queue))
    trade_execution_thread.daemon = True
    trade_execution_thread.start()

    # Keep the main thread alive
    while True:
        time.sleep(1)

if __name__ == '__main__':
    main()
