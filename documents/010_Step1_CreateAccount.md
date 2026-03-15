# Step 1: アカウント作成・ログイン（Swagger の使い方）

前: [010_Step0_Setup.md](010_Step0_Setup.md) ／ 次: [010_Step2_CreateTicket.md](010_Step2_CreateTicket.md)

---

## ポイント

- **アカウント作成**により、ベースAPI側で**秘密鍵（ウォレット）が作成**される。以降のチケットNFT発行・チェックインはこのアカウントで行う。
- この Step では **Swagger の操作**（Try it out → パラメータ入力 → Execute → レスポンス確認）を覚える。

---

## 手順

1. **Swagger UI**（`/swagger/`）を開く。
2. **アカウント作成**
   - `POST /api/accounts/create` を開き、「Try it out」→ `username` / `email` / `password` を入力（例: `testuser` / `test@example.com` / `password123`）→ **Execute**。
   - **201** かつ `{id, username}` が返れば成功。
3. **ログイン**
   - `POST /api/ext/v1/auth/login` を開き、同じ `username` / `password` を入力 → **Execute**。
   - **200** でログイン成功。以降、同一ブラウザで認証付きリクエストができる。
