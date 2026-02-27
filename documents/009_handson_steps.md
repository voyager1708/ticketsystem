# 008準拠の次手順（おすすめ順）

## Step 0: セットアップ完了確認（今ここ）
- `migrate` 済み
- `runserver` 起動
- 最小エンドポイント応答OK
- `Swagger UI`（`/api/docs/`）を開ける
- これは `2. Colabセットアップ` の完了条件に一致

## Step 1: Django APIの型を確認（短時間）
- URL → View/Serializer → JSONレスポンス → HTTPステータスの返し分け
- Swagger UI上でリクエスト/レスポンスを確認
- `3. Django APIの型を学ぶ` に対応

## Step 2: 必須API 1本目
- **アカウント作成** `POST /accounts`
- 必須項目バリデーション、`201 / 400` の返し分け

## Step 3: 必須API 2本目
- **チケット生成（テンプレート）** `POST /tickets/templates`
- 入力チェック、`201 / 400`

## Step 4: 必須API 3本目
- **チェックイン** `POST /tickets/{id}/checkin`
- 状態遷移（未チェックイン → チェックイン済み）、`404 / 409` を実装

## Step 5: 時間が余れば
- **配布** `POST /tickets/distribute`（実API連携）
- **報酬送付** `POST /rewards/send`（実API連携）

## 重要な整合ポイント
- まずは **必須3APIを完成**（ドキュメント方針どおり）
- 外部連携（Ordinal-X/BSV）は **実API利用**（Sandbox/検証環境を推奨）
- フォーム画面は作らず、Swagger UIで実装検証を行う

## 次アクション
この方針で進めるなら、次は `POST /accounts` の最小実装（モデルなし版 or SQLite保存版）から着手するのが最短です。