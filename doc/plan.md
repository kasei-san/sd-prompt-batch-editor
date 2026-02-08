# SD Prompt Batch Editor - 実装計画

## 進捗

| Step | 内容 | 状態 |
|------|------|------|
| 1 | 基盤ファイル (requirements.txt, .env, .gitignore, start.bat, app.py) | ✅ 完了 |
| 2 | PNGメタデータパーサー (metadata_parser.py) | ✅ 完了 |
| 3 | プロンプト編集エンジン (prompt_editor.py) | ✅ 完了 |
| 4 | フロントエンド (HTML/CSS/JS) | ✅ 完了 |
| 5 | Forge APIクライアント (forge_client.py) | ✅ 完了 |
| 6 | バッチ生成エンジン (app.py ワーカー) | ✅ 完了 |
| 7 | 画像保存処理 | ✅ 完了 |
| 8 | ドキュメント (README.md) | ✅ 完了 |

## Context

Stable Diffusion Forge で生成した複数の PNG 画像のプロンプトを一括編集し、変更後のプロンプトで再生成するローカル Web アプリを新規構築する。プロンプトの微調整を繰り返す作業の効率化が目的。

## 運用ルール
- **Git**: 各ステップ完了ごとにコミット
- **設定管理**: ディレクトリパス・ポート等は `.env` で管理、コードにハードコードしない
- **ドキュメント**: 最終ステップで `README.md` にアプリの使い方をまとめる
- **設計書**: `doc/plan.md` にこの計画書を配置

## ファイル構成

```
C:\Users\かせいさん\work\02\
├── start.bat              # 起動スクリプト (venv作成→依存install→サーバ起動→ブラウザ開く)
├── .env                   # 設定ファイル (SD_API_HOST, SD_API_PORT, APP_PORT, OUTPUT_DIR)
├── .env.example           # .env のテンプレート
├── .gitignore             # venv/, output/, .env, __pycache__/
├── app.py                 # Flask メインアプリ (全エンドポイント + 生成ワーカー)
├── metadata_parser.py     # PNG メタデータ読取・パース
├── prompt_editor.py       # プロンプトのトークナイズ・編集・共通タグ抽出
├── forge_client.py        # SD Forge API クライアント (txt2img, モデル解決)
├── requirements.txt       # flask, pillow, requests, python-dotenv
├── doc/
│   └── plan.md            # 設計書 (この文書)
├── static/
│   ├── style.css          # ダークテーマ CSS
│   └── app.js             # フロントエンド (D&D, 共通タグ分析, SSE進捗, プレビュー)
└── templates/
    └── index.html         # メインページ (Jinja2テンプレート)
```

## 実装ステップ

### Step 1: 基盤ファイル → git commit
- `requirements.txt`: Flask, Pillow, requests, python-dotenv
- `.env.example`: 設定テンプレート (SD_API_HOST=127.0.0.1, SD_API_PORT=7860, APP_PORT=4644, OUTPUT_DIR=./output)
- `.env`: `.env.example` と同内容 (gitignore対象)
- `.gitignore`: venv/, output/, .env, __pycache__/, *.pyc
- `start.bat`: venv作成→activate→pip install→`start http://localhost:4644`→`python app.py`
  - `.env` から設定を読み込み
- `app.py`: Flask最小構成 (python-dotenvで.env読み込み、ポート設定)

### Step 2: PNGメタデータパーサー (`metadata_parser.py`)
- Pillow で PNG の `parameters` テキストチャンクを読み取り
- Forge の `infotext_utils.py:251` の `parse_generation_parameters` ロジックを移植
- パースアルゴリズム:
  1. テキストを改行で分割し、最終行を `lastline` として取得
  2. `lastline` に `re_param = r'\s*(\w[\w \-/]+):\s*("(?:\\.|[^\\"])+"|[^,]*)'` のマッチが3個以上あれば設定行
  3. 残りの行を `Negative prompt:` で分割 → positive / negative
  4. 設定行を key-value 辞書に展開 (Steps, Sampler, CFG scale, Seed, Size, Model, Clip skip, Hires系)
  5. `Size` は `WxH` を width/height に分離、数値フィールドは型変換
- 参照: `C:\Users\かせいさん\work\llm\stable-diffusion-webui-forge\modules\infotext_utils.py` (251-430行)

### Step 3: プロンプト編集エンジン (`prompt_editor.py`) → git commit
- **トークナイザ**: 括弧深度を追跡してカンマ分割 (`(tag1, tag2:1.3)` を1トークンとして扱う)
- **タグ除去**: トークン単位のマッチ。括弧・重みを剥いた「コア部分」で比較 (例: `(masterpiece:1.2)` → コア `masterpiece`)
- **タグ追加**: プロンプト末尾にカンマ区切りで追加
- **共通タグ抽出**: 全画像のタグセットの積集合を計算

