from flask import Flask, render_template, redirect, request, session, url_for, jsonify
import requests
import os
from dotenv import load_dotenv
import time
import threading
import json


app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")
GUILDLIST_TOKEN = os.getenv("GUILDLIST_TOKEN")
DISC_API_BASE = "https://discord.com/api"
DISCORD_WEBHOOK_URL = os.getenv("WEBHOOK_URL")
ADMIN_DISCORD_ID = os.getenv("ADMIN_DISCORD_ID")
HEARTBEAT_TIMEOUT = 90
BOT_OFFLINE = False
bot_guilds = []
last_ping_time = time.time()
with open("last_ping.json", "w") as file:
    json.dump(last_ping_time, file)

@app.route("/")
def home():
    return render_template("home.html")

@app.route("/start-auth")
def login():
    return redirect(
        f"{DISC_API_BASE}/oauth2/authorize"
        f"?client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&response_type=code"
        f"&scope=identify%20guilds"
        )

@app.route("/callback")
def callback():
    code = request.args.get("code")
    data = {
        "client_id":CLIENT_ID,
        "client_secret":CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code":code,
        "redirect_uri":REDIRECT_URI,
        "scope":"identify guilds"
    }
    headers = { "Content-Type": "application/x-www-form-urlencoded"}
    
    response = requests.post(f"{DISC_API_BASE}/oauth2/token", data=data, headers=headers)
    response.raise_for_status()
    token_data = response.json()
    
    access_token = token_data["access_token"]
    session["access_token"] = access_token

    me_headers = {"Authorization": f"Bearer {access_token}"}
    me_resp = requests.get(f"{DISC_API_BASE}/users/@me", headers=me_headers)
    me_resp.raise_for_status()
    me = me_resp.json()

    session["discord_user_id"] = me["id"]
    
    return redirect("/dashboard")

@app.route("/admin")
def admin():
    if session.get("discord_user_id") != ADMIN_DISCORD_ID:
        return "Forbidden", 403

    token = session.get("access_token")
    if not token:
        return redirect("/")
    headers = { "Authorization": f"Bearer {token}"}
    user = requests.get(f"{DISC_API_BASE}/users/@me", headers=headers).json()
    return render_template("admin.html", user=user)

@app.route("/dashboard")
def dashboard():
    token = session.get("access_token")
    if not token:
        return redirect("/")
    headers = { "Authorization": f"Bearer {token}"}

    user = requests.get(f"{DISC_API_BASE}/users/@me", headers=headers).json()
    user_guilds = requests.get(f"{DISC_API_BASE}/users/@me/guilds", headers=headers).json()
    bot_guild_ids = {g["id"] for g in bot_guilds}
    for g in user_guilds:
        g["has_bot"] = g["id"] in bot_guild_ids
        g["is_admin"] = (int(g["permissions"]) & 0x00000008) == 0x00000008
    return render_template("dashboard.html", user=user, guilds=user_guilds, admin_id=ADMIN_DISCORD_ID)

@app.route("/config/<guild_id>")
def config_page(guild_id):
    token = session.get("access_token")
    if not token:
        return redirect("/")
    headers = {"Authorization": f"Bearer {token}"}
    user_guilds = requests.get(f"{DISC_API_BASE}/users/@me/guilds", headers=headers).json()

    for g in user_guilds:
        if g["id"] == guild_id and (int(g["permissions"]) & 0x00000008) == 0x00000008:
            return render_template("config.html", guild=g)
    return "You do not have permission to access this server's config.", 403

@app.route("/logout")
def logout():
    session.clear()

    return render_template("logout.html")

@app.route("/heartbeat", methods=["POST"])
def heartbeat():
    global last_ping_time, bot_guilds
    auth = request.headers.get("Authorization")
    if auth != f"Bearer {GUILDLIST_TOKEN}":
        return jsonify({"error": "Unauthorized"}), 403
    
    data = request.get_json()
    last_ping_time = time.time()
    with open("last_ping.json", "w") as file:
        json.dump(last_ping_time, file)
    if "guilds" in data:
        bot_guilds = data["guilds"]
    return jsonify({"status": "heartbeat received"}), 200

@app.route("/botstatus", methods=["GET"])
def botstatus():
    TimeSince = round(time.time() - last_ping_time, 2)
    return jsonify({"Bot Offline": BOT_OFFLINE, "Last Ping (Seconds)":f"{TimeSince} secs"}), 200

def check_heartbeat():
    global BOT_OFFLINE
    print(f"Start check_heartbeat", flush=True)
    time.sleep(120)
    while True:
        now = time.time()
        with open("last_ping.json", "r") as file:
            last_ping_time = json.load(file)
        elapsed = now - last_ping_time
        print(f"Last Heartbeat: {elapsed:.2f} secs ago", flush=True)
        if elapsed > HEARTBEAT_TIMEOUT:
            if not BOT_OFFLINE:
                print("Bot is now offline. Sending Alert.", flush=True)
                send_discord_alert(content = "⚠️Bot is offline!")
                BOT_OFFLINE = True
        else:
            if BOT_OFFLINE:
                send_discord_alert(content="🟢🎉 The bot is back online!")
                print("🟢🎉 Bot is back online!", flush=True)
                BOT_OFFLINE = False
        time.sleep(30)

def send_discord_alert(*, content):
    data = {"content":content}
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=data)
    except Exception as e:
        print(f"Failed to send alert: {e}", flush=True)

def start_monitor():
    thread = threading.Thread(target=check_heartbeat, daemon=True)
    thread.start()

start_monitor()

if __name__ == "__main__":
    app.run(port=12530)
