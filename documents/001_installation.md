# ハンズオン実行環境（2レーン構成・1ページ版）

この資料は、受講者PC差分を吸収するための実行環境ガイドです。  
基本方針は **標準: WSL2 + Docker**、**代替: WSL2 非Docker** です。

---

## 0. 先に結論（運用ルール）

- **標準手順（推奨）**: `WSL2 + Docker Desktop + docker compose`
- **代替手順（救済）**: `WSL2 + Python venv + ローカル起動`
- 講師案内は標準手順で統一し、Dockerが使えない受講者のみ代替手順へ誘導

---

## 1. 共通の事前準備（全員）

- Windows 11（または Windows 10 21H2 以降）
- WSL2 導入済み（Ubuntu 22.04 推奨）
- Git 導入済み
- リポジトリ取得済み

```bash
git clone <REPO_URL>
cd ticketsystem-dev
```

---

## 2. 標準手順（Dockerレーン）

### 対象

- 迷ったらこの手順
- 授業のデモと同じ環境で進めたい人

### 手順

1) Docker Desktop をインストールし、WSL integration を有効化  
2) WSL上でプロジェクトへ移動  
3) コンテナ起動

```bash
cd ~/ticketsystem-dev
docker compose -f docker-compose.dev.yml up -d --build
```

4) ヘルスチェック

```bash
curl -fsS http://localhost:8000/healthz
```

5) 終了時

```bash
docker compose -f docker-compose.dev.yml down
```

### 成功条件

- `healthz` が 200 を返す
- 受講者間で同じ挙動になる

---

## 3. 代替手順（非Dockerレーン）

### 対象

- Docker Desktopが社内ポリシーやPCスペック都合で利用不可
- 一時的にDocker起動が不安定

### 手順

1) WSL上でPython仮想環境を作成  
2) 依存をインストール  
3) サーバー起動

```bash
cd ~/ticketsystem-dev/app
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

4) 別ターミナルでヘルスチェック

```bash
curl -fsS http://localhost:8000/healthz
```

### 成功条件

- `healthz` が 200 を返す
- APIの基本シナリオ（login/create/image/checkin）が実行できる

---

## 4. どちらを選ぶか（判定表）

| 観点 | WSL2 + Docker（標準） | WSL2 非Docker（代替） |
|---|---|---|
| 再現性 | 高い | 中程度 |
| 初回セットアップ | やや重い | 軽い |
| トラブル時の切り分け | しやすい | 環境差で複雑化しやすい |
| 授業運用 | 安定 | 受講者ごとの差が出やすい |
| 推奨度 | **◎** | ○（救済用途） |

---

## 5. 進行ルール（講師用）

- 講義開始時は全員をDockerレーンへ案内
- `15分` 以内に起動できない受講者は非Dockerレーンへ切替
- どちらのレーンでも最初のゴールは `GET /healthz = 200`
- 以降のAPIハンズオンは同じ資料で進行

---

## 6. よくある詰まりポイント

- Dockerが起動しない: Docker Desktop再起動、WSL integration確認
- ポート競合: `8000` 使用中プロセスを停止
- 非Dockerで依存エラー: 仮想環境再作成後に `pip install -r requirements.txt`
- 改行/権限エラー: すべてWSL内でコマンド実行（Windows側PowerShell直実行を避ける）

---

## 7. 配布パッケージ設計（初期状態 / 完成状態）

ハンズオンは **2状態をセットで管理** する。

- **初期状態（start）**: 受講者が作業を開始する状態
- **完成状態（goal）**: 講師の正解状態（デモ・救済・比較用）

### 推奨構成

- Gitタグ
  - `handson/v1-start`
  - `handson/v1-goal`
- Dockerイメージタグ
  - `ghcr.io/<org>/ticketsystem-web:v1-start`
  - `ghcr.io/<org>/ticketsystem-web:v1-goal`

### 当日の運用ルール

- 受講者は `v1-start` のみ配布
- 講師は `v1-goal` を手元に保持（詰まり時の即時救済に使用）
- 進行が難しい回は中間チェックポイントタグも追加（例: `v1-step3`）

### 受講者向け最小手順（start）

```bash
git clone <REPO_URL>
cd ticketsystem-dev
git checkout handson/v1-start
./bin/start-dev
```

### 講師向け切替手順（goal確認）

```bash
git checkout handson/v1-goal
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

### 目的

- 全員の開始点を固定して説明を簡潔にする
- 正解環境を即時提示できるようにして授業停止時間を減らす
