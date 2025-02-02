import random
import time
from datetime import datetime
from uuid import uuid1, uuid4

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InlineQueryResultCachedPhoto,
    InputTextMessageContent,
    Update,
)
from telegram.constants import ChatAction, ChatID
from telegram.error import BadRequest
from telegram.ext import ContextTypes
from telegram.helpers import escape_markdown

from ..config.config import settings
from ..logger import logger
from ..model import ImgQuote, MemberData, TextQuote
from ..utils import generate_quote_img, message_recorder, random_unit
from .jobs import del_message


async def quote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(
        f"[{update.effective_chat.title}]({update.effective_user.name})"
        + f" {update.effective_message.text}"
    )
    await message_recorder(update, context)
    if not update.effective_message.reply_to_message:
        sent_message = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            reply_to_message_id=update.effective_message.id,
            text="请回复一条消息",
        )
        logger.info(f"Bot: {sent_message.text}")
        return
    quote_message = update.effective_message.reply_to_message
    quote_user = quote_message.from_user
    is_save_data = True
    forward_from_user = quote_message.forward_from
    is_chat = False
    is_bot = False
    if forward_from_user:
        quote_user = forward_from_user
    if quote_message.sender_chat:
        quote_user = quote_message.sender_chat
        is_chat = True
    if not is_chat:
        if quote_user.is_bot:
            is_bot = True
    not_user = (
        is_chat
        or is_bot
        or quote_user.id
        in [
            ChatID.ANONYMOUS_ADMIN,
            ChatID.FAKE_CHANNEL,
            ChatID.SERVICE_CHAT,
        ]
    )
    if (
        not (forward_from_user and quote_message.forward_sender_name)
        and update.effective_chat.type != "private"
    ):
        if (
            not context.chat_data["members_data"].get(quote_user.id, None)
            and not not_user
        ):
            member_data_obj = MemberData(
                id=quote_user.id,
                name=quote_user.full_name,
                msg_num=0,
                quote_num=0,
            )
            context.chat_data["members_data"][quote_user.id] = member_data_obj
            context.chat_data["members_data"][quote_user.id].quote_num += 1
    if quote_message.forward_sender_name and forward_from_user is None:
        is_save_data = False
    try:
        await context.bot.pin_chat_message(
            chat_id=update.effective_chat.id,
            message_id=quote_message.id,
            disable_notification=True,
        )
        logger.debug(f"Bot将 {quote_message.text} 置顶")
    except BadRequest as e:
        if e.message == "Not enough rights to manage pinned messages in the chat":
            pass
        else:
            raise e
    if not context.chat_data.get("quote_messages", None):
        context.chat_data["quote_messages"] = []
    if quote_message.id not in context.chat_data["quote_messages"]:
        context.chat_data["quote_messages"].append(quote_message.id)
        logger.debug(
            f"将{quote_message.id}([{update.effective_chat.title}]({quote_user.title if is_chat else quote_user.name}))"  # noqa: E501
            + "加入chat quote"
        )
    sent_message = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="已记录名言",
        reply_to_message_id=quote_message.id,
    )
    context.job_queue.run_once(
        del_message,
        3,
        data={"message_id": sent_message.message_id},
        chat_id=update.effective_chat.id,
        user_id=update.effective_user.id,
    )
    if not quote_message.text:
        # 如果不是文字消息, 在此处return
        return
    # 是文字消息
    if not is_save_data:
        return
    if not context.bot_data["quotes"].get(quote_user.id, None) and not not_user:
        context.bot_data["quotes"][quote_user.id] = {}
        context.bot_data["quotes"][quote_user.id]["img"] = []
        context.bot_data["quotes"][quote_user.id]["text"] = []
    if not not_user:
        uuid = uuid1()
        quote_text_obj = TextQuote(
            id=uuid, content=quote_message.text, created_at=datetime.now()
        )
        context.bot_data["quotes"][quote_user.id]["text"].append(quote_text_obj)
        logger.debug(f"[{quote_text_obj.content}]({quote_text_obj.id})" + "已保存")
    if len(quote_message.text) > 200:
        # 如果文字长度超过200, 则不生成图片
        await update.message.reply_text(text="字数太多了！不排了！")
        return
    avatar_photo = (await context.bot.get_chat(chat_id=quote_user.id)).photo
    if not avatar_photo:
        # 如果没有头像, 或因为权限设置无法获取到头像, 直接
        return
    # 尝试生成图片
    try:
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, action=ChatAction.UPLOAD_PHOTO
        )
        avatar = await (await avatar_photo.get_big_file()).download_as_bytearray()
        quote_img = await generate_quote_img(
            avatar=avatar,
            text=quote_message.text,
            name=quote_user.title if is_chat else quote_user.name,
        )
        sent_photo = await context.bot.send_photo(
            chat_id=update.effective_chat.id, photo=quote_img
        )
        if not_user:
            return
        photo_id = sent_photo.photo[0].file_id
        # 保存图像数据
        quote_img_obj = ImgQuote(
            id=uuid,
            content=photo_id,
            created_at=datetime.now(),
            text=quote_message.text,
        )
        context.bot_data["quotes"][quote_user.id]["img"].append(quote_img_obj)
    except Exception as e:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"生成图像时出错: {e.__class__.__name__}: {e}",
        )
        logger.error(f"{e.__class__.__name__}: {e}")


