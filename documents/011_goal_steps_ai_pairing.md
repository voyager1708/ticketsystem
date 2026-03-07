# v1-start から Goal までの実行ステップ（AI併走版）

`handson/v1-start` の生徒が「次に何をするか」を迷わないための一本道ガイド。**各 Step の詳細はリンク先のファイルを開く。**

| Step | ファイル | 内容 |
|------|----------|------|
| **Step 0** | [010_Step0_Setup.md](010_Step0_Setup.md) | セットアップ完了確認（migrate, runserver, healthz, Swagger）＋ APIの型を確認 |
| **Step 1** | [010_Step1_CreateAccount.md](010_Step1_CreateAccount.md) | 必須API 1本目：アカウント作成・サインアップ |
| **Step 2** | [010_Step2_CreateTicket.md](010_Step2_CreateTicket.md) | 必須API 2本目：チケット生成（`POST /api/ext/v1/ticket/create`） |
| **Step 3** | [010_Step3_Checkin.md](010_Step3_Checkin.md) | 必須API 3本目：チェックイン（`GET/POST /api/ext/v1/ticket/checkin`） |
| **Step 4** | [010_Step4_Reward.md](010_Step4_Reward.md) | 余力があれば：配布・報酬送付 |

---

## Goal 判定

- 必須3API が Swagger から実行できる
- 主要な異常系（少なくとも2パターン）を説明できる
- 自分の実装差分を説明できる

## 進行ルール（重要）

- まずは必須3API を完成
- 外部連携（Ordinal-X/BSV）は実API利用（Sandbox推奨）
- フロント画面は作らず、Swagger 中心で検証
