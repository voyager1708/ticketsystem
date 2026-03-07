#!/usr/bin/env python3
"""
Build a single self-contained ticket HTML for NFT:
- Reads the actual JPEG background file from disk and embeds it as Base64 in img src.
- Embeds the ticket/metadata JSON inside the HTML so one NFT asset = HTML (visual + data).
"""
import base64
import json
from pathlib import Path

# Paths
ROOT = Path(__file__).resolve().parent.parent
BG_PATH = ROOT / "image_samples" / "background.jpg"  # Actual JPEG file to embed
OUT_PATH = ROOT / "image_samples" / "ticket_sample.html"

# Ticket data (from 021_ticket_create_api_spec.md subTypeData.ticket)
TICKET = {
    "event_name": "Summer Festival 2026",
    "event_date": "2026-08-15T18:00:00+09:00",
    "venue": "Tokyo Dome",
    "seat": "A-15",
    "holder_paymail": "user@example.com",
    "created_at": "2026-01-26T10:00:00Z",
}

# Full NFT metadata (MAP) to embed in HTML - one NFT = one HTML with this JSON inside
NFT_METADATA = {
    "map": {
        "app": "Ticket System",
        "name": "Summer Festival 2026 Ticket",
        "type": "ord",
        "subType": "collectionItem",
        "subTypeData": {
            "ticket": TICKET.copy(),
        },
    },
    "insc": {
        "file": {
            "hash": "...",
            "size": 0,
            "type": "text/html",
        },
    },
}


def format_date(iso: str) -> str:
    """Display date in readable form."""
    if not iso:
        return ""
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%Y年%m月%d日 %H:%M")
    except Exception:
        return iso


def main():
    # 1) Read actual JPEG file and encode as Base64 for img src
    if not BG_PATH.exists():
        raise SystemExit(f"Background image not found: {BG_PATH}")
    bg_bytes = BG_PATH.read_bytes()
    b64 = base64.b64encode(bg_bytes).decode("ascii")
    data_uri = f"data:image/jpeg;base64,{b64}"

    event_date_display = format_date(TICKET["event_date"])
    created_display = format_date(TICKET["created_at"])

    # 2) JSON to embed in HTML (for NFT: one file = visual + data)
    nft_json_escaped = json.dumps(NFT_METADATA, ensure_ascii=False, indent=2)

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Summer Festival 2026 Ticket</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center; background: #1a1a2e; }}
    .ticket {{
      width: 800px;
      height: 450px;
      position: relative;
      overflow: hidden;
      border-radius: 12px;
      box-shadow: 0 8px 32px rgba(0,0,0,0.4);
    }}
    .ticket-bg {{
      position: absolute;
      left: 0;
      top: 0;
      width: 100%;
      height: 100%;
      object-fit: cover;
      z-index: 0;
    }}
    .ticket-info {{
      position: absolute;
      left: 0;
      top: 0;
      width: 42%;
      height: 100%;
      padding: 40px 32px;
      display: flex;
      flex-direction: column;
      justify-content: center;
      z-index: 1;
      background: linear-gradient(to right, rgba(26,26,46,0.85) 0%, rgba(26,26,46,0.4) 70%, transparent 100%);
      color: #fff;
      font-family: "Segoe UI", "Hiragino Sans", "Yu Gothic UI", sans-serif;
    }}
    .ticket-info h1 {{
      font-size: 22px;
      font-weight: 700;
      line-height: 1.3;
      margin-bottom: 24px;
      letter-spacing: 0.02em;
      text-shadow: 0 1px 2px rgba(0,0,0,0.5);
    }}
    .ticket-info .row {{
      font-size: 14px;
      line-height: 1.9;
      display: flex;
      align-items: baseline;
      gap: 10px;
    }}
    .ticket-info .label {{
      color: rgba(255,255,255,0.75);
      min-width: 100px;
      font-weight: 500;
    }}
    .ticket-info .value {{
      color: #fff;
      font-weight: 600;
    }}
  </style>
</head>
<body>
  <!-- NFT metadata: one HTML = one NFT with embedded JSON. Parsers can read via id="nft-metadata". -->
  <script type="application/json" id="nft-metadata">
{nft_json_escaped}
  </script>

  <div class="ticket">
    <img class="ticket-bg" src="{data_uri}" alt="" />
    <div class="ticket-info">
      <h1>{TICKET["event_name"]}</h1>
      <div class="row"><span class="label">日時</span><span class="value">{event_date_display}</span></div>
      <div class="row"><span class="label">会場</span><span class="value">{TICKET["venue"]}</span></div>
      <div class="row"><span class="label">座席</span><span class="value">{TICKET["seat"]}</span></div>
      <div class="row"><span class="label">所有者</span><span class="value">{TICKET["holder_paymail"]}</span></div>
      <div class="row"><span class="label">発行日</span><span class="value">{created_display}</span></div>
    </div>
  </div>
</body>
</html>
"""
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(html, encoding="utf-8")
    print(f"Wrote {OUT_PATH} ({len(html)} chars)")
    print(f"  - Background: {BG_PATH} (Base64 in img src)")
    print(f"  - JSON embedded in <script type=\"application/json\" id=\"nft-metadata\">")


if __name__ == "__main__":
    main()