async def set_quote_probability(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(
        f"[{update.effective_chat.title}]({update.effective_user.name})"
        + f" {update.effective_message.text}"
    )
    await message_recorder(update, context)
    if update.effective_chat.type != "private":
        admins = await context.bot.get_chat_administrators(
            chat_id=update.effective_chat.id
        )
        if (
            update.effective_user.id not in [admin.user.id for admin in admins]
            and update.effective_user.id not in settings["owners"]
        ):
            sent_message = await context.bot.send_message(
                chat_id=update.effective_chat.id, text="你没有权限哦"
            )
            logger.info(f"Bot: {sent_message.text}")
            return
    try:
        probability = float(update.effective_message.text.split(" ")[1])
    except ValueError:
        sent_message = await context.bot.send_message(
            chat_id=update.effective_chat.id, text="概率是在[0,1]之间的浮点数,请检查输入"  # noqa: E501
        )
        logger.info(f"Bot: {sent_message.text}")
        return
    except IndexError:
        sent_message = await context.bot.send_message(
            chat_id=update.effective_chat.id, text="请指定概率"
        )
        logger.info(f"Bot: {sent_message.text}")
        return
    if probability < 0 or probability > 1:
        sent_message = await context.bot.send_message(
            chat_id=update.effective_chat.id, text="概率是在[0,1]之间的浮点数,请检查输入"  # noqa: E501
        )
        logger.info(f"Bot: {sent_message.text}")
        return
    context.chat_data["quote_probability"] = probability
    sent_message = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"将本聊天的名言提醒设置概率为{probability}啦",
    )
    logger.info(f"Bot: {sent_message.text}")


async def random_quote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    this_chat = update.effective_chat
    this_user = update.effective_user
    this_message = update.effective_message
    logger.info(
        f"[{this_chat.title}]({this_user.name if this_user else None})"
        + (f" {this_message.text}" if this_message.text else "<非文本消息>")
    )
    await message_recorder(update, context)
    probability = context.chat_data.get("quote_probability", 0.001)
    probability = float(probability)
    flag = random_unit(probability)
    if update.effective_message.text is not None:
        if update.effective_message.text.startswith("/qrand"):
            flag = True
    if not flag:
        return
    if not context.chat_data.get("quote_messages", None):
        return
    try:
        to_forward_message_id: int = random.choice(context.chat_data["quote_messages"])
        sent_message = await context.bot.forward_message(
            chat_id=update.effective_chat.id,
            from_chat_id=update.effective_chat.id,
            message_id=to_forward_message_id,
        )
        logger.info(
            "Bot: " + (f"{sent_message.text}" if sent_message.text else "<非文本消息>")
        )
    except BadRequest:
        logger.error(f"{to_forward_message_id} 未找到,从chat quote中移除")
        context.chat_data["quote_messages"].remove(to_forward_message_id)
    except Exception as e:
        logger.error(f"{e.__class__.__name__}: {e}")
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text=f"{e.__class__.__name__}: {e}"
        )


