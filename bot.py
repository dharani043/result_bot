import json
import time
import requests
from checker import fetch_results
from config import BOT_TOKEN

API = f"https://api.telegram.org/bot{BOT_TOKEN}"

MASTER_CHAT_ID = 6647553282
POLL_INTERVAL = 300  # 5 minutes
stop_fetching = False  # Global flag to stop fetch operations

OFFSET_FILE = "offset.txt"


# ---------------- OFFSET HANDLING ----------------
def get_offset():
    try:
        with open(OFFSET_FILE, "r") as f:
            return int(f.read().strip())
    except:
        return 0


def save_offset(offset):
    with open(OFFSET_FILE, "w") as f:
        f.write(str(offset))


# ---------------- TELEGRAM HELPERS ----------------
def send(chat_id, msg):
    try:
        requests.post(
            f"{API}/sendMessage",
            data={"chat_id": chat_id, "text": msg},
            timeout=10
        )
    except requests.RequestException:
        pass  # Fail silently for message sending


# ---------------- USER STORAGE ----------------
def load_users():
    try:
        with open("users.json") as f:
            return json.load(f)
    except:
        return []


def save_users(data):
    with open("users.json", "w") as f:
        json.dump(data, f, indent=2)


# ---------------- COMMAND HANDLER ----------------
def handle_commands():
    global stop_fetching
    offset = get_offset()
    try:
        res = requests.get(
            f"{API}/getUpdates",
            params={"offset": offset + 1},
            timeout=15
        ).json()
    except (requests.RequestException, ValueError):
        return  # Skip this cycle on network/JSON errors

    if "result" not in res:
        return

    users = load_users()

    for update in res["result"]:
        save_offset(update["update_id"])

        if "message" not in update:
            continue

        msg = update["message"]
        chat_id = msg["chat"]["id"]
        text = msg.get("text", "").strip()

        if not text:
            continue

        parts = text.split()
        cmd = parts[0].lower()

        # ---------- /START ----------
        if cmd == "/start":
            welcome_msg = (
                "🎓 Welcome to Result Bot!\n\n"
                "📋 **Available Commands:**\n"
                "• `/add ROLL DOB` - Add student (DD/MM/YYYY)\n"
                "• `/remove ROLL` - Remove student\n"
                "• `/list` - Show your students\n"
                "• `/status` - Bot status\n"
                "• `/health` - Portal health check\n"
                "• `/help` - Show this help\n\n"
                "📝 **Example:**\n"
                "`/add 727723EUEC001 15/08/2005`\n\n"
                "🔔 You'll get notified when results are available!\n\n"
                f"💬 Your Chat ID: `{chat_id}`"
            )
            send(chat_id, welcome_msg)

        # ---------- /HELP ----------
        elif cmd == "/help":
            help_msg = (
                "🤖 **Result Bot Help**\n\n"
                "📋 **Commands:**\n"
                "• `/start` - Welcome message\n"
                "• `/add ROLL DOB` - Add student for monitoring\n"
                "  Format: `/add 727723EUEC001 15/08/2005`\n\n"
                "• `/remove ROLL` - Remove student\n"
                "  Format: `/remove 727723EUEC001`\n\n"
                "• `/list` - Show all your added students\n"
                "• `/status` - Show bot status & your student count\n"
                "• `/health` - Check result portal status\n"
                "• `/help` - Show this detailed help\n\n"
                "⚡ **Admin Commands:**\n"
                "• `/fetchnow` - Force check all results\n"
                "• `/stop` - Stop ongoing fetch operations\n\n"
                "🔔 **How it works:**\n"
                "1. Add students using `/add` command\n"
                "2. Bot checks results every 5 minutes\n"
                "3. You get notified when results are out\n\n"
                "📞 **Support:** Contact admin if issues occur"
            )
            send(chat_id, help_msg)

        # ---------- /ADD ----------
        elif cmd == "/add":
            if len(parts) != 3:
                send(chat_id, "❌ Usage: /add ROLL DD/MM/YYYY")
                continue

            roll = parts[1].upper()
            dob = parts[2]

            # 🔑 IMMEDIATE ACK (CRITICAL FIX)
            send(chat_id, f"⏳ Adding {roll}...")

            exists = any(
                u["roll"] == roll and u["chat_id"] == chat_id
                for u in users
            )

            if exists:
                send(chat_id, f"⚠️ {roll} already added")
            else:
                users.append({
                    "roll": roll,
                    "dob": dob,
                    "chat_id": chat_id,
                    "notified": False
                })
                save_users(users)
                send(chat_id, f"✅ {roll} added successfully")

        # ---------- /REMOVE ----------
        elif cmd == "/remove":
            if len(parts) != 2:
                send(chat_id, "❌ Usage: /remove ROLL")
                continue

            roll = parts[1].upper()
            before = len(users)

            users = [
                u for u in users
                if not (u["roll"] == roll and u["chat_id"] == chat_id)
            ]

            save_users(users)

            if len(users) == before:
                send(chat_id, f"⚠️ {roll} not found")
            else:
                send(chat_id, f"🗑️ {roll} removed successfully")

        # ---------- /LIST ----------
        elif cmd == "/list":
            my_users = [u for u in users if u["chat_id"] == chat_id]

            if not my_users:
                send(chat_id, "📭 No students added")
            else:
                msg = "📋 Students:\n"
                for u in my_users:
                    msg += f"- {u['roll']}\n"
                send(chat_id, msg)

        # ---------- /STATUS ----------
        elif cmd == "/status":
            my_users = [u for u in users if u["chat_id"] == chat_id]
            send(
                chat_id,
                f"📊 Bot Status\n\n"
                f"👥 Students: {len(my_users)}\n"
                f"⏱ Poll interval: {POLL_INTERVAL}s\n"
                f"🟢 Running"
            )

        # ---------- /FETCHNOW ----------
        elif cmd == "/fetchnow":
            if int(chat_id) != int(MASTER_CHAT_ID):
                send(chat_id, "⛔ Not authorized")
                continue

            stop_fetching = False
            send(chat_id, "⚡ Fetching results now...")
            try:
                count = force_fetch_all()
                if stop_fetching:
                    send(chat_id, "⛔ Fetch operation stopped by admin")
                else:
                    send(chat_id, f"✅ Results pushed to {count} students")
            except Exception as e:
                send(chat_id, "❌ Fetch failed. Try again later.")
        
        # ---------- /STOP ----------
        elif cmd == "/stop":
            if int(chat_id) != int(MASTER_CHAT_ID):
                send(chat_id, "⛔ Not authorized")
                continue
            
            stop_fetching = True
            send(chat_id, "⛔ Stopping all fetch operations...")
        
        elif cmd == "/health":
            status = check_portal_health()

            if status == "OK":
                msg = "🩺 Portal Health\n\n🌐 Portal: UP\n🗄 Database: UP"
            elif status == "DB_DOWN":
                msg = "🩺 Portal Health\n\n🌐 Portal: UP\n🗄 Database: UNDER MAINTENANCE"
            else:
                msg = "🩺 Portal Health\n\n🌐 Portal: DOWN"

            send(chat_id, msg)


