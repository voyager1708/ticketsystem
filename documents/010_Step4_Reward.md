# Step 4: 余力があれば（発展）— 配布・報酬送付

前: [010_Step3_Checkin.md](010_Step3_Checkin.md)

---

## 内容

- **`POST /tickets/distribute`**（実API連携）
- **`POST /rewards/send`**（実API連携）

必須3API（アカウント作成・チケット生成・チェックイン）が完了したら、余力があれば上記の実API連携に進む。

---

## Goal 判定

- 必須3API が Swagger から実行できる
- 主要な異常系（少なくとも2パターン）を説明できる
- 自分の実装差分を説明できる

## 進行ルール（重要）

- まずは必須3API を完成
- 外部連携（Ordinal-X/BSV）は実API利用（Sandbox推奨）
- フロント画面は作らず、Swagger 中心で検証
