# ============================================================
# ГЕНЕРАТОР ИДЕЙ ПОДАРКОВ — TELEGRAM BOT
# Запуск: python app.py
# Требуется: pip install python-telegram-bot==21.10 flask supabase
# Переменные окружения: TELEGRAM_BOT_TOKEN, PROVIDER_TOKEN, SUPABASE_URL, SUPABASE_KEY
# ============================================================

import uuid
import logging
import os
import random
import asyncio
import threading
import sqlite3
from datetime import date

from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.error import Conflict
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    PreCheckoutQueryHandler,
    MessageHandler,
    filters,
)

from supabase import create_client, Client

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
# РАБОТА С БАЗОЙ ДАННЫХ Supabase
# ============================================================
supabase: Client = create_client(
    os.environ.get("SUPABASE_URL"),
    os.environ.get("SUPABASE_KEY")
)

PREMIUM_TABLE = "premium_users"

def init_db():
    """Проверка подключения"""
    try:
        supabase.table(PREMIUM_TABLE).select("*").limit(1).execute()
        print("Supabase connected")
    except Exception as e:
        print(f"Supabase error: {e}")

def add_premium_user(user_id: int):
    try:
        supabase.table(PREMIUM_TABLE).upsert({"user_id": user_id}).execute()
        return True
    except Exception as e:
        print(f"Add error: {e}")
        return False

def remove_premium_user(user_id: int):
    try:
        supabase.table(PREMIUM_TABLE).delete().eq("user_id", user_id).execute()
        return True
    except Exception as e:
        print(f"Remove error: {e}")
        return False

def is_premium_user(user_id: int) -> bool:
    try:
        res = supabase.table(PREMIUM_TABLE).select("*").eq("user_id", user_id).execute()
        return len(res.data) > 0
    except Exception as e:
        print(f"Check error: {e}")
        return False

def load_premium_users():
    premium_dict = {}
    try:
        res = supabase.table(PREMIUM_TABLE).select("*").execute()
        for item in res.data:
            premium_dict[item["user_id"]] = True
    except Exception as e:
        print(f"Load error: {e}")
    return premium_dict

# ============================================================
# Хранилище для счётчиков, дат, премиум-статуса и фильтров
# ============================================================
user_requests = {}      # user_id -> количество идей за сегодня
user_premium = {}       # user_id -> True/False (загружается из БД)
user_last_date = {}     # user_id -> дата последнего сброса (YYYY-MM-DD)
user_filters = {}       # user_id -> 'budget', 'middle', 'premium' или None
MAX_FREE = 5
ADMIN_ID = 426916872    # Твой Telegram ID

