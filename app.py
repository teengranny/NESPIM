# ============================================================
# ГЕНЕРАТОР ИДЕЙ ПОДАРКОВ — TELEGRAM BOT
# Запуск: python app.py
# Требуется: pip install python-telegram-bot==21.10 flask
# Переменная окружения: TELEGRAM_BOT_TOKEN
# ============================================================

import logging
import os
import random
import asyncio
import threading
from datetime import date

from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import Conflict
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    filters,
)

# ============================================================
# Flask-сервер для healthcheck (чтобы Render не убивал процесс)
# ============================================================
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Bot is running!", 200

@flask_app.route('/health')
def health():
    return "OK", 200

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_flask, daemon=True).start()

# ============================================================
# Хранилище для счётчиков, дат, премиум-статуса и фильтров
# ============================================================
user_requests = {}      # user_id -> количество идей за сегодня
user_premium = {}       # user_id -> True/False
user_last_date = {}     # user_id -> дата последнего сброса (YYYY-MM-DD)
user_filters = {}       # user_id -> 'budget', 'middle', 'premium' или None
MAX_FREE = 5

# ============================================================
# БАЗА ПОДАРКОВ (исправленная версия)
# ============================================================
GIFTS_DB = {
    "man": [
        {"title": "Умные часы с функцией мониторинга здоровья", "emoji": "⌚", "priceType": "premium", "description": "Подойдут для отслеживания физической активности и контроля показателей здоровья — полезно для тех, кто ведёт активный образ жизни.", "ozonLink": "https://takprdm.ru/0W944W82VmCiW7u0/?redirectTo=https%3A%2F%2Fwww.wildberries.ru%2Fcatalog%2F117603041%2Fdetail.aspx&erid=Y1jgkD6uB6jK1phqkTLTbNJPiD1a"},
        {"title": "Набор инструментов в кейсе", "emoji": "🔧", "priceType": "middle", "description": "Практичный подарок для домашнего мастера — поможет справиться с бытовыми задачами и организовать хранение мелочей.", "ozonLink": "https://takprdm.ru/0W944W82VmChQ0C0/?redirectTo=https%3A%2F%2Fwww.wildberries.ru%2Fcatalog%2F49844802%2Fdetail.aspx&erid=Y1jgkD6uB6jK1phqkTLTbNJPiD1a"},
        {"title": "Термокружка с подогревом от USB", "emoji": "🥤", "priceType": "budget", "description": "Удобна в дороге и на работе — позволяет наслаждаться горячим напитком в любое время.", "ozonLink": "https://ozon.ru/click/usb_heated_mug"},
        {"title": "Беспроводные наушники с шумоподавлением", "emoji": "🎧", "priceType": "middle", "description": "Идеальны для прослушивания музыки и разговоров — обеспечат комфорт в транспорте и офисе.", "ozonLink": "https://ozon.ru/click/wireless_noise_cancelling"},
        {"title": "Кожаный портфель для документов", "emoji": "💼", "priceType": "premium", "description": "Стильный аксессуар для делового человека — подчеркнёт статус и поможет организовать рабочие материалы.", "ozonLink": "https://ozon.ru/click/leather_briefcase"},
        {"title": "Набор для барбекю с аксессуарами", "emoji": "🍖", "priceType": "middle", "description": "Порадует любителя отдыха на природе — сделает пикники ещё приятнее и удобнее.", "ozonLink": "https://ozon.ru/click/bbq_tool_set"},
        {"title": "Подписка на стриминговый сервис", "emoji": "🎬", "priceType": "budget", "description": "Подарит доступ к разнообразному контенту — подойдёт для расслабления после рабочего дня.", "ozonLink": "https://ozon.ru/click/streaming_subscription"},
        {"title": "Фитнес‑браслет с отслеживанием сна", "emoji": "⌚", "priceType": "middle", "description": "Поможет следить за качеством отдыха и физической активностью — хороший выбор для заботы о здоровье.", "ozonLink": "https://ozon.ru/click/fitness_tracker_sleep"},
        {"title": "Power bank с солнечной батареей", "emoji": "🔋", "priceType": "middle", "description": "Портативный источник энергии для зарядки гаджетов в дороге.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Кожаный ремень ручной работы", "emoji": "🧵", "priceType": "premium", "description": "Стильный аксессуар, дополняющий любой образ.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Набор для ухода за обувью", "emoji": "🥾", "priceType": "budget", "description": "Поможет поддерживать обувь в идеальном состоянии.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Беспроводная колонка с защитой от воды", "emoji": "🔊", "priceType": "middle", "description": "Для прослушивания музыки на природе.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Кружка с подогревом от прикуривателя", "emoji": "☕", "priceType": "budget", "description": "Сохранит напиток горячим в машине.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Фитнес‑коврик премиум‑класса", "emoji": "🤸", "priceType": "premium", "description": "Для домашних тренировок и йоги.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Мультитул в компактном корпусе", "emoji": "🛠️", "priceType": "middle", "description": "Набор инструментов всегда под рукой.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Подписка на стриминговый сервис спортивных трансляций", "emoji": "📺", "priceType": "budget", "description": "Доступ к матчам и турнирам.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Термобельё из мериноса", "emoji": "🥽", "priceType": "middle", "description": "Согреет в холодную погоду, отводит влагу.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Электронная книга с подсветкой", "emoji": "📚", "priceType": "premium", "description": "Для чтения в любых условиях.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Автомобильный органайзер", "emoji": "🚗", "priceType": "budget", "description": "Организует пространство в салоне.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Умный браслет для отслеживания активности", "emoji": "🦾", "priceType": "middle", "description": "Мотивирует быть активнее.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Набор бокалов для виски с камнями", "emoji": "🥃", "priceType": "middle", "description": "Для ценителей благородных напитков.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Рюкзак для ноутбука с защитой от дождя", "emoji": "🎒", "priceType": "premium", "description": "Практичный аксессуар для работы и путешествий.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Настольная игра в жанре стратегии", "emoji": "🎲", "priceType": "budget", "description": "Для увлекательных вечеров с друзьями.", "ozonLink": "https://ozon.ru/click/temp"},
    ],
    "woman": [
        {"title": "Набор косметики премиум‑бренда", "emoji": "💄", "priceType": "premium", "description": "Порадует ценительницу ухода за собой — включает средства для разных этапов бьюти‑рутины.", "ozonLink": "https://ozon.ru/click/premium_cosmetics_set"},
        {"title": "Шарф из кашемира", "emoji": "🧣", "priceType": "middle", "description": "Стильный и тёплый аксессуар на холодное время года — добавит элегантности любому образу.", "ozonLink": "https://ozon.ru/click/cashmere_scarf"},
        {"title": "Аромадиффузор с набором эфирных масел", "emoji": "🕯️", "priceType": "middle", "description": "Создаст уютную атмосферу дома — поможет расслабиться и улучшить настроение.", "ozonLink": "https://ozon.ru/click/aroma_diffuser_oils"},
        {"title": "Книга любимого автора в коллекционном издании", "emoji": "📖", "priceType": "budget", "description": "Для любительницы чтения — порадует красивым оформлением и содержанием.", "ozonLink": "https://ozon.ru/click/collector_book"},
        {"title": "Набор для домашнего спа", "emoji": "🧴", "priceType": "middle", "description": "Позволит устроить салонный уход дома — идеальный вариант для релаксации.", "ozonLink": "https://ozon.ru/click/home_spa_kit"},
        {"title": "Сумка‑тоут из экокожи", "emoji": "👜", "priceType": "premium", "description": "Вместительная и стильная — подойдёт для работы и прогулок, дополнит гардероб.", "ozonLink": "https://ozon.ru/click/eco_leather_tote"},
        {"title": "Умное зеркало для макияжа с подсветкой", "emoji": "🪞", "priceType": "premium", "description": "Облегчит нанесение косметики — пригодится для точного нанесения макияжа в любых условиях.", "ozonLink": "https://ozon.ru/click/smart_makeup_mirror"},
        {"title": "Набор ароматических свечей ручной работы", "emoji": "🕯️", "priceType": "budget", "description": "Создаст романтическую атмосферу — украсит интерьер и наполнит дом приятным ароматом.", "ozonLink": "https://ozon.ru/click/handmade_candles_set"},
        {"title": "Набор ароматических саше для гардероба", "emoji": "🌼", "priceType": "budget", "description": "Наполнит одежду приятным ароматом.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Шёлковый шарф с авторским принтом", "emoji": "🧣", "priceType": "middle", "description": "Стильный акцент в образе.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Массажер для лица с функцией подогрева", "emoji": "💆‍♀️", "priceType": "middle", "description": "Поможет расслабиться и улучшить состояние кожи.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Набор натуральной косметики ручной работы", "emoji": "🧴", "priceType": "premium", "description": "Бережный уход с природными компонентами.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Фотоальбом в кожаном переплёте", "emoji": "🖼️", "priceType": "middle", "description": "Сохранит воспоминания на долгие годы.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Умные весы с анализом состава тела", "emoji": "⚖️", "priceType": "premium", "description": "Помогут следить за здоровьем и фигурой.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Набор чайных чашек с блюдцами", "emoji": "☕️", "priceType": "budget", "description": "Украсит чаепитие и добавит уюта.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Браслет с гравировкой", "emoji": "💍", "priceType": "middle", "description": "Персональный аксессуар с особым смыслом.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Набор эфирных масел и диффузор", "emoji": "🌿", "priceType": "middle", "description": "Создаст атмосферу релаксации дома.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Сумка‑шоппер из органического хлопка", "emoji": "🛍️", "priceType": "budget", "description": "Экологичный и практичный аксессуар.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Комплект шёлкового постельного белья", "emoji": "🛌", "priceType": "premium", "description": "Обеспечит комфортный сон.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Компактный отпариватель для одежды", "emoji": "💨", "priceType": "middle", "description": "Быстро приведёт вещи в порядок.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Книга по кулинарии от известного шеф‑повара", "emoji": "🍳", "priceType": "budget", "description": "Вдохновит на новые кулинарные эксперименты.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Набор кистей для макияжа профессионального уровня", "emoji": "🪞", "priceType": "premium", "description": "Для безупречного образа.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Абонемент в СПА на месяц", "emoji": "🧖‍♀️", "priceType": "premium", "description": "Время для отдыха и восстановления.", "ozonLink": "https://ozon.ru/click/temp"},
    ],
    "child": [
        {"title": "Конструктор с элементами дополненной реальности", "emoji": "🧩", "priceType": "middle", "description": "Развивает логику и воображение — совмещает игру с современными технологиями.", "ozonLink": "https://ozon.ru/click/ar_construction_set"},
        {"title": "Велосипед с дополнительными колёсами", "emoji": "🚲", "priceType": "middle", "description": "Для активного отдыха на свежем воздухе — поможет научиться кататься и укрепить здоровье.", "ozonLink": "https://ozon.ru/click/bike_training_wheels"},
        {"title": "Набор для научных экспериментов", "emoji": "🔬", "priceType": "budget", "description": "Пробудит интерес к науке — позволит провести увлекательные опыты дома под присмотром взрослых.", "ozonLink": "https://ozon.ru/click/science_experiment_kit"},
        {"title": "Интерактивная игрушка‑робот", "emoji": "🤖", "priceType": "middle", "description": "Развлечёт и обучит основам программирования — подойдёт для развития алгоритмического мышления.", "ozonLink": "https://ozon.ru/click/interactive_robot"},
        {"title": "Настольная игра для всей семьи", "emoji": "🎲", "priceType": "budget", "description": "Укрепит общение и научит стратегическому мышлению — разнообразит вечера и сплотит семью.", "ozonLink": "https://ozon.ru/click/family_board_game"},
        {"title": "Рюкзак с 3D‑принтом любимого персонажа", "emoji": "🎒", "priceType": "budget", "description": "Поднимет настроение и пригодится в школе — яркий и практичный аксессуар.", "ozonLink": "https://ozon.ru/click/character_backpack"},
        {"title": "Набор для рисования светом", "emoji": "✨", "priceType": "middle", "description": "Откроет новые творческие возможности — позволит создавать необычные картины и развивать фантазию.", "ozonLink": "https://ozon.ru/click/light_drawing_set"},
        {"title": "Самокат с подсветкой колёс", "emoji": "🛴", "priceType": "middle", "description": "Подарит радость от катания вечером — безопасный и стильный транспорт для прогулок.", "ozonLink": "https://ozon.ru/click/light_up_scooter"},
        {"title": "Набор фломастеров с неоновыми цветами", "emoji": "🎨", "priceType": "budget", "description": "Для ярких и необычных рисунков.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Интерактивная обучающая игрушка", "emoji": "🤖", "priceType": "middle", "description": "Познакомит с буквами и цифрами в игровой форме.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Пазл из 1000 элементов с изображением космоса", "emoji": "🧩", "priceType": "middle", "description": "Развивает логику и усидчивость.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Детский микроскоп с набором образцов", "emoji": "🔬", "priceType": "premium", "description": "Пробудит интерес к науке.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Надувной бассейн для дачи", "emoji": "🏊", "priceType": "budget", "description": "Радость и веселье в жаркие дни.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Набор для создания слайма", "emoji": "🤲", "priceType": "budget", "description": "Увлекательный творческий процесс.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Велосипед с защитной экипировкой", "emoji": "🚴", "priceType": "premium", "description": "Для безопасных прогулок и активного отдыха.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Конструктор с моторизированными деталями", "emoji": "🧱", "priceType": "middle", "description": "Развивает инженерные навыки.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Настольная игра «виселица» для изучения английского", "emoji": "🗣️", "priceType": "budget", "description": "Обучение через игру.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Проектор звёздного неба", "emoji": "🌠", "priceType": "middle", "description": "Создаст волшебную атмосферу в детской.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Набор для выращивания кристаллов", "emoji": "💎", "priceType": "middle", "description": "Увлекательный научный эксперимент.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Мягкие кубики с буквами", "emoji": "🅰️", "priceType": "budget", "description": "Для обучения и игры одновременно.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Робот‑трансформер с пультом управления", "emoji": "🤖", "priceType": "middle", "description": "Увлекательная игрушка для мальчиков.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Набор акварельных красок и кистей", "emoji": "🖌️", "priceType": "budget", "description": "Для первых шагов в живописи.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Интерактивный глобус с дополненной реальностью", "emoji": "🌍", "priceType": "premium", "description": "Познание мира в игровой форме.", "ozonLink": "https://ozon.ru/click/temp"},
    ],
    "colleague": [
        {"title": "Беспроводная зарядная станция", "emoji": "🔋", "priceType": "middle", "description": "Упростит зарядку гаджетов на рабочем месте — сэкономит время и освободит пространство от проводов.", "ozonLink": "https://ozon.ru/click/wireless_charging_station"},
        {"title": "Ежедневник с персонализированной обложкой", "emoji": "📓", "priceType": "budget", "description": "Поможет организовать рабочий график — практичный инструмент для планирования задач.", "ozonLink": "https://ozon.ru/click/personalized_notebook"},
        {"title": "Кружка‑хамелеон", "emoji": "☕", "priceType": "budget", "description": "Добавит позитива в перерывы на кофе — меняет цвет при нагревании, поднимает настроение.", "ozonLink": "https://takprdm.ru/0W944W82VmCiLsm0/?redirectTo=https%3A%2F%2Fwww.wildberries.ru%2Fcatalog%2F15462468%2Fdetail.aspx&erid=Y1jgkD6uB6jK1phqkTLTbNJPiD1a"},
        {"title": "Набор качественных ручек и маркеров", "emoji": "✒️", "priceType": "budget", "description": "Пригодится для работы с документами — надёжный инструмент для заметок и презентаций.", "ozonLink": "https://ozon.ru/click/premium_pens_set"},
        {"title": "Мини‑увлажнитель воздуха для рабочего стола", "emoji": "💨", "priceType": "middle", "description": "Улучшит микроклимат в офисе — поможет сохранить комфорт в течение дня.", "ozonLink": "https://ozon.ru/click/desktop_humidifier"},
        {"title": "Подставка для ног эргономичной формы", "emoji": "🦶", "priceType": "middle", "description": "Снизит нагрузку при долгой работе за компьютером — повысит комфорт и заботу о здоровье.", "ozonLink": "https://ozon.ru/click/foot_rest_ergonomic"},
        {"title": "Портативная колонка с Bluetooth", "emoji": "🔊", "priceType": "middle", "description": "Разнообразит перерывы и встречи — позволит слушать музыку или проводить аудиоконференции.", "ozonLink": "https://ozon.ru/click/bluetooth_speaker"},
        {"title": "Подарочный сертификат в книжный магазин", "emoji": "🎁", "priceType": "budget", "description": "Даст возможность выбрать то, что действительно нужно — универсальный вариант для коллеги с любыми интересами.", "ozonLink": "https://ozon.ru/click/bookstore_gift_card"},
        {"title": "Подставка для смартфона на рабочий стол", "emoji": "📱", "priceType": "budget", "description": "Удобный аксессуар для видеозвонков.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Набор стикеров для заметок разных цветов", "emoji": "📋", "priceType": "budget", "description": "Поможет организовать задачи.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Термокружка с логотипом компании", "emoji": "☕", "priceType": "middle", "description": "Практичный и корпоративный подарок.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Настольный органайзер для канцелярии", "emoji": "🗂️", "priceType": "middle", "description": "Наведёт порядок на рабочем месте.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Беспроводная мышь эргономичной формы", "emoji": "🖱️", "priceType": "middle", "description": "Комфорт при длительной работе.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Подписка на сервис облачного хранения данных", "emoji": "💾", "priceType": "budget", "description": "Дополнительное пространство для файлов.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Мини‑очиститель воздуха для рабочего стола", "emoji": "💨", "priceType": "middle", "description": "Улучшит микроклимат в офисе.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "USB‑хаб с несколькими портами", "emoji": "💻", "priceType": "middle", "description": "Решит проблему нехватки разъёмов.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Коврик для мыши с индивидуальным принтом", "emoji": "🖱️", "priceType": "budget", "description": "Добавит индивидуальности рабочему месту.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Набор качественных маркеров для флипчарта", "emoji": "🖍️", "priceType": "middle", "description": "Для презентаций и мозговых штурмов.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Умная лампа с регулировкой яркости", "emoji": "💡", "priceType": "premium", "description": "Создаст комфортное освещение для работы.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Портативный сканер документов", "emoji": "🖨️", "priceType": "premium", "description": "Упростит работу с бумажными носителями.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Ежедневник в кожаной обложке", "emoji": "🗓️", "priceType": "premium", "description": "Поможет планировать задачи и встречи.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Беспроводные наушники для конференц‑звонков", "emoji": "🎧", "priceType": "premium", "description": "Обеспечат чёткую связь.", "ozonLink": "https://ozon.ru/click/temp"},
        {"title": "Набор экологичных ручек из переработанных материалов", "emoji": "✒️", "priceType": "budget", "description": "Забота об экологии и рабочем процессе.", "ozonLink": "https://ozon.ru/click/temp"},
    ],
}

PRICE_LABELS = {
    "budget": "бюджетная",
    "middle": "средняя",
    "premium": "премиум",
}

CATEGORIES = {
    "man": "👔 Мужчине",
    "woman": "🌸 Женщине",
    "child": "🧸 Ребёнку",
    "colleague": "🤝 Коллеге",
}

# ============================================================
# ФУНКЦИИ ДЛЯ ФИЛЬТРОВ И ГЕНЕРАЦИИ
# ============================================================

def get_random_gift(category: str, price_filter: str = None) -> dict:
    gifts = GIFTS_DB.get(category, [])
    if not gifts:
        return {"title": "Скоро добавим идеи", "emoji": "🎁", "priceType": "", "description": "Пожалуйста, выберите другую категорию.", "ozonLink": "https://ozon.ru/"}
    if price_filter:
        filtered = [g for g in gifts if g.get("priceType") == price_filter]
        if filtered:
            gifts = filtered
    return random.choice(gifts)

def format_gift_message(gift: dict) -> str:
    price_label = PRICE_LABELS.get(gift.get("priceType", ""), "")
    price_line = f"💰 Стоимость: {price_label}\n" if price_label else ""
    return f"{gift['emoji']} *{gift['title']}*\n{price_line}\n{gift['description']}\n\n[Купить →]({gift['ozonLink']})"

def get_main_keyboard(user_id: int) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(label, callback_data=f"cat:{key}")] for key, label in CATEGORIES.items()]
    if user_premium.get(user_id, False):
        current_filter = user_filters.get(user_id)
        if current_filter == 'budget':
            filter_label = "🎯 Фильтр: бюджетный"
        elif current_filter == 'middle':
            filter_label = "🎯 Фильтр: средний"
        elif current_filter == 'premium':
            filter_label = "🎯 Фильтр: премиум"
        else:
            filter_label = "🎯 Фильтр по бюджету"
        buttons.append([InlineKeyboardButton(filter_label, callback_data="filter")])
    return InlineKeyboardMarkup(buttons)

