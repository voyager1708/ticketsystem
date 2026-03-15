# Step 3: 必須API 3本目（チェックイン）

前: [010_Step2_CreateTicket.md](010_Step2_CreateTicket.md) ／ 次: [010_Step4_Reward.md](010_Step4_Reward.md)

---

## 内容

チェックインは **Swagger UI**（`/swagger/`）の **ticket** タグ配下の次の2オペレーションで扱う。

| 操作 | メソッド | パス | Swagger 上の概要 |
|------|----------|------|------------------|
| 状態確認 | GET | `/api/ext/v1/ticket/checkin` | Ticket check-in status |
| チェックイン実行 | POST | `/api/ext/v1/ticket/checkin` | Ticket check-in execute |

- **GET**  
  - クエリパラメータ `token`（必須）でチェックイントークンを渡す。  
  - token を検証して `nft_origin` を確定し、`TicketCheckinRecord` の有無で `used` / `used_at` / `nft_origin` / `message` を返す。更新は行わない。
- **POST**  
  - リクエストボディ（JSON）の `token`（必須）でチェックイントークンを渡す。  
  - token を検証して `nft_origin` を確定し、`TicketCheckinRecord` で使用済み状態を管理。  
  - **初回**: `used_at` を保存してチェックイン完了し、`reward_nft` を返す（Step4参照）。  
  - **2回目以降**: 既存レコードを参照し `Already checked in` を返す。

Swagger から試す手順は [010_Step1_CreateAccount.md](010_Step1_CreateAccount.md)（Try it out → パラメータ入力 → Execute → レスポンス確認）に準じる。

- チェックインAPIは `TicketCheckinRecord` で状態を保持する。このテーブル（`reward_nft_origin` 含む）は **起動時に作成される**（Docker の場合はコンテナ起動時の entrypoint で migrate、非 Docker の場合は [001_Setup_v1_start.md](001_Setup_v1_start.md) の代替手順で migrate を実行）。

---

## Goal 判定

- Swagger で **POST** `/api/ext/v1/ticket/checkin` を初回実行したとき、`used=true` と `message=Checked in` が返る。

## Appendix

- 同じ token で再実行したとき、`message=Already checked in` が返る。
- Swagger で **GET** `/api/ext/v1/ticket/checkin` に `token` を渡したとき、`used` と `used_at` を確認できる。

---

