#!/usr/bin/env python3
"""
Telegram Unban Bot - Render Deployment
Author: Your Name
Version: 2.1.0
"""

import os
import sys
import logging
import asyncio
from datetime import datetime
from typing import Optional

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Third-party imports
from flask import Flask, request, jsonify
from telegram import Update, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ApplicationBuilder
)
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ========== CONFIGURATION ==========
class Config:
    """Application configuration."""
    
    # Bot Configuration (REQUIRED)
    BOT_TOKEN = os.getenv('BOT_TOKEN', '').strip()
    CHANNEL_ID = os.getenv('CHANNEL_ID', '').strip()
    
    # Render automatically provides PORT
    PORT = int(os.getenv('PORT', 10000))
    
    # Webhook URL (Render provides RENDER_EXTERNAL_URL)
    RENDER_EXTERNAL_URL = os.getenv('RENDER_EXTERNAL_URL', '').strip()
    WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}/webhook" if RENDER_EXTERNAL_URL else None
    
    # Bot mode
    MODE = os.getenv('MODE', 'production').lower()
    DEBUG = MODE == 'development'
    
    @classmethod
    def validate(cls) -> bool:
        """Validate configuration."""
        errors = []
        
        # Check BOT_TOKEN
        if not cls.BOT_TOKEN:
            errors.append("BOT_TOKEN is not set")
        elif not cls.BOT_TOKEN.startswith('bot') and ':' not in cls.BOT_TOKEN:
            errors.append("BOT_TOKEN format is invalid. Should be like: 1234567890:ABCdefGhIJKlmNoPQRsTUVwxyZ")
        
        # Check CHANNEL_ID
        if not cls.CHANNEL_ID:
            errors.append("CHANNEL_ID is not set")
        else:
            try:
                cls.CHANNEL_ID = int(cls.CHANNEL_ID)
            except ValueError:
                errors.append("CHANNEL_ID must be a number")
        
        # Check for Render
        if not cls.RENDER_EXTERNAL_URL:
            print("⚠️  RENDER_EXTERNAL_URL not set. Webhook might not work properly.")
        
        if errors:
            print("❌ Configuration Errors:")
            for error in errors:
                print(f"   - {error}")
            print("\n🔧 Setup Instructions:")
            print("1. Create bot: @BotFather → /newbot")
            print("2. Get channel ID: Add @userinfobot to your channel, send /start")
            print("3. Add bot to channel as ADMIN with Ban Users permission")
            print("4. Set environment variables in Render:")
            print("   - BOT_TOKEN: your_bot_token")
            print("   - CHANNEL_ID: your_channel_id")
            print("   - MODE: production")
            return False
        
        print("✅ Configuration validated successfully!")
        print(f"🤖 Bot Token: {cls.BOT_TOKEN[:10]}...")
        print(f"📢 Channel ID: {cls.CHANNEL_ID}")
        print(f"🌐 Port: {cls.PORT}")
        print(f"🔧 Mode: {cls.MODE}")
        print(f"🌍 External URL: {cls.RENDER_EXTERNAL_URL or 'Not set'}")
        
        return True

# Validate config
if not Config.validate():
    sys.exit(1)

# ========== LOGGING SETUP ==========
def setup_logging():
    """Configure logging for Render."""
    log_level = logging.DEBUG if Config.DEBUG else logging.INFO
    
    # Configure root logger
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.StreamHandler(sys.stdout),  # Render captures stdout
            logging.FileHandler('bot.log', encoding='utf-8') if not Config.DEBUG else None
        ]
    )
    
    # Reduce noise from libraries
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('telegram').setLevel(logging.INFO)
    
    logger = logging.getLogger(__name__)
    logger.info("Logging configured for %s mode", Config.MODE)
    
    return logger

logger = setup_logging()

# ========== FLASK APP ==========
app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False

# ========== GLOBAL STATE ==========
bot_app: Optional[Application] = None
bot_start_time: Optional[datetime] = None

