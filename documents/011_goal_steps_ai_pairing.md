# v1-start から Goal までの実行ステップ（AI併走版）

このファイルは、`handson/v1-start` の生徒が「次に何をするか」を迷わないための一本道ガイドです。

## Step 0: セットアップ完了確認（開始条件）
- `migrate` 済み
- `runserver` 起動済み
- `GET /healthz` が成功
- `Swagger UI`（`/swagger/`）を開ける

### AIに聞くときの例　※AIは指示があるまで利用しないでください
```text
Step 0 の確認中です。
healthz が 200 になりません。実行コマンドは「...」、エラーは「...」です。
最短で確認すべき点を3つ教えてください。
```

## Step 1: APIの型を確認（短時間）
- URL -> View/Serializer -> JSONレスポンスの流れを確認
- `200/201/400/404/409` の返し分けを把握
- Swaggerで1本だけ動作確認して基準を作る

## Step 2: 必須API 1本目（アカウント作成・サインアップ）
- `POST /api/accounts/create`（ローカルにユーザー作成 + ベースAPIへ sign-up 転送）
- username, email, password 必須、group（任意）を送信
- 成功条件: 201 で `{id, username}` が返り、`POST /api/ext/v1/auth/login` でログインできる

## Step 3: 必須API 2本目（チケット生成）
- `POST /tickets/create`
- 入力チェック
- `201 / 400` を返し分け
- 成功条件: 生成結果を後続APIで使える

## Step 4: 必須API 3本目（チェックイン）
- `POST /tickets/{id}/checkin`
- 状態遷移（未チェックイン -> チェックイン済み）
- `404 / 409` を実装
- 成功条件: 1回目成功、2回目が重複扱いになる

### AIに聞くとき
```text
Step 4 のチェックイン実装中です。
期待は「2回目が409」ですが、実際は「...」です。
状態判定ロジックで確認すべき条件を、上から3つ提案してください。
```

## Step 5: 余力があれば（発展）
- `POST /tickets/distribute`（実API連携）
- `POST /rewards/send`（実API連携）

## Goal 判定
- 必須3APIがSwaggerから実行できる
- 主要な異常系（少なくとも2パターン）を説明できる
- 自分の実装差分を説明できる

## 進行ルール（重要）
- まずは必須3APIを完成
- 外部連携（Ordinal-X/BSV）は実API利用（Sandbox推奨）
- フロント画面は作らず、Swagger中心で検証