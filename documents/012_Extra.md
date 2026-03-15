# 追加演習: チケット・報酬表示 Web ページ（/tickets/）

Step 0〜4 を一通り終えたあと、余力がある方向けの演習です。**取得したチケットと報酬NFTを表示する Web ページ**を実装します。

- **URL**: `/tickets/`（トップや Swagger にはリンクを出さず、path の追加のみ）
- **技術**: Django テンプレートで「マイチケット」「マイ報酬」の 2 セクションを表示。レスポンシブ ＋ CSS。
---

## AI プロンプト（1回で成功させる用）

以下をそのまま AI（Cursor など）に貼り付けて、Plan または Agent で実装させる。**既存の TicketListAPIView / RewardListAPIView は一切変更しない**。追加のみで実装すること。

```text
このプロジェクトに「マイチケット・報酬」を表示する Web ページを追加してください。既存コードは変更せず、追加のみで実装します。

【要件】

1. URL は /tickets/ とする。トップや Swagger にはリンクを出さない（path の追加のみ）。

2. ページ用のビュー TicketsPageView（django.views.View の get のみ）を app/ticket_service/views.py の末尾に追加する。
   - request.build_absolute_uri で /api/ext/v1/ticket/list と /api/ext/v1/reward/list の URL を組み立て、requests.get(url, cookies=dict(request.COOKIES)) で取得する。
   - いずれかが 401 なら redirect("/accounts/login/?next=/tickets/") する。
   - 両方 200 なら JSON の results を ticket_list / reward_list として取得する。
   - 各チケット（ticket_list の各要素）について、TicketCheckinRecord を nft_origin で検索し、レコードがあれば item["used"]=True と item["used_at"]=record.used_at の日時文字列（"%Y-%m-%d %H:%M"）、なければ item["used"]=False, item["used_at"]=None を付与する。
   - render(request, "ticket_service/tickets.html", {"ticket_list": ticket_list, "reward_list": reward_list}) で返す。

3. 報酬画像用のビュー RewardImageAPIView を app/ticket_service/views.py に追加する。
   - GET /api/ext/v1/reward/image/<nft_origin> で、未ログイン時は 401（JSON で detail）、NFT なしは 404（JSON で error）を返す。
   - 認証は既存の _get_proxy_cookies(request) を使う。
   - BaseAPIClient().get_nft_raw(nft_origin, cookies) で生バイトを取得し、strip_ordinals_envelope(raw_bytes) した結果を body とする。
   - Content-Type は api_client.get_nft(nft_origin, cookies) の content_type / original_file_name から判定（image/jpeg, image/png 等）。分からなければ image/png。
   - return HttpResponse(body, content_type=content_type) で返す。

4. テンプレート app/ticket_service/templates/ticket_service/tickets.html を新規作成する。
   - 1ページに「マイチケット」「マイ報酬」の2セクション。
   - マイチケット: ticket_list をループ。各カードに ticket_image_url の img、カード本文に「使用済み（used_at）」または「未使用」を表示。続けて event_name, event_date, venue, seat。チェックインリンクは item.used が False のときだけ item.checkin_url を表示する（使用済みのときは出さない）。
   - マイ報酬: reward_list をループ。各カードに img の src を /api/ext/v1/reward/image/{{ item.nft_origin }} とする。本文に reward_name, reward_for, created_at。
   - viewport メタタグと {% load static %} で {% static 'ticket_service/tickets.css' %} を読み込む。

5. app/ticket_service/static/ticket_service/tickets.css を新規作成する。カード型のグリッドレイアウト、メディアクエリで小画面1列・大画面2列。.ticket-card img / .reward-card img は width:100%; height:auto;。.ticket-status はフォントサイズと余白を調整。

6. URL の追加
   - app/ticket_system/urls.py に path('tickets/', TicketsPageView.as_view(), name='tickets') を追加し、TicketsPageView を import に含める。
   - app/ticket_service/urls.py に path('ext/v1/reward/image/<str:nft_origin>', RewardImageAPIView.as_view(), name='ext-reward-image') を追加し、RewardImageAPIView を import に含める（reward/list の前後でよい）。

【制約】
- TicketListAPIView と RewardListAPIView およびそれらのメソッドは一切編集しない。
- 上記のファイル・クラス・テンプレートのみを追加または新規作成する。

実装後、変更したファイル一覧と、/tickets/ に未ログインでアクセスするとログイン画面にリダイレクトすること・ログイン後はマイチケットとマイ報酬が表示され使用済みは「使用済み（日時）」・未使用のみチェックインボタンが出ること・報酬画像が表示されることを簡潔に報告してください。
```
