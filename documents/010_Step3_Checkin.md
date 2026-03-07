# Step 3: 必須API 3本目（チェックイン）

前: [010_Step2_CreateTicket.md](010_Step2_CreateTicket.md) ／ 次: [010_Step4_Reward.md](010_Step4_Reward.md)

---

## 内容

- **実パス**: `GET/POST /api/ext/v1/ticket/checkin`（資料では `POST /tickets/{id}/checkin` と表記することあり）
- 状態遷移（未チェックイン → チェックイン済み）
- `404 / 409` を実装
- **成功条件**: 1回目成功、2回目が重複扱いになる

---

## AIに聞くとき

```text
Step 3 のチェックイン実装中です。
期待は「2回目が409」ですが、実際は「...」です。
状態判定ロジックで確認すべき条件を、上から3つ提案してください。
```
