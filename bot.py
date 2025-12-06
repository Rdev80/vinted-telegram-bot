import os
from urllib.parse import urlparse, parse_qsl, urlencode

import requests
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from db import (
    init_db,
    add_search,
    get_searches,
    get_all_searches,
    get_seen_items,
    add_seen_items,
    delete_search,
)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Estados para la conversación de /crearbusqueda
ASK_QUERY, ASK_SIZE, ASK_MIN_PRICE, ASK_MAX_PRICE, ASK_INCLUDE, ASK_EXCLUDE = range(6)


# ==========================
#      COMANDOS BÁSICOS
# ==========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "¡Hola! 👋 Soy tu bot de Vinted.\n\n"
        "Comandos:\n"
        " /menu - Mostrar menú con botones\n"
        " /crearbusqueda - Crear búsqueda paso a paso\n"
        " /misbusquedas - Ver tus búsquedas guardadas\n"
        " /delsearch <ID> - Borrar una búsqueda por ID\n"
        " /cancel - Cancelar creación de búsqueda actual\n"
    )


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ["/crearbusqueda", "/misbusquedas"],
        ["/cancel"],
    ]
    reply_markup = ReplyKeyboardMarkup(
        keyboard, resize_keyboard=True, one_time_keyboard=False
    )
    await update.message.reply_text("Menú principal:", reply_markup=reply_markup)