# ========== BOT COMMAND HANDLERS ==========
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    user = update.effective_user
    logger.info(f"Start command from {user.id} (@{user.username})")
    
    welcome_text = (
        f"👋 Hello {user.mention_html()}!\n\n"
        f"🤖 <b>Telegram Unban Bot</b>\n\n"
        f"📋 <b>Available Commands:</b>\n"
        f"• /start - Show this message\n"
        f"• /help - Get help\n"
        f"• /unban [user_id] - Unban a user\n\n"
        f"🚀 <b>Quick Usage:</b>\n"
        f"1. Get user ID from @userinfobot\n"
        f"2. Send me: <code>/unban 123456789</code>\n"
        f"   OR just send the number\n\n"
        f"⚙️ <b>Current Settings:</b>\n"
        f"• Channel ID: <code>{Config.CHANNEL_ID}</code>\n"
        f"• Bot Status: ✅ Active\n\n"
        f"Need help? Type /help"
    )
    
    await update.message.reply_html(welcome_text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    help_text = (
        "🆘 <b>Help & Support</b>\n\n"
        "📋 <b>Commands:</b>\n"
        "/start - Start the bot\n"
        "/help - Show this help\n"
        "/unban [ID] - Unban a user\n\n"
        "🎯 <b>How to Unban:</b>\n"
        "1. Get the user's ID from @userinfobot\n"
        "2. Send me: <code>/unban USER_ID</code>\n"
        "   Example: <code>/unban 123456789</code>\n"
        "   OR just send the number\n\n"
        "⚠️ <b>Requirements:</b>\n"
        "• I must be an admin in your channel\n"
        "• I need 'Ban Users' permission\n"
        "• Channel ID must be correct\n\n"
        f"🔧 <b>Configured Channel:</b> <code>{Config.CHANNEL_ID}</code>\n\n"
        "❓ <b>Problems?</b>\n"
        "1. Check I'm admin in channel\n"
        "2. Check channel ID is correct\n"
        "3. Make sure user is actually banned"
    )
    
    await update.message.reply_html(help_text)

async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /unban command."""
    user = update.effective_user
    logger.info(f"Unban command from {user.id}")
    
    # Check if user provided ID
    if not context.args:
        await update.message.reply_html(
            "❌ <b>Usage:</b> <code>/unban USER_ID</code>\n\n"
            "Example: <code>/unban 123456789</code>\n\n"
            "Get user ID from @userinfobot"
        )
        return
    
    user_id = context.args[0].strip()
    await process_unban_request(update, user_id)

async def handle_direct_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle direct messages (non-commands)."""
    text = update.message.text.strip()
    
    if not text:
        return
    
    # If message is just numbers (likely a user ID)
    if text.isdigit() and len(text) >= 5:
        await process_unban_request(update, text)
    elif not text.startswith('/'):
        # Not a command and not a number
        await update.message.reply_html(
            "📝 <b>Send me a User ID to unban</b>\n\n"
            "1. Get user ID from @userinfobot\n"
            "2. Send me the number\n"
            "   Example: <code>123456789</code>\n\n"
            "Or use: <code>/unban 123456789</code>"
        )

async def process_unban_request(update: Update, user_id: str) -> None:
    """Process unban request."""
    try:
        # Convert to integer
        target_user_id = int(user_id)
        chat_id = update.effective_chat.id
        
        logger.info(f"Processing unban: User {target_user_id} from channel {Config.CHANNEL_ID}")
        
        # Send processing message
        processing_msg = await update.message.reply_html(
            f"⏳ <b>Processing...</b>\n"
            f"User: <code>{user_id}</code>\n"
            f"Channel: <code>{Config.CHANNEL_ID}</code>"
        )
        
        # Attempt to unban
        result = await update.effective_chat.bot.unban_chat_member(
            chat_id=Config.CHANNEL_ID,
            user_id=target_user_id,
            only_if_banned=True
        )
        
        # Success
        await processing_msg.edit_text(
            f"✅ <b>Successfully Unbanned!</b>\n\n"
            f"👤 User ID: <code>{user_id}</code>\n"
            f"📢 Channel: <code>{Config.CHANNEL_ID}</code>\n\n"
            f"🎉 The user can now join the channel again.",
            parse_mode='HTML'
        )
        
        logger.info(f"Successfully unbanned user {target_user_id}")
        
    except ValueError:
        await update.message.reply_html(
            "❌ <b>Invalid User ID!</b>\n\n"
            "User ID must contain only numbers.\n"
            "Example: <code>123456789</code>"
        )
    except Exception as e:
        error_msg = str(e).lower()
        logger.error(f"Unban error: {error_msg}")
        
        if "not enough rights" in error_msg:
            await update.message.reply_html(
                "❌ <b>Permission Denied!</b>\n\n"
                "I need to be an <b>ADMIN</b> in the channel with:\n"
                "• <b>Ban Users</b> permission\n\n"
                f"Channel: <code>{Config.CHANNEL_ID}</code>\n\n"
                "Please add me as admin and try again."
            )
        elif "chat not found" in error_msg:
            await update.message.reply_html(
                "❌ <b>Channel Not Found!</b>\n\n"
                f"Channel ID <code>{Config.CHANNEL_ID}</code> is incorrect.\n"
                "Please check your configuration."
            )
        elif "user not found" in error_msg:
            await update.message.reply_html("❌ User not found!")
        elif "not banned" in error_msg:
            await update.message.reply_html(
                "✅ <b>User is not banned!</b>\n\n"
                f"User <code>{user_id}</code> can already join the channel."
            )
        else:
            await update.message.reply_html(
                f"❌ <b>Error:</b> {error_msg[:200]}\n\n"
                "Please try again later."
            )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle bot errors."""
    logger.error(f"Bot error: {context.error}", exc_info=True)
    
    # Try to notify user
    if update and update.effective_message:
        try:
            await update.effective_message.reply_html(
                "⚠️ <b>An error occurred!</b>\n"
                "Please try again later."
            )
        except:
            pass

# ========== BOT SETUP ==========
async def create_bot_application() -> Application:
    """Create and configure the bot application."""
    logger.info("Creating bot application...")
    
    # Build application
    builder = ApplicationBuilder().token(Config.BOT_TOKEN)
    
    # Configure for webhook mode (required for Render)
    builder = (
        builder
        .read_timeout(30)
        .write_timeout(30)
        .connect_timeout(30)
        .pool_timeout(30)
    )
    
    app_instance = builder.build()
    
    # Register handlers
    app_instance.add_handler(CommandHandler("start", start_command))
    app_instance.add_handler(CommandHandler("help", help_command))
    app_instance.add_handler(CommandHandler("unban", unban_command))
    
    # Handle direct messages (user IDs)
    app_instance.add_handler(MessageHandler(
        filters.TEXT & filters.ChatType.PRIVATE & ~filters.COMMAND,
        handle_direct_message
    ))
    
    # Error handler
    app_instance.add_error_handler(error_handler)
    
    logger.info("Bot application created successfully")
    return app_instance

async def setup_webhook(app_instance: Application) -> bool:
    """Set up webhook for the bot."""
    if not Config.WEBHOOK_URL:
        logger.warning("No WEBHOOK_URL configured, skipping webhook setup")
        return False
    
    try:
        logger.info(f"Setting webhook to: {Config.WEBHOOK_URL}")
        
        # Set webhook
        await app_instance.bot.set_webhook(
            url=Config.WEBHOOK_URL,
            max_connections=50,
            drop_pending_updates=True,
            allowed_updates=["message", "callback_query"]
        )
        
        # Verify webhook
        webhook_info = await app_instance.bot.get_webhook_info()
        logger.info(f"Webhook info: {webhook_info.url}")
        
        if webhook_info.url == Config.WEBHOOK_URL:
            logger.info("✅ Webhook set successfully")
            return True
        else:
            logger.error(f"Webhook mismatch: {webhook_info.url} != {Config.WEBHOOK_URL}")
            return False
            
    except Exception as e:
        logger.error(f"Failed to set webhook: {e}")
        return False

async def initialize_bot():
    """Initialize the bot application."""
    global bot_app, bot_start_time
    
    try:
        logger.info("🚀 Initializing Telegram Bot...")
        
        # Create bot application
        bot_app = await create_bot_application()
        
        # Initialize
        await bot_app.initialize()
        
        # Get bot info
        bot_info = await bot_app.bot.get_me()
        logger.info(f"🤖 Bot Info: @{bot_info.username} (ID: {bot_info.id})")
        
        # Setup webhook (required for Render)
        if not await setup_webhook(bot_app):
            logger.warning("⚠️ Running without webhook (not recommended for Render)")
        
        # Start bot (non-blocking)
        await bot_app.start()
        
        bot_start_time = datetime.utcnow()
        logger.info("✅ Bot initialized and ready!")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize bot: {e}", exc_info=True)
        return False

# ========== FLASK ROUTES ==========
@app.route('/')
def home():
    """Home page."""
    uptime = str(datetime.utcnow() - bot_start_time) if bot_start_time else "0:00:00"
    
    return jsonify({
        "status": "online",
        "service": "Telegram Unban Bot",
        "version": "2.1.0",
        "uptime": uptime,
        "endpoints": {
            "/health": "Health check",
            "/info": "Bot information",
            "/webhook": "Telegram webhook (POST only)"
        },
        "environment": {
            "mode": Config.MODE,
            "port": Config.PORT,
            "has_webhook": bool(Config.WEBHOOK_URL)
        }
    })

@app.route('/health')
def health():
    """Health check endpoint for Render."""
    try:
        bot_status = "running" if bot_app and bot_app.running else "starting"
        
        response = {
            "status": "healthy",
            "bot": bot_status,
            "timestamp": datetime.utcnow().isoformat(),
            "checks": {
                "bot_initialized": bot_app is not None,
                "bot_running": bot_app.running if bot_app else False,
                "config_valid": True
            }
        }
        
        return jsonify(response), 200
    except Exception as e:
        return jsonify({"status": "unhealthy", "error": str(e)}), 500

@app.route('/info')
def info():
    """Bot information."""
    return jsonify({
        "channel_id": Config.CHANNEL_ID,
        "bot_configured": bool(Config.BOT_TOKEN),
        "webhook_url": Config.WEBHOOK_URL or "Not configured",
        "render_url": Config.RENDER_EXTERNAL_URL or "Not set",
        "start_time": bot_start_time.isoformat() if bot_start_time else None,
        "mode": Config.MODE
    })

@app.route('/webhook', methods=['POST'])
async def webhook():
    """Handle Telegram webhook updates."""
    try:
        if not bot_app:
            return jsonify({"error": "Bot not initialized"}), 503
        
        # Get update from request
        json_data = request.get_json()
        
        if not json_data:
            return jsonify({"error": "No JSON data"}), 400
        
        # Create update object
        update = Update.de_json(json_data, bot_app.bot)
        
        # Process update
        await bot_app.process_update(update)
        
        return jsonify({"status": "ok"}), 200
        
    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route('/set_webhook', methods=['POST'])
async def set_webhook_manual():
    """Manually set webhook (for debugging)."""
    try:
        if not bot_app:
            return jsonify({"error": "Bot not initialized"}), 503
        
        result = await setup_webhook(bot_app)
        
        if result:
            return jsonify({
                "success": True,
                "webhook_url": Config.WEBHOOK_URL,
                "message": "Webhook set successfully"
            }), 200
        else:
            return jsonify({
                "success": False,
                "error": "Failed to set webhook"
            }), 500
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ========== APPLICATION LIFECYCLE ==========
def run_app():
    """Run the Flask application."""
    logger.info(f"Starting Flask app on port {Config.PORT}")
    
    # Development mode
    if Config.DEBUG:
        app.run(
            host='0.0.0.0',
            port=Config.PORT,
            debug=True,
            use_reloader=False  # Disable reloader for async compatibility
        )
    else:
        # Production mode
        from waitress import serve
        serve(
            app,
            host='0.0.0.0',
            port=Config.PORT,
            threads=4,
            channel_timeout=30
        )

async def main():
    """Main async entry point."""
    # Initialize bot
    if not await initialize_bot():
        logger.error("Failed to initialize bot. Exiting.")
        sys.exit(1)
    
    # Start Flask app in background
    import threading
    flask_thread = threading.Thread(target=run_app, daemon=True)
    flask_thread.start()
    
    logger.info(f"✅ Bot is running on port {Config.PORT}")
    logger.info(f"🌍 Webhook URL: {Config.WEBHOOK_URL or 'Not set'}")
    
    # Keep the main thread alive
    try:
        while True:
            await asyncio.sleep(3600)  # Sleep for 1 hour
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        if bot_app:
            await bot_app.stop()
            await bot_app.shutdown()
        sys.exit(0)

# ========== ENTRY POINT ==========
if __name__ == '__main__':
    # Run the async main function
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)