import socket
import threading
import uuid
import time
import json
import bcrypt

# サーバー設定
TCP_HOST = "127.0.0.1"
TCP_PORT = 8000
UDP_HOST = "127.0.0.1"
UDP_PORT = 8001

# 操作コード
CREATE_ROOM = 1
JOIN_ROOM = 2

# 状態コード
REQUEST = 0
ACKNOWLEDGE = 1
COMPLETE = 2

# ステータスコード
SUCCESS = 0
ROOM_EXISTS = 1
ROOM_NOT_FOUND = 2
INVALID_PASSWORD = 3

# クライアント管理
CLEANUP_INTERVAL = 20
INACTIVITY_TIMEOUT = 300

# チャットルーム管理
chat_rooms = {}
"""
{
room_name: {
    host_token: host_token,
    password: password,
    tokens: {token: ip_address}
    }
}
"""
tokens = {}
"""
{
token: {
    room_name:room_name,
    username:username
    }
}
"""
client_timestamp = {}
"""
{token:timestamp}
"""

# ロック
rooms_lock = threading.Lock()
tokens_lock = threading.Lock()
timestamp_lock = threading.Lock()

# イベント
udp_closed = threading.Event()


def generate_token():
    """一意のトークンを生成"""
    return str(uuid.uuid4())


def handle_tcp_connection(client_socket, client_address):
    """TCP接続の処理"""
    try:
        # ヘッダー受信 (32バイト)
        header = client_socket.recv(32)
        if not header or len(header) < 32:
            print("Invalid Header")
            return

        room_name_size = header[0]
        operation = header[1]
        state = header[2]
        payload_size = int.from_bytes(header[3:32], byteorder="big")

        # ボディ受信
        body = client_socket.recv(room_name_size + payload_size)
        if not body or len(body) < room_name_size + payload_size:
            print("Invalid Body")
            return

        room_name = body[:room_name_size].decode("utf-8")
        payload = body[room_name_size : room_name_size + payload_size]

        if operation == CREATE_ROOM and state == REQUEST:
            # チャットルーム作成リクエスト
            try:
                create_data = json.loads(payload.decode("utf-8"))
                username = create_data.get("username", "")
                password = create_data.get("password", "")
                handle_create_room(
                    client_socket, room_name, username, client_address, password
                )
            except json.JSONDecodeError:
                # 不正なペイロード
                send_tcp_response(
                    client_socket, room_name, operation, ACKNOWLEDGE, INVALID_PASSWORD
                )

        elif operation == JOIN_ROOM and state == REQUEST:
            # チャットルーム参加リクエスト
            try:
                join_data = json.loads(payload.decode("utf-8"))
                username = join_data.get("username", "")
                password = join_data.get("password", "")
                handle_join_room(
                    client_socket, room_name, username, client_address, password
                )
            except json.JSONDecodeError:
                # 不正なペイロード
                send_tcp_response(
                    client_socket, room_name, operation, ACKNOWLEDGE, INVALID_PASSWORD
                )

    except Exception as e:
        print(f"TCP処理エラー: {e}")
    finally:
        client_socket.close()


def handle_create_room(client_socket, room_name, username, client_address, password=""):
    """チャットルーム作成処理"""
    with rooms_lock:
        if room_name in chat_rooms:
            # 既に同名のルームが存在する
            send_tcp_response(
                client_socket, room_name, CREATE_ROOM, ACKNOWLEDGE, ROOM_EXISTS
            )
            return

        # 新しいトークン生成
        host_token = generate_token()

        # パスワードがある場合はハッシュ化
        hashed_password = hash_password(password)

        # チャットルーム作成
        chat_rooms[room_name] = {
            "host_token": host_token,
            "password": hashed_password,  # ハッシュ化したパスワードを文字列として保存
            "tokens": {host_token: client_address},
        }

    with tokens_lock:
        tokens[host_token] = {"room_name": room_name, "username": username}

    with timestamp_lock:
        client_timestamp[host_token] = time.time()

    # 成功応答
    send_tcp_response(client_socket, room_name, CREATE_ROOM, ACKNOWLEDGE, SUCCESS)

    # トークン送信
    send_tcp_complete(client_socket, room_name, CREATE_ROOM, host_token)

    print(f"ルーム作成: {room_name}, ホスト: {username}, アドレス: {client_address}")

    # UDP port 受信
    udp_port_bytes = client_socket.recv(2)
    udp_port = int.from_bytes(udp_port_bytes, "big")
    with rooms_lock:
        chat_rooms[room_name]["tokens"][host_token] = (client_address[0], udp_port)


