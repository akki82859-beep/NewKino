import asyncio
import logging
import aiosqlite
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder

# --- SOZLAMALAR ---
TOKEN = "9246054045:AAFw1Q_rEKn2-lKJ7kgGjlXknroUUOSdDNo"
ADMIN_ID = 5757319779
  # <--- O'z Telegram ID raqamingizni yozing (faqat raqam)
CHANNEL_USERNAME = ""  # Majburiy obuna kerak bo'lmasa bo'sh qoldiring

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())
DB_NAME = "movies.db"


# --- STATES (Admin uchun holatlar) ---
class AddMovie(StatesGroup):
  waiting_for_code = State()
  waiting_for_video = State()
  waiting_for_title = State()


# --- DATABASE BILAN ISHLASH ---
async def db_start():
  async with aiosqlite.connect(DB_NAME) as db:
    await db.execute("""
            CREATE TABLE IF NOT EXISTS movies (
                code TEXT PRIMARY KEY,
                file_id TEXT,
                title TEXT
            )
        """)
    await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY
            )
        """)
    await db.commit()


# --- MAJBURIY OBUNANI TEKSHIRISH ---
async def check_subscription(user_id: int) -> bool:
  if not CHANNEL_USERNAME:
    return True
  try:
    member = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
    if member.status in ["member", "administrator", "creator"]:
      return True
  except Exception:
    pass
  return False


# --- START BUYRUG'I ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
  user_id = message.from_user.id

  async with aiosqlite.connect(DB_NAME) as db:
    await db.execute(
        "INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,)
    )
    await db.commit()

  if not await check_subscription(user_id):
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(
            text="📢 Kanalga obuna bo'lish",
            url=f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}",
        )
    )
    builder.row(
        types.InlineKeyboardButton(
            text="✅ Obunani tekshirish", callback_data="check_sub"
        )
    )
    await message.answer(
        "Botdan foydalanish uchun quyidagi kanalimizga obuna bo'ling:",
        reply_markup=builder.as_markup(),
    )
    return

  await message.answer(
      f"Salom, {message.from_user.first_name}! 🎬\n\n"
      "Bu kino boti. Menga kinoning **kodini** yuboring (masalan: `101`),"
      " men sizga o'sha kinoni topib beraman."
  )


@dp.callback_query(F.data == "check_sub")
async def process_check_sub(callback: types.CallbackQuery):
  user_id = callback.from_user.id
  if await check_subscription(user_id):
    await callback.message.delete()
    await callback.message.answer(
        "Rahmat! Obuna tasdiqlandi. Endi kino kodini yuborishingiz mumkin:"
    )
  else:
    await callback.answer(
        "Siz hali hamma kanallarga obuna bo'lmadingiz! ❌", show_alert=True
    )


# --- ADMIN PANEL: KINO QO'SHISH ---
@dp.message(Command("add"))
async def cmd_add(message: types.Message, state: FSMContext):
  if message.from_user.id != ADMIN_ID:
    await message.answer("Sizda bu buyruqdan foydalanish huquqi yo'q. ❌")
    return

  await state.set_state(AddMovie.waiting_for_code)
  await message.answer("Yangi kino uchun **kod** kiriting (masalan: `101`):")


@dp.message(AddMovie.waiting_for_code)
async def process_movie_code(message: types.Message, state: FSMContext):
  await state.update_data(code=message.text)
  await state.set_state(AddMovie.waiting_for_video)
  await message.answer("Endi kino **videolarini (faylini)** botga yuboring:")


@dp.message(AddMovie.waiting_for_video, F.video)
async def process_movie_video(message: types.Message, state: FSMContext):
  file_id = message.video.file_id
  await state.update_data(file_id=file_id)
  await state.set_state(AddMovie.waiting_for_title)
  await message.answer("Endi kino **nomini** yuboring:")


@dp.message(AddMovie.waiting_for_title)
async def process_movie_title(message: types.Message, state: FSMContext):
  title = message.text
  data = await state.get_data()
  code = data["code"]
  file_id = data["file_id"]

  async with aiosqlite.connect(DB_NAME) as db:
    await db.execute(
        "INSERT OR REPLACE INTO movies (code, file_id, title) VALUES (?, ?, ?)",
        (code, file_id, title),
    )
    await db.commit()

  await state.clear()
  await message.answer(
      f"✅ Kino muvaffaqiyatli qo'shildi!\n\nKod: {code}\nNomi: {title}"
  )


@dp.message(Command("stat"))
async def cmd_stat(message: types.Message):
  if message.from_user.id != ADMIN_ID:
    return

  async with aiosqlite.connect(DB_NAME) as db:
    async with db.execute("SELECT COUNT(*) FROM users") as cursor:
      users_count = (await cursor.fetchone())[0]
    async with db.execute("SELECT COUNT(*) FROM movies") as cursor:
      movies_count = (await cursor.fetchone())[0]

  await message.answer(
      f"📊 Bot statistikasi:\n\n👤 Obunachilar: {users_count} ta\n🎬 Kinolar:"
      f" {movies_count} ta"
  )


# --- KINONI QIDIRISH ---
@dp.message(F.text)
async def get_movie(message: types.Message):
  user_id = message.from_user.id

  if not await check_subscription(user_id):
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(
            text="📢 Kanalga obuna bo'lish",
            url=f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}",
        )
    )
    builder.row(
        types.InlineKeyboardButton(
            text="✅ Obunani tekshirish", callback_data="check_sub"
        )
    )
    await message.answer(
        "Botdan foydalanish uchun avval kanalimizga obuna bo'ling:",
        reply_markup=builder.as_markup(),
    )
    return

  code = message.text.strip()

  async with aiosqlite.connect(DB_NAME) as db:
    async with db.execute(
        "SELECT file_id, title FROM movies WHERE code = ?", (code,)
    ) as cursor:
      movie = await cursor.fetchone()

  if movie:
    file_id, title = movie
    await message.answer_video(
        video=file_id, caption=f"🎬 **{title}**\n\n📥 Bizning bot"
    )
  else:
    await message.answer(
        "❌ Kechirasiz, bu kod bo'yicha hech qanday kino topilmadi."
        " Boshqa kodni kiriting."
    )


async def main():
  await db_start()
  logging.basicConfig(level=logging.INFO)
  print("Kino boti muvaffaqiyatli ishga tushdi! 🚀")
  await dp.start_polling(bot)


if __name__ == "__main__":
  asyncio.run(main())