# ---------------- RESULT CHECKERS ----------------
def force_fetch_all():
    global stop_fetching
    users = load_users()
    if not users:
        return 0
    
    # Limit batch size to prevent blocking
    batch_size = 10
    sent = 0
    
    for i in range(0, len(users), batch_size):
        if stop_fetching:
            break
            
        batch = users[i:i + batch_size]
        try:
            results = fetch_results(batch)
            
            for u in batch:
                if stop_fetching:
                    break
                    
                roll = u["roll"]
                result = results.get(roll)
                if result and result != "DB_DOWN":
                    send(
                        u["chat_id"],
                        f"🎓 RESULT UPDATE\n\n"
                        f"👤 Roll No: {roll}\n\n{result}"
                    )
                    u["notified"] = True
                    sent += 1
        except Exception:
            if stop_fetching:
                break
            continue  # Skip failed batches
    
    save_users(users)
    return sent

def check_portal_health():
    try:
        users = load_users()[:1]  # test with ONE roll
        if not users:
            return "No test user"

        test_user = users[0]
        res = fetch_results([test_user])
        value = list(res.values())[0]

        if value == "DB_DOWN":
            return "DB_DOWN"
        elif value:
            return "OK"
        else:
            return "NO_RESULT"

    except Exception:
        return "PORTAL_DOWN"

def check_results():
    global stop_fetching
    users = load_users()
    if not users or stop_fetching:
        return

    results = fetch_results(users)

    for u in users:
        if stop_fetching:
            break
            
        roll = u["roll"]
        res = results.get(roll)

        if res == "DB_DOWN":
            send(
                MASTER_CHAT_ID,
                "⚠️ Result portal database is under maintenance.\nBot will retry."
            )
            return

        if res and not u["notified"]:
            send(
                u["chat_id"],
                f"🎓 RESULT OUT!\n\n"
                f"👤 Roll No: {roll}\n\n{res}"
            )
            u["notified"] = True

    save_users(users)


# ---------------- MAIN LOOP ----------------
def main():
    last_check = 0

    while True:
        handle_commands()  # FAST, NON-BLOCKING

        now = time.time()
        if now - last_check >= POLL_INTERVAL:
            check_results()  # HEAVY PLAYWRIGHT
            last_check = now

        # Sleep for remaining time or 1 second max for responsiveness
        sleep_time = min(POLL_INTERVAL - (now - last_check), 1)
        time.sleep(max(sleep_time, 0.1))


if __name__ == "__main__":
    main()