# ハンズオン運営メモ（講師・TA 向け）

001〜010 は学生向け。このファイルは運営用のメモです。

---

## Goal ブランチとの対応（重要）
- **実装の正**は Git の **`handson/v1-goal`** ブランチ。実装・検証時は `git diff handson/v1-start origin/handson/v1-goal` や Swagger のパスで goal と比較して確認すること。
- 本資料の「5API」と goal の実際のエンドポイントの対応は以下のとおり。

| 本資料 | goal ブランチのパス | 備考 |
|--------|----------------------|------|
| 1) アカウント作成 | ローカル作成 + ベースAPI sign-up 転送 | **v1-start で事前実装済み**（`POST /api/accounts/create`）。転送のみは `POST /api/ext/v1/auth/sign-up`。goal には同APIなし |
| 2) チケット生成 | `POST /api/ext/v1/ticket/create` | 本資料では `POST /tickets/create` と表記 |
| 3) 配布 | （余力） | チケット画像取得など |
| 4) チェックイン | `GET/POST /api/ext/v1/ticket/checkin` | 本資料では `POST /tickets/{id}/checkin` と表記 |
| 5) 報酬送付 | （余力） | チェックイン完了時の報酬 |

---

## Step2（CreateTicket）を学生演習にするための削除ポイント

`documents/010_Step2_CreateTicket.md` は「学生が AI に `TicketCreateAPIView` を実装させる」前提です。  
現在の `handson/v1-ticket-create` は既に実装済みのため、演習化するには以下を削除して「未実装状態」に戻す。

### まず必須で削る（Step2 は成立）

1. `app/ticket_service/views.py`
   - `class TicketCreateAPIView` を丸ごと削除
   - `TicketCreateAPIView` 内の `_extract_session_cookies()` も同時に削除
2. `app/ticket_service/urls.py`
   - import から `TicketCreateAPIView` を削除
   - `path('ext/v1/ticket/create', ...)` を削除

これで、Step2 の指示どおり学生が `views.py` と `urls.py` を AI で編集する課題になる。






### 任意で削る（難易度・ノイズ調整）

Step2 だけに集中させたい場合は、以下も候補。

- `app/ticket_service/views.py`
  - `TicketImageAPIView`, `TicketHtmlAPIView`（Step2 の必須範囲外）
  - 先頭の `TicketCheckinUrl` import と `_get_checkin_url_from_metadata()`（上記 API を消すなら不要）
- `app/ticket_service/models.py` / `app/ticket_service/migrations/0006_ticketcheckinurl.py`
  - `TicketCheckinUrl` モデル（DB 永続化は Step2 の必須ではない）
- `documents/043_playwright_ticket_image.md`
  - 画像API運用メモ（Step2 では不要）

### 削除しない方がよいもの（Step2 で再利用）

- `app/ticket_service/services/ticket_service.py` の `TicketService` 既存メソッド
- `app/ticket_service/services/base_api_client.py` の `BaseAPIClient` 既存メソッド
- `documents/040_ticket_create_api_spec.md`（学生が参照する仕様）
- `image_samples/ticket_sample.html`（アップロード用テンプレ）

### 運営向けの実施手順（推奨）

1. 上記「必須で削る」を実施
2. `./bin/restart-dev`
3. Swagger で `POST /api/ext/v1/ticket/create` が消えていることを確認
4. 学生に `010_Step2_CreateTicket.md` のプロンプトを実施させる
5. 学生実装後に 201/400/401 を確認

---

## 追加演習案: チケット・報酬表示 Web ページ（/tickets/）

RewardList API を学生に実装させる代わりに、**取得したチケットと報酬NFTを表示する Web ページ**を実装する案。学生向けの演習内容・AIプロンプトは **[012_Extra.md](012_Extra.md)** にまとめてある。講師は余力 Step や本メモで案内する。

---

## 不要ドキュメント削除の進め方の目安（031・040は残す）

**残す**: `031_Ordinalx_API.md`, `040_ticket_create_api_spec.md`。000 の「詰まったときの参照」は 031 と 040（チケット作成仕様）のみに整理済み。031 内の 040/042/049 参照は削除済み。

**削除するファイル**（032 以降の演習不要分、12件）を**削除して問題が少ない順**に並べる。

| 順 | ファイル | 作業メモ |
|---|----------|----------|
| 1 | `045_colab_execution_steps.md` | 他から参照なし。そのまま削除 |
| 2 | `047_wsl_debug.md` | 044 からのみ参照。044 も削除するので先に削除可 |
| 3 | `043_playwright_ticket_image.md` | 044・050 からのみ参照。先に削除可 |
| 4 | `032_handson_step3_ticket_create.md` | 044 からのみ参照。先に削除可 |
| 5 | `055_overview_diagram.md` | 誰からも参照されていない。そのまま削除可 |
| 6 | `046_docker_installation.md` | 044・048 から参照。先に削除可 |
| 7 | `048_wsl_docker_api_check.md` | 055 から参照。055 削除後なら削除可 |
| 8 | `044_slides_cell_map.md` | 000 からは既に削除済み。そのまま削除可 |
| 9 | （050 は本メモのため**残す**。削除しない） | — |
| 10 | `056_tickets_page_design.md` | 012_Extra から参照。**012_Extra の「設計詳細…056」の1行を削除してから**本ファイルを削除 |
| 11 | `040_swagger_auth_troubleshooting.md` | 000・031 からは参照削除済み。そのまま削除可 |
| 12 | `049_session_auth_reference.md` | 同上 |
| 13 | `042_architecture_reference.md` | 000・031 からは参照削除済み。そのまま削除可 |