def handle_join_room(client_socket, room_name, username, client_address, password=""):
    """チャットルーム参加処理"""
    with rooms_lock:
        if room_name not in chat_rooms:
            # ルームが存在しない
            send_tcp_response(
                client_socket, room_name, JOIN_ROOM, ACKNOWLEDGE, ROOM_NOT_FOUND
            )
            return

        room = chat_rooms[room_name]

        # パスワードの検証
        room_password = room["password"]
        if not verify_password(password, room_password):
            send_tcp_response(
                client_socket, room_name, JOIN_ROOM, ACKNOWLEDGE, INVALID_PASSWORD
            )
            return

        # 新しいトークン生成
        user_token = generate_token()

        # トークンをルームに追加
        room["tokens"][user_token] = client_address

    with tokens_lock:
        tokens[user_token] = {"room_name": room_name, "username": username}

    with timestamp_lock:
        client_timestamp[user_token] = time.time()

    # 成功応答
    send_tcp_response(client_socket, room_name, JOIN_ROOM, ACKNOWLEDGE, SUCCESS)

    # トークン送信
    send_tcp_complete(client_socket, room_name, JOIN_ROOM, user_token)

    # 参加メッセージをルームに送信
    system_message = f"{username} がチャットルームに参加しました"
    broadcast_message_to_room(room_name, system_message, None)

    print(f"ルーム参加: {room_name}, ユーザー: {username}, アドレス: {client_address}")

    # UDP port 受信
    udp_port_bytes = client_socket.recv(2)
    udp_port = int.from_bytes(udp_port_bytes, "big")
    with rooms_lock:
        chat_rooms[room_name]["tokens"][user_token] = (client_address[0], udp_port)


def send_tcp_response(client_socket, room_name, operation, state, status_code):
    """TCP応答送信"""
    room_name_bytes = room_name.encode("utf-8")
    room_name_size = len(room_name_bytes)

    status_bytes = status_code.to_bytes(1, byteorder="big")
    payload_size = len(status_bytes)

    # ヘッダー作成
    header = bytes([room_name_size, operation, state]) + payload_size.to_bytes(
        29, byteorder="big"
    )

    # 送信
    client_socket.sendall(header + room_name_bytes + status_bytes)


def send_tcp_complete(client_socket, room_name, operation, token):
    """TCP完了応答送信"""
    room_name_bytes = room_name.encode("utf-8")
    room_name_size = len(room_name_bytes)

    token_bytes = token.encode("utf-8")
    payload_size = len(token_bytes)

    # ヘッダー作成
    header = bytes([room_name_size, operation, COMPLETE]) + payload_size.to_bytes(
        29, byteorder="big"
    )

    # 送信
    client_socket.sendall(header + room_name_bytes + token_bytes)


def handle_udp_message(udp_socket):
    _MIN_HEADER_SIZE = 2
    """UDP メッセージ処理"""
    while not udp_closed.is_set():
        try:
            data, addr = udp_socket.recvfrom(4096)
            if not data:
                continue

            if len(data) < _MIN_HEADER_SIZE:
                print("Invalid request data. message contains two bytes at least.")
                continue

            room_name_size = data[0]
            token_size = data[1]

            room_name = data[2 : 2 + room_name_size].decode("utf-8")
            token = data[2 + room_name_size : 2 + room_name_size + token_size].decode(
                "utf-8"
            )
            message = data[2 + room_name_size + token_size :].decode("utf-8")

            process_message(room_name, token, message, addr)

        except Exception as e:
            print(f"UDP message handle error: {e}")


def process_message(room_name, token, message, addr):
    """メッセージ処理"""
    with rooms_lock:
        if room_name not in chat_rooms:
            return

        room = chat_rooms[room_name]

        if token not in room["tokens"]:
            return

        if room["tokens"][token] != addr:
            return

    with tokens_lock:
        if token not in tokens:
            return

        username = tokens[token]["username"]

    with timestamp_lock:
        if token not in client_timestamp:
            return

        client_timestamp[token] = time.time()

    print("broard cast")

    # メッセージブロードキャスト
    formatted_message = f"{username}: {message}"
    broadcast_message_to_room(room_name, formatted_message, token)

    # ホスト退出チェック
    if token == room["host_token"] and message.strip().lower() == "/exit":
        close_chat_room(room_name)


def send_message_bytes_to_client(ip, message_bytes):
    """各自にメッセージを送信"""

    # UDP送信
    try:
        print(ip)
        udp_socket.sendto(message_bytes, ip)
    except Exception as e:
        print(f"メッセージ送信エラー: {e}")


