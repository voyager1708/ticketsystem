# ハンズオン運営メモ（講師・TA 向け）

001〜011 は学生向け。このファイルは運営用のメモです。

---

## Goal ブランチとの対応（重要）
- **実装の正**は Git の **`handson/v1-goal`** ブランチ。実装・検証時は `git diff handson/v1-start origin/handson/v1-goal` や Swagger のパスで goal と比較して確認すること。
- 本資料の「5API」と goal の実際のエンドポイントの対応は以下のとおり。

| 本資料 | goal ブランチのパス | 備考 |
|--------|----------------------|------|
| 1) アカウント作成 | ローカル作成 + ベースAPI sign-up 転送 | **v1-start で事前実装済み**（`POST /api/accounts/create`）。転送のみは `POST /api/ext/v1/auth/sign-up`。goal には同APIなし |
| 2) チケット生成 | `POST /api/ext/v1/ticket/create` | 本資料では `POST /tickets/create` と表記 |
| 3) 配布 | （余力） | チケット画像取得など |
| 4) チェックイン | `GET/POST /api/ext/v1/ticket/checkin` | 本資料では `POST /tickets/{id}/checkin` と表記 |
| 5) 報酬送付 | （余力） | チェックイン完了時の報酬 |

---