async def del_quote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(
        f"[{update.effective_chat.title}]({update.effective_user.name})"
        + f" {update.effective_message.text}"
    )
    await message_recorder(update, context)
    if not context.chat_data.get("quote_messages", None):
        sent_message = await context.bot.send_message(
            chat_id=update.effective_chat.id, text="该聊天没有名言呢"
        )
        logger.info(f"Bot: {sent_message.text}")
        return
    if not update.effective_message.reply_to_message:
        sent_message = await context.bot.send_message(
            chat_id=update.effective_chat.id, text="请回复要移出语录的消息"
        )
        logger.info(f"Bot: {sent_message.text}")
        return
    quote_message = update.effective_message.reply_to_message
    if quote_message.id in context.chat_data["quote_messages"]:
        context.chat_data["quote_messages"].remove(quote_message.id)
        logger.debug(
            f"将{quote_message.id}([{update.effective_chat.title}]({update.effective_user.name}))"
            + "移出chat quote"
        )
        try:
            await context.bot.unpin_chat_message(
                chat_id=update.effective_chat.id, message_id=quote_message.id
            )
            logger.debug(
                "Bot将"
                + (
                    f"{quote_message.text}" if quote_message.text else "<一条非文本消息>"
                )  # noqa: E501
                + "取消置顶"
            )
        except Exception as e:
            logger.error(f"{e.__class__.__name__}: {e}")
        sent_message = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="已移出语录",
            reply_to_message_id=quote_message.id,
        )
        logger.info(f"Bot: {sent_message.text}")
    else:
        sent_message = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="该消息不在语录中;请对原始的名言消息使用",
            reply_to_message_id=quote_message.id,
        )
        logger.info(f"Bot: {sent_message.text}")


_clear_chat_quote_markup = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton("算了", callback_data="cancel_clear_chat_quote"),
            InlineKeyboardButton("确认清空", callback_data="clear_chat_quote"),
        ]
    ]
)


async def clear_chat_quote_ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(
        f"[{update.effective_chat.title}]({update.effective_user.name})"
        + f" {update.effective_message.text}"
    )
    await message_recorder(update, context)
    if not context.chat_data.get("quote_messages", None):
        sent_message = await context.bot.send_message(
            chat_id=update.effective_chat.id, text="该聊天没有名言呢"
        )
        logger.info(f"Bot: {sent_message.text}")
        return
    if update.effective_chat.type != "private":
        this_chat_member = await update.effective_chat.get_member(
            update.effective_user.id
        )
        if this_chat_member.status != "creator":
            await update.effective_message.reply_text("你没有权限哦")
            return
    sent_message = await update.message.reply_text(
        text="真的要清空该聊天的语录吗?\n\n用户个人数据不会被此操作清除",
        reply_markup=_clear_chat_quote_markup,
    )
    logger.info(f"Bot: {sent_message.text}")


async def clear_chat_quote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        if (
            update.effective_user.id
            != update.callback_query.message.reply_to_message.from_user.id
        ):
            await context.bot.answer_callback_query(
                callback_query_id=update.callback_query.id,
                text="你没有权限哦",
                show_alert=True,
            )
            return
    if not context.chat_data.get("quote_messages", None):
        return
    edited_message = await context.bot.edit_message_text(
        chat_id=update.effective_chat.id,
        text="正在清空...",
        message_id=update.callback_query.message.id,
    )
    for message_id in context.chat_data["quote_messages"]:
        try:
            unpin_ok = await context.bot.unpin_chat_message(
                chat_id=update.effective_chat.id, message_id=message_id
            )
            if unpin_ok:
                logger.debug(f"Bot将{message_id}取消置顶")
        except BadRequest:
            continue
        except Exception as e:
            logger.error(e)
            await context.bot.send_message(
                chat_id=update.effective_chat.id, text=f"{e.__class__.__name__}: {e}"
            )
            time.sleep(0.5)
            continue
    context.chat_data["quote_messages"] = []
    sent_message = await context.bot.edit_message_text(
        chat_id=update.effective_chat.id,
        text="已清空该聊天的语录",
        message_id=edited_message.id,
    )
    logger.info(f"Bot: {sent_message.text}")


