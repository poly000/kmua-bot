from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import ContextTypes

from ..logger import logger


_back_home_markup = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton("返回", callback_data="back_home"),
        ]
    ]
)

_clear_quote_buttons = [
    InlineKeyboardButton("清空图片名言", callback_data="clear_user_img_quote"),
    InlineKeyboardButton("清空文字名言", callback_data="clear_user_text_quote"),
]


async def user_data_manage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    img_quote_len = len(context.bot_data["quotes"].get(user_id, {}).get("img", []))
    text_quote_len = len(context.bot_data["quotes"].get(user_id, {}).get("text", []))
    quote_len = img_quote_len + text_quote_len
    statistics_data = f"""
你的统计信息:

你的ID: `{update.effective_user.id}`
已保存的名言总数: *{quote_len}*
图片名言数量: *{img_quote_len}*
文字名言数量: *{text_quote_len}*
"""
    await context.bot.edit_message_text(
        chat_id=update.effective_chat.id,
        text=statistics_data,
        reply_markup=_back_home_markup,
        parse_mode="MarkdownV2",
        message_id=update.callback_query.message.id,
    )


async def clear_user_text_quote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.bot_data["quotes"].get(user_id, {}).get("text", []):
        sent_message = await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            text="你还没有名言",
            message_id=update.callback_query.message.id,
            reply_markup=_back_home_markup,
        )
        logger.info(f"Bot: {sent_message.text}")
        return
    context.bot_data["quotes"][user_id]["text"] = []
    await context.bot.edit_message_text(
        chat_id=update.effective_chat.id,
        message_id=update.callback_query.message.message_id,
        text="已清空你的语录",
        reply_markup=_back_home_markup,
    )


async def clear_user_img_quote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.bot_data["quotes"].get(user_id, {}).get("img", []):
        sent_message = await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            text="你还没有名言",
            message_id=update.callback_query.message.id,
            reply_markup=_back_home_markup,
        )
        logger.info(f"Bot: {sent_message.text}")
        return
    context.bot_data["quotes"][user_id]["img"] = []
    await context.bot.edit_message_text(
        chat_id=update.effective_chat.id,
        message_id=update.callback_query.message.message_id,
        text="已清空你的语录",
        reply_markup=_back_home_markup,
    )


