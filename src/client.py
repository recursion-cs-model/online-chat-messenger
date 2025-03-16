import socket
import threading
import json
import argparse

from models.room_operation_code import RoomOperationCode

# サーバー設定（デフォルト値）
DEFAULT_SERVER_HOST = "localhost"
DEFAULT_TCP_PORT = 8000
DEFAULT_UDP_PORT = 8001

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

# クライアント状態
client_token = None
client_room = None
client_username = None
running = True
udp_socket = None


def send_udp_port(tcp_socket, server_host):
    global udp_socket
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.bind((server_host, 0))
    client_udp_port = udp_socket.getsockname()[1]
    client_udp_port_bytes = client_udp_port.to_bytes(2, "big")
    tcp_socket.send(client_udp_port_bytes)


def create_room(server_host, tcp_port, room_name, username):
    """新しいチャットルームを作成する"""
    global client_token, client_room, client_username

    # TCP ソケット作成
    tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        tcp_socket.connect((server_host, tcp_port))

        # リクエストデータ準備
        room_name_bytes = room_name.encode("utf-8")
        room_name_size = len(room_name_bytes)

        username_bytes = username.encode("utf-8")
        payload_size = len(username_bytes)

        # ヘッダー作成
        header = bytes([room_name_size, CREATE_ROOM, REQUEST]) + payload_size.to_bytes(
            29, byteorder="big"
        )

        # リクエスト送信
        tcp_socket.sendall(header + room_name_bytes + username_bytes)

        # 応答受信
        response_header = tcp_socket.recv(32)
        if not response_header or len(response_header) < 32:
            print("サーバーからの応答がありません")
            return False

        response_room_name_size = response_header[0]
        # response_operation = response_header[1]
        # response_state = response_header[2]
        response_payload_size = int.from_bytes(response_header[3:32], byteorder="big")

        response_body = tcp_socket.recv(response_room_name_size + response_payload_size)
        if (
            not response_body
            or len(response_body) < response_room_name_size + response_payload_size
        ):
            print("サーバーからの応答が不完全です")
            return False

        # response_room_name = response_body[:response_room_name_size].decode("utf-8")
        status_code = response_body[response_room_name_size]

        if status_code != SUCCESS:
            if status_code == ROOM_EXISTS:
                print(f"ルーム '{room_name}' は既に存在します")
            else:
                print(f"ルーム作成エラー: コード {status_code}")
            return False

        # 完了応答の受信
        complete_header = tcp_socket.recv(32)
        if not complete_header or len(complete_header) < 32:
            print("サーバーからの完了応答がありません")
            return False

        complete_room_name_size = complete_header[0]
        # complete_operation = complete_header[1]
        # complete_state = complete_header[2]
        complete_payload_size = int.from_bytes(complete_header[3:32], byteorder="big")

        complete_body = tcp_socket.recv(complete_room_name_size + complete_payload_size)
        if (
            not complete_body
            or len(complete_body) < complete_room_name_size + complete_payload_size
        ):
            print("サーバーからの完了応答が不完全です")
            return False

        # complete_room_name = complete_body[:complete_room_name_size].decode("utf-8")
        token = complete_body[complete_room_name_size:].decode("utf-8")

        # クライアント状態を更新
        client_token = token
        client_room = room_name
        client_username = username

        # udp port を送信
        send_udp_port(tcp_socket, server_host)

        print(f"チャットルーム '{room_name}' を作成しました！")
        print("あなたはホストとして参加しています。退出するには '/exit' と入力してください。")
        return True

    except Exception as e:
        print(f"ルーム作成中にエラーが発生しました: {e}")
        return False
    finally:
        tcp_socket.close()


def join_room(server_host, tcp_port, room_name, username, password=None):
    """既存のチャットルームに参加する"""
    global client_token, client_room, client_username

    # TCP ソケット作成
    tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        tcp_socket.connect((server_host, tcp_port))

        # リクエストデータ準備
        room_name_bytes = room_name.encode("utf-8")
        room_name_size = len(room_name_bytes)

        # ペイロードとしてJSONを使用
        payload_data = {"username": username, "password": password if password else ""}
        payload_bytes = json.dumps(payload_data).encode("utf-8")
        payload_size = len(payload_bytes)

        # ヘッダー作成
        header = bytes([room_name_size, JOIN_ROOM, REQUEST]) + payload_size.to_bytes(
            29, byteorder="big"
        )

        # リクエスト送信
        tcp_socket.sendall(header + room_name_bytes + payload_bytes)

        # 応答受信
        response_header = tcp_socket.recv(32)
        if not response_header or len(response_header) < 32:
            print("サーバーからの応答がありません")
            return False

        response_room_name_size = response_header[0]
        # response_operation = response_header[1]
        # response_state = response_header[2]
        response_payload_size = int.from_bytes(response_header[3:32], byteorder="big")

        response_body = tcp_socket.recv(response_room_name_size + response_payload_size)
        if (
            not response_body
            or len(response_body) < response_room_name_size + response_payload_size
        ):
            print("サーバーからの応答が不完全です")
            return False

        # response_room_name = response_body[:response_room_name_size].decode("utf-8")
        status_code = response_body[response_room_name_size]

        if status_code != SUCCESS:
            if status_code == ROOM_NOT_FOUND:
                print(f"ルーム '{room_name}' は存在しません")
            elif status_code == INVALID_PASSWORD:
                print("パスワードが正しくありません")
            else:
                print(f"ルーム参加エラー: コード {status_code}")
            return False

        # 完了応答の受信
        complete_header = tcp_socket.recv(32)
        if not complete_header or len(complete_header) < 32:
            print("サーバーからの完了応答がありません")
            return False

        complete_room_name_size = complete_header[0]
        # complete_operation = complete_header[1]
        # complete_state = complete_header[2]
        complete_payload_size = int.from_bytes(complete_header[3:32], byteorder="big")

        complete_body = tcp_socket.recv(complete_room_name_size + complete_payload_size)
        if (
            not complete_body
            or len(complete_body) < complete_room_name_size + complete_payload_size
        ):
            print("サーバーからの完了応答が不完全です")
            return False

        # complete_room_name = complete_body[:complete_room_name_size].decode("utf-8")
        token = complete_body[complete_room_name_size:].decode("utf-8")

        # クライアント状態を更新
        client_token = token
        client_room = room_name
        client_username = username

        # udp port を送信
        send_udp_port(tcp_socket, server_host)

        print(f"チャットルーム '{room_name}' に参加しました！")
        print("退出するには '/exit' と入力してください。")
        return True

    except Exception as e:
        print(f"ルーム参加中にエラーが発生しました: {e}")
        return False
    finally:
        tcp_socket.close()