# ============================================================
# БАЗА ПОДАРКОВ 
# ============================================================
GIFTS_DB = {
    "man": [
        {"title": "Умные часы с мониторингом здоровья", "emoji": "⌚", "priceType": "premium", "description": "Отслеживают пульс, сон и калории. Мотивируют больше двигаться.", "ozonLink": "https://takprdm.ru/0W944W82VmCiW7u0/?redirectTo=https%3A%2F%2Fwww.wildberries.ru%2Fcatalog%2F117603041%2Fdetail.aspx&erid=Y1jgkD6uB6jK1phqkTLTbNJPiD1a"},
        {"title": "Набор инструментов в кейсе", "emoji": "🔧", "priceType": "middle", "description": "Упорядочивают инструменты. Выручают при мелком ремонте.", "ozonLink": "https://takprdm.ru/0W944W82VmChQ0C0/?redirectTo=https%3A%2F%2Fwww.wildberries.ru%2Fcatalog%2F49844802%2Fdetail.aspx&erid=Y1jgkD6uB6jK1phqkTLTbNJPiD1a"},
        {"title": "Термокружка с подогревом от USB", "emoji": "🥤", "priceType": "budget", "description": "Заряжается от ноутбука. Сохраняет кофе горячим часами.", "ozonLink": "https://takprdm.ru/0W944W82iWCikk40/?redirectTo=https%3A%2F%2Fwww.wildberries.ru%2Fcatalog%2F808840619%2Fdetail.aspx&erid=Y1jgkD6uB6jK1phqkTLTbNJNKvJZ"},
        {"title": "Наушники с шумоподавлением", "emoji": "🎧", "priceType": "middle", "description": "Глушат шум в метро. Дают чистый звук для музыки и звонков.", "ozonLink": "https://takprdm.ru/0W944W82VmCiEqK0/?redirectTo=https%3A%2F%2Fwww.wildberries.ru%2Fcatalog%2F218663900%2Fdetail.aspx&erid=Y1jgkD6uB6jK1phqkTLTbNJPiD1a"},
        {"title": "Кожаный портфель для документов", "emoji": "💼", "priceType": "premium", "description": "Выглядит дорого. Вмещает ноутбук и бумаги для переговоров.", "ozonLink": "https://takprdm.ru/0W944W82VmCjDbm0/?redirectTo=https%3A%2F%2Fwww.wildberries.ru%2Fcatalog%2F168850908%2Fdetail.aspx&erid=Y1jgkD6uB6jK1phqkTLTbNJPiD1a"},
        {"title": "Набор для барбекю", "emoji": "🍖", "priceType": "middle", "description": "Превращает шашлыки в ритуал. Всё для идеального мяса в одной сумке.", "ozonLink": "https://takprdm.ru/0W944W82iWCilSG0/?redirectTo=https%3A%2F%2Fwww.wildberries.ru%2Fcatalog%2F831907337%2Fdetail.aspx&erid=Y1jgkD6uB6jK1phqkTLTbNJNKvJZ"},
        {"title": "Подписка на стриминг", "emoji": "🎬", "priceType": "budget", "description": "Открывает тысячи фильмов. Спасает от скуки вечером. Попробуйте Кинопоиск, Okko или IVI.", "ozonLink": None},
        {"title": "Фитнес-браслет со сном", "emoji": "⌚", "priceType": "middle", "description": "Считает шаги, анализирует фазы сна. Помогает просыпаться бодрым.", "ozonLink": "https://takprdm.ru/0W944W82VmCjEei0/?redirectTo=https%3A%2F%2Fwww.wildberries.ru%2Fcatalog%2F74627555%2Fdetail.aspx&erid=Y1jgkD6uB6jK1phqkTLTbNJPiD1a"},
        {"title": "Пауэр банк с солнечной батареей", "emoji": "🔋", "priceType": "middle", "description": "Заряжает гаджеты в походе от солнца. Незаменим в дороге.", "ozonLink": None},
        {"title": "Ремень ручной работы", "emoji": "🧵", "priceType": "premium", "description": "Добавляет образу завершённость. Служит годами, не теряя формы.", "ozonLink": "https://takprdm.ru/0W944W82VmChdZ40/?redirectTo=https%3A%2F%2Fwww.wildberries.ru%2Fcatalog%2F74417966%2Fdetail.aspx&erid=Y1jgkD6uB6jK1phqkTLTbNJPiD1a"},
        {"title": "Набор для ухода за обувью", "emoji": "🥾", "priceType": "budget", "description": "Продлевает жизнь ботинкам. Держит обувь в идеальном состоянии.", "ozonLink": "https://takprdm.ru/0W944W82IGCdV_00/?redirectTo=https%3A%2F%2Fwww.wildberries.ru%2Fcatalog%2F51785624%2Fdetail.aspx&erid=Y1jgkD6uB6jK1phqkTLTbNJNHZn6"},
        {"title": "Влагозащищённая колонка", "emoji": "🔊", "priceType": "middle", "description": "Не боится дождя и песка. Играет громко на природе.", "ozonLink": "https://takprdm.ru/0W944W82VmCiF6S0/?redirectTo=https%3A%2F%2Fwww.wildberries.ru%2Fcatalog%2F218647115%2Fdetail.aspx&erid=Y1jgkD6uB6jK1phqkTLTbNJPiD1a"},
        {"title": "Автокружка с подогревом", "emoji": "☕", "priceType": "budget", "description": "Греет чай прямо в машине. Не даёт напитку остыть в пробке.", "ozonLink": None},
        {"title": "Фитнес-коврик премиум", "emoji": "🤸", "priceType": "premium", "description": "Амортизирует суставы. Подходит для йоги и интенсивных тренировок.", "ozonLink": None},
        {"title": "Мультитул", "emoji": "🛠️", "priceType": "middle", "description": "Заменяет 10 инструментов. Помещается в карман, всегда под рукой.", "ozonLink": "https://takprdm.ru/0W944W82IGCdso40/?redirectTo=https%3A%2F%2Fwww.wildberries.ru%2Fcatalog%2F29997674%2Fdetail.aspx&erid=Y1jgkD6uB6jK1phqkTLTbNJNHZn6"},
        {"title": "Подписка на спорт", "emoji": "📺", "priceType": "budget", "description": "Открывает все матчи сезона. Не пропустишь ни одной игры.", "ozonLink": None},
        {"title": "Термобельё из мериноса", "emoji": "🥽", "priceType": "middle", "description": "Греет в мороз и отводит пот. Идеально для зимы.", "ozonLink": None},
        {"title": "Электронная книга", "emoji": "📚", "priceType": "premium", "description": "Вмещает тысячи книг. Читается даже в темноте без напряжения глаз.", "ozonLink": None},
        {"title": "Автоорганайзер", "emoji": "🚗", "priceType": "budget", "description": "Наводит порядок в салоне. Карманы для мелочей и крючки для пакетов.", "ozonLink": None},
        {"title": "Бокалы для виски с камнями", "emoji": "🥃", "priceType": "budget", "description": "Охлаждают напиток без льда. Выглядят стильно в любом баре.", "ozonLink": "https://takprdm.ru/0W944W81S0CNRX00/?redirectTo=https%3A%2F%2Fwww.wildberries.ru%2Fcatalog%2F200603612%2Fdetail.aspx&erid=Y1jgkD6uB6jK1phqkTLTbNJNEZjp"},
        {"title": "Непромокаемый рюкзак", "emoji": "🎒", "priceType": "premium", "description": "Защищает технику в дождь. Удобен для работы и путешествий.", "ozonLink": "https://takprdm.ru/0W944W82VmCjDtG0/?redirectTo=https%3A%2F%2Fwww.wildberries.ru%2Fcatalog%2F221256950%2Fdetail.aspx&erid=Y1jgkD6uB6jK1phqkTLTbNJPiD1a"},
        {"title": "Настольная игра-стратегия", "emoji": "🎲", "priceType": "budget", "description": "Тренирует логику. Объединяет друзей за одним столом.", "ozonLink": "https://takprdm.ru/0W944W82iWCiq4e0/?redirectTo=https%3A%2F%2Fwww.wildberries.ru%2Fcatalog%2F557293327%2Fdetail.aspx&erid=Y1jgkD6uB6jK1phqkTLTbNJNKvJZ"},
    ],
    "woman": [
        {"title": "Набор премиум-косметики", "emoji": "💄", "priceType": "premium", "description": "Дарит коже здоровье и сияние. Полный ритуал ухода в одной коробке.", "ozonLink": "https://ozon.ru/click/premium_cosmetics_set"},
        {"title": "Шарф из кашемира", "emoji": "🧣", "priceType": "middle", "description": "Согревает в холода. Добавляет образу элегантности и уюта.", "ozonLink": None},
        {"title": "Аромадиффузор с маслами", "emoji": "🕯️", "priceType": "middle", "description": "Наполняет дом приятными ароматами. Расслабляет после рабочего дня.", "ozonLink": "https://takprdm.ru/0W944W82IGCe47W0/?redirectTo=https%3A%2F%2Fwww.wildberries.ru%2Fcatalog%2F332858245%2Fdetail.aspx&erid=Y1jgkD6uB6jK1phqkTLTbNJNHZn6"},
        {"title": "Книга в коллекционном переплёте", "emoji": "📖", "priceType": "budget", "description": "Радует глаз и душу. Идеальный подарок для любительницы чтения.", "ozonLink": "https://takprdm.ru/0W944W82IGCeuJu0/?redirectTo=https%3A%2F%2Fwww.wildberries.ru%2Fcatalog%2F333489541%2Fdetail.aspx&erid=Y1jgkD6uB6jK1phqkTLTbNJNHZn6"},
        {"title": "Набор для домашнего спа", "emoji": "🧴", "priceType": "middle", "description": "Устраивает салонный уход дома. Пена, скраб, маска — всё включено.", "ozonLink": None},
        {"title": "Сумка-тоут из экокожи", "emoji": "👜", "priceType": "premium", "description": "Вместительная и стильная. Подходит и для офиса, и для прогулок.", "ozonLink": "https://takprdm.ru/0W944W82VmCjFCK0/?redirectTo=https%3A%2F%2Fwww.wildberries.ru%2Fcatalog%2F175293507%2Fdetail.aspx&erid=Y1jgkD6uB6jK1phqkTLTbNJPiD1a"},
        {"title": "Умное зеркало для макияжа", "emoji": "🪞", "priceType": "premium", "description": "Подсвечивает лицо, как в студии. Помогает наносить мейкап идеально.", "ozonLink": "https://takprdm.ru/0W944W82VmCiA9C0/?redirectTo=https%3A%2F%2Fwww.wildberries.ru%2Fcatalog%2F212800299%2Fdetail.aspx&erid=Y1jgkD6uB6jK1phqkTLTbNJPiD1a"},
        {"title": "Набор ароматических свечей", "emoji": "🕯️", "priceType": "budget", "description": "Создают романтическую атмосферу. Наполняют дом теплом и уютом.", "ozonLink": "https://takprdm.ru/0W944W82VmCh1yC0/?redirectTo=https%3A%2F%2Fwww.wildberries.ru%2Fcatalog%2F544808808%2Fdetail.aspx&erid=Y1jgkD6uB6jK1phqkTLTbNJPiD1a"},
        {"title": "Аромасаше для гардероба", "emoji": "🌼", "priceType": "budget", "description": "Пропитывают одежду нежным запахом. Больше не нужен освежитель.", "ozonLink": "https://takprdm.ru/0W944W82IGCdb180/?redirectTo=https%3A%2F%2Fwww.wildberries.ru%2Fcatalog%2F15861058%2Fdetail.aspx&erid=Y1jgkD6uB6jK1phqkTLTbNJNHZn6"},
        {"title": "Шёлковый шарф с принтом", "emoji": "🧣", "priceType": "middle", "description": "Добавляет яркий акцент любому наряду. Лёгкий, приятный на ощупь.", "ozonLink": None},
        {"title": "Автоматический массажёр для лица", "emoji": "💆‍♀️", "priceType": "middle", "description": "Разглаживает морщины, снимает отёки. Домашний SPA-ритуал.", "ozonLink": "https://takprdm.ru/0W944W82VmChOeG0/?redirectTo=https%3A%2F%2Fwww.wildberries.ru%2Fcatalog%2F30027837%2Fdetail.aspx&erid=Y1jgkD6uB6jK1phqkTLTbNJPiD1a"},
        {"title": "Натуральная косметика ручной работы", "emoji": "🧴", "priceType": "premium", "description": "Состоит из природных компонентов. Бережно ухаживает за кожей.", "ozonLink": None},
        {"title": "Фотоальбом в кожаном переплёте", "emoji": "🖼️", "priceType": "middle", "description": "Сохраняет важные моменты на десятилетия. Приятно перелистывать.", "ozonLink": "https://takprdm.ru/0W944W82VmChM9S0/?redirectTo=https%3A%2F%2Fwww.wildberries.ru%2Fcatalog%2F171594838%2Fdetail.aspx&erid=Y1jgkD6uB6jK1phqkTLTbNJPiD1a"},
        {"title": "Умные весы с анализом тела", "emoji": "⚖️", "priceType": "premium", "description": "Показывают процент жира, мышц, воды. Помогают следить за фигурой.", "ozonLink": None},
        {"title": "Набор чайных чашек", "emoji": "☕️", "priceType": "budget", "description": "Украшают чаепитие. Поднимают настроение с каждым глотком.", "ozonLink": "https://takprdm.ru/0W944W83fmCk2BS0/?redirectTo=https%3A%2F%2Fozon.ru%2Fproduct%2F726253681&erid=Y1jgkD6uB6jK1phqkTLTbNJPh84B"},
        {"title": "Браслет с гравировкой", "emoji": "💍", "priceType": "budget", "description": "Персональное послание на запястье. Носится каждый день как напоминание.", "ozonLink": "https://takprdm.ru/0W944W82iWCisBy0/?redirectTo=https%3A%2F%2Fwww.wildberries.ru%2Fcatalog%2F499688041%2Fdetail.aspx&erid=Y1jgkD6uB6jK1phqkTLTbNJNKvJZ"},
        {"title": "Эфирные масла и диффузор", "emoji": "🌿", "priceType": "middle", "description": "Расслабляют, улучшают сон, очищают воздух. Природная ароматерапия дома.", "ozonLink": "https://takprdm.ru/0W944W82VmCiRzS0/?redirectTo=https%3A%2F%2Fwww.wildberries.ru%2Fcatalog%2F191847454%2Fdetail.aspx&erid=Y1jgkD6uB6jK1phqkTLTbNJPiD1a"},
        {"title": "Сумка-шоппер из хлопка", "emoji": "🛍️", "priceType": "budget", "description": "Заменяет десятки пакетов. Экологично и стильно.", "ozonLink": "https://takprdm.ru/0W944W83fWCkSge0/?redirectTo=https%3A%2F%2Fozon.ru%2Fproduct%2F2796087514&erid=Y1jgkD6uB6jK1phqkTLTbNJPR5bp"},
        {"title": "Шёлковое постельное бельё", "emoji": "🛌", "priceType": "premium", "description": "Дарит королевский сон. Разглаживает волосы и кожу во время сна.", "ozonLink": None},
        {"title": "Отпариватель для одежды", "emoji": "💨", "priceType": "middle", "description": "Убирает складки за минуту. Не гладит, а парит — безопасно для любых тканей.", "ozonLink": "https://takprdm.ru/0W944W82VmCiIe40/?redirectTo=https%3A%2F%2Fwww.wildberries.ru%2Fcatalog%2F223294386%2Fdetail.aspx&erid=Y1jgkD6uB6jK1phqkTLTbNJPiD1a"},
        {"title": "Кулинарная книга шеф-повара", "emoji": "🍳", "priceType": "budget", "description": "Вдохновляет на новые рецепты. Превращает готовку в удовольствие.", "ozonLink": "https://takprdm.ru/0W944W82IGCdhzm0/?redirectTo=https%3A%2F%2Fwww.wildberries.ru%2Fcatalog%2F10976037%2Fdetail.aspx&erid=Y1jgkD6uB6jK1phqkTLTbNJNHZn6"},
        {"title": "Кисти для макияжа профессиональные", "emoji": "🪞", "priceType": "budget", "description": "Создают безупречный тон и растушёвку. Инструменты визажиста.", "ozonLink": "https://takprdm.ru/0W944W82IGCdR_80/?redirectTo=https%3A%2F%2Fwww.wildberries.ru%2Fcatalog%2F18572180%2Fdetail.aspx&erid=Y1jgkD6uB6jK1phqkTLTbNJNHZn6"},
        {"title": "Абонемент в СПА на месяц", "emoji": "🧖‍♀️", "priceType": "premium", "description": "Дарит полное расслабление и уход. Лучшее, что можно подарить себе.", "ozonLink": None},
    ],
    "child": [
        {"title": "Конструктор с дополненной реальностью", "emoji": "🧩", "priceType": "middle", "description": "Оживает на экране смартфона. Развивает логику и воображение.", "ozonLink": None},
        {"title": "Велосипед с доп. колёсами", "emoji": "🚲", "priceType": "middle", "description": "Учит кататься без страха. Дарит свободу движения и веселье.", "ozonLink": None},
        {"title": "Набор для научных опытов", "emoji": "🔬", "priceType": "budget", "description": "Пробуждает интерес к химии и физике. Можно вырастить кристаллы или извергнуть вулкан.", "ozonLink": "https://takprdm.ru/0W944W83fWCjxoO0/?redirectTo=https%3A%2F%2Fozon.ru%2Fproduct%2F2322967333&erid=Y1jgkD6uB6jK1phqkTLTbNJPR5bp"},
        {"title": "Интерактивный робот", "emoji": "🤖", "priceType": "middle", "description": "Программируется, танцует, отвечает на команды. Развивает алгоритмическое мышление.", "ozonLink": "https://takprdm.ru/0W944W83fWCjyVe0/?redirectTo=https%3A%2F%2Fozon.ru%2Fproduct%2F2419097064&erid=Y1jgkD6uB6jK1phqkTLTbNJPR5bp"},
        {"title": "Настольная игра для семьи", "emoji": "🎲", "priceType": "budget", "description": "Объединяет всех за одним столом. Учит стратегии и терпению.", "ozonLink": "https://takprdm.ru/0W944W83fWClEoa0/?redirectTo=https%3A%2F%2Fozon.ru%2Fproduct%2F2195914158&erid=Y1jgkD6uB6jK1phqkTLTbNJPR5bp"},
        {"title": "Рюкзак с 3D-принтом", "emoji": "🎒", "priceType": "budget", "description": "Яркий и практичный. Ребёнок сам захочет собираться в школу.", "ozonLink": "https://takprdm.ru/0W944W82VmCjDtm0/?redirectTo=https%3A%2F%2Fwww.wildberries.ru%2Fcatalog%2F176375498%2Fdetail.aspx&erid=Y1jgkD6uB6jK1phqkTLTbNJPiD1a"},
        {"title": "Набор для рисования светом", "emoji": "✨", "priceType": "middle", "description": "Создаёт картины в воздухе. Тренирует мелкую моторику и фантазию.", "ozonLink": "https://takprdm.ru/0W944W82rWCjHvy0/?redirectTo=https%3A%2F%2Fozon.ru%2Fproduct%2F907937364&erid=Y1jgkD6uB6jK1phqkTLTbNJPRRcZ"},
        {"title": "Самокат детский", "emoji": "🛴", "priceType": "middle", "description": "Безопасен вечером благодаря ярким огням. Дарит радость от катания.", "ozonLink": "https://takprdm.ru/0W944W82qmCj8e40/?redirectTo=https%3A%2F%2Fozon.ru%2Fproduct%2F995363766&erid=Y1jgkD6uB6jK1phqkTLTbNJPQ13N"},
        {"title": "Пищевые фломастеры", "emoji": "🎨", "priceType": "budget", "description": "Безопасные, яркие цвета. Для рисования на еде и украшения десертов.", "ozonLink": "https://takprdm.ru/0W944W82IGCf8di0/?redirectTo=https%3A%2F%2Fwww.wildberries.ru%2Fcatalog%2F166651319%2Fdetail.aspx&erid=Y1jgkD6uB6jK1phqkTLTbNJNHZn6"},
        {"title": "Обучающая игрушка", "emoji": "🤖", "priceType": "middle", "description": "Знакомит с буквами и цифрами через игру. Говорит, поёт, задаёт загадки.", "ozonLink": "https://takprdm.ru/0W944W81mGCVs_W0/?redirectTo=https%3A%2F%2Fwww.wildberries.ru%2Fcatalog%2F143361615%2Fdetail.aspx&erid=Y1jgkD6uB6jK1phqkTLTbNJNJEaJ"},
        {"title": "Пазл «Космос» 1000 деталей", "emoji": "🧩", "priceType": "middle", "description": "Развивает усидчивость. Итоговая картина украсит стену.", "ozonLink": "https://takprdm.ru/0W944W81mGCUalC0/?redirectTo=https%3A%2F%2Fwww.wildberries.ru%2Fcatalog%2F523237171%2Fdetail.aspx&erid=Y1jgkD6uB6jK1phqkTLTbNJNJEaJ"},
        {"title": "Детский микроскоп", "emoji": "🔬", "priceType": "premium", "description": "Показывает невидимый мир. В комплекте готовые образцы для изучения.", "ozonLink": "https://takprdm.ru/0W944W82IGCej4a0/?redirectTo=https%3A%2F%2Fwww.wildberries.ru%2Fcatalog%2F334104537%2Fdetail.aspx&erid=Y1jgkD6uB6jK1phqkTLTbNJNHZn6"},
        {"title": "Надувной бассейн", "emoji": "🏊", "priceType": "budget", "description": "Спасает в жару на даче. Легко надувается и складывается.", "ozonLink": None},
        {"title": "Набор для слаймов", "emoji": "🤲", "priceType": "budget", "description": "Позволяет создать игрушку своими руками. Занимает детей на часы.", "ozonLink": "https://takprdm.ru/0W944W82rWCjLLO0/?redirectTo=https%3A%2F%2Fozon.ru%2Fproduct%2F3552576523&erid=Y1jgkD6uB6jK1phqkTLTbNJPRRcZ"},
        {"title": "Велосипед с защитной экипировкой", "emoji": "🚴", "priceType": "premium", "description": "Полный комплект для безопасного катания. Шлем, наколенники, налокотники.", "ozonLink": None},
        {"title": "Конструктор с моторами", "emoji": "🧱", "priceType": "middle", "description": "Позволяет собрать действующие механизмы. Развивает инженерное мышление.", "ozonLink": "https://takprdm.ru/0W944W83fWCmfla0/?redirectTo=https%3A%2F%2Fozon.ru%2Fproduct%2F2299537421&erid=Y1jgkD6uB6jK1phqkTLTbNJPR5bp"},
        {"title": "Обучающий планшет для изучения английского", "emoji": "🗣️", "priceType": "budget", "description": "Учит новым словам в увлекательной форме. Подходит для всей семьи.", "ozonLink": "https://takprdm.ru/0W944W82IGCeSiW0/?redirectTo=https%3A%2F%2Fwww.wildberries.ru%2Fcatalog%2F333466588%2Fdetail.aspx&erid=Y1jgkD6uB6jK1phqkTLTbNJNHZn6"},
        {"title": "Проектор звёздного неба", "emoji": "🌠", "priceType": "middle", "description": "Превращает потолок в космос. Успокаивает перед сном.", "ozonLink": "https://takprdm.ru/0W944W83fWClGj40/?redirectTo=https%3A%2F%2Fozon.ru%2Fproduct%2F2195918255&erid=Y1jgkD6uB6jK1phqkTLTbNJPR5bp"},
        {"title": "Набор для выращивания кристаллов", "emoji": "💎", "priceType": "budget", "description": "Настоящая научная лаборатория дома. Выращивает сверкающие кристаллы за несколько дней.", "ozonLink": "https://takprdm.ru/0W944W83fWCkZia0/?redirectTo=https%3A%2F%2Fozon.ru%2Fproduct%2F2042146146&erid=Y1jgkD6uB6jK1phqkTLTbNJPR5bp"},
        {"title": "Мягкие кубики с буквами", "emoji": "🅰️", "priceType": "middle", "description": "Безопасны даже для самых маленьких. Помогают выучить алфавит.", "ozonLink": "https://takprdm.ru/0W944W81mWCVJBy0/?redirectTo=https%3A%2F%2Fwww.wildberries.ru%2Fcatalog%2F99808168%2Fdetail.aspx&erid=Y1jgkD6uB6jK1phqkTLTbNJPQ55b"},
        {"title": "Робот-трансформер", "emoji": "🤖", "priceType": "middle", "description": "Превращается в машину. Управляется дистанционно, участвует в битвах.", "ozonLink": "https://takprdm.ru/0W944W83fWCmfkS0/?redirectTo=https%3A%2F%2Fozon.ru%2Fproduct%2F2195932914&erid=Y1jgkD6uB6jK1phqkTLTbNJPR5bp"},
        {"title": "Акварельные краски и кисти", "emoji": "🖌️", "priceType": "budget", "description": "Позволяют делать первые шаги в живописи. Яркие цвета, хорошее качество.", "ozonLink": "https://takprdm.ru/0W944W82VmChGDS0/?redirectTo=https%3A%2F%2Fwww.wildberries.ru%2Fcatalog%2F14089786%2Fdetail.aspx&erid=Y1jgkD6uB6jK1phqkTLTbNJPiD1a"},
        {"title": "Интерактивный глобус", "emoji": "🌍", "priceType": "premium", "description": "Интерактивный вращающийся глобус. Наглядно показывает страны и океаны.", "ozonLink": "https://takprdm.ru/0W944W82rWCjKZO0/?redirectTo=https%3A%2F%2Fozon.ru%2Fproduct%2F1652106182&erid=Y1jgkD6uB6jK1phqkTLTbNJPRRcZ"},
    ],
    "colleague": [
        {"title": "Беспроводная зарядная станция", "emoji": "🔋", "priceType": "middle", "description": "Заряжает телефон, часы, наушники одновременно. Избавляет от проводов на столе.", "ozonLink": None},
        {"title": "Ежедневник с персонализацией", "emoji": "📓", "priceType": "budget", "description": "Помогает не забывать о задачах. Можно добавить имя или логотип.", "ozonLink": "https://takprdm.ru/0W944W83fWCjzq80/?redirectTo=https%3A%2F%2Fozon.ru%2Fproduct%2F2669546666&erid=Y1jgkD6uB6jK1phqkTLTbNJPR5bp"},
        {"title": "Кружка-хамелеон", "emoji": "☕", "priceType": "budget", "description": "Меняет цвет от горячего напитка. Поднимает настроение в офисе.", "ozonLink": "https://takprdm.ru/0W944W82VmCiLsm0/?redirectTo=https%3A%2F%2Fwww.wildberries.ru%2Fcatalog%2F15462468%2Fdetail.aspx&erid=Y1jgkD6uB6jK1phqkTLTbNJPiD1a"},
        {"title": "Органайзер для канцелярии", "emoji": "🗂️", "priceType": "budget", "description": "Наводит порядок в ящиках стола. Всё для ручек, стикеров и скрепок.", "ozonLink": "https://takprdm.ru/0W944W83fWCj_8u0/?redirectTo=https%3A%2F%2Fozon.ru%2Fproduct%2F3461435095&erid=Y1jgkD6uB6jK1phqkTLTbNJPR5bp"},
        {"title": "Беспроводная мышь эргономичная", "emoji": "🖱️", "priceType": "middle", "description": "Снимает нагрузку с запястья. Удобна при долгой работе за компьютером.", "ozonLink": "https://takprdm.ru/0W944W82VmCiQxC0/?redirectTo=https%3A%2F%2Fwww.wildberries.ru%2Fcatalog%2F139276681%2Fdetail.aspx&erid=Y1jgkD6uB6jK1phqkTLTbNJPiD1a"},
        {"title": "Облачное хранилище (подписка)", "emoji": "💾", "priceType": "budget", "description": "Дополнительные гигабайты для файлов. Доступно с любого устройства.", "ozonLink": None},
        {"title": "Мини-увлажнитель воздуха", "emoji": "💨", "priceType": "middle", "description": "Убирает пыль и аллергены. Делает воздух свежим даже в маленьком кабинете.", "ozonLink": "https://takprdm.ru/0W944W82VmCiJ7u0/?redirectTo=https%3A%2F%2Fwww.wildberries.ru%2Fcatalog%2F178300578%2Fdetail.aspx&erid=Y1jgkD6uB6jK1phqkTLTbNJPiD1a"},
        {"title": "USB-хаб на 4 порта", "emoji": "💻", "priceType": "middle", "description": "Решает проблему нехватки разъёмов. Подключайте флешки, мышь, клавиатуру одновременно.", "ozonLink": "https://takprdm.ru/0W944W82VmCiXXu0/?redirectTo=https%3A%2F%2Fwww.wildberries.ru%2Fcatalog%2F208261896%2Fdetail.aspx&erid=Y1jgkD6uB6jK1phqkTLTbNJPiD1a"},
        {"title": "Коврик для мыши с принтом", "emoji": "🖱️", "priceType": "budget", "description": "Добавляет индивидуальности рабочему месту. Можно заказать свой дизайн.", "ozonLink": "https://takprdm.ru/0W944W82VmChiL80/?redirectTo=https%3A%2F%2Fwww.wildberries.ru%2Fcatalog%2F186943497%2Fdetail.aspx&erid=Y1jgkD6uB6jK1phqkTLTbNJPiD1a"},
        {"title": "Маркеры для флипчарта", "emoji": "🖍️", "priceType": "budget", "description": "Яркие, не выцветают, легко стираются. Идеальны для презентаций и мозговых штурмов.", "ozonLink": "https://takprdm.ru/0W944W83fWCj-5e0/?redirectTo=https%3A%2F%2Fozon.ru%2Fproduct%2F2883452453&erid=Y1jgkD6uB6jK1phqkTLTbNJPR5bp"},
        {"title": "Умная лампа с регулировкой яркости", "emoji": "💡", "priceType": "premium", "description": "Создаёт комфортный свет для работы. Не напрягает глаза даже вечером.", "ozonLink": "https://takprdm.ru/0W944W82VmCiO2i0/?redirectTo=https%3A%2F%2Fwww.wildberries.ru%2Fcatalog%2F171379394%2Fdetail.aspx&erid=Y1jgkD6uB6jK1phqkTLTbNJPiD1a"},
        {"title": "Портативный сканер", "emoji": "🖨️", "priceType": "premium", "description": "Цифрует документы за секунды. Компактный, помещается в сумку.", "ozonLink": None},
        {"title": "Ежедневник в кожаном переплёте", "emoji": "🗓️", "priceType": "middle", "description": "Превращает планирование в ритуал. Стильный аксессуар для статусного человека.", "ozonLink": "https://takprdm.ru/0W944W82IGCdVjm0/?redirectTo=https%3A%2F%2Fwww.wildberries.ru%2Fcatalog%2F51887588%2Fdetail.aspx&erid=Y1jgkD6uB6jK1phqkTLTbNJNHZn6"},
        {"title": "Наушники для конференций", "emoji": "🎧", "priceType": "premium", "description": "Отсекают шум, передают голос чётко. Идеальны для удалённой работы.", "ozonLink": "https://takprdm.ru/0W944W82VmCiDGq0/?redirectTo=https%3A%2F%2Fwww.wildberries.ru%2Fcatalog%2F208216536%2Fdetail.aspx&erid=Y1jgkD6uB6jK1phqkTLTbNJPiD1a"},
        {"title": "Оригинальные ручки", "emoji": "✒️", "priceType": "budget", "description": "Универсальный выбор. Приятно писать, поднимают настроение.", "ozonLink": "https://takprdm.ru/0W944W82rWCjNVC0/?redirectTo=https%3A%2F%2Fozon.ru%2Fproduct%2F2824284705&erid=Y1jgkD6uB6jK1phqkTLTbNJPRRcZ"},
        {"title": "Подставка для смартфона", "emoji": "📱", "priceType": "budget", "description": "Удобно для видеозвонков. Освобождает руки.", "ozonLink": "https://takprdm.ru/0W944W83fWCj-je0/?redirectTo=https%3A%2F%2Fozon.ru%2Fproduct%2F2923468514&erid=Y1jgkD6uB6jK1phqkTLTbNJPR5bp"},
        {"title": "Набор стикеров для заметок", "emoji": "📋", "priceType": "budget", "description": "Яркие, разных цветов. Не дают забыть важные задачи.", "ozonLink": "https://takprdm.ru/0W944W82IGCeCUe0/?redirectTo=https%3A%2F%2Fwww.wildberries.ru%2Fcatalog%2F12994162%2Fdetail.aspx&erid=Y1jgkD6uB6jK1phqkTLTbNJNHZn6"},
        {"title": "Термокружка с логотипом", "emoji": "☕", "priceType": "budget", "description": "Корпоративный подарок, который используют каждый день. Долго сохраняет тепло.", "ozonLink": "https://takprdm.ru/0W944W83fmCk4400/?redirectTo=https%3A%2F%2Fozon.ru%2Fproduct%2F3285150867&erid=Y1jgkD6uB6jK1phqkTLTbNJPh84B"},
        {"title": "Настольный органайзер", "emoji": "🗂️", "priceType": "budget", "description": "Убирает беспорядок на столе. Отсеки для документов, визитниц, телефона.", "ozonLink": "https://takprdm.ru/0W944W82IGCe6K40/?redirectTo=https%3A%2F%2Fwww.wildberries.ru%2Fcatalog%2F135927753%2Fdetail.aspx&erid=Y1jgkD6uB6jK1phqkTLTbNJNHZn6"},
        {"title": "Подставка для ног эргономичная", "emoji": "🦶", "priceType": "budget", "description": "Снижает нагрузку на спину. Помогает сохранять правильную позу.", "ozonLink": "https://takprdm.ru/0W944W82VmChudu0/?redirectTo=https%3A%2F%2Fwww.wildberries.ru%2Fcatalog%2F61336211%2Fdetail.aspx&erid=Y1jgkD6uB6jK1phqkTLTbNJPiD1a"},
    ],
}
PRICE_LABELS = {"budget": "бюджетная", "middle": "средняя", "premium": "премиум"}
CATEGORIES = {"man": "👔 Мужчине", "woman": "🌸 Женщине", "child": "🧸 Ребёнку", "colleague": "🤝 Коллеге"}

