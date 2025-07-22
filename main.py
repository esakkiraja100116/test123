import asyncio
import os
import json
from datetime import datetime
from typing import Dict
from pathlib import Path
from slack_sdk import WebClient
from slack_sdk.socket_mode import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse
from slack_sdk.errors import SlackApiError
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Load environment variables - these must be set in .env file
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
CHANNEL_NAME = os.getenv("CHANNEL_NAME")

# JSON file path for storing messages
MESSAGES_FILE = "slack_messages.json"

# Validate that all required environment variables are set
if not all([SLACK_BOT_TOKEN, SLACK_APP_TOKEN, CHANNEL_ID, CHANNEL_NAME]):
    missing_vars = []
    if not SLACK_BOT_TOKEN:
        missing_vars.append("SLACK_BOT_TOKEN")
    if not SLACK_APP_TOKEN:
        missing_vars.append("SLACK_APP_TOKEN")
    if not CHANNEL_ID:
        missing_vars.append("CHANNEL_ID")
    if not CHANNEL_NAME:
        missing_vars.append("CHANNEL_NAME")
    
    print("❌ Error: Missing required environment variables:")
    for var in missing_vars:
        print(f"   - {var}")
    print("\n📝 Please create a .env file with the required variables.")
    print("💡 You can copy env.example to .env and fill in your values.")
    exit(1)