def receive_messages():
    """UDPでメッセージを受信する"""
    global running

    while running:
        try:
            # メッセージ受信
            data, _ = udp_socket.recvfrom(4094)  # 最大4094バイト
            if data:
                message = data.decode("utf-8")
                print(message)

                # ルーム閉鎖メッセージを検出
                if message == "チャットルームが閉じられました":
                    print("チャットルームが閉じられました。プログラムを終了します。")
                    running = False
                    break
        except Exception as e:
            if running:  # 正常終了でない場合のみエラー表示
                print(f"メッセージ受信中にエラーが発生しました: {e}")
            break


def send_message(server_host, udp_port, message):
    """UDPでメッセージを送信する"""
    global client_token, client_room

    if not client_token or not client_room:
        print("チャットルームに接続されていません")
        return False

    try:
        # メッセージデータ準備
        room_name_bytes = client_room.encode("utf-8")
        room_name_size = len(room_name_bytes)

        token_bytes = client_token.encode("utf-8")
        token_size = len(token_bytes)

        message_bytes = message.encode("utf-8")

        # パケット作成
        packet = bytes([room_name_size, token_size]) + room_name_bytes + token_bytes + message_bytes

        # 送信
        udp_socket.sendto(packet, (server_host, udp_port))
        return True

    except Exception as e:
        print(f"メッセージ送信中にエラーが発生しました: {e}")
        return False


def start_client():
    global running

    parser = argparse.ArgumentParser(description="チャットメッセンジャークライアント")
    parser.add_argument("--host", default=DEFAULT_SERVER_HOST, help="サーバーホスト")
    parser.add_argument("--tcp-port", type=int, default=DEFAULT_TCP_PORT, help="TCPポート")
    parser.add_argument("--udp-port", type=int, default=DEFAULT_UDP_PORT, help="UDPポート")
    args = parser.parse_args()

    print("=== チャットメッセンジャークライアント ===")
    print("1. 新しいチャットルームを作成")
    print("2. 既存のチャットルームに参加")
    input_room_ope_code = input("選択してください (1/2): ")

    match RoomOperationCode(int(input_room_ope_code)):
        case RoomOperationCode.CREATE_ROOM:
            room_name = input("作成するルーム名: ")
            username = input("あなたのユーザー名: ")

            if create_room(args.host, args.tcp_port, room_name, username):
                # メッセージ受信スレッド起動
                receive_thread = threading.Thread(target=receive_messages, daemon=True)
                receive_thread.start()

                # メッセージ送信ループ
                try:
                    while running:
                        message = input()
                        if message.strip().lower() == "/exit":
                            send_message(args.host, args.udp_port, "/exit")
                            running = False
                            break
                        elif message:
                            send_message(args.host, args.udp_port, message)
                except KeyboardInterrupt:
                    running = False
                    print("\nプログラムを終了します...")
                finally:
                    if udp_socket:
                        udp_socket.close()

        case RoomOperationCode.JOIN_ROOM:
            room_name = input("参加するルーム名: ")
            username = input("あなたのユーザー名: ")
            use_password = input("パスワードが必要ですか？ (y/n): ").lower() == "y"
            password = input("パスワード: ") if use_password else None

            if join_room(args.host, args.tcp_port, room_name, username, password):
                # メッセージ受信スレッド起動
                receive_thread = threading.Thread(target=receive_messages, daemon=True)
                receive_thread.start()

                # メッセージ送信ループ
                try:
                    while running:
                        message = input()
                        if message.strip().lower() == "/exit":
                            send_message(args.host, args.udp_port, "/exit")
                            running = False
                            break
                        elif message:
                            send_message(args.host, args.udp_port, message)
                except KeyboardInterrupt:
                    running = False
                    print("\nプログラムを終了します...")
                finally:
                    if udp_socket:
                        udp_socket.close()

        case _:
            print("無効な選択です。プログラムを終了します。")


if __name__ == "__main__":
    start_client()