### Step 4: フロントエンド (`templates/index.html`, `static/app.js`, `static/style.css`) → git commit
UI構成:
```
[SD Forge接続状態: ● / ×]  [APIポート設定: 7860]
┌─ ドラッグ&ドロップゾーン ────────────────┐
│  PNG画像をここにドロップ                    │
└───────────────────────────────────────┘
┌─ 読み込んだ画像一覧 (サムネイルグリッド) ──┐
│  [thumb] [thumb] [thumb] ...  [×全削除]    │
└───────────────────────────────────────┘
┌─ 共通プロンプト ─────────────────────────┐
│  Positive共通: masterpiece, best quality   │
│  Negative共通: worst quality, low quality  │
└───────────────────────────────────────┘
┌─ プロンプト編集 ─────────────────────────┐
│  削除 Positive: [________________]         │
│  削除 Negative: [________________]         │
│  追加 Positive: [________________]         │
│  追加 Negative: [________________]         │
│  [プレビュー]  [生成実行]                   │
└───────────────────────────────────────┘
┌─ プレビュー / 進捗 ─────────────────────┐
│  (プレビュー: 各画像の編集後プロンプト)     │
│  (生成中: プログレスバー + 各画像の状態)    │
└───────────────────────────────────────┘
```

- ドラッグ&ドロップ: `image/png` のみ受け付け、`POST /api/upload` でサーバーに送信
- 共通タグ分析: フロントエンド側で全画像のタグ集合の積集合を計算して表示
- プレビュー: 編集結果をサーバーに送らず、フロントエンドで計算して各画像の編集後プロンプトを表示
- 進捗表示: SSE (Server-Sent Events) で生成進捗をリアルタイム受信
- 完了通知: Web Notification API でブラウザ通知 + 画面内トースト

### Step 5: Forge APIクライアント (`forge_client.py`) → git commit
- 接続確認: `GET /sdapi/v1/options`
- txt2img呼び出し: メタデータ→APIペイロード変換

  メタデータキー → APIキー対応表:
  | PNG metadata | API payload |
  |---|---|
  | positive_prompt | prompt |
  | negative_prompt | negative_prompt |
  | Steps | steps |
  | Sampler | sampler_name |
  | Schedule type | scheduler |
  | CFG scale | cfg_scale |
  | Seed | seed |
  | Size-1, Size-2 | width, height |
  | Model + Model hash | override_settings.sd_model_checkpoint |
  | Clip skip | override_settings.CLIP_stop_at_last_layers |
  | Hires upscale | hr_scale (+ enable_hr: true) |
  | Hires steps | hr_second_pass_steps |
  | Hires upscaler | hr_upscaler |
  | Denoising strength | denoising_strength |

- モデル名解決: `/sdapi/v1/sd-models` から取得したリストと Model hash で完全一致→Model名で部分一致の順にマッチ
- 全リクエストで `send_images: true`, `save_images: false`, `override_settings_restore_afterwards: true`
- タイムアウト: 600秒 (Hires有効時の長時間生成に対応)

### Step 6: バッチ生成エンジン (`app.py` 内の生成ワーカー) → git commit
- `POST /api/generate` → バックグラウンドスレッドで生成開始、セッションID返却
- 同モデルの画像をグルーピングしてモデル切替回数を最小化
- 各画像ごとに: プロンプト編集適用 → APIペイロード構築 → txt2img API呼び出し → 画像保存
- SSE (`GET /api/generate/progress`) で進捗イベント配信:
  - `progress`: 現在の画像番号/全体数、ファイル名
  - `image_done`: 1枚完了
  - `error`: エラー発生
  - `complete`: 全完了、出力ディレクトリパス

### Step 7: 画像保存 → git commit
- 出力先: `.env` の `OUTPUT_DIR` 配下に `YYYYMMDDHHMMSS/` サブディレクトリを作成
- ファイル名: `{元のファイル名}.png`
- base64デコード後、PNGメタデータ (parameters) が含まれていればそのまま保存。なければ API response の info から復元

### Step 8: ドキュメント → git commit
- `doc/plan.md`: この設計書を配置
- `README.md`: アプリの概要、セットアップ手順、使い方、設定項目(.env)を記載

## APIエンドポイント一覧

| メソッド | パス | 機能 |
|---|---|---|
| GET | `/` | index.html |
| POST | `/api/upload` | PNG画像アップロード、メタデータ解析して返却 |
| POST | `/api/generate` | バッチ生成開始 |
| GET | `/api/generate/progress` | SSE進捗ストリーム |
| GET | `/api/check-forge` | Forge API接続確認 |

## 注意点・エッジケース
- **括弧内カンマ**: `(tag1, tag2:1.3)` を1トークンとして扱うトークナイザが必須
- **LORA記法**: `<lora:name:0.8>` は山括弧内なのでトークナイザで正しく1トークンになる
- **Forge API同期性**: txt2img は同期API。順次呼び出しが正しい
- **メタデータなしPNG**: エラーとしてユーザーに通知、他の画像は正常処理
- **ComfyUI/NovelAI形式**: 非対応。`parameters` キーに `Steps:` が含まれるかで判定

## 検証方法
1. `start.bat` 実行 → ブラウザが `http://localhost:4644` で開くこと
2. Forge未起動時に接続状態が正しく表示されること
3. Forge生成済みPNG 3-5枚をドロップ → メタデータ正常読取、共通タグ表示
4. タグ削除・追加を入力してプレビュー → 編集結果が正しいこと
5. 生成実行 → 進捗バー動作、`output/YYYYMMDDHHMMSS/` にPNG保存
6. 保存PNGにメタデータが埋め込まれていること
7. 同一seed+同一設定の再生成で、プロンプト変更分のみ反映されていること