def build_gift_keyboard(category: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎲 Ещё идея", callback_data=f"cat:{category}")],
        [InlineKeyboardButton("↩️ Выбрать категорию", callback_data="menu")],
    ])

# ============================================================
# ОБРАБОТЧИКИ
# ============================================================

async def start(update: Update, context) -> None:
    user_id = update.effective_user.id
    if user_id not in user_requests:
        user_requests[user_id] = 0
    if user_id not in user_last_date:
        user_last_date[user_id] = date.today().isoformat()
    await update.message.reply_text(
        "🎁 *Подарочный гуру*\n\n"
        "Привет! Устал ломать голову над подарками? Я помогу.\n"
        "5 идей — в подарок от меня. Хочешь ещё? Премиум открывает безлимит за 199 ₽.\n\n"
        "Просто выбери, кому ищем подарок 👇",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(user_id),
    )

async def help_command(update: Update, context) -> None:
    user_id = update.effective_user.id
    await update.message.reply_text(
        "🎁 *Подарочный гуру*\n\n"
        "Команды:\n"
        "/start — показать меню выбора категории\n"
        "/help — это сообщение\n"
        "/premium — купить безлимит за 199 ₽\n\n"
        "Бесплатно — 5 идей в день. Премиум даёт безлимит, фильтры по бюджету и сохранение списка.",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(user_id),
    )

