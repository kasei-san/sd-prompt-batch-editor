# SD Prompt Batch Editor

Stable Diffusion Forge で生成した複数の PNG 画像のプロンプトを一括編集し、変更後のプロンプトで再生成するローカル Web アプリ。

## セットアップ

### 必要環境
- Python 3.10+
- Stable Diffusion WebUI Forge (API有効)

### 起動方法

`start.bat` をダブルクリックするだけで起動する。

```
start.bat
```

以下が自動で実行される:
1. Python venv 作成 (初回のみ)
2. 依存パッケージのインストール
3. ブラウザで `http://localhost:4644` を開く
4. Flask サーバーを起動

### 手動起動

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

## 使い方

1. **Forge を起動** しておく (`--api` フラグ付き)
2. `start.bat` でアプリを起動
3. 画面上部で Forge の接続状態を確認 (緑●なら接続済み)
4. **PNG画像をドラッグ&ドロップ** (Forge/A1111で生成したメタデータ付きPNG)
5. 共通プロンプトが自動表示される
6. **プロンプト編集**:
   - 削除 Positive/Negative: 除去したいタグをカンマ区切りで入力
   - 追加 Positive/Negative: 追加したいタグをカンマ区切りで入力
7. **プレビュー** で編集結果を確認
8. **生成実行** で一括再生成

生成された画像は `output/YYYYMMDDHHMMSS/` ディレクトリに保存される。

## 設定 (.env)

| 変数 | デフォルト | 説明 |
|------|-----------|------|
| `SD_API_HOST` | `127.0.0.1` | Forge API のホスト |
| `SD_API_PORT` | `7860` | Forge API のポート |
| `APP_PORT` | `4644` | このアプリのポート |
| `OUTPUT_DIR` | `./output` | 生成画像の出力先ディレクトリ |

## 対応形式

- **対応**: Stable Diffusion WebUI / Forge で生成した PNG (parameters メタデータ付き)
- **非対応**: ComfyUI形式、NovelAI形式、メタデータなしPNG

## ファイル構成

```
├── start.bat              # 起動スクリプト
├── .env                   # 設定ファイル
├── .env.example           # 設定テンプレート
├── app.py                 # Flask メインアプリ
├── metadata_parser.py     # PNG メタデータ読取・パース
├── prompt_editor.py       # プロンプト編集エンジン
├── forge_client.py        # Forge API クライアント
├── requirements.txt       # Python依存パッケージ
├── doc/plan.md            # 設計書
├── static/
│   ├── style.css          # ダークテーマ CSS
│   └── app.js             # フロントエンド JS
└── templates/
    └── index.html         # メインページ
```
