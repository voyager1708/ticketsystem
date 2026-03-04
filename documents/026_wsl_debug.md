# WSL の Ubuntu にアクセスして DEBUG する

ドキュメント（`001_setup_v1_start.md` 等）のとおり、Windows では **WSL2 の Ubuntu** 内で Docker / ターミナルを動かす想定です。  
Cursor（または VS Code）から **WSL 内のこのプロジェクトを開き、ブレークポイントでデバッグ**する手順です。

---

## 1. Cursor で「WSL のフォルダ」を開く

1. **コマンドパレット**を開く: `Ctrl+Shift+P`（Mac は `Cmd+Shift+P`）
2. **「Reopen Folder in WSL」** または **「Connect to WSL」** を実行
   - 初回は「WSL」拡張のインストールを促される場合はインストールする
3. プロジェクトルート（`ticketsystem-start`）を WSL 上で開く
   - 既に WSL の Ubuntu ターミナルで `cd` している場合は、そのフォルダを「開く」でも可

これでエディタが **WSL 内の Linux 環境** に接続され、ターミナル・Python インタープリタ・デバッグがすべて WSL 上で動きます。

---

## 2. WSL 内で Python 環境を用意する（デバッグ用）

デバッグでは **Docker ではなく、WSL 内の Python + venv** で `runserver` を動かします（ブレークポイントが止まります）。

WSL の Ubuntu ターミナルで、プロジェクトルートにいる状態で:

```bash
cd app
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
```

※ 非 Docker 手順と同じです（`documents/001_setup_v1_start.md` の「3. 代替手順」）。

---

## 3. Cursor で Python インタープリタを WSL の venv に合わせる

1. `Ctrl+Shift+P` → **「Python: Select Interpreter」**
2. 一覧から **WSL 内の venv** を選ぶ  
   - 例: `.\\.venv\\Scripts\\python.exe` ではなく、  
     **`\\wsl$\\Ubuntu\\home\<ユーザー>\...\ticketsystem-start\app\.venv\bin\python`** のような WSL パス

WSL でフォルダを開いていれば、「Python 3.x.x ('.venv': venv)」のように `.venv` が表示されます。

---

## 4. デバッグの実行

1. ブレークポイントを置く  
   - 例: `app/ticket_service/views.py` の該当行の左クリック
2. 左サイドバーで **「Run and Debug」**（または `Ctrl+Shift+D`）を開く
3. 構成で **「Django (WSL): runserver」** を選択
4. **緑の再生ボタン** でデバッグ開始

ブラウザや `curl` で `http://localhost:8000/...` にアクセスすると、ブレークポイントで停止します。

---

## 5. よくあること

| 現象 | 対処 |
|------|------|
| 「Python が見つからない」 | 「Python: Select Interpreter」で WSL の `.venv` を選択する |
| ブレークで止まらない | 構成が「Django (WSL): runserver」か確認。`justMyCode: false` のためライブラリにも止められる |
| ポート 8000 が使えない | 既に Docker の `runserver` や別プロセスが 8000 を使っている場合は、Docker を止めるか `launch.json` の `args` で別ポート（例: `8002`）を指定する |

---

## 6. 設定ファイル

- **`.vscode/launch.json`**  
  - 「Django (WSL): runserver」で `app/manage.py runserver 0.0.0.0:8000` を実行します。  
  - 作業ディレクトリは `app` です。

WSL の Ubuntu に「アクセス」してデバッグする＝**Cursor で「Reopen in WSL」し、WSL の Python で runserver をデバッグ起動する**流れになります。
