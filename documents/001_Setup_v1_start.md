# インストール手順（v1-start → Goal）

この資料は、`handson/v1-start` からハンズオンを開始し、**Step 0 まで**の環境を整えるためのセットアップ手順です。  
進め方は「自分で手を動かす + AIに詰まりを相談する」の2本立てです。

---

## Goal で提供される機能

ハンズオン完了時（Goal）に、次の機能が動作している状態を目指します。

### これからやること（5本のAPI）

| Step | 機能 | エンドポイント | 成功の目安 |
|------|------|----------------|------------|
| 2 | アカウント作成（サインアップ） | `POST /api/accounts/create` | ローカルにユーザー作成しつつベースAPIへ sign-up 転送。username / email / password / group（任意）。201 または 400。単なる転送のみは `POST /api/ext/v1/auth/sign-up` |
| 3 | チケット生成 | `POST /tickets/create` | 入力チェック、201 / 400、後続APIで利用可能。チケット確認時に **QRコードを表示** する。 |
| 4 | チェックイン | `POST /tickets/{id}/checkin` | 未チェックイン→チェックイン済みの遷移、404 / 409 の扱い |
| 5 | 配布 | `POST /tickets/distribute` | 実API連携。作成したチケットを利用者に届ける。チケット画像（QR付き）の取得や、NFTとして受領者へ送る連携を含む。 |
| 6 | 報酬送付 | `POST /rewards/send` | 実API連携。チェックイン完了時に報酬NFTを送る処理。 |

### Goal の判定

- 上記必須5APIが Swagger UI（`/swagger/`）から実行できる
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
| Step 5 | 必須API 4本目：配布（チケット画像QR・NFT連携） | — |
| Step 6 | 必須API 5本目：報酬送付（チェックイン時の報酬NFT） | — |
| **Goal** | 必須5APIがSwaggerで検証でき、チケット確認でQR表示、異常系を説明できる | — |

詳細な実行順は `documents/011_goal_steps_ai_pairing.md` に従ってください。

---

## この資料のゴール（環境構築の完了）

この資料は **「環境のインストール・起動・動作確認」** だけを扱います。

- ローカルでAPIサーバーを起動する
- `GET /healthz` が `200` を返す
- Swagger UI（`/swagger/`）を開ける

**上記ができたら** → 次は **[010_Step0_Setup.md](010_Step0_Setup.md)** で「Step 0: 開始条件の確認 ＋ APIの型を確認」に進んでください。  
そのあと [011_goal_steps_ai_pairing.md](011_goal_steps_ai_pairing.md) の表に従い、Step 1 以降のファイルを順に進めます。

---

## 環境構築の順番

以下を**上から順に**進めてください。済んだら「状態」を 済 に書き換えてチェックできます。

| # | 項目 | 状態 |
|---|------|------|
| ① | Ubuntuのインストール | 未 |
| ② | Ubuntu起動 | 未 |
| ③ | 管理者権限 | 未 |
| ⑤ | プロジェクト取得と起動 | 未 |
| ④ | Dockerの導入 | 未 |
| ⑥ | IDE（統合開発環境）のインストール | 未 |

各項目の手順は下記のとおりです。

---

## ① Ubuntuのインストール（OS 別の前提）

以降のコマンドは **Linux 環境のターミナル** を前提にしています。OS に応じて次のように準備してください。

