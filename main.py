# <--------------- MewMusic --------------->
import os
import sqlite3
import telebot
from telebot import types
from datetime import datetime
from dotenv import load_dotenv
from collections import Counter

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN)

ADMINS = [8476695954]

#pip install -r requirements.txt


# <--------------- SQL Database --------------->
DB_NAME = "mewmusic.db"

def init_db():
    """Инициализация всех таблиц базы данных"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # 1. Таблица Users (Основная информация)
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY, 
                    username TEXT, 
                    reg_date TEXT
                )''')

    # 2. Таблица Stats (Детальная статистика пользователя)
    # Поля genres, languages и liked_ids хранят данные в формате строк через запятую
    c.execute('''CREATE TABLE IF NOT EXISTS stats (
                    user_id INTEGER PRIMARY KEY, 
                    total_listens INTEGER DEFAULT 0, 
                    genres TEXT DEFAULT '', 
                    languages TEXT DEFAULT '', 
                    liked_songs_count INTEGER DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )''')

    # 3. Таблица Music (Репозиторий песен)
    # song_id хранится как TEXT для поддержки формата 000001
    c.execute('''CREATE TABLE IF NOT EXISTS music (
                    song_id TEXT PRIMARY KEY, 
                    title TEXT, 
                    artist TEXT, 
                    url TEXT, 
                    albums TEXT, 
                    genre TEXT, 
                    language TEXT,
                    listens INTEGER DEFAULT 0, 
                    reactions INTEGER DEFAULT 0
                )''')

    # 4. Таблица Favorites (Связь пользователей и избранных песен)
    c.execute('''CREATE TABLE IF NOT EXISTS favorites (
                    user_id INTEGER, 
                    song_id TEXT, 
                    PRIMARY KEY (user_id, song_id),
                    FOREIGN KEY (user_id) REFERENCES users (user_id),
                    FOREIGN KEY (song_id) REFERENCES music (song_id)
                )''')

    conn.commit()
    conn.close()
    print("База данных MewMusic успешно инициализирована.")

# <--------------- Функции взаимодействия --------------->

def get_next_song_id():
    """Генерирует следующий ID в формате 000 001"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM music")
    count = c.fetchone()[0] + 1
    conn.close()
    return f"{count:06d}"

def db_register_user(user_id, username):
    """Регистрация пользователя и создание пустой статистики"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    now = datetime.now().strftime("%d.%m.%Y")
    c.execute("INSERT OR IGNORE INTO users (user_id, username, reg_date) VALUES (?, ?, ?)", 
              (user_id, username, now))
    c.execute("INSERT OR IGNORE INTO stats (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def db_add_song(title, artist, url, genre, lang, album_id):
    """Добавление новой песни в базу"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    new_id = get_next_song_id()
    c.execute("""INSERT INTO music (song_id, title, artist, url, genre, language, albums) 
                 VALUES (?, ?, ?, ?, ?, ?, ?)""", 
              (new_id, title, artist, url, genre, lang, album_id))
    conn.commit()
    conn.close()
    return new_id

