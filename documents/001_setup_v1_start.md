# インストール手順（v1-start → Goal）

この資料は、`handson/v1-start` からハンズオンを開始し、**Step 0 まで**の環境を整えるためのセットアップ手順です。  
進め方は「自分で手を動かす + AIに詰まりを相談する」の2本立てです。

---

## Goal で提供される機能

ハンズオン完了時（Goal）に、次の機能が動作している状態を目指します。

### 必須（3本のAPI）

| Step | 機能 | エンドポイント | 成功の目安 |
|------|------|----------------|------------|
| 2 | アカウント作成（サインアップ） | `POST /api/accounts/create` | ローカルにユーザー作成しつつベースAPIへ sign-up 転送。username / email / password / group（任意）。201 または 400。単なる転送のみは `POST /api/ext/v1/auth/sign-up` |
| 3 | チケット生成 | `POST /tickets/create` | 入力チェック、201 / 400、後続APIで利用可能 |
| 4 | チェックイン | `POST /tickets/{id}/checkin` | 未チェックイン→チェックイン済みの遷移、404 / 409 の扱い |

### 余力があれば（発展）

- **配布** `POST /tickets/distribute`（実API連携）  
  作成したチケットを利用者に届ける処理。チケット画像（QR付き）の取得や、NFTとして受領者へ送る連携を含む。
- **報酬送付** `POST /rewards/send`（実API連携）  
  チェックイン完了時に報酬NFTを送る処理。

### Goal の判定

- 上記必須3APIが Swagger UI（`/swagger/`）から実行できる
- 主要な異常系（少なくとも2パターン）を説明できる
- 自分の実装内容（AI提案を含む）を説明できる

---

## v1-start から Goal までのステップ

| # | 内容 | この資料で扱う |
|---|------|----------------|
| **Step 0** | セットアップ完了確認 | ✅ 下記「この資料のゴール」で完了 |
| Step 1 | APIの型を確認（URL → View → JSON、ステータス返し分け） | — |
| Step 2 | 必須API 1本目：アカウント作成（sign-up） | — |
| Step 3 | 必須API 2本目：チケット生成 | — |
| Step 4 | 必須API 3本目：チェックイン | — |
| Step 5 | 余力があれば：配布・報酬送付 | — |
| **Goal** | 必須3APIがSwaggerで検証でき、異常系を説明できる | — |

詳細な実行順は `documents/011_goal_steps_ai_pairing.md` に従ってください。

---

## この資料のゴール（Step 0 の完了）

- ローカルでAPIサーバーを起動する
- `GET /healthz` が `200` を返す
- Swagger UI（`/swagger/`）を開ける
- 上記ができたら、`011_goal_steps_ai_pairing.md` の **Step 1** に進める

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

以下の手順で進んでください。

### Docker が未インストールの場合（方法1: 公式リポジトリで入れる・推奨）

`docker` コマンドが見つからない場合は、まず Docker をインストールします。**`docker compose`（Compose v2）** が使えるように、公式リポジトリから入れます。

1. **公式リポジトリの追加とインストール**（WSL2 / Ubuntu 系）

   ```bash
   sudo apt update
   sudo apt install -y ca-certificates curl gnupg
   sudo install -m 0755 -d /etc/apt/keyrings
   curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo tee /etc/apt/keyrings/docker.asc > /dev/null
   sudo chmod a+r /etc/apt/keyrings/docker.asc
   echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
   sudo apt update
   sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
   ```

2. **Docker の起動**（WSL2 では自動起動しないことがあるため、ターミナルを開いたあとで実行）

   ```bash
   sudo service docker start
   ```

3. **インストール確認**

   ```bash
   docker --version
   docker compose version
   ```

   両方表示されれば、このあとの「コンテナのビルド・起動」に進めます。

---

0. **Docker の起動**（WSL2 などでは自動起動しないため、コンテナを動かす前に実行する）
   ```bash
   sudo service docker start
   ```

   ```text
   APIが利用可能かを確認します。
   ```

   ```bash
   sudo docker compose -f docker-compose.yml -f docker-compose.dev.yml exec ticket_web python manage.py check_base_api --insecure
   BASE_API_URL = https://bsvapi01.cds.tohoku.ac.jp
   SSL verification: OFF (--insecure)
   ```

   ```text
   GET https://bsvapi01.cds.tohoku.ac.jp  ->  200
   ```


1. **`.env` の用意**  
   `.env` が無い場合は、プロジェクトルートで以下を実行する。
   ```bash
   cp .env.example .env
   ```
   （必要に応じて `.env` 内の `SECRET_KEY` や DB 接続先などを編集する。）

2. **コンテナのビルド・起動**  
   `docker-compose.dev.yml` は上書き用のため、**`bin/start-dev` を使う**（内部で `docker compose -f docker-compose.yml -f docker-compose.dev.yml` を実行）。
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.dev.yml build --no-cache ticket_web
   ./bin/start-dev
   ```
   設定変更やイメージ更新を反映したいときは `./bin/restart-dev` を使う（再起動ではなく再作成で反映）。

3. **動作確認**（このリポジトリの Docker はポート **8001** で待ち受けます）
   ```bash
   curl -fsS http://localhost:8001/healthz
   ```

※ `docker` が未インストールの場合は、上記「Docker が未インストールの場合（方法1: 公式リポジトリで入れる）」の手順でインストールしてから、再度コンテナのビルド・起動を試してください。

### 成功条件（Step 0）

- `curl` の結果が `200` 系レスポンス
- ブラウザで `http://localhost:8001/swagger/` を開ける


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
- `http://localhost:8000/swagger/` で Swagger UI を開ける
- その後、`documents/011_goal_steps_ai_pairing.md` の Step 1 に進める

---

## 5. よくある詰まりと対処

- Dockerが起動しない: Dockerアプリ再起動 → もう一度 `up -d --build`
- ポート `8001`（Docker）競合: 既存のコンテナやプロセスを停止して再実行（非Docker の場合は `8000`）
- `pip install`失敗: 仮想環境を作り直して再実行
- パス混在: 必ずリポジトリ配下でコマンド実行

---

## 6. この後に読む順番

1. `documents/011_goal_steps_ai_pairing.md`（実行ステップ目次）。各 Step の詳細は `010_Step0_Setup.md` 〜 `010_Step4_Reward.md` を順に参照。