async def misbusquedas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    searches = get_searches(user.id)

    if not searches:
        await update.message.reply_text(
            "No tienes búsquedas guardadas aún.\n"
            "Usa /crearbusqueda para añadir una 😉",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    lines = ["📚 Tus búsquedas guardadas:"]
    for sid, query, size, min_price, max_price, inc, exc, url, created_at in searches:
        texto = f"- ID {sid}: {query}"
        if size:
            texto += f" | talla: {size}"
        if min_price is not None:
            texto += f" | mín: {min_price}€"
        if max_price is not None:
            texto += f" | máx: {max_price}€"
        if inc:
            texto += f" | incluye: {inc}"
        if exc:
            texto += f" | excluye: {exc}"
        lines.append(texto)

    await update.message.reply_text("\n".join(lines), reply_markup=ReplyKeyboardRemove())


async def delsearch_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not context.args:
        await update.message.reply_text("Uso: /delsearch <ID>")
        return

    try:
        search_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("El ID debe ser un número.")
        return

    user_searches = get_searches(user.id)
    valid_ids = {s[0] for s in user_searches}

    if search_id not in valid_ids:
        await update.message.reply_text("No tienes ninguna búsqueda con ese ID.")
        return

    delete_search(search_id)
    await update.message.reply_text("🗑️ Búsqueda eliminada correctamente.")


# ==========================
#   /CREARBUSQUEDA WIZARD
# ==========================

async def crearbusqueda_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Perfecto, vamos a crear una búsqueda nueva.\n\n"
        "1️⃣ Escribe el texto que pondrías en Vinted "
        "(ej: 'nike dunk', 'chaqueta lonsdale', etc.):",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ASK_QUERY


async def ask_size(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query_text = update.message.text.strip()
    if not query_text:
        await update.message.reply_text("El texto no puede estar vacío. Escribe algo:")
        return ASK_QUERY

    context.user_data["new_query"] = query_text
    await update.message.reply_text(
        "2️⃣ Ahora escribe la talla (ej: '43', 'L', 'M').\n"
        "Si no quieres filtrar por talla, escribe: ninguna"
    )
    return ASK_SIZE


async def ask_min_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    size_text = update.message.text.strip()
    if size_text.lower() == "ninguna":
        size_text = ""
    context.user_data["new_size"] = size_text

    await update.message.reply_text(
        "3️⃣ Escribe el *precio mínimo* en euros (ej: 10).\n"
        "Si no quieres mínimo, escribe: 0"
    )
    return ASK_MIN_PRICE


async def ask_max_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    price_text = update.message.text.strip().replace(",", ".")
    try:
        min_price_value = float(price_text)
        if min_price_value <= 0:
            min_price = None
        else:
            min_price = min_price_value
    except ValueError:
        await update.message.reply_text(
            "No he entendido ese número. Escribe solo el precio mínimo (ej: 10):"
        )
        return ASK_MIN_PRICE

    context.user_data["new_min_price"] = min_price

    await update.message.reply_text(
        "4️⃣ Ahora escribe el *precio máximo* en euros (ej: 40).\n"
        "Si no quieres máximo, escribe: 0"
    )
    return ASK_MAX_PRICE


async def ask_include(update: Update, context: ContextTypes.DEFAULT_TYPE):
    price_text = update.message.text.strip().replace(",", ".")
    try:
        max_price_value = float(price_text)
        if max_price_value <= 0:
            max_price = None
        else:
            max_price = max_price_value
    except ValueError:
        await update.message.reply_text(
            "No he entendido ese número. Escribe solo el precio máximo (ej: 40):"
        )
        return ASK_MAX_PRICE

    context.user_data["new_max_price"] = max_price

    await update.message.reply_text(
        "5️⃣ Palabras que *debe contener* el título (separadas por coma).\n"
        "Ejemplo: original, box, etiqueta\n"
        "Si no quieres obligar a ninguna, escribe: ninguna"
    )
    return ASK_INCLUDE


async def ask_exclude(update: Update, context: ContextTypes.DEFAULT_TYPE):
    include_text = update.message.text.strip()
    if include_text.lower() == "ninguna":
        include_text = ""
    context.user_data["new_include"] = include_text

    await update.message.reply_text(
        "6️⃣ Palabras que *NO quieres* que aparezcan en el título "
        "(separadas por coma).\n"
        "Ejemplo: réplica, fake, roto\n"
        "Si no quieres excluir nada, escribe: ninguna"
    )
    return ASK_EXCLUDE


async def crearbusqueda_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    exclude_text = update.message.text.strip()
    if exclude_text.lower() == "ninguna":
        exclude_text = ""

    query = context.user_data.get("new_query", "").strip()
    size = context.user_data.get("new_size", "").strip() or None
    min_price = context.user_data.get("new_min_price")
    max_price = context.user_data.get("new_max_price")
    include_words = context.user_data.get("new_include", "").strip() or None
    exclude_words = exclude_text.strip() or None

    # Construimos el search_text que usará Vinted (texto + talla)
    full_text = query
    if size:
        full_text += f" {size}"

    base_url = "https://www.vinted.es/catalog"
    params = {"search_text": full_text}
    url = base_url + "?" + urlencode(params)

    add_search(
        user_id=user.id,
        query=query,
        size=size,
        min_price=min_price,
        max_price=max_price,
        include_words=include_words,
        exclude_words=exclude_words,
        url=url,
    )

    resumen = f"✅ Búsqueda creada:\n- Texto: {query}"
    if size:
        resumen += f"\n- Talla: {size}"
    if min_price is not None:
        resumen += f"\n- Precio mín: {min_price}€"
    if max_price is not None:
        resumen += f"\n- Precio máx: {max_price}€"
    if include_words:
        resumen += f"\n- Debe incluir: {include_words}"
    if exclude_words:
        resumen += f"\n- Excluye: {exclude_words}"
    resumen += f"\n\nURL interna:\n{url}"

    await update.message.reply_text(resumen)
    return ConversationHandler.END


async def crearbusqueda_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Se ha cancelado la creación de la búsqueda.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END


# ==========================
#      VINTED SCRAPER
# ==========================

def build_vinted_api_url(search_url: str) -> str:
    parsed = urlparse(search_url)
    query_params = dict(parse_qsl(parsed.query))
    if "per_page" not in query_params:
        query_params["per_page"] = "20"
    api_base = "https://www.vinted.es/api/v2/catalog/items"
    return api_base + "?" + urlencode(query_params)


def fetch_vinted_items(search_url: str):
    api_url = build_vinted_api_url(search_url)

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; VintedBot/1.0)",
        "Accept": "application/json",
    }

    resp = requests.get(api_url, headers=headers, timeout=10)
    resp.raise_for_status()

    data = resp.json()
    items = data.get("items") or data.get("catalog_items") or []

    results = []
    for item in items:
        item_id = item.get("id")
        if item_id is None:
            continue

        title = (
            item.get("title")
            or item.get("description")
            or "Artículo sin título"
        )

        price_info = item.get("price") or item.get("price_numeric") or {}
        price_amount = "?"
        currency = "€"

        if isinstance(price_info, dict):
            price_amount = (
                price_info.get("amount")
                or price_info.get("value")
                or price_info.get("number")
                or "?"
            )
            currency = price_info.get("currency", "€")
        elif isinstance(price_info, (int, float, str)):
            price_amount = str(price_info)

        url = item.get("url") or f"https://www.vinted.es/items/{item_id}"

        results.append(
            {
                "id": str(item_id),
                "title": title,
                "price": price_amount,
                "currency": currency,
                "url": url,
            }
        )

    return results


