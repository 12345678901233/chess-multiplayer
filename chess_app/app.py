import json
import os
import uuid
from typing import Dict

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_FILE = os.path.join(BASE_DIR, "users.json")

app = Flask(__name__, template_folder="templates")
app.config["SECRET_KEY"] = "chess-local-secret"
socketio = SocketIO(app, cors_allowed_origins="*")

online_users: Dict[str, str] = {}


def ensure_users_file() -> None:
    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, "w", encoding="utf-8") as file:
            json.dump({}, file)


def read_users() -> dict:
    ensure_users_file()
    with open(USERS_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def write_users(users: dict) -> None:
    with open(USERS_FILE, "w", encoding="utf-8") as file:
        json.dump(users, file, indent=2)


@app.route("/")
def index():
    return render_template("index.html")


@socketio.on("register")
def handle_register(data):
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if not username or not password:
        emit("register_response", {"ok": False, "message": "Username and password are required."})
        return

    users = read_users()
    if username in users:
        emit("register_response", {"ok": False, "message": "Username already exists."})
        return

    users[username] = password
    write_users(users)
    emit("register_response", {"ok": True, "message": "Registration successful."})


@socketio.on("login")
def handle_login(data):
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    users = read_users()
    if username not in users or users[username] != password:
        emit("login_response", {"ok": False, "message": "Invalid credentials."})
        return

    online_users[username] = request.sid
    emit("login_response", {"ok": True, "username": username})


@socketio.on("send_challenge")
def handle_send_challenge(data):
    challenger = (data.get("from") or "").strip()
    target = (data.get("to") or "").strip()

    if target not in online_users:
        emit("challenge_response", {"ok": False, "message": "User not online."})
        return

    target_sid = online_users[target]
    emit("receive_challenge", {"from": challenger}, to=target_sid)
    emit("challenge_response", {"ok": True, "message": f"Challenge sent to {target}."})


@socketio.on("accept_challenge")
def handle_accept_challenge(data):
    challenger = (data.get("challenger") or "").strip()
    challenged = (data.get("challenged") or "").strip()

    if challenger not in online_users or challenged not in online_users:
        emit("start_game", {"ok": False, "message": "One of the players is offline."})
        return

    room_id = f"room-{uuid.uuid4().hex}"
    challenger_sid = online_users[challenger]
    challenged_sid = online_users[challenged]

    join_room(room_id, sid=challenger_sid)
    join_room(room_id, sid=challenged_sid)

    emit(
        "start_game",
        {
            "ok": True,
            "room_id": room_id,
            "white": challenger,
            "black": challenged,
            "your_color": "white",
            "opponent": challenged,
        },
        to=challenger_sid,
    )
    emit(
        "start_game",
        {
            "ok": True,
            "room_id": room_id,
            "white": challenger,
            "black": challenged,
            "your_color": "black",
            "opponent": challenger,
        },
        to=challenged_sid,
    )


@socketio.on("make_move")
def handle_make_move(data):
    room_id = data.get("room_id")
    move = data.get("move")
    fen = data.get("fen")

    if not room_id or not move:
        return

    emit("move_made", {"move": move, "fen": fen}, to=room_id, include_self=False)


@socketio.on("disconnect")
def handle_disconnect():
    sid = request.sid
    disconnected_user = None

    for username, user_sid in list(online_users.items()):
        if user_sid == sid:
            disconnected_user = username
            online_users.pop(username, None)
            break

    if disconnected_user:
        print(f"User disconnected: {disconnected_user}")


if __name__ == "__main__":
    ensure_users_file()
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)