async def premium(update: Update, context) -> None:
    await update.message.reply_text(
        "✨ *Премиум-доступ* ✨\n\n"
        "💰 Стоимость: *199 рублей* (единоразово)\n\n"
        "Что вы получите:\n"
        "✅ *Безлимит идей* подарков\n"
        "✅ *Фильтр по бюджету* (бюджетный, средний, премиум)\n"
        "✅ *Сохранение понравившихся идей*\n\n"
        "Скоро оплата будет доступна. Следите за обновлениями!\n\n"
        "А пока можете продолжать пользоваться бесплатными идеями (осталось счётчик).",
        parse_mode="Markdown"
    )

async def activate_premium(update: Update, context) -> None:
    admin_id = 426916872  # ЗАМЕНИ НА СВОЙ TELEGRAM ID (можно узнать у @userinfobot)
    if update.effective_user.id != admin_id:
        await update.message.reply_text("⛔ У вас нет прав для этой команды.")
        return
    try:
        user_id = int(context.args[0])
        user_premium[426916872] = True
        user_requests[user_id] = 0  # сбросим счётчик
        # дату последнего сброса не трогаем, чтобы не обнулять лимит принудительно
        await update.message.reply_text(f"✅ Премиум активирован для пользователя {user_id}!")
    except (IndexError, ValueError):
        await update.message.reply_text("❗ Используйте: /activate ID_пользователя")

