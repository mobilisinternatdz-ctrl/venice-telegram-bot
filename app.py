import os
import httpx

from fastapi import FastAPI, Request, HTTPException

app = FastAPI()

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
VENICE_API_KEY = os.environ["VENICE_API_KEY"]

VENICE_URL = "https://api.venice.ai/api/v1/chat/completions"

MODEL = "venice-uncensored"

# ذاكرة مؤقتة للمحادثات
conversations = {}

MAX_MESSAGES = 10


async def send_telegram_message(chat_id, text):

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    # Telegram له حد لحجم الرسالة
    chunks = [
        text[i:i + 4000]
        for i in range(0, len(text), 4000)
    ]

    async with httpx.AsyncClient(timeout=60) as client:

        for chunk in chunks:

            await client.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": chunk,
                }
            )


async def ask_venice(chat_id, message):

    if chat_id not in conversations:

        conversations[chat_id] = [
            {
                "role": "system",
                "content": (
                    "أنت مساعد ذكاء اصطناعي داخل بوت Telegram. "
                    "أجب باللغة العربية إذا كان المستخدم يتحدث بالعربية. "
                    "كن واضحًا ومفيدًا."
                )
            }
        ]

    conversations[chat_id].append(
        {
            "role": "user",
            "content": message
        }
    )

    # الاحتفاظ بآخر الرسائل فقط
    if len(conversations[chat_id]) > MAX_MESSAGES + 1:

        conversations[chat_id] = (
            [conversations[chat_id][0]]
            + conversations[chat_id][-MAX_MESSAGES:]
        )

    headers = {
        "Authorization": f"Bearer {VENICE_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": MODEL,
        "messages": conversations[chat_id],
        "stream": False,
    }

    async with httpx.AsyncClient(timeout=120) as client:

        response = await client.post(
            VENICE_URL,
            headers=headers,
            json=payload
        )

        response.raise_for_status()

        data = response.json()

    answer = data["choices"][0]["message"]["content"]

    conversations[chat_id].append(
        {
            "role": "assistant",
            "content": answer
        }
    )

    return answer


@app.get("/")
async def home():

    return {
        "status": "online",
        "bot": "Venice Telegram Bot"
    }


@app.post("/webhook")
async def webhook(request: Request):

    update = await request.json()

    if "message" not in update:
        return {"ok": True}

    message = update["message"]

    if "chat" not in message:
        return {"ok": True}

    chat_id = message["chat"]["id"]

    text = message.get("text", "")

    if not text:
        return {"ok": True}

    # أوامر Telegram
    if text == "/start":

        await send_telegram_message(
            chat_id,
            "👋 مرحبًا!\n\n"
            "أنا بوت ذكاء اصطناعي يعمل بواسطة Venice AI 🤖\n\n"
            "أرسل لي أي سؤال."
        )

        return {"ok": True}

    if text == "/help":

        await send_telegram_message(
            chat_id,
            "🤖 أرسل أي سؤال وسأجيبك بواسطة الذكاء الاصطناعي.\n\n"
            "/start - بدء البوت\n"
            "/reset - مسح الذاكرة\n"
            "/help - المساعدة"
        )

        return {"ok": True}

    if text == "/reset":

        conversations.pop(chat_id, None)

        await send_telegram_message(
            chat_id,
            "🧹 تم مسح ذاكرة المحادثة."
        )

        return {"ok": True}

    try:

        answer = await ask_venice(
            chat_id,
            text
        )

        await send_telegram_message(
            chat_id,
            answer
        )

    except Exception as e:

        print("ERROR:", repr(e))

        await send_telegram_message(
            chat_id,
            "❌ حدث خطأ أثناء الاتصال بـ Venice AI."
        )

    return {"ok": True}