def broadcast_message_to_room(room_name, message, exclude_token=None):
    """ルーム内の全員にメッセージをブロードキャスト"""
    with rooms_lock:
        if room_name not in chat_rooms:
            return

        room = chat_rooms[room_name]
        recipients = []
        print(recipients)

        for token, ip in room["tokens"].items():
            if token != exclude_token:
                recipients.append((token, ip))
        print(recipients)

    # UDP送信
    message_bytes = message.encode("utf-8")
    for token, ip in recipients:
        send_message_bytes_to_client(ip, message_bytes)


def close_chat_room(room_name):
    """チャットルームを閉じる"""
    with rooms_lock:
        if room_name not in chat_rooms:
            return

        room = chat_rooms[room_name]
        tokens_to_remove = list(room["tokens"].keys())

    # 閉じるメッセージを送信
    broadcast_message_to_room(room_name, "チャットルームが閉じられました", None)

    with rooms_lock:
        # ルームを削除
        del chat_rooms[room_name]

    # トークンを削除
    with tokens_lock:
        for token in tokens_to_remove:
            if token in tokens:
                del tokens[token]

    # timestampを削除
    with timestamp_lock:
        for token in tokens_to_remove:
            if token in client_timestamp:
                del client_timestamp[token]

    print(f"ルーム閉鎖: {room_name}")


def cleanup_inactive_clients():
    """非アクティブなクライアントのクリーンアップ"""
    while True:
        time.sleep(CLEANUP_INTERVAL)
        current_time = time.time()

        rooms_to_check = []
        with rooms_lock:
            rooms_to_check = list(chat_rooms.keys())

        for room_name in rooms_to_check:
            with rooms_lock:
                if room_name not in chat_rooms:
                    continue

                room = chat_rooms[room_name]
                host_token = room["host_token"]

            if current_time - client_timestamp.get(host_token, 0) > INACTIVITY_TIMEOUT:
                close_chat_room(room_name)
                continue

            inactive_members = []
            for token, ip in room["tokens"].items():
                if token == host_token:
                    continue
                last_active = client_timestamp.get(token, 0)
                if current_time - last_active > INACTIVITY_TIMEOUT:
                    inactive_members.append((token, ip))

            for token, ip in inactive_members:
                send_message_bytes_to_client(
                    ip,
                    "しばらく発言しなかったので、チャットルームから退出させました".encode(
                        "utf-8"
                    ),
                )
                with rooms_lock:
                    del room["tokens"][token]
                with tokens_lock:
                    del tokens[token]
                with timestamp_lock:
                    del client_timestamp[token]


def start_server():
    """サーバー起動"""
    # TCP ソケット設定
    tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp_socket.setsockopt(
        socket.SOL_SOCKET, socket.SO_REUSEADDR, 1
    )  # 即座のアドレス再利用許可
    tcp_socket.bind((TCP_HOST, TCP_PORT))
    tcp_socket.listen(5)  # 同時接続数

    # UDP ソケット設定
    global udp_socket
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.bind((UDP_HOST, UDP_PORT))

    # UDP処理スレッド起動
    udp_thread = threading.Thread(
        target=handle_udp_message, args=(udp_socket,), daemon=True
    )
    udp_thread.start()

    # クリーンアップスレッド起動
    cleanup_thread = threading.Thread(target=cleanup_inactive_clients, daemon=True)
    cleanup_thread.start()

    print(f"サーバー起動: TCP {TCP_HOST}:{TCP_PORT}, UDP {UDP_HOST}:{UDP_PORT}")

    try:
        while True:
            # TCP接続待機
            client_socket, client_address = tcp_socket.accept()
            client_thread = threading.Thread(
                target=handle_tcp_connection,
                args=(client_socket, client_address),
                daemon=True,
            )
            client_thread.start()

    except KeyboardInterrupt:
        print("サーバー停止中...")
    finally:
        tcp_socket.close()
        udp_closed.set()
        udp_socket.close()
        print("サーバー停止完了")


def hash_password(password):
    """パスワードをハッシュ化する"""
    password_bytes = password.encode("utf-8")
    hashed = bcrypt.hashpw(password_bytes, bcrypt.gensalt(12)).decode("utf-8")
    return hashed


def verify_password(plain_password, hashed_password):
    """ハッシュ化されたパスワードを検証する"""
    password_bytes = plain_password.encode('utf-8')
    if isinstance(hashed_password, str):
        hashed_password = hashed_password.encode("utf-8")
    result = bcrypt.checkpw(password_bytes, hashed_password)
    return result


if __name__ == "__main__":
    start_server()
