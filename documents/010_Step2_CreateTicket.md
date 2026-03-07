# Step 2: 必須API 2本目（チケット生成）

---

## 内容

- **実パス**: `POST /api/ext/v1/ticket/create`
- 必須: `event_name`, `event_date`, `ticket_html`（チケット用 HTML ファイル）
- **成功条件**: 201 で nft_origin 等が返り、後続のチェックイン等で使える

---

## image_samples の HTML

- **`image_samples/ticket_sample.html`**: チケットのレイアウト例（イベント名・日時・会場・座席・所有者などを表示する 1 枚の HTML）。
- このファイルをベースに、**プレースホルダ**を入れた HTML を `ticket_html` としてアップロードする。

### プレースホルダ

- HTML 内に `{{ event_name }}`, `{{ event_date }}`, `{{ venue }}`, `{{ seat }}`, `{{ holder_paymail }}` などを書いておくと、API がリクエストの値で置換してから NFT 用 HTML を生成する。
- 例: 固定の「Summer Festival 2026」の代わりに `{{ event_name }}` と書く。

---

詳細仕様: `021_ticket_create_api_spec.md`。動作確認: `015_handson_step3_ticket_create.md`。