async def user_quote_manage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    quotes = context.bot_data["quotes"].get(user_id, {}).get("text", [])
    img_quotes = context.bot_data["quotes"].get(user_id, {}).get("img", [])
    if not quotes and not img_quotes:
        sent_message = await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            text="你没有名言",
            message_id=update.callback_query.message.id,
            reply_markup=_back_home_markup,
        )
        logger.info(f"Bot: {sent_message.text}")
        return
    quotes_content = [quote.content for quote in quotes]
    is_short = False
    if len(quotes) <= 5:
        is_short = True
    pages = 1 if is_short else (len(quotes) // 5) + (1 if len(quotes) % 5 else 0)
    current_page = 1
    keyboard, line = [], []
    if is_short:
        for i, quote in enumerate(quotes):
            line.append(
                InlineKeyboardButton(
                    i + 1, callback_data=f"delete_quote_{str(quote.id)}"
                )
            )
        keyboard.append(line)
    if not is_short:
        for i, quote in enumerate(quotes[(current_page - 1) * 5 : current_page * 5]):
            line.append(InlineKeyboardButton(i + 1, callback_data=str(quote.id)))
        keyboard.append(line)
        navigation_buttons = [
            InlineKeyboardButton("上一页", callback_data=f"prev_page_{current_page}"),
            InlineKeyboardButton(f"第{current_page}/{pages}页", callback_data="noop"),
            InlineKeyboardButton("下一页", callback_data=f"next_page_{current_page}"),
        ]
        keyboard.append(navigation_buttons)
    keyboard.append(_clear_quote_buttons)
    keyboard.append([InlineKeyboardButton("返回", callback_data="back_home")])
    quote_manage_markup = InlineKeyboardMarkup(keyboard)
    start_index = (current_page - 1) * 5
    end_index = current_page * 5
    text = f"你的名言(第{current_page}/{pages}页):\n点击序号对应的按钮删除名言\n\n"
    for i, quote in enumerate(quotes_content[start_index:end_index]):
        text += f"{i + 1 + start_index} - {quote}\n"
    await context.bot.edit_message_text(
        chat_id=update.effective_chat.id,
        text=text,
        reply_markup=quote_manage_markup,
        message_id=update.callback_query.message.id,
    )


async def prev_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current_page = int(update.callback_query.data.split("_")[2])
    user_id = update.effective_user.id
    quotes = context.bot_data["quotes"].get(user_id, {}).get("text", [])
    pages = (len(quotes) // 5) + (1 if len(quotes) % 5 else 0)
    if current_page == 1:
        return
    current_page -= 1
    start_index = (current_page - 1) * 5
    end_index = current_page * 5
    text = f"你的名言(第{current_page}/{pages}页):\n点击序号对应的按钮删除名言\n\n"
    for i, quote in enumerate(quotes[start_index:end_index]):
        text += f"{i + 1 + start_index} - {quote.content}\n"
    navigation_buttons = [
        InlineKeyboardButton("上一页", callback_data=f"prev_page_{current_page}"),
        InlineKeyboardButton(f"第{current_page}/{pages}页", callback_data="noop"),
        InlineKeyboardButton("下一页", callback_data=f"next_page_{current_page}"),
    ]
    keyboard, line = [], []
    for i, quote in enumerate(quotes[start_index:end_index]):
        line.append(
            InlineKeyboardButton(
                i + 1 + start_index, callback_data=f"delete_quote_{str(quote.id)}"
            )
        )
    keyboard.append(line)
    keyboard.append(navigation_buttons)
    keyboard.append(_clear_quote_buttons)
    keyboard.append([InlineKeyboardButton("返回", callback_data="back_home")])
    quote_manage_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.edit_message_text(
        chat_id=update.effective_chat.id,
        text=text,
        reply_markup=quote_manage_markup,
        message_id=update.callback_query.message.id,
    )


async def next_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current_page = int(update.callback_query.data.split("_")[2])
    user_id = update.effective_user.id
    quotes = context.bot_data["quotes"].get(user_id, {}).get("text", [])
    pages = (len(quotes) // 5) + (1 if len(quotes) % 5 else 0)
    if current_page == pages:
        return
    current_page += 1
    start_index = (current_page - 1) * 5
    end_index = current_page * 5
    text = f"你的名言(第{current_page}/{pages}页):\n点击序号对应的按钮删除名言\n\n"
    for i, quote in enumerate(quotes[start_index:end_index]):
        text += f"{i + 1 + start_index} - {quote.content}\n"
    navigation_buttons = [
        InlineKeyboardButton("上一页", callback_data=f"prev_page_{current_page}"),
        InlineKeyboardButton(f"第{current_page}/{pages}页", callback_data="noop"),
        InlineKeyboardButton("下一页", callback_data=f"next_page_{current_page}"),
    ]
    keyboard, line = [], []
    for i, quote in enumerate(quotes[start_index:end_index]):
        line.append(
            InlineKeyboardButton(
                i + 1 + start_index, callback_data=f"delete_quote_{str(quote.id)}"
            )
        )
    keyboard.append(line)
    keyboard.append(navigation_buttons)
    keyboard.append(_clear_quote_buttons)
    keyboard.append([InlineKeyboardButton("返回", callback_data="back_home")])
    quote_manage_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.edit_message_text(
        chat_id=update.effective_chat.id,
        text=text,
        reply_markup=quote_manage_markup,
        message_id=update.callback_query.message.id,
    )


async def delete_quote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    quote_id = update.callback_query.data.split("_")[2]
    user_id = update.effective_user.id
    text_quotes = context.bot_data["quotes"].get(user_id, {}).get("text", [])
    img_quotes = context.bot_data["quotes"].get(user_id, {}).get("img", [])
    for i, quote in enumerate(text_quotes):
        if str(quote.id) == quote_id:
            for j, img_quote in enumerate(img_quotes):
                if img_quote.id == quote_id:
                    img_quotes.pop(j)
                    break
            text_quotes.pop(i)
            break
    await user_quote_manage(update, context)