def db_log_listen(user_id, song_id, genre, lang):
    """Логирование прослушивания: +1 к песне и +1 к юзеру"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # Обновляем глобальные прослушивания песни
    c.execute("UPDATE music SET listens = listens + 1 WHERE song_id = ?", (song_id,))
    # Обновляем статы юзера
    c.execute("UPDATE stats SET total_listens = total_listens + 1 WHERE user_id = ?", (user_id,))
    
    # Логика добавления жанра в историю для рекомендаций (упрощенно)
    c.execute("SELECT genres FROM stats WHERE user_id = ?", (user_id,))
    res = c.fetchone()
    if res:
        current_genres = res[0]
        updated_genres = f"{current_genres},{genre}".strip(",")
        c.execute("UPDATE stats SET genres = ? WHERE user_id = ?", (updated_genres, user_id))
        
    conn.commit()
    conn.close()

# Запуск инициализации при импорте/запуске файла
if __name__ == "__main__":
    init_db()



# <--------------- Bot Commands --------------->
@bot.message_handler(commands=['start', 'menu'])
def send_welcome(message):
    """Приветствие и вывод списка команд"""
    # Регистрируем пользователя в базе данных
    db_register_user(message.from_user.id, message.from_user.username)
    
    # Красиво оформленный текст с использованием Markdown
    welcome_text = (
        f"✨ *Welcome to MewMusic, {message.from_user.first_name}!* ✨\n\n"
        "I'm your personal music assistant. Here is what I can do:\n\n"
        "🎵 *Music Discovery*\n"
        "— /search : Find tracks by name or artist\n"
        "— /random : Get 25 random songs from our library\n"
        "— /id `[ID]` : Get a specific song (`+000001`) or album (`-001`)\n\n"
        "🎧 *Personalized*\n"
        "— /reco : Smart recommendations based on your taste\n"
        "— /favorites : Your liked collection\n"
        "— /stats : Your listening insights and top genres\n\n"
        "⚙️ *System*\n"
        "— /menu : Show this list of commands\n"
        "— /add : Add new music (Admin only)\n\n"
        "*Ready to dive into the sound?* 🐾"
    )
    
    # Отправляем сообщение с поддержкой Markdown
    bot.send_message(
        message.chat.id, 
        welcome_text, 
        parse_mode='Markdown'
    )

@bot.message_handler(commands=['search'])
def search_command(message):
    """Шаг 1: Инициация поиска"""
    msg = bot.send_message(
        message.chat.id, 
        "🔍 *What are we looking for?*\nSend me the name of the song or the artist:", 
        parse_mode='Markdown'
    )
    # Регистрируем следующий шаг: ждем текст от пользователя
    bot.register_next_step_handler(msg, perform_search_logic)

def perform_search_logic(message):
    """Шаг 2: Обработка текста и выдача результата"""
    search_query = message.text
    if not search_query:
        return # Если пользователь прислал не текст

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Ищем совпадения (первые 5)
    sql_query = f"%{search_query}%"
    c.execute("""SELECT song_id, title, artist, url, genre, language 
                 FROM music 
                 WHERE title LIKE ? OR artist LIKE ? 
                 LIMIT 5""", (sql_query, sql_query))
    results = c.fetchall()
    
    if not results:
        bot.send_message(message.chat.id, "😿 *Nothing found.* Try another keywords!", parse_mode='Markdown')
    else:
        bot.send_message(message.chat.id, f"✅ *Found {len(results)} tracks for you:*", parse_mode='Markdown')
        
        for res in results:
            s_id, title, artist, post_url, genre, lang = res
            
            # Подпись к файлу
            caption = (
                f"🎵 *{artist} — {title}*\n"
                f"🆔 ID: `+{s_id}`\n"
                f"📂 Genre: {genre} | 🌍: {lang}"
            )

            # Создаем кнопку под песней
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔥 Add to Favorites", callback_data=f"like_{s_id}"))

            # Пытаемся отправить файл через copy_message из канала
            try:
                # Парсим ID сообщения из ссылки (последняя часть URL)
                msg_id = int(post_url.split('/')[-1])
                # Канал (предпоследняя часть URL)
                chat_id = post_url.split('/')[-2]
                
                # Формируем правильный ID чата (если это публичный канал — через @)
                from_chat = f"@{chat_id}" if not chat_id.isdigit() else f"-100{chat_id}"

                bot.copy_message(
                    chat_id=message.chat.id,
                    from_chat_id=from_chat,
                    message_id=msg_id,
                    caption=caption,
                    parse_mode="Markdown",
                    reply_markup=markup
                )
                
                # Записываем прослушивание в базу
                db_log_listen(message.from_user.id, s_id, genre, lang)

            except Exception as e:
                # Если не получилось переслать, просто даем инфу текстом
                bot.send_message(message.chat.id, f"⚠️ *Track found but cannot be sent:*\n{caption}", 
                                 parse_mode='Markdown', reply_markup=markup)
                print(f"Error copying message: {e}")

    conn.close()

@bot.message_handler(commands=['id'])
def find_by_id(message):
    """Поиск по ID: +ID для одной песни, -ID для альбома"""
    try:
        # Разбиваем сообщение, чтобы получить только ID (например, +000001)
        raw_id = message.text.split()[1]
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        
        # --- ЛОГИКА АЛЬБОМА (начинается с '-') ---
        if raw_id.startswith('-'):
            album_id = raw_id[1:] # Убираем минус
            c.execute("SELECT song_id, title, artist FROM music WHERE albums LIKE ?", (f"%{album_id}%",))
            tracks = c.fetchall()
            
            if tracks:
                res_text = f"💿 *Album {album_id} tracks:*\n\n"
                for t in tracks:
                    res_text += f"• `+{t[0]}` {t[2]} - {t[1]}\n"
                res_text += "\n_Type /id +ID to get the track_"
                bot.send_message(message.chat.id, res_text, parse_mode="Markdown")
            else:
                bot.reply_to(message, "❌ *Album not found.*", parse_mode="Markdown")

        # --- ЛОГИКА ПЕСНИ (начинается с '+') ---
        elif raw_id.startswith('+'):
            song_id = raw_id[1:] # Убираем плюс
            c.execute("SELECT * FROM music WHERE song_id = ?", (song_id,))
            song = c.fetchone()
            
            if song:
                # song_id=0, title=1, artist=2, url=3, albums=4, genre=5, lang=6
                caption = f"🎵 *{song[2]} — {song[1]}*\n🆔 ID: `+{song[0]}`\n📂 Genre: {song[5]}"
                
                # Кнопка избранного
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("🔥 Add to Favorites", callback_data=f"like_{song[0]}"))

                try:
                    # Пересылка из ТГК (парсим URL из БД)
                    url_parts = song[3].split('/')
                    msg_id = int(url_parts[-1])
                    chat_handle = url_parts[-2]
                    from_chat = f"@{chat_handle}" if not chat_handle.isdigit() else f"-100{chat_handle}"

                    bot.copy_message(
                        chat_id=message.chat.id,
                        from_chat_id=from_chat,
                        message_id=msg_id,
                        caption=caption,
                        parse_mode="Markdown",
                        reply_markup=markup
                    )
                    # Логируем прослушивание
                    db_log_listen(message.from_user.id, song_id, song[5], song[6])
                except:
                    bot.send_message(message.chat.id, f"⚠️ Track data exists, but file is missing:\n{caption}", 
                                     parse_mode="Markdown", reply_markup=markup)
            else:
                bot.reply_to(message, "❌ *Song ID not found.*", parse_mode="Markdown")
        
        else:
            bot.reply_to(message, "❓ Use `+` for song or `-` for album. Example: `/id +000001`", parse_mode="Markdown")
            
        conn.close()
    except IndexError:
        bot.reply_to(message, "❗ Please provide an ID. Example: `/id +000001`", parse_mode="Markdown")
    except Exception as e:
        print(f"Error in /id: {e}")
        bot.reply_to(message, "🛡️ An error occurred while fetching ID.")

@bot.message_handler(commands=['stats'])
def show_stats(message):
    """Вывод детальной статистики пользователя"""
    user_id = message.from_user.id
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Получаем данные из таблицы stats и дату регистрации из users
    c.execute("""SELECT s.total_listens, s.genres, s.liked_songs_count, u.reg_date 
                 FROM stats s 
                 JOIN users u ON s.user_id = u.user_id 
                 WHERE s.user_id = ?""", (user_id,))
    data = c.fetchone()
    conn.close()

    if data:
        total_listens, genres_str, liked_count, reg_date = data
        
        # Анализируем топ жанров
        top_genres_text = "None yet 🎧"
        if genres_str:
            # Превращаем строку "Pop,Rock,Pop" в список и считаем частоту
            genres_list = [g.strip() for g in genres_str.split(',') if g.strip()]
            genre_counts = Counter(genres_list).most_common(3) # Берем топ-3
            top_genres_text = ", ".join([f"{g[0]} ({g[1]})" for g in genre_counts])

        # Формируем красивый отчет
        stats_msg = (
            f"📊 *Personal Statistics for {message.from_user.first_name}*\n"
            f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            f"📅 *Member since:* `{reg_date}`\n"
            f"🎧 *Total Listens:* `{total_listens}`\n"
            f"❤️ *Favorite Songs:* `{liked_count}`\n\n"
            f"🔝 *Your Top Genres:*\n_{top_genres_text}_\n"
            f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            f"Keep listening to unlock more insights! 🐾"
        )
        
        bot.send_message(message.chat.id, stats_msg, parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, "❌ Stats not found. Try /start first!")

@bot.message_handler(commands=['add'])
def add_song_command(message):
    """
    Добавление новой песни администратором.
    Формат: /add URL | Title | Artist | Genre | Lang | AlbumID
    """
    
    # 1. Проверка прав (твой ID должен быть в списке ADMINS в начале файла)
    if message.from_user.id not in ADMINS:
        bot.reply_to(message, "❌ *Access Denied.* Вы не являетесь администратором.", parse_mode="Markdown")
        return

    try:
        # 2. Очищаем текст от команды и разбиваем по разделителю |
        raw_text = message.text.replace('/add', '').strip()
        
        # Если текста после /add нет совсем
        if not raw_text:
            raise ValueError("Empty command")

        # Разделяем и сразу убираем лишние пробелы по краям каждого элемента
        parts = [item.strip() for item in raw_text.split('|')]

        # 3. Проверяем, все ли 6 аргументов на месте
        if len(parts) < 6:
            bot.reply_to(
                message, 
                "⚠️ *Ошибка формата!*\n\n"
                "Вы ввели не все данные. Нужно 6 полей, разделенных `|`.\n"
                "Пример:\n`/add Ссылка | Название | Артист | Рок | EN | 001`",
                parse_mode="Markdown"
            )
            return

        # Распаковываем данные в переменные
        url, title, artist, genre, lang, album_id = parts

        # 4. Сохраняем в базу данных (используем ранее созданную функцию)
        # Она сама сгенерирует ID вида 000001
        new_song_id = db_add_song(title, artist, url, genre, lang, album_id)

        # 5. Уведомление об успехе
        success_text = (
            f"✅ *Песня успешно добавлена!*\n"
            f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            f"🆔 ID для поиска: `+{new_song_id}`\n"
            f"🎵 *{artist} — {title}*\n"
            f"📂 Жанр: `{genre}`\n"
            f"🌍 Язык: `{lang}`\n"
            f"💿 Альбом: `{album_id}`\n"
            f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            f"Проверьте работу через: `/id +{new_song_id}`"
        )
        
        bot.send_message(message.chat.id, success_text, parse_mode="Markdown")

    except Exception as e:
        # Ловим критические ошибки (например, проблемы с БД)
        print(f"Error in /add: {e}")
        bot.reply_to(
            message, 
            "❌ *Произошла ошибка при добавлении.*\n"
            "Убедитесь, что формат верный:\n"
            "`URL | Title | Artist | Genre | Lang | AlbumID`", 
            parse_mode="Markdown"
        )

@bot.message_handler(commands=['random'])
def random_songs(message):
    """Выдача списка из 25 случайных треков из базы данных"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Выбираем случайные 25 записей
    c.execute("""SELECT song_id, title, artist 
                 FROM music 
                 ORDER BY RANDOM() 
                 LIMIT 25""")
    songs = c.fetchall()
    conn.close()

    if not songs:
        bot.send_message(message.chat.id, "📭 *The music library is empty.* Check back later!", parse_mode="Markdown")
        return

    # Формируем список. Используем моноширинный шрифт для ID, чтобы на него было удобно нажимать
    response = "🎲 *Your Daily Mix (25 Random Tracks):*\n"
    response += "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n\n"
    
    for s in songs:
        # Формат: +000001 Artist - Title
        response += f"🆔 `+{s[0]}` — *{s[2]}* - {s[1]}\n"
    
    response += "\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
    response += "💡 *Tip:* _Tap on the ID to copy it, then use_ `/id +ID` _to get the track!_"

    bot.send_message(message.chat.id, response, parse_mode="Markdown")

# <--------------- MewMusic --------------->
# POLLING
if __name__ == "__main__":
    print("MewMusic is online...")
    bot.polling(none_stop=True)