class RealtimeSlackListener:
    def __init__(self, bot_token: str, app_token: str, channel_id: str):
        self.bot_token = bot_token
        self.app_token = app_token
        self.channel_id = channel_id
        self.channel_name = CHANNEL_NAME
        
        # Initialize clients
        self.web_client = WebClient(token=bot_token)
        self.socket_client = SocketModeClient(
            app_token=app_token,
            web_client=self.web_client
        )
        
        # Register event handler
        self.socket_client.socket_mode_request_listeners.append(self.handle_message_events)
        
        # Initialize messages file
        self.initialize_messages_file()
        
    def initialize_messages_file(self):
        """Initialize the JSON file for storing messages"""
        if not Path(MESSAGES_FILE).exists():
            with open(MESSAGES_FILE, 'w', encoding='utf-8') as f:
                json.dump({
                    "channel_name": self.channel_name,
                    "channel_id": self.channel_id,
                    "messages": []
                }, f, indent=2, ensure_ascii=False)
            print(f"📁 Created new messages file: {MESSAGES_FILE}")
        
    def save_message_to_json(self, message_data: Dict):
        """Save message to JSON file"""
        try:
            # Check if file exists and has content
            if Path(MESSAGES_FILE).exists() and Path(MESSAGES_FILE).stat().st_size > 0:
                # Read existing messages
                with open(MESSAGES_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            else:
                # Initialize new data structure
                data = {
                    "channel_name": self.channel_name,
                    "channel_id": self.channel_id,
                    "messages": []
                }
            
            # Add new message
            data["messages"].append(message_data)
            
            # Write back to file
            with open(MESSAGES_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            print(f"💾 Message saved to {MESSAGES_FILE}")
            
        except Exception as e:
            print(f"❌ Error saving message to JSON: {e}")
            # Try to create a fresh file as fallback
            try:
                data = {
                    "channel_name": self.channel_name,
                    "channel_id": self.channel_id,
                    "messages": [message_data]
                }
                with open(MESSAGES_FILE, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                print(f"🔄 Created fresh {MESSAGES_FILE} with message")
            except Exception as fallback_error:
                print(f"❌ Critical error: Could not save message at all: {fallback_error}")
        
    def get_user_info(self, user_id: str) -> Dict:
        """Get user information by user ID"""
        try:
            response = self.web_client.users_info(user=user_id)
            user = response["user"]
            return {
                "id": user["id"],
                "name": user["name"],
                "real_name": user.get("real_name", ""),
                "display_name": user.get("profile", {}).get("display_name", ""),
                "email": user.get("profile", {}).get("email", "")
            }
        except SlackApiError as e:
            return {"id": user_id, "name": "Unknown", "real_name": "", "display_name": "", "email": ""}
    
    def format_timestamp(self, ts: str) -> str:
        """Convert Slack timestamp to readable format"""
        timestamp = float(ts)
        dt = datetime.fromtimestamp(timestamp)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    
    def print_message(self, event: Dict):
        """Print message instantly when received and save to JSON"""
        user_info = self.get_user_info(event["user"])
        formatted_time = self.format_timestamp(event["ts"])
        
        # Create message data for JSON storage
        message_data = {
            "timestamp": formatted_time,
            "slack_timestamp": event["ts"],
            "user": {
                "id": user_info["id"],
                "name": user_info["name"],
                "real_name": user_info["real_name"],
                "display_name": user_info["display_name"],
                "email": user_info["email"]
            },
            "message": event["text"],
            "channel_name": self.channel_name,
            "channel_id": self.channel_id,
            "message_id": event.get("client_msg_id", ""),
            "thread_ts": event.get("thread_ts", ""),
            "parent_user_id": event.get("parent_user_id", ""),
            "reactions": event.get("reactions", []),
            "attachments": event.get("attachments", []),
            "files": event.get("files", [])
        }
        
        # Print to console
        print("\n🔔 NEW MESSAGE!")
        print("=" * 60)
        print(f"📅 {formatted_time}")
        print(f"👤 {user_info['real_name']} (@{user_info['name']})")
        print(f"💬 {event['text']}")
        print(f"📍 #{self.channel_name}")
        print("=" * 60)
        
        # Save to JSON file
        self.save_message_to_json(message_data)
    
    def handle_message_events(self, client: SocketModeClient, req: SocketModeRequest):
        """Handle incoming message events in real-time"""
        
        # Acknowledge the request immediately
        response = SocketModeResponse(envelope_id=req.envelope_id)
        client.send_socket_mode_response(response)
        
        # Debug: Print all incoming events
        print(f"\n📨 Received event type: {req.type}")
        if req.type == "events_api":
            event = req.payload["event"]
            print(f"📋 Event details: {event.get('type', 'unknown')} in channel {event.get('channel', 'unknown')}")
            
            # Check if it's a message in our target channel
            if (event["type"] == "message" and 
                event.get("channel") == self.channel_id and
                "user" in event and  # Skip bot messages
                event.get("subtype") is None):  # Skip edits, deletes, etc.
                
                print(f"✅ Processing message from user {event['user']}")
                # Print the message instantly
                self.print_message(event)
            else:
                print(f"❌ Skipping event: type={event.get('type')}, channel={event.get('channel')}, user={'user' in event}, subtype={event.get('subtype')}")
        elif req.type == "interactive":
            print(f"🔘 Interactive event received")
        else:
            print(f"📝 Other event type: {req.type}")
    
    def start_listening(self):
        """Start real-time listening for messages"""
        print(f"🚀 Starting REAL-TIME listener for #{self.channel_name}...")
        print(f"📡 Connected to channel: {self.channel_id}")
        
        # Test bot access to channel
        try:
            channel_info = self.web_client.conversations_info(channel=self.channel_id)
            print(f"✅ Bot can access channel: {channel_info['channel']['name']}")
        except SlackApiError as e:
            print(f"❌ Bot cannot access channel: {e.response['error']}")
            print("💡 Make sure the bot is added to the channel!")
            return
        
        print("🔔 Waiting for messages... (Press Ctrl+C to stop)")
        print("⚡ Messages will appear INSTANTLY when posted!")
        print("🔍 Debug mode: All events will be logged")
        print("-" * 60)
        
        try:
            # Connect to Slack WebSocket
            self.socket_client.connect()
            
            # Keep the connection alive
            while True:
                import time
                time.sleep(1)
                
        except KeyboardInterrupt:
            print("\n\n👋 Stopping real-time listener...")
            self.socket_client.disconnect()
        except Exception as e:
            print(f"❌ Error: {e}")
            self.socket_client.disconnect()

# Run the real-time listener
if __name__ == "__main__":
    print("⚡ REAL-TIME Slack Message Listener")
    print("=" * 40)
    
    # Create and start real-time listener
    listener = RealtimeSlackListener(SLACK_BOT_TOKEN, SLACK_APP_TOKEN, CHANNEL_ID)
    listener.start_listening() 