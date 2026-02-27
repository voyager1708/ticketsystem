# 学習導線（v1-start → Goal）

このプロジェクトは、**「Blockchain を使ったチケット発行システムを構築しよう」** というハンズオンの資料です。  
**Docker ベース**の環境で、**Cursor（AI）** を使いながら構築を進めます。  
`handson/v1-start` から出発し、Goal（必須3API が動作し Swagger で検証できる状態）まで、このフォルダの資料を**読む順**に並べたガイドが以下です。

---

## 最初に読む（必須）

| # | 資料 | 内容 |
|---|------|------|
| 1 | `001_setup_v1_start.md` | 開発環境の起動。`GET /healthz = 200` と Swagger UI まで到達する |
| 2 | `002_handson_plan.md` | 2時間の全体像・タイムテーブル・到達目標（Goal）の確認 |
| 3 | `003_goal_steps_ai_pairing.md` | Step 1 以降の実行順。Cursor（AI）と一緒に必須3API を実装し、Swagger UI（`/api/docs/`）で検証する |

---

## 詰まったときの参照（必要に応じて）

| # | 資料 | こんなときに |
|---|------|--------------|
| 5 | `005_session_auth_reference.md` | 認証・セッション・Cookie で失敗したとき |
| 6 | `006_swagger_auth_troubleshooting.md` | Swagger のログイン／ログアウトで失敗したとき |
| 7 | `007_ticket_create_api_spec.md` | チケット作成APIの仕様を確認したいとき |
| 8 | `008_architecture_reference.md` | 設計の背景や判断根拠を確認したいとき |
| 9 | `009_slides_cell_map.md` | 授業スライドと手順の対応を確認したいとき |
| — | `010_colab_execution_steps.md` | Colab で API を試す場合の手順（任意・今回は使用しない） |

---

## AI を活用するときのルール

- **事実を先に渡す**：実行したコマンド・入力・エラー全文
- **「次の1手」を聞く**：いきなり全面修正は頼まない
- **変更後は再実行**：同じ手順で動くか確認する
- **秘密情報は渡さない**：パスワード・APIキーは貼らない
