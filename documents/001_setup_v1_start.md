# インストール手順（v1-start → Goal）

この資料は、`handson/v1-start` からハンズオンを開始し、**Step 0 まで**の環境を整えるためのセットアップ手順です。  
進め方は「自分で手を動かす + AIに詰まりを相談する」の2本立てです。

---

## Goal で提供される機能

ハンズオン完了時（Goal）に、次の機能が動作している状態を目指します。

### 必須（3本のAPI）

| Step | 機能 | エンドポイント | 成功の目安 |
|------|------|----------------|------------|
| 2 | アカウント作成 | `POST /accounts` | 必須項目チェック、201 / 400 の返し分け |
| 3 | チケット生成 | `POST /tickets/templates` | 入力チェック、201 / 400、後続APIで利用可能 |
| 4 | チェックイン | `POST /tickets/{id}/checkin` | 未チェックイン→チェックイン済みの遷移、404 / 409 の扱い |

### 余力があれば（発展）

- **配布** `POST /tickets/distribute`（実API連携）  
  作成したチケットを利用者に届ける処理。チケット画像（QR付き）の取得や、NFTとして受領者へ送る連携を含む。
- **報酬送付** `POST /rewards/send`（実API連携）  
  チェックイン完了時に報酬NFTを送る処理。

### Goal の判定

- 上記必須3APIが Swagger UI（`/api/docs/`）から実行できる
- 主要な異常系（少なくとも2パターン）を説明できる
- 自分の実装内容（AI提案を含む）を説明できる

---

## v1-start から Goal までのステップ

| # | 内容 | この資料で扱う |
|---|------|----------------|
| **Step 0** | セットアップ完了確認 | ✅ 下記「この資料のゴール」で完了 |
| Step 1 | APIの型を確認（URL → View → JSON、ステータス返し分け） | — |
| Step 2 | 必須API 1本目：アカウント作成 | — |
| Step 3 | 必須API 2本目：チケット生成 | — |
| Step 4 | 必須API 3本目：チェックイン | — |
| Step 5 | 余力があれば：配布・報酬送付 | — |
| **Goal** | 必須3APIがSwaggerで検証でき、異常系を説明できる | — |

詳細な実行順は `documents/003_goal_steps_ai_pairing.md` に従ってください。

---

## この資料のゴール（Step 0 の完了）

- ローカルでAPIサーバーを起動する
- `GET /healthz` が `200` を返す
- Swagger UI（`/api/docs/`）を開ける
- 上記ができたら、`003_goal_steps_ai_pairing.md` の **Step 1** に進める

---

## OS 別の前提

以降のコマンドは **Linux 環境のターミナル** を前提にしています。OS に応じて次のように準備してください。

| OS | 準備 |
|----|------|
| **Windows** | **WSL2** で **Ubuntu 24.04** を使う。PowerShell で `wsl --install -d Ubuntu-24.04` を実行し、再起動後に Ubuntu を起動。以降は WSL の Ubuntu ターミナルで `git` / `docker` を実行する。 |
| **macOS** | 標準のターミナル（または iTerm 等）でそのまま実行。Docker は [Docker Desktop for Mac](https://docs.docker.com/desktop/install/mac-install/) または `brew install docker` で導入。 |
| **Linux** | そのままターミナルで実行。Docker は各ディストリのパッケージ（例: Ubuntu は `apt install docker.io docker-compose-plugin`）で導入。 |

---

## 1. 最初にそろえるもの（全員）

- Git
- Python 3.11 以上（非Docker手順を使う場合）
- Docker（推奨手順を使う場合）
- このリポジトリ

```bash
git clone <REPO_URL>
cd ticketsystem-start
git checkout handson/v1-start
```

---

## 2. 推奨手順（Docker）

迷ったらこの手順を選んでください。

```bash
docker compose -f docker-compose.dev.yml up -d --build
curl -fsS http://localhost:8000/healthz
```

### 成功条件（Step 0）

- `curl` の結果が `200` 系レスポンス
- ブラウザで `http://localhost:8000/api/docs/` を開ける

### 終了時

```bash
docker compose -f docker-compose.dev.yml down
```

---

## 3. 代替手順（非Docker）

Dockerが使えない場合のみ、こちらを使ってください。

```bash
cd app
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

別ターミナルで確認:

```bash
curl -fsS http://localhost:8000/healthz
```

### 成功条件（Step 0）

- `GET /healthz` が `200`
- `http://localhost:8000/api/docs/` で Swagger UI を開ける
- その後、`documents/003_goal_steps_ai_pairing.md` の Step 1 に進める

---

## 4. AIと一緒に進めるテンプレ

詰まったら、以下の4点をAIに渡して相談してください。

1. 実行したコマンド
2. 期待した結果
3. 実際の結果（エラーメッセージ全文）
4. いまのブランチ名（`handson/v1-start`）

プロンプト例:

```text
私は ticketsystem-start の handson/v1-start を進めています。
いま実行したコマンドは「...」です。
期待は「healthz が 200」でしたが、実際は「...」というエラーです。
次に確認すべき点を優先度順に3つ教えてください。
```

---

## 5. よくある詰まりと対処

- Dockerが起動しない: Dockerアプリ再起動 → もう一度 `up -d --build`
- ポート`8000`競合: 既存プロセスを停止して再実行
- `pip install`失敗: 仮想環境を作り直して再実行
- パス混在: 必ずリポジトリ配下でコマンド実行

---

## 6. この後に読む順番

1. `documents/002_handson_plan.md`（全体像・タイムテーブル）
2. `documents/003_goal_steps_ai_pairing.md`（Step 1 以降の実行順）
3. `documents/010_colab_execution_steps.md`（Colabで実行する場合・今回は使用しない）

`Goal` までの実装は、`v1-start` の状態を崩さず、各Stepでこまめに動作確認しながら進めるのが最短です。
