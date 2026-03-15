# 012_refines: API実装プロンプト集（候補1〜3）

このドキュメントは、追加APIを AI で実装するためのプロンプト集です。  
候補1〜3の内容に対応する、実装用プロンプトをまとめています。

---

## 候補1: RewardランキングAPI

- API: `GET /api/ext/v1/reward/stats`
- 返したい値: `reward_count`, `latest_reward_at`, `top_reward_for_event`
- 完了条件: `200` で集計JSON、未ログイン時 `401`
- AI往復の目安:
  1. API骨組みと認証追加
  2. 集計ロジック追加
  3. Swagger整備とレスポンス調整

```text
あなたは Django REST Framework の実装アシスタントです。
既存の reward/list 実装を参考に、RewardランキングAPIを追加してください。

実装対象:
- GET /api/ext/v1/reward/stats

要件:
1) app/ticket_service/views.py に RewardStatsAPIView を追加
   - authentication_classes = [CsrfExemptSessionAuthentication]
   - permission_classes = [AllowAny]
   - 未ログイン時は 401 と {"detail": "Authentication credentials were not provided."}
2) BaseAPIClient.get_user_nfts(session_cookies) を使ってログインユーザーのNFT一覧を取得
3) check-in報酬NFTのみを対象に集計し、以下を返す
   - reward_count: 報酬NFT件数
   - latest_reward_at: 最新報酬の日時（無ければ null）
   - top_reward_for_event: 最頻出の reward_for（無ければ null）
4) app/ticket_service/urls.py に
   path('ext/v1/reward/stats', RewardStatsAPIView.as_view(), name='ext-reward-stats')
   を追加
5) drf-spectacular の extend_schema を付与

制約:
- 新規外部連携は追加しない
- 既存APIの挙動を壊さない

最後に:
- 変更ファイル一覧
- 実装要点
- 200/401 のレスポンス例
を報告してください。
```

---

## 候補2: チェックイン履歴API

- API: `GET /api/ext/v1/ticket/checkin/history`
- データ源: `TicketCheckinRecord`
- 返したい値: `nft_origin`, `used_at`, `reward_nft_origin`
- 完了条件: 新しい順、空配列対応、`401` 対応
- AI往復の目安:
  1. View+URL追加
  2. Queryset整形/ページング（任意）
  3. スキーマとエラーハンドリング調整

```text
あなたは Django REST Framework の実装アシスタントです。
既存の checkin 実装と同じスタイルで、チェックイン履歴APIを追加してください。

実装対象:
- GET /api/ext/v1/ticket/checkin/history

要件:
1) app/ticket_service/views.py に TicketCheckinHistoryAPIView を追加
   - authentication_classes = [CsrfExemptSessionAuthentication]
   - permission_classes = [AllowAny]
   - 未ログイン時は 401 と {"detail": "Authentication credentials were not provided."}
2) TicketCheckinRecord を used_at 降順で取得
3) レスポンス形式は {"count": int, "results": [...]} とし、
   results の各要素は nft_origin, used_at, reward_nft_origin を返す
4) データが無い場合は 200 + {"count":0,"results":[]}
5) app/ticket_service/urls.py に
   path('ext/v1/ticket/checkin/history', TicketCheckinHistoryAPIView.as_view(), name='ext-ticket-checkin-history')
   を追加
6) drf-spectacular の extend_schema を付与

任意:
- limit / offset の簡易ページング

制約:
- DBマイグレーションは不要
- 既存 checkin API の挙動は変更しない

最後に:
- 変更ファイル一覧
- 実装要点
- 200/401 のレスポンス例
を報告してください。
```

---

## 候補3: Reward画像プレビューAPI

- API: `GET /api/ext/v1/reward/image/current`
- 内容: 現在登録中の `checkin_reward_image` を返す（未登録時はデフォルト画像）
- 完了条件: 画像レスポンス（jpeg/png）で返る、フォールバック動作
- AI往復の目安:
  1. View+URL追加
  2. 画像読み出し/フォールバック
  3. Content-Type調整とSwagger反映

```text
あなたは Django REST Framework の実装アシスタントです。
既存の RewardCreate と checkin 報酬画像参照ロジックに合わせて、現在画像プレビューAPIを追加してください。

実装対象:
- GET /api/ext/v1/reward/image/current

要件:
1) app/ticket_service/views.py に RewardCurrentImageAPIView を追加
   - authentication_classes = [CsrfExemptSessionAuthentication]
   - permission_classes = [AllowAny]
2) 画像ソースの優先順:
   - TicketDesign.get_active().checkin_reward_image
   - image_samples/SendaiArt1_Reward.jpg（フォールバック）
3) 画像バイトを HttpResponse で返却
4) Content-Type を拡張子に応じて適切に設定（image/jpeg, image/png など）
5) app/ticket_service/urls.py に
   path('ext/v1/reward/image/current', RewardCurrentImageAPIView.as_view(), name='ext-reward-image-current')
   を追加
6) drf-spectacular の schema を付与（画像レスポンス）

制約:
- 既存 reward/create と ticket/checkin の挙動を壊さない
- 新規外部連携は追加しない

最後に:
- 変更ファイル一覧
- 実装要点
- 成功時のレスポンスヘッダ例（Content-Type）
- フォールバック時の挙動
を報告してください。
```

---

## 整合チェック

- 候補1: `GET /api/ext/v1/reward/stats`
- 候補2: `GET /api/ext/v1/ticket/checkin/history`
- 候補3: `GET /api/ext/v1/reward/image/current`
- 各候補に「内容 / 完了条件 / AI往復目安 / 実装プロンプト」を記載済み
