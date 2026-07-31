import csv
import time
import os
from datetime import datetime
from selenium import webdriver
import pyautogui

# Конфигурация
CSV_FILE = 'links.csv'
SAVE_FOLDER = 'screens'

def main():
    print("Старт программы...")
    
    # 1. Проверяем наличие файла с ссылками
    if not os.path.exists(CSV_FILE):
        print(f"ОШИБКА: Файл {CSV_FILE} не найден в папке с приложением!")
        input("Нажмите Enter для выхода...")
        return

    # 2. Создаем папку для скриншотов
    if not os.path.exists(SAVE_FOLDER):
        os.makedirs(SAVE_FOLDER)
        print(f"Создана папка: {SAVE_FOLDER}")

    # 3. Настройка браузера Chrome
    print("Инициализация браузера Chrome...")
    options = webdriver.ChromeOptions()
    options.add_argument('--start-maximized')
    options.add_experimental_option("excludeSwitches", ['enable-automation'])
    
    try:
        driver = webdriver.Chrome(options=options)
        print("Браузер успешно запущен.")
    except Exception as e:
        print(f"ОШИБКА при запуске браузера: {e}")
        print("Убедитесь, что у вас установлен Google Chrome.")
        input("Нажмите Enter для выхода...")
        return

    try:
        # 4. Читаем файл с ссылками
        with open(CSV_FILE, mode='r', encoding='utf-8') as file:
            reader = list(csv.DictReader(file))
            print(f"Найдено строк в CSV: {len(reader)}")
            
            if len(reader) == 0:
                print("ВНИМАНИЕ: Файл links.csv пустой или не содержит данных под заголовками!")

            for row in reader:
                url = row['URL']
                section_name = row['Раздел']
                
                print(f"-> Открываю раздел: {section_name} ({url})")
                driver.get(url)
                
                print("Жду загрузки страницы (7 сек)...")
                time.sleep(7) 
                
                print("Вызываю календарь Windows...")
                pyautogui.hotkey('win', 'alt', 'd')
                time.sleep(1.5)
                
                timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                safe_name = "".join([c for c in section_name if c.isalnum() or c in ' -_']).strip()
                filename = f"{SAVE_FOLDER}/{timestamp}_{safe_name}.png"
                
                print( делаю скриншот...")
                pyautogui.screenshot(filename)
                print(f"Скриншот сохранен: {filename}")
                
                print("Скрываю календарь...")
                pyautogui.hotkey('win', 'alt', 'd')
                time.sleep(1)
                
    except Exception as e:
        print(f"Произошла ошибка во время работы цикла: {e}")
    finally:
        driver.quit()
        print("Работа скрипта завершена.")
        input("Нажмите Enter для выхода...")

if __name__ == '__main__':
    main()