※ 削除対象は 050 を除く **12 件**（032, 040, 042, 043, 044, 045, 046, 047, 048, 049, 055, 056）。

---

## 追加演習案: Reward 一覧 API（List Reward NFTs）

`/api/ext/v1/ticket/list` と同じ考え方で、ログインユーザーの NFT 一覧から「報酬NFT」を抽出して返す API を追加できる。  
推奨パスは `GET /api/ext/v1/reward/list`。

### 期待する最小仕様（学生課題向け）

- 認証方式: `CsrfExemptSessionAuthentication` + `AllowAny`（既存の list 系と合わせる）
- 未ログイン時: `401 {"detail": "Authentication credentials were not provided."}`
- 処理:
  1) `_extract_session_cookies()` でクッキー取得  
  2) `BaseAPIClient.get_user_nfts(session_cookies)` で一覧取得  
  3) 各 NFT の metadata から報酬 NFT を判定して絞り込み
- 報酬判定（例）:
  - `metadata.ticket.reward_type == "checkin_reward"`  
  - または `metadata.MAP.subTypeData.ticket.reward_type == "checkin_reward"`（map 形式差分を吸収）
- 返却例:
  - `count`
  - `results[]`（`nft_origin`, `reward_for`, `reward_name`, `created_at` など）

### StepX（RewardList）を学生演習にするための削除ポイント

Reward 一覧 API を先に講師側で実装しておき、学生演習時に未実装状態へ戻す場合のメモ。

#### まず必須で削る（RewardList 課題は成立）

1. `app/ticket_service/views.py`
   - `class RewardListAPIView` を丸ごと削除
   - `RewardListAPIView` 内のヘルパー（`_extract_session_cookies`, `_is_checkin_reward`, `_extract_reward_ticket_metadata`）も同時に削除
   - **注意**: `TicketListAPIView` 側にも同名ヘルパーがあるため、削除対象は `RewardListAPIView` クラス内のみ
2. `app/ticket_service/urls.py`
   - import から `RewardListAPIView` を削除
   - `path('ext/v1/reward/list', ...)` を削除

これで、学生が `views.py` と `urls.py` を AI で編集して実装する課題にできる。

#### 任意で削る（難易度・ノイズ調整）

- `documents/` 配下の RewardList 用仕様メモ（作った場合）
- `views.py` 内の RewardList 専用ユーティリティ関数（他 API で未使用なら削除）

#### 削除しない方がよいもの（再利用）

- `app/ticket_service/services/base_api_client.py` の `get_user_nfts()`
- `app/ticket_service/views.py` の既存 list/checkin 実装（認証・レスポンス形の参考）
- `documents/010_Step4_Reward.md`（報酬の文脈理解に使える）

### 学生に渡す AI プロンプト（そのまま利用可）

以下を `010_StepX_RewardList.md` などに載せて実施させる想定。

```text
あなたは Django REST Framework の実装アシスタントです。
既存コードを読み、/api/ext/v1/ticket/list の実装スタイルに合わせて、
報酬NFT一覧 API を新規実装してください。

目的:
- GET /api/ext/v1/reward/list を追加する
- ログインユーザーが所有するNFT一覧から、check-in報酬NFTだけを抽出して返す

要件:
1) app/ticket_service/views.py に RewardListAPIView を追加
   - authentication_classes = [CsrfExemptSessionAuthentication]
   - permission_classes = [AllowAny]
   - 未ログイン時は 401 と {"detail": "Authentication credentials were not provided."}
2) BaseAPIClient.get_user_nfts(session_cookies) を使ってNFT一覧を取得
3) metadata から reward_type=checkin_reward を判定して絞り込む
   - metadata.ticket.reward_type
   - metadata.MAP/map.subTypeData.ticket.reward_type
   の両方に対応
4) レスポンスは 200 で {"count": <int>, "results": [ ... ]} 形式
   - 各要素に nft_origin は必須
   - 可能なら reward_for, reward_name, created_at も含める
5) app/ticket_service/urls.py に path('ext/v1/reward/list', RewardListAPIView.as_view(), name='ext-reward-list') を追加
6) drf-spectacular の extend_schema を付け、Swagger に表示されるようにする

制約:
- 既存APIの挙動は壊さない
- 既存コードの命名・エラーメッセージ・実装スタイルに合わせる
- 変更ファイルは最小限にする

最後に:
- 変更したファイル一覧
- 実装内容の要点
- 想定レスポンス例（200/401）
を簡潔に報告してください。
```
