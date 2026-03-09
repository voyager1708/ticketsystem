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

## Step2（CreateTicket）を学生演習にするための削除ポイント

`documents/010_Step2_CreateTicket.md` は「学生が AI に `TicketCreateAPIView` を実装させる」前提です。  
現在の `handson/v1-ticket-create` は既に実装済みのため、演習化するには以下を削除して「未実装状態」に戻す。

### まず必須で削る（これだけで Step2 は成立）

1. `app/ticket_service/views.py`
   - `class TicketCreateAPIView` を丸ごと削除
   - `TicketCreateAPIView` 内の `_extract_session_cookies()` も同時に削除
2. `app/ticket_service/urls.py`
   - import から `TicketCreateAPIView` を削除
   - `path('ext/v1/ticket/create', ...)` を削除

これで、Step2 の指示どおり学生が `views.py` と `urls.py` を AI で編集する課題になる。

### 任意で削る（難易度・ノイズ調整）

Step2 だけに集中させたい場合は、以下も候補。

- `app/ticket_service/views.py`
  - `TicketImageAPIView`, `TicketHtmlAPIView`（Step2 の必須範囲外）
  - 先頭の `TicketCheckinUrl` import と `_get_checkin_url_from_metadata()`（上記 API を消すなら不要）
- `app/ticket_service/models.py` / `app/ticket_service/migrations/0006_ticketcheckinurl.py`
  - `TicketCheckinUrl` モデル（DB 永続化は Step2 の必須ではない）
- `documents/022_playwright_ticket_image.md`
  - 画像API運用メモ（Step2 では不要）

### 削除しない方がよいもの（Step2 で再利用）

- `app/ticket_service/services/ticket_service.py` の `TicketService` 既存メソッド
- `app/ticket_service/services/base_api_client.py` の `BaseAPIClient` 既存メソッド
- `documents/021_ticket_create_api_spec.md`（学生が参照する仕様）
- `image_samples/ticket_sample.html`（アップロード用テンプレ）

### 運営向けの実施手順（推奨）

1. 上記「必須で削る」を実施
2. `./bin/restart-dev`
3. Swagger で `POST /api/ext/v1/ticket/create` が消えていることを確認
4. 学生に `010_Step2_CreateTicket.md` のプロンプトを実施させる
5. 学生実装後に 201/400/401 を確認
