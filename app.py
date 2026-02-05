# app.py - Telegram Unban Bot with Enhanced Debugging
import logging
import asyncio
import threading
import os
import sys
from typing import Optional
from datetime import datetime
from flask import Flask, request, jsonify
from waitress import serve
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv

# ========== Load Environment Variables ==========
load_dotenv()

# ========== Configuration ==========
class Config:
    """Configuration management."""
    
    # Bot Configuration
    BOT_TOKEN = os.getenv('BOT_TOKEN', '').strip()
    
    # Channel Configuration
    CHANNEL_ID = os.getenv('CHANNEL_ID', '').strip()
    if CHANNEL_ID:
        try:
            CHANNEL_ID = int(CHANNEL_ID)
        except ValueError:
            print(f"❌ ERROR: CHANNEL_ID must be a number, got '{CHANNEL_ID}'")
            sys.exit(1)
    
    # Server Configuration
    PORT = int(os.getenv('PORT', 10000))
    HOST = os.getenv('HOST', '0.0.0.0')
    
    # Webhook Configuration
    WEBHOOK_URL = os.getenv('WEBHOOK_URL', '').strip()
    WEBHOOK_PATH = f"/{BOT_TOKEN}" if BOT_TOKEN else "/webhook"
    
    # Mode
    DEVELOPMENT = os.getenv('DEVELOPMENT', 'false').lower() == 'true'
    
    @classmethod
    def validate(cls):
        """Validate configuration."""
        errors = []
        
        if not cls.BOT_TOKEN:
            errors.append("BOT_TOKEN is required (get from @BotFather)")
        
        if not cls.CHANNEL_ID:
            errors.append("CHANNEL_ID is required (must be a number)")
        
        if cls.BOT_TOKEN and not cls.BOT_TOKEN.startswith('bot'):
            if ':' not in cls.BOT_TOKEN:
                errors.append("BOT_TOKEN format incorrect. Should be like: 1234567890:ABCdefGhIJKlmNoPQRsTUVwxyZ")
        
        if errors:
            print("❌ Configuration errors:")
            for error in errors:
                print(f"   - {error}")
            print("\n📝 Setup instructions:")
            print("1. Create bot: @BotFather → /newbot")
            print("2. Get channel ID: Add @userinfobot to channel, send /start")
            print("3. Add bot as admin in channel with ban permissions")
            return False
        
        print("✅ Configuration validated!")
        print(f"🤖 Bot Token: {cls.BOT_TOKEN[:10]}...")
        print(f"📢 Channel ID: {cls.CHANNEL_ID}")
        print(f"🌐 Port: {cls.PORT}")
        print(f"🔧 Mode: {'Development' if cls.DEVELOPMENT else 'Production'}")
        
        # Test bot token
        try:
            bot = Bot(cls.BOT_TOKEN)
            bot_info = asyncio.run(bot.get_me())
            print(f"✅ Bot connected: @{bot_info.username} ({bot_info.id})")
        except Exception as e:
            print(f"❌ Failed to connect to bot: {e}")
            return False
        
        return True

# Validate configuration
if not Config.validate():
    sys.exit(1)

# ========== Logging Setup ==========
logging.basicConfig(
    level=logging.DEBUG if Config.DEVELOPMENT else logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/app/logs/bot.log', encoding='utf-8')
    ]
)

# Set specific log levels
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('telegram').setLevel(logging.INFO)

logger = logging.getLogger(__name__)

# ========== Flask Application ==========
app = Flask(__name__)

# ========== Global State ==========
application: Optional[Application] = None
event_loop: Optional[asyncio.AbstractEventLoop] = None

# ========== Bot Handlers ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    user = update.effective_user
    logger.info(f"Start command from user {user.id}")
    
    message = (
        f"👋 Hi {user.mention_html()}!\n\n"
        f"🤖 <b>Unban Bot Active</b>\n\n"
        f"📋 <b>Commands:</b>\n"
        f"• /start - Show this message\n"
        f"• /help - Help guide\n"
        f"• /unban [ID] - Unban user\n\n"
        f"🎯 <b>How to use:</b>\n"
        f"1. Get user ID from @userinfobot\n"
        f"2. Send me the ID\n"
        f"3. I'll unban them\n\n"
        f"⚡ <b>Quick unban:</b>\n"
        f"Just send: <code>123456789</code>\n\n"
        f"📢 <b>Channel ID:</b> <code>{Config.CHANNEL_ID}</code>\n"
        f"🔧 <b>Bot Status:</b> ✅ Active"
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
        "⚠️ <b>Important:</b>\n"
        "• I must be an admin in your channel\n"
        "• I need 'Ban Users' permission\n"
        "• Channel ID must be correct\n\n"
        f"🔧 <b>Current Channel:</b> <code>{Config.CHANNEL_ID}</code>"
    )
    await update.message.reply_html(help_text)