def get_random_gift(category: str, price_filter: str = None) -> dict:
    gifts = GIFTS_DB.get(category, [])
    if not gifts:
        return {"title": "Скоро добавим идеи", "emoji": "🎁", "priceType": "", "description": "Выберите другую категорию.", "ozonLink": None}
    if price_filter:
        filtered = [g for g in gifts if g.get("priceType") == price_filter]
        if filtered:
            gifts = filtered
    return random.choice(gifts)

def format_gift_message(gift: dict) -> str:
    price_label = PRICE_LABELS.get(gift.get("priceType", ""), "")
    price_line = f"💰 Стоимость: {price_label}\n" if price_label else ""
    base = f"{gift['emoji']} *{gift['title']}*\n{price_line}\n{gift['description']}"
    if gift.get("ozonLink"):
        base += f"\n\n[Купить →]({gift['ozonLink']})"
    return base

def get_main_keyboard(user_id: int) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(label, callback_data=f"cat:{key}")] for key, label in CATEGORIES.items()]
    if user_premium.get(user_id, False):
        current_filter = user_filters.get(user_id)
        if current_filter:
            filter_label = f"🎯 Фильтр: {PRICE_LABELS.get(current_filter, current_filter)}"
        else:
            filter_label = "🎯 Фильтр по бюджету"
        buttons.append([InlineKeyboardButton(filter_label, callback_data="filter")])
    # Кнопка поддержки для всех пользователей
    buttons.append([InlineKeyboardButton("📞 Поддержка", callback_data="support")])
    return InlineKeyboardMarkup(buttons)

