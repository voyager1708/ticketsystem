# Step 2: 必須API 2本目（チケット生成）

前: [010_Step1_CreateAccount.md](010_Step1_CreateAccount.md) ／ 次: [010_Step3_Checkin.md](010_Step3_Checkin.md)

---

## 内容

- **実パス**: `POST /api/ext/v1/ticket/create`
- 必須: `event_name`, `event_date`, `ticket_html`（チケット用 HTML ファイル）
- **成功条件**: 201 で nft_origin 等が返り、後続のチェックイン等で使える

---

## image_samples の HTML

- **`image_samples/ticket_sample.html`**: チケットのレイアウト例（イベント名・日時・会場・座席・所有者などを表示する 1 枚の HTML）。
- このファイルをベースに、**プレースホルダ**を入れた HTML を `ticket_html` としてアップロードします。

### プレースホルダ

- HTML 内に `{{ event_name }}`, `{{ event_date }}`, `{{ venue }}`, `{{ seat }}`, `{{ holder_paymail }}` などを書いておくと、API がリクエストの値で置換してから NFT 用 HTML を生成します。
- 例: 固定の「Summer Festival 2026」の代わりに `{{ event_name }}` と書きます。

---

## 実施手順（TicketCreateAPIView を作成します）

この Step では **TicketCreateAPIView を作成**し、チケット作成 API を実装します。以下のプロンプトを AI に渡し、**Plan または Agent** で `views.py` と `urls.py` への追加・修正を AI に実施させます。

### ① プロンプト全文（コピペ用）

以下を**すべて**コピーし、AI（Cursor など）に貼り付けます。**Plan モードまたは Agent モード**で、AI がコードを生成し、`app/ticket_service/views.py` と `app/ticket_service/urls.py` を直接編集するように促します。

```text
POST /api/ext/v1/ticket/create を実装したい。

- 仕様は documents/021_ticket_create_api_spec.md の 3.2 と 5 に従います。multipart/form-data で event_name, event_date, ticket_html（ファイル）必須。任意で venue, seat, recipient_paymail。
- チケットの作成サービス（TicketService と BaseAPIClient）を呼んで、HTML を生成して NFT を作成する View にしてほしい。認証はセッションクッキーで、無ければ 401。必須項目が無いときは 400、サーバーエラーは 500。成功時は 201 で nft_origin や checkin_url などを返します。
- app/ticket_service/views.py の AuthUserProxyAPIView の直後に TicketCreateAPIView を追加し、app/ticket_service/urls.py に ext/v1/ticket/create の path を追加します。

【AI への指示】
- Plan または Agent で、次のファイルを**直接編集**します。app/ticket_service/views.py の AuthUserProxyAPIView の直後に TicketCreateAPIView クラスを追加し、app/ticket_service/urls.py に TicketCreateAPIView の import と path('ext/v1/ticket/create', ...) を追加してください。
- 実装する際は、次を参照して細部を決めてからコードを生成してください。
  - documents/021_ticket_create_api_spec.md でリクエスト・レスポンスの形式とエラーの扱いを確認します。
  - app/ticket_service/services/ticket_service.py の TicketService と app/ticket_service/services/base_api_client.py の BaseAPIClient の既存メソッドを参照し、チケット作成に使うメソッド名・引数・戻り値を合わせます。
  - エラーメッセージの文言・201 レスポンスのキー名・認証（_extract_session_cookies の動き）・DRF の authentication_classes / parser_classes / @extend_schema の内容を、既存コードのスタイルに揃えて実装します。
```

### ② 実施後の確認

1. Swagger で `POST /api/ext/v1/ticket/create` が表示されている。
2. 必須を欠くと 400、認証なしで 401。
3. 正常系で 201、レスポンスに `nft_origin` 等が含まれる。

   **201 レスポンスの例**:

```json
{
  "status": "success",
  "message": "Ticket NFT created successfully",
  "nft_origin": "29bb3af6a4d5d3d15fa1f78b0c90523d95fb57eba4a9098b61a2e942fde7f3fa_0",
  "transaction_id": "29bb3af6a4d5d3d15fa1f78b0c90523d95fb57eba4a9098b61a2e942fde7f3fa",
  "ticket_image_url": "/api/ext/v1/ticket/image/29bb3af6a4d5d3d15fa1f78b0c90523d95fb57eba4a9098b61a2e942fde7f3fa_0",
  "checkin_url": "http://127.0.0.1:8001/api/ext/v1/ticket/checkin?token=29bb3af6a4d5d3d15fa1f78b0c90523d95fb57eba4a9098b61a2e942fde7f3fa_0:1vysUl:Mv1rkvCvy7K-h6WNDvqmSiJWTK9I9M-8pTeOcBDNbzM",
  "nft_information": {
    "nft_id": 29,
    "nft_origin": "29bb3af6a4d5d3d15fa1f78b0c90523d95fb57eba4a9098b61a2e942fde7f3fa_0",
    "current_nft_location": "29bb3af6a4d5d3d15fa1f78b0c90523d95fb57eba4a9098b61a2e942fde7f3fa_0",
    "original_file_name": "ticket.html",
    "content_type": "text/html",
    "name": "test1 Ticket",
    "metadata": {
      "MAP": {
        "app": "Ticket System",
        "name": "test1 Ticket",
        "type": "ord",
        "subType": "collectionItem",
        "subTypeData": {
          "ticket": {
            "seat": "A10-1",
            "venue": "Address1",
            "created_at": "2026-03-07T14:19:05.153055Z",
            "event_date": "2026-09-04T16:07:48",
            "event_name": "test1",
            "holder_paymail": "ysato3_ysato3@bsvapi01.cds.tohoku.ac.jp"
          }
        }
      }
    },
    "created_at": "2026-03-07T23:19:06.910643+09:00",
    "updated_at": "2026-03-07T23:19:07.628485+09:00",
    "deleted_at": null
  }
}
```

4. **WOC で確認**: 201 で返った `nft_origin` または `transaction_id` を使い、WOC 上で該当インスクリプションを検索する。content-type が `text/html` のインスクリプションとして登録されており、デコードするとアップロードしたチケット HTML の内容（イベント名・日付等の置換後）が表示されることを確認する。（仕様の詳細は [021_ticket_create_api_spec.md](021_ticket_create_api_spec.md) の「4.4 WOC でチケット HTML を確認する」を参照。）

 origin/handson/v1-ticket-create


 
ずれた場合は [030_TicketCreateAPIView_reference.md](030_TicketCreateAPIView_reference.md) を参照します。

---

詳細仕様: [021_ticket_create_api_spec.md](021_ticket_create_api_spec.md)。別手順: [016_handson_ticket_create_ai_prompt.md](016_handson_ticket_create_ai_prompt.md)。

