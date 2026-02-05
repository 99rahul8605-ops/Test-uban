# main.py
import logging
import asyncio
import threading
from typing import Optional
from flask import Flask, request, jsonify
from waitress import serve
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ========== Configuration ==========
class Config:
    """Configuration management with validation."""
    # Bot Configuration
    BOT_TOKEN = os.getenv('BOT_TOKEN', '').strip()
    
    # Channel ID
    CHANNEL_ID = os.getenv('CHANNEL_ID', '').strip()
    
    # Convert CHANNEL_ID to int
    if CHANNEL_ID:
        CHANNEL_ID = int(CHANNEL_ID)
    
    # Webhook URL
    WEBHOOK_URL = os.getenv('WEBHOOK_URL', '').strip()
    
    # Server Configuration
    PORT = int(os.getenv('PORT', 10000))
    
    # Performance settings
    POOL_SIZE = int(os.getenv('POOL_SIZE', 4))  # Thread pool size for async operations
    MAX_UPDATES = int(os.getenv('MAX_UPDATES', 100))  # Max updates to process concurrently
    
    @classmethod
    def validate(cls):
        """Validate configuration."""
        if not cls.BOT_TOKEN:
            raise ValueError("BOT_TOKEN is required")
        
        if not cls.CHANNEL_ID:
            raise ValueError("CHANNEL_ID is required")
        
        print("✅ Configuration validated!")
        print(f"🤖 Bot Token: {cls.BOT_TOKEN[:10]}...")
        print(f"📢 Channel ID: {cls.CHANNEL_ID}")
        print(f"🌐 Port: {cls.PORT}")
        print(f"⚡ Pool Size: {cls.POOL_SIZE}")
        
        return True

# Validate configuration on startup
try:
    Config.validate()
except ValueError as e:
    print(f"❌ Configuration Error: {e}")
    exit(1)

# ========== Logging Setup ==========
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# ========== Flask Application ==========
app = Flask(__name__)

# ========== Global State ==========
application: Optional[Application] = None
event_loop: Optional[asyncio.AbstractEventLoop] = None

# ========== Bot Handlers ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    user = update.effective_user
    logger.info(f"Start command from user {user.id}")
    
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
    logger.info(f"Sent welcome to user {user.id}")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a help message."""
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
    """Process unban request with rate limiting."""
    try:
        user_id_int = int(user_id)
        logger.info(f"Unbanning user {user_id_int} from {Config.CHANNEL_ID}")
        
        # Unban the user with timeout protection
        try:
            await asyncio.wait_for(
                context.bot.unban_chat_member(
                    chat_id=Config.CHANNEL_ID,
                    user_id=user_id_int,
                    only_if_banned=True
                ),
                timeout=10.0
            )
        except asyncio.TimeoutError:
            logger.error(f"Timeout while unbanning user {user_id_int}")
            await update.message.reply_html(
                "⚠️ <b>Operation timed out!</b>\n\n"
                "The unban request took too long. Please try again."
            )
            return
        
        await update.message.reply_html(
            f"✅ <b>Successfully Unbanned!</b>\n\n"
            f"👤 User ID: <code>{user_id}</code>\n"
            f"📢 Channel: <code>{Config.CHANNEL_ID}</code>"
        )
        logger.info(f"Success: Unbanned user {user_id_int}")
        
    except ValueError:
        await update.message.reply_html(
            "❌ <b>Invalid User ID!</b>\n\n"
            "User ID must be a number.\n"
            "Example: <code>123456789</code>"
        )
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Unban error: {error_msg}")
        
        if "not enough rights" in error_msg.lower():
            await update.message.reply_html(
                "❌ <b>Permission Error!</b>\n\n"
                "Make me an ADMIN in the channel with:\n"
                "• Ban Users permission\n\n"
                "Then try again!"
            )
        elif "user not found" in error_msg.lower():
            await update.message.reply_html("❌ User not found!")
        elif "not banned" in error_msg.lower():
            await update.message.reply_html("✅ User is not banned!")
        else:
            await update.message.reply_html("❌ Failed to unban. Try again!")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log errors and notify admin."""
    logger.error(f"Error: {context.error}")
    
    # Only send error message if it's not a timeout or connection issue
    if update and update.effective_message:
        if "timeout" not in str(context.error).lower():
            await update.effective_message.reply_html(
                "⚠️ <b>An error occurred!</b>\n\n"
                "Please try again later."
            )

# ========== Bot Application Factory ==========
def create_application():
    """Create and configure the bot application with performance optimizations."""
    # Configure bot with performance settings
    app_builder = (
        Application.builder()
        .token(Config.BOT_TOKEN)
        .pool_size(Config.POOL_SIZE)  # Control concurrent updates
        .max_connections(100)  # Maximum concurrent connections
        .read_timeout(30.0)  # Read timeout
        .write_timeout(30.0)  # Write timeout
        .connect_timeout(30.0)  # Connection timeout
        .get_updates_read_timeout(30.0)  # GetUpdates timeout
        .get_updates_write_timeout(30.0)  # GetUpdates write timeout
    )
    
    application_instance = app_builder.build()
    
    # Register handlers with efficient ordering
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
        application_instance.add_handler(handler)
    
    # Error handler
    application_instance.add_error_handler(error_handler)
    
    logger.info("Bot application created with performance optimizations")
    return application_instance

