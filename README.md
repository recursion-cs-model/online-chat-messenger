# Quick Start
## 仮想環境の作成
```bash
python3 -m venv venv
source venv/bin/activate # MacOSの場合
source venv/Scripts/activate # Windowsの場合
```

## パッケージのインストール
```bash
pip install -r requirements.txt
```

## サーバーの起動
```bash
python3 src/server.py
```

## クライアントの起動
```bash
python3 src/client.py
```

## 仮想環境の停止
停止
```bash
deactivate
```

# 開発者向け

## コミット時にフォーマッタを実行
```bash
pre-commit install
```

# データ構造
## チャットルーム作成・参加時のパケットのデータ構造（TCP）
### ヘッダー (32バイト)
| バイト位置 | サイズ | 内容 | 説明 |
|------------|--------|------|------|
| 0 | 1 byte | room_name_size | ルーム名のバイト長 |
| 1 | 1 byte | operation | 操作コード |
| 2 | 1 byte | state | 状態コード |
| 3-31 | 29 bytes | payload_size | ペイロードのバイト長 (big endian) |

### 操作コード (operation)
| 値 | 定数 | 説明 |
|----|------|------|
| 1 | CREATE_ROOM | チャットルーム作成 |
| 2 | JOIN_ROOM | チャットルーム参加 |

### 状態コード (state)
| 値 | 定数 | 説明 |
|----|------|------|
| 0 | REQUEST | クライアントからのリクエスト |
| 1 | ACKNOWLEDGE | サーバーからの応答確認 |
| 2 | COMPLETE | 処理完了 |

### ボディ
| セクション | サイズ | 内容 | 説明 |
|------------|--------|------|------|
| ルーム名 | room_name_size bytes | room_name | UTF-8でエンコードされたルーム名 |
| ペイロード | payload_size bytes | payload | リクエスト/レスポンスの内容 |

### チャットルーム作成リクエストのペイロード
```json
{
  "username": "ユーザー名",
  "password": "ルームパスワード"
}
```
| フィールド | 型 | 必須 | 説明 |
|---------|----|----|-----|
| username | 文字列 | YES | ルーム作成者のユーザー名 |
| password | 文字列 | NO | ルームへのアクセスに必要なパスワード（省略可） |

### チャットルーム参加リクエストのペイロード
```json
{
  "username": "ユーザー名",
  "password": "ルームパスワード"
}
```
| フィールド | 型 | 必須 | 説明 |
|---------|----|----|-----|
| username | 文字列 | YES | 参加者のユーザー名 |
| password | 文字列 | CONDITIONAL | ルームにパスワードが設定されている場合に必須 |

### サーバーレスポンスのペイロード（ACKNOWLEDGE）
```
  <status_code> (1バイト)
```
| ステータスコード | 値 | 説明 |
|--------------|----|----|
| SUCCESS | 0 | 処理が成功 |
| ROOM_EXISTS | 1 | 同名のルームが既に存在する |
| ROOM_NOT_FOUND | 2 | 指定されたルームが存在しない |
| INVALID_PASSWORD | 3 | パスワードが無効または不一致 |

### サーバーレスポンスのペイロード（COMPLETE）
```
  <token> (UTF-8エンコードされた文字列)
```
| フィールド | 説明 |
|---------|-----|
| token | ルームへのアクセスに必要な認証トークン |

## チャットメッセージ送受信時のパケットのデータ構造（UDP）
| フィールド | サイズ | 説明 |
|------------|--------|------|
| room_name_size | 1 byte | ルーム名の長さ |
| token_size | 1 byte | トークンの長さ |
| room_name | 可変長 (room_name_size) | UTF-8エンコードされたルーム名 |
| token | 可変長 (token_size) | UTF-8エンコードされた認証トークン |
| message | 残りすべて | UTF-8エンコードされたメッセージ本文 |