# ==========================
#   JOB PERIÓDICO (CHECK)
# ==========================

async def check_vinted_job(context: ContextTypes.DEFAULT_TYPE):
    application = context.application

    all_searches = get_all_searches()
    if not all_searches:
        return

    for search_id, user_id, url, min_price, max_price, inc, exc in all_searches:
        try:
            items = fetch_vinted_items(url)
            print(f"[INFO] search_id={search_id}, user_id={user_id}, encontrados={len(items)} artículos")
        except Exception as e:
            print(f"[ERROR] Al pedir Vinted para search_id={search_id}: {e}")
            continue

        if not items:
            continue

        seen_ids = get_seen_items(search_id)

        new_items = []
        for item in items:
            if item["id"] in seen_ids:
                continue

            title_lower = (item["title"] or "").lower()

            # Precio
            precio = None
            try:
                precio = float(str(item["price"]).replace(",", "."))
            except Exception:
                pass

            # Filtro de precio mínimo/máximo
            if min_price is not None and precio is not None and precio < min_price:
                continue
            if max_price is not None and precio is not None and precio > max_price:
                continue

            # Filtro de palabras obligatorias
            if inc:
                palabras_inc = [w.strip().lower() for w in inc.split(",") if w.strip()]
                if not all(p in title_lower for p in palabras_inc):
                    continue

            # Filtro de palabras excluidas
            if exc:
                palabras_exc = [w.strip().lower() for w in exc.split(",") if w.strip()]
                if any(p in title_lower for p in palabras_exc):
                    continue

            new_items.append(item)

        if not new_items:
            continue

        add_seen_items(search_id, [item["id"] for item in new_items])

        # Agrupamos en un solo mensaje (máx 5 para no hacer tochos)
        max_to_show = 5
        lines = ["🔔 *Nuevos artículos en Vinted*"]
        for idx, item in enumerate(new_items[:max_to_show], start=1):
            texto_precio = f"{item['price']} {item['currency']}"
            lines.append(
                f"\n{idx}. {item['title']}\n"
                f"   Precio: {texto_precio}\n"
                f"   {item['url']}"
            )

        if len(new_items) > max_to_show:
            lines.append(f"\n(+{len(new_items) - max_to_show} más...)")

        text = "\n".join(lines)

        try:
            await application.bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode="Markdown",
            )
        except Exception as e:
            print(f"[ERROR] Al enviar mensaje a user_id={user_id}: {e}")


# ==========================
#           MAIN
# ==========================

def main():
    if not TOKEN:
        raise RuntimeError(
            "No se ha encontrado la variable de entorno TELEGRAM_BOT_TOKEN.\n"
            "En CMD puedes hacer:\n"
            'set TELEGRAM_BOT_TOKEN=TU_TOKEN_AQUI'
        )

    init_db()

    app = Application.builder().token(TOKEN).build()

    # Comandos simples
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CommandHandler("misbusquedas", misbusquedas))
    app.add_handler(CommandHandler("delsearch", delsearch_cmd))

    # Conversación para /crearbusqueda
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("crearbusqueda", crearbusqueda_start)],
        states={
            ASK_QUERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_size)],
            ASK_SIZE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_min_price)],
            ASK_MIN_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_max_price)],
            ASK_MAX_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_include)],
            ASK_INCLUDE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_exclude)],
            ASK_EXCLUDE: [MessageHandler(filters.TEXT & ~filters.COMMAND, crearbusqueda_finish)],
        },
        fallbacks=[CommandHandler("cancel", crearbusqueda_cancel)],
    )
    app.add_handler(conv_handler)

    # Job periódico
    app.job_queue.run_repeating(
        check_vinted_job,
        interval=120,   # cada 2 minutos
        first=10,
    )

    print("Bot arrancado... esperando mensajes.")
    app.run_polling()


if __name__ == "__main__":
    main()
