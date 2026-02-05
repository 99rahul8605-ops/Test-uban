# app.py - Merged Telegram Unban Bot
import logging
import asyncio
import threading
import os
import sys
from typing import Optional, Dict, Any
from datetime import datetime
from flask import Flask, request, jsonify
from waitress import serve
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv

# ========== Load Environment Variables ==========
load_dotenv()

# ========== Configuration Class ==========
class Config:
    """Centralized configuration management."""
    
    # Bot Configuration
    BOT_TOKEN = os.getenv('BOT_TOKEN', '').strip()
    
    # Channel Configuration
    CHANNEL_ID = os.getenv('CHANNEL_ID', '').strip()
    if CHANNEL_ID:
        CHANNEL_ID = int(CHANNEL_ID)
    
    # Webhook Configuration
    WEBHOOK_URL = os.getenv('WEBHOOK_URL', '').strip()
    WEBHOOK_PATH = f"/{BOT_TOKEN}" if BOT_TOKEN else "/webhook"
    
    # Server Configuration
    PORT = int(os.getenv('PORT', 10000))
    HOST = os.getenv('HOST', '0.0.0.0')
    
    # Performance Configuration
    POOL_SIZE = int(os.getenv('POOL_SIZE', 4))
    MAX_CONNECTIONS = int(os.getenv('MAX_CONNECTIONS', 100))
    
    # Logging Configuration
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()
    LOG_FILE = os.getenv('LOG_FILE', '/app/logs/bot.log')
    
    # Feature Flags
    USE_WEBHOOK = os.getenv('USE_WEBHOOK', 'false').lower() == 'true'
    DEVELOPMENT = os.getenv('DEVELOPMENT', 'false').lower() == 'true'
    
    @classmethod
    def validate(cls) -> bool:
        """Validate configuration and return True if valid."""
        errors = []
        
        if not cls.BOT_TOKEN:
            errors.append("BOT_TOKEN is required")
        
        if not cls.CHANNEL_ID:
            errors.append("CHANNEL_ID is required")
        
        if errors:
            print("❌ Configuration errors:")
            for error in errors:
                print(f"   - {error}")
            return False
        
        print("✅ Configuration validated!")
        print(f"🤖 Bot Token: {cls.BOT_TOKEN[:10]}...")
        print(f"📢 Channel ID: {cls.CHANNEL_ID}")
        print(f"🌐 Port: {cls.PORT}")
        print(f"⚡ Pool Size: {cls.POOL_SIZE}")
        print(f"🔧 Mode: {'Development' if cls.DEVELOPMENT else 'Production'}")
        print(f"🌐 Webhook: {'Enabled' if cls.USE_WEBHOOK and cls.WEBHOOK_URL else 'Disabled'}")
        
        return True

# Validate configuration
if not Config.validate():
    sys.exit(1)

# ========== Logging Setup ==========
def setup_logging():
    """Configure logging with proper formatting and handlers."""
    
    # Create logs directory if it doesn't exist
    log_dir = os.path.dirname(Config.LOG_FILE)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
    
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, Config.LOG_LEVEL, logging.INFO),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(Config.LOG_FILE, encoding='utf-8')
        ]
    )
    
    # Suppress noisy logs
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('telegram').setLevel(logging.INFO)
    
    return logging.getLogger(__name__)

logger = setup_logging()

# ========== Flask Application ==========
app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False

# ========== Global State ==========
application: Optional[Application] = None
event_loop: Optional[asyncio.AbstractEventLoop] = None

# ========== Bot Handlers ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    user = update.effective_user
    logger.info(f"Start from user {user.id}")
    
    message = (
        f"👋 Hi {user.mention_html()}!\n\n"
        f"🤖 <b>Unban Bot Active</b>\n\n"
        f"📋 <b>Commands:</b>\n"
        f"• /start - Start bot\n"
        f"• /help - Help guide\n"
        f"• /unban [ID] - Unban user\n\n"
        f"🎯 <b>How to use:</b>\n"
        f"1. Get user ID from @userinfobot\n"
        f"2. Send me the ID\n"
        f"3. I'll unban them\n\n"
        f"⚡ <b>Quick unban:</b>\n"
        f"Just send: <code>123456789</code>\n\n"
        f"📢 Channel ID: <code>{Config.CHANNEL_ID}</code>"
    )
    
    await update.message.reply_html(message)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    help_text = (
        "🆘 <b>HELP GUIDE</b>\n\n"
        "📋 <b>Commands:</b>\n"
        "/start - Start the bot\n"
        "/help - Show this guide\n"
        "/unban [ID] - Unban a user\n\n"
        "🎯 <b>How to unban:</b>\n"
        "1. Get user ID from @userinfobot\n"
        "2. Send: <code>/unban 123456789</code>\n"
        "OR just send the ID\n\n"
        "⚠️ <b>Note:</b> I must be an admin in your channel!"
    )
    await update.message.reply_html(help_text)

