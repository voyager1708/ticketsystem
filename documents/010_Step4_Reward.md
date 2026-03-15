# Step 4: Reward（報酬）

前: [010_Step3_Checkin.md](010_Step3_Checkin.md)

---

## 内容

**報酬NFTは、チェックインを実行したタイミングで処理される。**  
Step 3 のチェックインAPI（`POST /api/ext/v1/ticket/checkin`）を呼び出したとき、初回チェックインであればその場で報酬NFTが作成・送付され、レスポンスの `reward_nft` に結果が含まれる。

| 役割 | API | 説明 |
|------|-----|------|
| **チェックイン実行時に報酬を処理** | `POST /api/ext/v1/ticket/checkin` | チェックイン実行のたびに、未使用チケットなら報酬NFTを作成して返す。既に `TicketCheckinRecord.reward_nft_origin` があればそれを返し、無ければ `TicketDesign.checkin_reward_image`（未登録時は `image_samples/SendaiArt1_Reward.jpg`）で報酬NFT作成を試行し、`TicketCheckinRecord` を保存して使用済みに更新する。 |
| **報酬画像の事前登録** | `POST /api/ext/v1/reward/create` | チェックイン実行時に使う報酬用画像を登録するだけのAPI（このAPI単体ではNFTは作成しない）。`reward_image` 未指定時はデフォルト画像を登録する。 |

このStepでは、**チェックイン実行時**に報酬が動く流れと、その報酬で使う画像の登録を扱う。

---

## Goal 判定

- Swagger で **チェックイン実行**（`POST /api/ext/v1/ticket/checkin`）したとき、レスポンスに `reward_nft` が含まれる。

## Appendix

- 同じ token で再実行すると、保存済み `reward_nft_origin` を再利用して `reward_nft` が返る。
- `POST /api/ext/v1/reward/create` で登録した画像が、**次回以降のチェックイン実行時**の報酬NFT作成で使われる。

## 進行ルール（重要）

- 検証は Swagger または curl で行う。
- まず **チェックイン実行**（checkin API）経由で報酬が返ることを確認する。
- DB の前提: 起動時の migrate で `TicketCheckinRecord`（`reward_nft_origin` 含む）が作成済みであること（Docker は entrypoint、非 Docker は 001 の代替手順）。

