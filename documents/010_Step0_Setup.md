# Step 0: セットアップ ＋ APIの型確認

このファイルは **Step 0 のみ**。次は [010_Step1_CreateAccount.md](010_Step1_CreateAccount.md)（Step 1）。

---

## 目的・進め方（共通）

題材はチケットシステム（アカウント作成、チケット生成、チェックイン、報酬送付）

- **目的**: `handson/v1-start` から **Goal** まで、API開発の「設計 → 実装 → 検証」を体験する。
- **進め方**: Stepごとに成功条件を満たしたら次へ。
- **前提**: 実行環境はローカル　Django + DRF + Swagger UI。開始ブランチは `handson/v1-start`。
- **到達目標（Goal）**: 必須3API（アカウント作成・チケット生成・チェックイン）が Swagger から実行でき、主要な異常系を説明できる。

---

## 1. セットアップ（開始条件）

- `runserver` 起動済み
- `GET /healthz` が成功
- `Swagger UI`（`/swagger/`）を開ける

---

## 2. APIの型を確認

- Swagger で 1 本だけ叩き、返ってきた結果を見て基準を作る（例: `GET /api/ext/v1/auth/user`）

   → 想定: ログインしていないので **「Error: Unauthorized」**（401）が返る
　 → この「異常系の返し方」を見て、API の型（URL → View → ステータス・レスポンス）を把握する
　 → あわせて、この先出てくる `200/201/400/404/409` の返し分けのイメージをつかむ

以上ができたら **[010_Step1_CreateAccount.md](010_Step1_CreateAccount.md)** に進む。
