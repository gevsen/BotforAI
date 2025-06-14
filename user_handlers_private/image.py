# user_handlers_private/image.py
from aiogram import Router, types, F, Bot
from aiogram.fsm.context import FSMContext

import config
import keyboards as kb
from states import ImageGeneration

image_router = Router(name="user_image")

# Note: Global private chat filter (F.chat.type == 'private') is applied in user_handlers_private/__init__.py

# --- Обработчики генерации изображений ---

@image_router.callback_query(F.data == 'menu_image_gen')
async def image_gen_start(callback: types.CallbackQuery, state: FSMContext, bot: Bot, user_level: int):
    model_status_cache = bot["model_status_cache"]
    # api_service = bot["api_service"] # Not directly used here, but process_image_prompt will use it

    if config.IMAGE_MODEL in model_status_cache and not model_status_cache[config.IMAGE_MODEL]:
        await callback.answer("⚠️ Эта функция временно недоступна.", show_alert=True)
        return

    if user_level == 0: # user_level is passed by AccessControlMiddleware
        await callback.answer("⚠️ Эта функция доступна только для платных подписчиков.", show_alert=True)
        return

    await state.set_state(ImageGeneration.waiting_for_prompt)
    await callback.message.edit_text(
        "Отправьте ваш запрос (промпт) для генерации изображения.",
        reply_markup=kb.get_cancel_keyboard() # Assuming kb.get_cancel_keyboard() exists
    )
    await callback.answer()

@image_router.message(ImageGeneration.waiting_for_prompt, F.text)
async def process_image_prompt(message: types.Message, state: FSMContext, bot: Bot):
    await state.clear() # Clear state after getting the prompt
    prompt = message.text
    msg = await message.answer("🎨 Создаю шедевр... Это может занять до минуты.")

    api_service = bot["api_service"] # Get APIService from bot context
    db = bot["db"] # Get Database from bot context

    try:
        image_url, error = await api_service.generate_image(model=config.IMAGE_MODEL, prompt=prompt)

        if error:
            error_text = f"❌ Ошибка для админа: {error}" if message.from_user.id in config.ADMIN_IDS else "❌ Произошла ошибка. Попробуйте изменить запрос или обратитесь в поддержку."
            await msg.edit_text(error_text)
        else:
            if image_url: # Ensure URL is not None
                await bot.send_photo(chat_id=message.chat.id, photo=image_url, caption=f"✅ Ваш шедевр по запросу: `{prompt}`")
                await msg.delete()
                if message.from_user.id not in config.ADMIN_IDS:
                    await db.add_request(message.from_user.id, config.IMAGE_MODEL)
            else: # Should not happen if error is None, but as a safeguard
                await msg.edit_text("❌ Произошла неизвестная ошибка при генерации изображения.")

    except Exception as e:
        # Log the full exception e for admin/debug purposes
        # logger.error(f"Error in process_image_prompt: {e}", exc_info=True)
        error_text = f"❌ Ошибка для админа (exception): {e}" if message.from_user.id in config.ADMIN_IDS else "❌ Произошла непредвиденная ошибка. Пожалуйста, попробуйте позже."
        await msg.edit_text(error_text)