def build_gift_keyboard(category: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎲 Ещё идея", callback_data=f"cat:{category}")],
        [InlineKeyboardButton("↩️ Выбрать категорию", callback_data="menu")],
    ])

# ============================================================
# ОБРАБОТЧИКИ КОМАНД
# ============================================================

async def start(update: Update, context):
    user_id = update.effective_user.id
    if user_id not in user_requests:
        user_requests[user_id] = 0
    if user_id not in user_last_date:
        user_last_date[user_id] = date.today().isoformat()
    await update.message.reply_text(
        "🎁 *Подарочный гуру*\n\nПривет! 5 идей — в подарок от меня. Хочешь ещё? Премиум за 199 ₽.\n\nВыбери категорию 👇",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(user_id),
    )

async def help_command(update: Update, context):
    user_id = update.effective_user.id
    await update.message.reply_text(
        "🎁 *Подарочный гуру*\n\nКоманды:\n/start — главное меню\n/help — это сообщение\n/premium — купить безлимит\n/support — связаться с администратором\n\nБесплатно 5 идей в день. Премиум даёт безлимит и фильтр по бюджету.",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(user_id),
    )

async def premium(update: Update, context):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    title = "✨ Премиум-доступ ✨"
    description = "Безлимит идей подарков + фильтр по бюджету"
    payload = f"premium_{user_id}"
    currency = "RUB"
    # цена 19900 копеек = 199 руб (или 8000 для теста)
    prices = [LabeledPrice("Премиум-доступ (30 дней)", 19900)]
    
    await context.bot.send_invoice(
        chat_id=chat_id,
        title=title,
        description=description,
        payload=payload,
        provider_token=os.environ.get("PROVIDER_TOKEN"),
        currency=currency,
        prices=prices,
        start_parameter=f"premium_{user_id}_{uuid.uuid4().hex[:8]}",
        need_email=True,
        need_phone_number=True
    )