| OS | 準備 |
|----|------|
| **Windows** | **WSL2** で **Ubuntu 24.04** を使う。PowerShell で `wsl --install -d Ubuntu-24.04` を実行し、再起動後に Ubuntu を起動。以降は WSL の Ubuntu ターミナルで `git` / `docker` を実行する。 |
| **macOS** | 標準のターミナル（または iTerm 等）でそのまま実行。Docker は [Docker Desktop for Mac](https://docs.docker.com/desktop/install/mac-install/) または `brew install docker` で導入。 |
| **Linux** | そのままターミナルで実行。Docker は各ディストリのパッケージ（例: Ubuntu は `apt install docker.io docker-compose-plugin`）で導入。 |

---

## ② Ubuntu起動

- **Windows（WSL2）**: スタートメニューなどから **Ubuntu** を起動し、ターミナル（黒い画面）を開く。
- **macOS / Linux**: **ターミナル**（または iTerm 等）を開く。

以降のコマンドは、このターミナルで実行します。

---

## ③ 管理者権限

- 本手順では、**`sudo -s` で root（管理者）になってから操作する**前提で記載しています。ターミナルで `sudo -s` を実行し、パスワード入力後に表示される `#` プロンプトの状態で、以降の作業を行ってください。
- 手順中には `sudo` を付けたコマンドがそのまま書かれている箇所もありますが、root のまま実行する場合は `sudo` を省略して実行してかまいません。`sudo` 付きのまま実行しても問題ありません。
- **Docker を使う場合**: あとで ④ の手順で `docker` グループに自分を追加し、通常ユーザーに戻ったあとでも `sudo` なしで `docker` を実行できるようにします。

---

## ④ Dockerの導入

Docker が未インストールの場合のみ、以下の手順でインストールしてください。インストール後は **⑤ プロジェクト取得と起動** に進み、クローンしたプロジェクト直下でコンテナをビルド・起動します。

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

2. **Docker ソケット権限の設定**（初回のみ）

   `permission denied while trying to connect to the Docker daemon socket` を避けるため、インストール直後に現在ユーザーを `docker` グループに追加します。

   ```bash
   sudo usermod -aG docker $USER
   newgrp docker
   ```

   - `newgrp docker` は「今開いているターミナル」に反映します。
   - 新しいターミナルにも反映したい場合は、いったんログアウト（または WSL 再起動）して再ログインしてください。

3. **Docker の起動**（WSL2 では自動起動しないことがあるため、ターミナルを開いたあとで実行）

   ```bash
   sudo service docker start
   ```

4. **インストール確認**

   ```bash
   docker --version
   docker compose version
   ```
---

### 代替手順（非Docker）

Docker が使えない場合のみ、以下でサーバーを起動できます（④ の代わり）。Python 3.11 以上と Git が必要です。
Dockerが使えない場合のみ、こちらを使ってください。

```bash
cd app
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

---

## ⑤ プロジェクト取得と起動

- **Git** が入っていること（Ubuntu なら `sudo apt install -y git` で導入可能）。
- このリポジトリを手元にクローンし、ハンズオン用ブランチに切り替えます。

```bash
cd ~
git clone https://github.com/voyager1708/ticketsystem.git
cd ticketsystem-start
git checkout handson/v1-start
# または: git switch handson/v1-start
```

続いて、**プロジェクト直下（ticketsystem-start）** で以下を実行してください。  
（Docker がまだ動いていない場合は、**④** の「3. Docker の起動」を先に実行してください。）

1. **`.env` の用意**  
   `.env` が無い場合は、プロジェクトルートで以下を実行する。
   ```bash
   cp .env.example .env
   ```
   **このハンズオンでは `.env` の `BASE_API_URL` に設定する。** 例（東北大学ベースAPI利用時）:
   ```bash
   # .env で BASE_API_URL を指定
   BASE_API_URL=https://bsvapi01.cds.tohoku.ac.jp
   ```
   必要に応じて `SECRET_KEY` や DB 接続先なども編集する。　※今回は編集せずにそのままでいきます。

2. **コンテナのビルド・起動**  
   **`bin/start-dev` を使って起動**（内部で `docker compose -f docker-compose.yml -f docker-compose.dev.yml` を実行）。
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.dev.yml build --no-cache ticket_web
   ./bin/start-dev
   ```
   設定変更やイメージ更新を反映したいときは `./bin/restart-dev` を使う（再起動ではなく再作成で反映）。  
   **理由**: 単なる「再起動」は同じコンテナを止めてまた動かすだけなので、`.env` の変更・Dockerfile の変更・compose の設定変更はコンテナに取り込まれません。一方「再作成」はいったんコンテナを削除してから作り直すため、イメージのビルドし直しや設定の変更が反映されます。

3. **拡張API動作確認**（このリポジトリの Docker はポート **8001** で待ち受けます）
   ```bash
   curl -i -sS http://127.0.0.1:8001/healthz | head -5
   HTTP/1.1 200 OK
   Server: gunicorn
   Date: Fri, 13 Mar 2026 06:18:00 GMT
   Connection: close
   Content-Type: text/html; charset=utf-8
   ```

※ `docker` が未インストールの場合は、**④ Dockerの導入** の手順でインストールしてから試してください。

### 成功条件（この資料のゴール＝環境構築完了）

- `curl` の結果が `200` 系レスポンス
- ブラウザで `http://127.0.0.1:8001/swagger/` を開ける  
→ ここまでできたら [010_Step0_Setup.md](010_Step0_Setup.md) に進む

---

## ⑥ IDE（統合開発環境）のインストール

このハンズオンでは **Cursor**（または VS Code）を推奨します。

- **Cursor**: [https://cursor.com](https://cursor.com) からダウンロード・インストール。AI と併走してコードを書く想定です。
- **VS Code**: [https://code.visualstudio.com](https://code.visualstudio.com) からダウンロード・インストール。

インストール後、**⑤ でクローンしたプロジェクトのフォルダ**（`ticketsystem-start`）を「ファイル → フォルダーを開く」で開いて作業します。

---

## よくある詰まりと対処

- Dockerが起動しない: Dockerアプリ再起動 → もう一度 `up -d --build`
- ポート `8001`（Docker）競合: 既存のコンテナやプロセスを停止して再実行（非Docker の場合は `8000`）
- `pip install`失敗: 仮想環境を作り直して再実行
- パス混在: 必ずリポジトリ配下でコマンド実行

---

## この後に読む順番

| 順番 | 資料 | 役割 |
|------|------|------|
| 1 | **この資料（001）** | 環境構築（Docker/非Docker のインストール・起動・healthz/Swagger 確認） |
| 2 | [010_Step0_Setup.md](010_Step0_Setup.md) | Step 0：開始条件の確認 ＋ APIの型を1本叩いて確認 |
| 3 | [011_goal_steps_ai_pairing.md](011_goal_steps_ai_pairing.md) | 実行ステップ目次。Step 1 以降は `010_Step1_*` 〜 `010_Step4_*` を順に参照 |