async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /unban command."""
    if not context.args:
        await update.message.reply_html(
            "❌ <b>Usage:</b> <code>/unban USER_ID</code>\n"
            "Example: <code>/unban 123456789</code>"
        )
        return
    
    user_id = context.args[0]
    await process_unban(update, context, user_id)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle direct messages."""
    text = update.message.text.strip()
    
    if not text:
        return
    
    # Check if message is numeric (user ID)
    if text.isdigit() and len(text) >= 5:
        await process_unban(update, context, text)
    elif not text.startswith('/'):
        await update.message.reply_html(
            "❌ Send a valid User ID (numbers only)\n"
            "Example: <code>123456789</code>\n"
            "Get ID from @userinfobot"
        )

async def process_unban(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: str):
    """Process unban request."""
    try:
        user_id_int = int(user_id)
        logger.info(f"Unbanning user {user_id_int}")
        
        # Attempt to unban with timeout
        try:
            await asyncio.wait_for(
                context.bot.unban_chat_member(
                    chat_id=Config.CHANNEL_ID,
                    user_id=user_id_int,
                    only_if_banned=True
                ),
                timeout=15.0
            )
            
            await update.message.reply_html(
                f"✅ <b>Successfully Unbanned!</b>\n\n"
                f"👤 User ID: <code>{user_id}</code>\n"
                f"📢 Channel: <code>{Config.CHANNEL_ID}</code>"
            )
            logger.info(f"Unbanned user {user_id_int}")
            
        except asyncio.TimeoutError:
            logger.warning(f"Timeout unbanning user {user_id_int}")
            await update.message.reply_html(
                "⚠️ <b>Operation timed out!</b>\n"
                "The server took too long to respond. Please try again."
            )
            
    except ValueError:
        await update.message.reply_html(
            "❌ <b>Invalid User ID!</b>\n"
            "User ID must contain only numbers."
        )
    except Exception as e:
        error_msg = str(e).lower()
        logger.error(f"Unban error: {error_msg}")
        
        if "not enough rights" in error_msg:
            await update.message.reply_html(
                "❌ <b>Permission Error!</b>\n\n"
                "Make me an ADMIN in the channel with:\n"
                "• Ban Users permission\n\n"
                "Then try again!"
            )
        elif "user not found" in error_msg:
            await update.message.reply_html("❌ User not found!")
        elif "not banned" in error_msg:
            await update.message.reply_html("✅ User is not banned!")
        elif "chat not found" in error_msg:
            await update.message.reply_html("❌ Channel not found!")
        else:
            await update.message.reply_html("❌ Failed to unban. Try again!")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors in bot handlers."""
    logger.error(f"Bot error: {context.error}", exc_info=True)
    
    if update and update.effective_message:
        try:
            await update.effective_message.reply_html(
                "⚠️ <b>An error occurred!</b>\n"
                "Please try again later."
            )
        except:
            pass

# ========== Application Factory ==========
def create_application() -> Application:
    """Create and configure the bot application."""
    logger.info("Creating bot application...")
    
    # Configure with performance settings
    builder = Application.builder()
    builder.token(Config.BOT_TOKEN)
    
    if Config.POOL_SIZE > 1:
        builder.pool_size(Config.POOL_SIZE)
    
    app_instance = builder.build()
    
    # Register handlers
    handlers = [
        CommandHandler("start", start),
        CommandHandler("help", help_command),
        CommandHandler("unban", unban_command),
        MessageHandler(
            filters.TEXT & filters.ChatType.PRIVATE & ~filters.COMMAND,
            handle_message
        )
    ]
    
    for handler in handlers:
        app_instance.add_handler(handler)
    
    app_instance.add_error_handler(error_handler)
    
    logger.info(f"Bot application created with pool size: {Config.POOL_SIZE}")
    return app_instance

# ========== Bot Initialization ==========
def init_bot():
    """Initialize the bot in a separate thread."""
    global application, event_loop
    
    try:
        logger.info("Initializing bot...")
        
        # Create event loop
        event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(event_loop)
        
        # Create application
        application = create_application()
        
        # Initialize
        event_loop.run_until_complete(application.initialize())
        logger.info("Bot initialized")
        
        # Setup webhook if enabled
        if Config.USE_WEBHOOK and Config.WEBHOOK_URL:
            webhook_url = f"{Config.WEBHOOK_URL}{Config.WEBHOOK_PATH}"
            logger.info(f"Setting webhook to: {webhook_url}")
            
            event_loop.run_until_complete(
                application.bot.set_webhook(
                    webhook_url,
                    max_connections=Config.MAX_CONNECTIONS,
                    drop_pending_updates=True,
                    allowed_updates=["message", "callback_query"]
                )
            )
            logger.info("Webhook set successfully")
            
        elif Config.DEVELOPMENT:
            # Start polling in development
            logger.info("Starting polling (development mode)")
            event_loop.create_task(application.run_polling(
                drop_pending_updates=True,
                allowed_updates=["message", "callback_query"]
            ))
            
    except Exception as e:
        logger.error(f"Failed to initialize bot: {e}", exc_info=True)
        sys.exit(1)

def start_bot():
    """Start bot initialization in background."""
    thread = threading.Thread(target=init_bot, daemon=True, name="BotThread")
    thread.start()
    logger.info("Bot initialization started")

# ========== Flask Routes ==========
@app.route('/')
def home():
    """Home endpoint."""
    return jsonify({
        "status": "online",
        "service": "Telegram Unban Bot",
        "version": "2.0.0",
        "timestamp": datetime.utcnow().isoformat(),
        "endpoints": {
            "health": "/health",
            "info": "/info",
            "webhook": Config.WEBHOOK_PATH
        }
    })

@app.route('/health')
def health():
    """Health check endpoint."""
    bot_status = "ready" if application and application.running else "starting"
    
    return jsonify({
        "status": "healthy",
        "bot": bot_status,
        "timestamp": datetime.utcnow().isoformat(),
        "uptime": getattr(app, 'start_time', datetime.utcnow()).isoformat()
    }), 200

@app.route('/info')
def info():
    """Information endpoint."""
    return jsonify({
        "channel_id": Config.CHANNEL_ID,
        "webhook_enabled": Config.USE_WEBHOOK,
        "webhook_url": Config.WEBHOOK_URL,
        "pool_size": Config.POOL_SIZE,
        "max_connections": Config.MAX_CONNECTIONS,
        "mode": "development" if Config.DEVELOPMENT else "production"
    })

@app.route(Config.WEBHOOK_PATH, methods=['POST'])
def webhook():
    """Handle Telegram webhook updates."""
    if not application:
        return jsonify({"error": "Bot not initialized"}), 503
    
    try:
        json_data = request.get_json()
        if not json_data:
            return jsonify({"error": "No data"}), 400
        
        # Process update
        update = Update.de_json(json_data, application.bot)
        
        if event_loop and event_loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                application.process_update(update),
                event_loop
            )
            future.result(timeout=10)
        else:
            asyncio.run(application.process_update(update))
        
        return jsonify({"status": "ok"}), 200
        
    except asyncio.TimeoutError:
        logger.warning("Webhook processing timeout")
        return jsonify({"status": "processing"}), 202
    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route('/webhook/set', methods=['POST'])
def set_webhook():
    """Manually set webhook."""
    if not Config.WEBHOOK_URL:
        return jsonify({"error": "WEBHOOK_URL not configured"}), 400
    
    webhook_url = f"{Config.WEBHOOK_URL}{Config.WEBHOOK_PATH}"
    
    try:
        if event_loop and event_loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                application.bot.set_webhook(webhook_url),
                event_loop
            )
            future.result(timeout=5)
        else:
            asyncio.run(application.bot.set_webhook(webhook_url))
        
        return jsonify({
            "success": True,
            "webhook_url": webhook_url
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/webhook/delete', methods=['POST'])
def delete_webhook():
    """Delete webhook."""
    try:
        if event_loop and event_loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                application.bot.delete_webhook(),
                event_loop
            )
            future.result(timeout=5)
        else:
            asyncio.run(application.bot.delete_webhook())
        
        return jsonify({"success": True}), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ========== Shutdown Handler ==========
def shutdown_handler():
    """Handle graceful shutdown."""
    logger.info("Shutting down...")
    
    if application and event_loop:
        try:
            if event_loop.is_running():
                future = asyncio.run_coroutine_threadsafe(
                    application.stop(),
                    event_loop
                )
                future.result(timeout=5)
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
    
    logger.info("Shutdown complete")

# Register shutdown handler
import atexit
atexit.register(shutdown_handler)

# ========== Application Startup ==========
if __name__ == '__main__':
    # Record startup time
    app.start_time = datetime.utcnow()
    
    # Start bot
    start_bot()
    
    # Start web server
    logger.info(f"Starting server on {Config.HOST}:{Config.PORT}")
    
    if Config.DEVELOPMENT:
        # Development server
        app.run(
            host=Config.HOST,
            port=Config.PORT,
            debug=True,
            use_reloader=False  # Disable reloader as it interferes with async
        )
    else:
        # Production server
        serve(
            app,
            host=Config.HOST,
            port=Config.PORT,
            threads=8,
            connection_limit=Config.MAX_CONNECTIONS,
            channel_timeout=30
        )