async def clear_chat_quote_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        if (
            update.effective_user.id
            != update.callback_query.message.reply_to_message.from_user.id
        ):
            await context.bot.answer_callback_query(
                callback_query_id=update.callback_query.id,
                text="你没有权限哦",
                show_alert=True,
            )
            return
    await update.callback_query.message.delete()


async def inline_query_quote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query
    user_id = update.inline_query.from_user.id
    quotes_data = context.bot_data["quotes"].get(user_id, {})
    text_quotes: list[TextQuote] = quotes_data.get("text", [])
    img_quotes: list[ImgQuote] = quotes_data.get("img", [])
    switch_pm_text = "名言管理"
    switch_pm_parameter = "start"
    is_personal = True
    cache_time = 10
    results = []
    no_quote_inline_markup = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "看看我的", url=f"https://t.me/{context.bot.username}?start=start"
                )
            ]
        ]
    )
    if not text_quotes and not img_quotes:
        results.append(
            InlineQueryResultArticle(
                id=uuid4(),
                title="你还没有保存任何名言",
                input_message_content=InputTextMessageContent("我还没有任何名言"),
                reply_markup=no_quote_inline_markup,
            )
        )
    else:
        if query:
            for text_quote in text_quotes:
                if query in text_quote.content:
                    create_at_str = text_quote.created_at.strftime(
                        "%Y年%m月%d日%H时%M分%S秒"
                    )  # noqa: E501
                    results.append(
                        InlineQueryResultArticle(
                            id=str(uuid4()),
                            title=text_quote.content,
                            input_message_content=InputTextMessageContent(
                                text_quote.content
                            ),
                        )
                    )
            for img_quote in img_quotes:
                if query in img_quote.text:
                    create_at_str = img_quote.created_at.strftime(
                        "%Y年%m月%d日%H时%M分%S秒"
                    )  # noqa: E501
                    results.append(
                        InlineQueryResultCachedPhoto(
                            id=str(uuid4()),
                            photo_file_id=img_quote.content,
                        )
                    )
            if len(results) == 0:
                results.append(
                    InlineQueryResultArticle(
                        id=str(uuid4()),
                        title="没有找到相关名言",
                        input_message_content=InputTextMessageContent(
                            message_text=f"我没有说过有 *{escape_markdown(query)}* 的名言!",  # noqa: E501
                            parse_mode="Markdown",
                        ),
                        reply_markup=no_quote_inline_markup,
                    )
                )
        else:
            results = []
            for text_quote in random.sample(text_quotes, min(len(text_quotes), 10)):
                create_at_str = text_quote.created_at.strftime(
                    "%Y年%m月%d日%H时%M分%S秒"
                )  # noqa: E501
                results.append(
                    InlineQueryResultArticle(
                        id=str(uuid4()),
                        title=text_quote.content,
                        input_message_content=InputTextMessageContent(
                            message_text=text_quote.content,
                        ),
                        description=f"于{create_at_str}记",
                    )
                )

            for img_quote in random.sample(img_quotes, min(len(img_quotes), 10)):
                create_at_str = img_quote.created_at.strftime(
                    "%Y年%m月%d日%H时%M分%S秒"
                )  # noqa: E501
                results.append(
                    InlineQueryResultCachedPhoto(
                        id=str(uuid4()),
                        photo_file_id=img_quote.content,
                    )
                )
    await update.inline_query.answer(
        results=results,
        switch_pm_text=switch_pm_text,
        switch_pm_parameter=switch_pm_parameter,
        is_personal=is_personal,
        cache_time=cache_time,
    )


async def clear_user_quote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(
        f"[{update.effective_chat.title}]({update.effective_user.name})"
        + f" {update.effective_message.text}"
    )
    user_id = update.effective_user.id
    if user_id not in settings.owners:
        return
    try:
        to_clear_id = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("请输入数字")
        return
    except IndexError:
        await update.effective_message.reply_text("请输入要清除的用户id")
        return
    if to_clear_id not in context.bot_data["quotes"].keys():
        await update.effective_message.reply_text("该用户没有名言")
        return
    context.bot_data["quotes"].pop(to_clear_id)
    await context.application.persistence.flush()
    await update.effective_message.reply_text("已清除该用户的名言")