async def pre_checkout_handler(update: Update, context):
    query = update.pre_checkout_query
    await query.answer(ok=True)

async def successful_payment_handler(update: Update, context):
    user_id = update.effective_user.id
    add_premium_user(user_id)
    user_premium[user_id] = True
    user_requests[user_id] = 0
    await update.message.reply_text(
        "✅ *Оплата прошла успешно!*\n\nПремиум-доступ активирован. Спасибо за поддержку! 🎉",
        parse_mode="Markdown"
    )

async def activate_premium(update: Update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Нет прав.")
        return
    try:
        user_id = int(context.args[0])
        add_premium_user(user_id)
        user_premium[user_id] = True
        user_requests[user_id] = 0
        await update.message.reply_text(f"✅ Премиум активирован для {user_id}!")
    except (IndexError, ValueError):
        await update.message.reply_text("❗ Используйте: /activate ID")

async def support(update: Update, context):
    await update.message.reply_text(
        "📧 *Поддержка*\n\n"
        "Если возникли вопросы или проблемы с оплатой – пишите на почту:\n\n"
        "[maryaninovan@mail.ru](mailto:maryaninovan@mail.ru)",
        parse_mode="Markdown",
        disable_web_page_preview=True
    )

async def button_callback(update: Update, context):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id
    premium_active = user_premium.get(user_id, False)

    if data == "menu":
        await query.edit_message_text(
            "🎁 *Подарочный гуру*\n\nВыбери категорию:",
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
            "🎯 *Выберите бюджет*:",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        return

    if data.startswith("filter_"):
        ftype = data.split("_")[1]
        if ftype == "budget":
            user_filters[user_id] = 'budget'
            text = "✅ Установлен бюджетный фильтр (до 1500 ₽)"
        elif ftype == "middle":
            user_filters[user_id] = 'middle'
            text = "✅ Установлен средний фильтр (1500-5000 ₽)"
        elif ftype == "premium":
            user_filters[user_id] = 'premium'
            text = "✅ Установлен премиум фильтр (от 5000 ₽)"
        elif ftype == "off":
            user_filters[user_id] = None
            text = "✅ Фильтр отключён"
        else:
            text = "❌ Неизвестный фильтр"
        await query.edit_message_text(
            text + "\n\nТеперь бот будет учитывать ваш бюджет.",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard(user_id)
        )
        return

    if data == "support":
        await query.edit_message_text(
            "📧 *Связь со мной*\n\n"
            "Если возникли вопросы или проблемы с оплатой – пишите на почту:\n\n"
            "[maryaninovan@mail.ru](mailto:maryaninovan@mail.ru)",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard(user_id),
            disable_web_page_preview=True
        )
        return

    if data.startswith("cat:"):
        category = data.split(":", 1)[1]
        if not premium_active:
            today = date.today().isoformat()
            last = user_last_date.get(user_id)
            if last != today:
                user_requests[user_id] = 0
                user_last_date[user_id] = today
            count = user_requests.get(user_id, 0)
            if count >= MAX_FREE:
                await query.edit_message_text(
                    "❌ *Лимит бесплатных идей на сегодня исчерпан!*\n\nОформи премиум за 199 ₽: /premium",
                    parse_mode="Markdown",
                    reply_markup=get_main_keyboard(user_id),
                )
                return
            user_requests[user_id] = count + 1
        price_filter = user_filters.get(user_id) if premium_active else None
        if price_filter not in ('budget', 'middle', 'premium'):
            price_filter = None
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

async def error_handler(update: object, context):
    if isinstance(context.error, Conflict):
        logger.warning("Conflict: another bot instance is running with this token.")
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
    init_db()
    global user_premium
    user_premium = load_premium_users()

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set")
    provider_token = os.environ.get("PROVIDER_TOKEN")
    if not provider_token:
        raise RuntimeError("PROVIDER_TOKEN not set")

    application = Application.builder().token(token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("premium", premium))
    application.add_handler(CommandHandler("activate", activate_premium))
    application.add_handler(CommandHandler("support", support))
    application.add_handler(PreCheckoutQueryHandler(pre_checkout_handler))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler))
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
