import csv
import time
import os
from datetime import datetime
from selenium import webdriver
import pyautogui

# Конфигурация
CSV_FILE = 'links.csv'
SAVE_FOLDER = 'screenshots'

def main():
    # 1. Создаем папку для скриншотов, если ее нет
    if not os.path.exists(SAVE_FOLDER):
        os.makedirs(SAVE_FOLDER)

    # 2. Настройка браузера Chrome
    options = webdriver.ChromeOptions()
    options.add_argument('--start-maximized') # Открыть на весь экран
    # Убираем плашку "Браузером управляет автоматизированное тестовое ПО"
    options.add_experimental_option("excludeSwitches", ['enable-automation'])
    
    print("Запуск браузера...")
    driver = webdriver.Chrome(options=options)

    try:
        # 3. Читаем файл с ссылками
        with open(CSV_FILE, mode='r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            
            for row in reader:
                url = row['URL']
                section_name = row['Раздел']
                
                print(f"Открываю: {section_name}")
                driver.get(url)
                
                # Ждем загрузки страницы и баннеров (настройте время под скорость интернета)
                time.sleep(7) 
                
                # 4. Открываем календарь Windows (горячая клавиша Win + Alt + D)
                pyautogui.hotkey('win', 'alt', 'd')
                
                # Ждем анимацию появления календаря
                time.sleep(1.5)
                
                # 5. Формируем безопасное имя файла
                timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                # Убираем запрещенные символы из названия раздела
                safe_name = "".join([c for c in section_name if c.isalnum() or c in ' -_']).strip()
                filename = f"{SAVE_FOLDER}/{timestamp}_{safe_name}.png"
                
                # 6. Делаем снимок всего экрана
                pyautogui.screenshot(filename)
                print(f" Сохранено: {filename}")
                
                # 7. Скрываем календарь
                pyautogui.hotkey('win', 'alt', 'd')
                
                # Небольшая пауза перед следующим разделом
                time.sleep(1)
                
    except FileNotFoundError:
        print(f" ОШИБКА: Файл {CSV_FILE} не найден. Проверьте, что он лежит рядом со скриптом.")
    except Exception as e:
        print(f" Произошла ошибка: {e}")
    finally:
        driver.quit()
        print("Скрипт завершил работу!")

if __name__ == '__main__':
    main()