async def button_callback(update: Update, context) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id

    # Проверяем, премиум ли пользователь
    premium_active = user_premium.get(user_id, False)

    # Обработка меню и категорий
    if data == "menu":
        await query.edit_message_text(
            "🎁 *Подарочный гуру*\n\nВыберите категорию:",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard(user_id),
        )
        return

    if data == "filter":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💰 Бюджетный (до 1500₽)", callback_data="filter_budget")],
            [InlineKeyboardButton("💰 Средний (1500-5000₽)", callback_data="filter_middle")],
            [InlineKeyboardButton("💰 Премиум (от 5000₽)", callback_data="filter_premium")],
            [InlineKeyboardButton("🚫 Отключить фильтр", callback_data="filter_off")],
            [InlineKeyboardButton("↩️ Назад", callback_data="menu")]
        ])
        await query.edit_message_text(
            "🎯 *Выберите бюджет*:\n\n"
            "Фильтр будет применяться при подборе идей подарков.",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        return

    if data.startswith("filter_"):
        filter_type = data.split("_")[1]
        if filter_type == "budget":
            user_filters[user_id] = 'budget'
            text = "✅ Установлен фильтр: *бюджетный* (до 1500 ₽)"
        elif filter_type == "middle":
            user_filters[user_id] = 'middle'
            text = "✅ Установлен фильтр: *средний* (1500-5000 ₽)"
        elif filter_type == "premium":
            user_filters[user_id] = 'premium'
            text = "✅ Установлен фильтр: *премиум* (от 5000 ₽)"
        elif filter_type == "off":
            user_filters[user_id] = None
            text = "✅ Фильтр отключён"
        else:
            text = "❌ Неизвестный фильтр"
        await query.edit_message_text(
            text + "\n\nТеперь при выборе категории бот будет учитывать ваш бюджет.",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard(user_id)
        )
        return

    if data.startswith("cat:"):
        category = data.split(":", 1)[1]

        # Если не премиум, проверяем лимит по дням
        if not premium_active:
            today = date.today().isoformat()
            last = user_last_date.get(user_id)
            if last != today:
                user_requests[user_id] = 0
                user_last_date[user_id] = today
            count = user_requests.get(user_id, 0)
            if count >= MAX_FREE:
                await query.edit_message_text(
                    "❌ *Лимит бесплатных идей на сегодня исчерпан!*\n\n"
                    "Подписка за *199 ₽* откроет:\n"
                    "✅ 200 идей в день\n"
                    "✅ Фильтры по бюджету и полу\n"
                    "✅ Сохранение списка и экспорт\n\n"
                    "Нажмите /premium, чтобы оформить.",
                    parse_mode="Markdown",
                    reply_markup=get_main_keyboard(user_id),
                )
                return
            user_requests[user_id] = count + 1

        # Получаем фильтр (только для премиум)
        price_filter = user_filters.get(user_id) if premium_active else None
        gift = get_random_gift(category, price_filter)
        category_label = CATEGORIES.get(category, category)
        text = f"*Идея подарка — {category_label}*\n\n{format_gift_message(gift)}"
        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=build_gift_keyboard(category),
            disable_web_page_preview=True,
        )
        return

async def error_handler(update: object, context) -> None:
    if isinstance(context.error, Conflict):
        logger.warning("Conflict: another bot instance is running with this token. Retrying... (stop the other instance to resolve this)")
    else:
        logger.error("Unhandled error: %s", context.error, exc_info=context.error)

# ============================================================
# ЗАПУСК
# ============================================================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is not set.")

    application = Application.builder().token(token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("premium", premium))
    application.add_handler(CommandHandler("activate", activate_premium))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_error_handler(error_handler)

    logger.info("Bot is starting...")

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )

if __name__ == "__main__":
    main()