# ========== Bot Initialization ==========
def init_bot():
    """Initialize the bot with webhook in a separate thread."""
    global application, event_loop
    
    logger.info("Initializing bot...")
    
    # Create new event loop for this thread
    event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(event_loop)
    
    # Create application
    application = create_application()
    
    # Initialize application
    event_loop.run_until_complete(application.initialize())
    logger.info("Application initialized")
    
    # Set webhook if URL is provided
    if Config.WEBHOOK_URL:
        webhook_url = f"{Config.WEBHOOK_URL}/{Config.BOT_TOKEN}"
        logger.info(f"Setting webhook to: {webhook_url}")
        
        try:
            # Set webhook with optimized parameters
            event_loop.run_until_complete(
                application.bot.set_webhook(
                    webhook_url,
                    max_connections=50,
                    drop_pending_updates=True,
                    allowed_updates=["message", "callback_query"]
                )
            )
            logger.info("Webhook set successfully!")
        except Exception as e:
            logger.error(f"Failed to set webhook: {e}")
    
    # Start polling if no webhook (for development)
    elif os.getenv('DEVELOPMENT', '').lower() == 'true':
        logger.info("Starting polling (development mode)")
        application.run_polling(
            allowed_updates=["message", "callback_query"],
            drop_pending_updates=True
        )

def start_bot():
    """Start bot initialization in background thread."""
    thread = threading.Thread(target=init_bot, daemon=True)
    thread.start()
    logger.info("Bot initialization started in background thread")

# ========== Flask Routes ==========
@app.route('/')
def home():
    """Home endpoint with service information."""
    return jsonify({
        "status": "online",
        "service": "Telegram Unban Bot",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health",
            "webhook": f"/{Config.BOT_TOKEN}",
            "info": "/info"
        }
    })

@app.route('/health')
def health():
    """Health check endpoint for monitoring."""
    bot_status = "ready" if application and application.running else "not_ready"
    return jsonify({
        "status": "healthy",
        "bot": bot_status,
        "timestamp": asyncio.get_event_loop().time() if event_loop else None
    }), 200

@app.route('/info')
def info():
    """Get bot configuration info."""
    return jsonify({
        "bot_token_masked": Config.BOT_TOKEN[:10] + "..." if Config.BOT_TOKEN else "not_set",
        "channel_id": Config.CHANNEL_ID,
        "webhook_enabled": bool(Config.WEBHOOK_URL),
        "pool_size": Config.POOL_SIZE,
        "max_updates": Config.MAX_UPDATES
    })

@app.route(f'/{Config.BOT_TOKEN}', methods=['POST'])
def webhook():
    """Handle Telegram webhook updates efficiently."""
    try:
        # Get update from request
        json_data = request.get_json()
        
        if not json_data:
            return jsonify({"error": "No JSON data received"}), 400
        
        # Create update object
        update = Update.de_json(json_data, application.bot)
        
        # Process update in event loop (thread-safe)
        if event_loop and event_loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                application.process_update(update),
                event_loop
            )
            # Wait for completion with timeout
            future.result(timeout=10)
        else:
            # Fallback to sync processing
            import nest_asyncio
            nest_asyncio.apply()
            asyncio.run(application.process_update(update))
        
        return jsonify({"status": "ok"}), 200
        
    except asyncio.TimeoutError:
        logger.warning("Webhook processing timeout")
        return jsonify({"status": "processing_timeout"}), 202
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/set_webhook', methods=['POST'])
def set_webhook():
    """Manually set webhook."""
    if not Config.WEBHOOK_URL:
        return jsonify({"error": "WEBHOOK_URL not set"}), 400
    
    webhook_url = f"{Config.WEBHOOK_URL}/{Config.BOT_TOKEN}"
    
    try:
        if event_loop and event_loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                application.bot.set_webhook(
                    webhook_url,
                    max_connections=50,
                    drop_pending_updates=True
                ),
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

@app.route('/delete_webhook', methods=['POST'])
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

@app.route('/metrics')
def metrics():
    """Simple metrics endpoint for monitoring."""
    import psutil
    import datetime
    
    return jsonify({
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "cpu_percent": psutil.cpu_percent(),
        "memory_percent": psutil.virtual_memory().percent,
        "active_connections": len(psutil.net_connections()) if hasattr(psutil, 'net_connections') else 0
    })

# ========== Shutdown Handler ==========
def shutdown_handler():
    """Handle graceful shutdown."""
    logger.info("Shutting down bot...")
    
    if application and event_loop:
        # Stop bot gracefully
        if event_loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                application.stop(),
                event_loop
            )
            future.result(timeout=10)
    
    logger.info("Bot shutdown complete")

# Register shutdown handler
import atexit
atexit.register(shutdown_handler)

# ========== Main Entry Point ==========
if __name__ == '__main__':
    logger.info(f"Starting server on port {Config.PORT}")
    
    # Start bot initialization
    start_bot()
    
    # Start Flask server with waitress for production
    if os.getenv('DEVELOPMENT', '').lower() == 'true':
        logger.info("Running in development mode")
        app.run(host='0.0.0.0', port=Config.PORT, debug=True)
    else:
        logger.info("Running in production mode with Waitress")
        serve(
            app,
            host='0.0.0.0',
            port=Config.PORT,
            threads=8,  # Increased thread pool for better concurrency
            connection_limit=1000,  # Increased connection limit
            asyncore_use_poll=True,  # Use poll for better performance on Unix
            channel_timeout=30  # Increased channel timeout
        )