async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /unban command."""
    logger.info(f"Unban command from {update.effective_user.id}")
    
    if not context.args:
        await update.message.reply_html(
            "❌ <b>Usage:</b> <code>/unban USER_ID</code>\n"
            "Example: <code>/unban 123456789</code>\n\n"
            "Get user ID from @userinfobot"
        )
        return
    
    user_id = context.args[0]
    await process_unban(update, context, user_id)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle direct messages."""
    text = update.message.text.strip()
    user_id = update.effective_user.id
    
    logger.info(f"Message from {user_id}: {text}")
    
    if not text:
        return
    
    # Check if message is numeric (user ID)
    if text.isdigit() and len(text) >= 5:
        await process_unban(update, context, text)
    elif not text.startswith('/'):
        await update.message.reply_html(
            "❌ Send a valid User ID (numbers only)\n"
            "Example: <code>123456789</code>\n"
            "Get ID from @userinfobot\n\n"
            "Or use: <code>/unban 123456789</code>"
        )

async def process_unban(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: str):
    """Process unban request."""
    try:
        user_id_int = int(user_id)
        chat_id = update.effective_chat.id
        
        logger.info(f"Attempting to unban user {user_id_int} from channel {Config.CHANNEL_ID}")
        
        # Send processing message
        processing_msg = await update.message.reply_html(
            f"🔄 <b>Processing...</b>\n"
            f"User: <code>{user_id}</code>\n"
            f"Channel: <code>{Config.CHANNEL_ID}</code>"
        )
        
        # Unban the user
        result = await context.bot.unban_chat_member(
            chat_id=Config.CHANNEL_ID,
            user_id=user_id_int,
            only_if_banned=True
        )
        
        logger.info(f"Unban result: {result}")
        
        # Edit the processing message with success
        await processing_msg.edit_text(
            f"✅ <b>Successfully Unbanned!</b>\n\n"
            f"👤 User ID: <code>{user_id}</code>\n"
            f"📢 Channel: <code>{Config.CHANNEL_ID}</code>\n\n"
            f"🎉 The user can now join the channel again.",
            parse_mode='HTML'
        )
        
    except ValueError:
        await update.message.reply_html(
            "❌ <b>Invalid User ID!</b>\n\n"
            "User ID must contain only numbers.\n"
            "Example: <code>123456789</code>"
        )
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Unban error: {error_msg}")
        
        if "not enough rights" in error_msg.lower():
            await update.message.reply_html(
                "❌ <b>Permission Error!</b>\n\n"
                "I need to be an ADMIN in the channel with:\n"
                "• Ban Users permission\n\n"
                f"Channel ID: <code>{Config.CHANNEL_ID}</code>\n\n"
                "Please add me as admin and try again."
            )
        elif "user not found" in error_msg.lower():
            await update.message.reply_html("❌ User not found!")
        elif "not banned" in error_msg.lower():
            await update.message.reply_html(
                "✅ User is not banned!\n\n"
                f"User <code>{user_id}</code> is not banned from the channel."
            )
        elif "chat not found" in error_msg.lower():
            await update.message.reply_html(
                "❌ <b>Channel not found!</b>\n\n"
                f"Channel ID <code>{Config.CHANNEL_ID}</code> is incorrect.\n"
                "Please check your configuration."
            )
        else:
            await update.message.reply_html(
                f"❌ <b>Error:</b> {error_msg[:100]}\n\n"
                "Please try again or check the bot logs."
            )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors."""
    logger.error(f"Update {update} caused error {context.error}", exc_info=True)
    
    if update and update.effective_message:
        try:
            await update.effective_message.reply_html(
                "⚠️ <b>An error occurred!</b>\n"
                "The developer has been notified."
            )
        except:
            pass

# ========== Bot Setup ==========
def create_application():
    """Create and configure the bot application."""
    logger.info("Creating bot application...")
    
    # Create application
    app_builder = Application.builder().token(Config.BOT_TOKEN)
    
    # Add persistence for development
    if Config.DEVELOPMENT:
        from telegram.ext import PersistenceDict
        app_builder.persistence(PersistenceDict())
    
    application_instance = app_builder.build()
    
    # Register handlers
    application_instance.add_handler(CommandHandler("start", start))
    application_instance.add_handler(CommandHandler("help", help_command))
    application_instance.add_handler(CommandHandler("unban", unban_command))
    application_instance.add_handler(MessageHandler(
        filters.TEXT & filters.ChatType.PRIVATE & ~filters.COMMAND,
        handle_message
    ))
    
    application_instance.add_error_handler(error_handler)
    
    logger.info("Bot handlers registered")
    return application_instance

def init_bot():
    """Initialize the bot."""
    global application, event_loop
    
    try:
        logger.info("=== Bot Initialization Start ===")
        
        # Create event loop
        event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(event_loop)
        
        # Create application
        application = create_application()
        
        # Initialize
        event_loop.run_until_complete(application.initialize())
        logger.info("✅ Bot initialized")
        
        # Start polling (simplest approach)
        logger.info("🔄 Starting bot polling...")
        
        # Run polling in background
        def run_polling():
            asyncio.set_event_loop(event_loop)
            event_loop.run_until_complete(application.run_polling(
                drop_pending_updates=True,
                timeout=30,
                pool_timeout=30,
                connect_timeout=30,
                read_timeout=30
            ))
        
        # Start polling in separate thread
        polling_thread = threading.Thread(target=run_polling, daemon=True)
        polling_thread.start()
        
        logger.info("✅ Bot polling started")
        
        # Wait a bit for bot to connect
        import time
        time.sleep(2)
        
        # Test bot connection
        bot_info = event_loop.run_until_complete(application.bot.get_me())
        logger.info(f"🤖 Bot Info: @{bot_info.username} (ID: {bot_info.id})")
        
        logger.info("=== Bot Initialization Complete ===")
        
    except Exception as e:
        logger.error(f"❌ Bot initialization failed: {e}", exc_info=True)
        sys.exit(1)

# ========== Flask Routes ==========
@app.route('/')
def home():
    """Home page."""
    return jsonify({
        "status": "online",
        "service": "Telegram Unban Bot",
        "version": "2.0.0",
        "timestamp": datetime.utcnow().isoformat(),
        "endpoints": {
            "/health": "Health check",
            "/info": "Bot info",
            "/debug": "Debug info"
        }
    })

@app.route('/health')
def health():
    """Health check."""
    bot_status = "ready" if application and application.running else "starting"
    return jsonify({
        "status": "healthy",
        "bot": bot_status,
        "timestamp": datetime.utcnow().isoformat()
    }), 200

@app.route('/info')
def info():
    """Bot information."""
    return jsonify({
        "bot_token_exists": bool(Config.BOT_TOKEN),
        "bot_token_preview": Config.BOT_TOKEN[:10] + "..." if Config.BOT_TOKEN else "not_set",
        "channel_id": Config.CHANNEL_ID,
        "port": Config.PORT,
        "mode": "development" if Config.DEVELOPMENT else "production",
        "webhook_url": Config.WEBHOOK_URL or "not_set"
    })

@app.route('/debug')
def debug():
    """Debug information."""
    try:
        bot_info = {}
        if application and application.bot:
            # Get bot info safely
            try:
                if event_loop and event_loop.is_running():
                    # We can't run async code here easily, just return basic info
                    bot_info = {"bot": "running", "event_loop": "active"}
            except:
                pass
        
        return jsonify({
            "python_version": sys.version,
            "environment": dict(os.environ),
            "working_directory": os.getcwd(),
            "files_in_dir": os.listdir('.'),
            "bot_info": bot_info,
            "config": {
                "bot_token_set": bool(Config.BOT_TOKEN),
                "channel_id": Config.CHANNEL_ID,
                "port": Config.PORT
            }
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/test-unban/<user_id>')
def test_unban(user_id):
    """Test unban endpoint (for debugging)."""
    try:
        from telegram import Bot
        bot = Bot(Config.BOT_TOKEN)
        
        async def test():
            try:
                await bot.unban_chat_member(
                    chat_id=Config.CHANNEL_ID,
                    user_id=int(user_id),
                    only_if_banned=True
                )
                return {"success": True, "user_id": user_id}
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        result = asyncio.run(test())
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ========== Main Execution ==========
if __name__ == '__main__':
    print("\n" + "="*50)
    print("🚀 Telegram Unban Bot Starting...")
    print("="*50 + "\n")
    
    # Create logs directory
    os.makedirs('/app/logs', exist_ok=True)
    
    # Initialize bot
    init_bot()
    
    # Start Flask server
    print(f"\n🌐 Starting web server on {Config.HOST}:{Config.PORT}")
    print("📝 Available endpoints:")
    print(f"   http://{Config.HOST}:{Config.PORT}/")
    print(f"   http://{Config.HOST}:{Config.PORT}/health")
    print(f"   http://{Config.HOST}:{Config.PORT}/debug")
    print(f"   http://{Config.HOST}:{Config.PORT}/test-unban/123456789")
    print("\n🤖 Bot should be running. Try sending /start to your bot.")
    print("="*50 + "\n")
    
    if Config.DEVELOPMENT:
        app.run(
            host=Config.HOST,
            port=Config.PORT,
            debug=True,
            use_reloader=False
        )
    else:
        serve(
            app,
            host=Config.HOST,
            port=Config.PORT,
            threads=4,
            channel_timeout=30
        )