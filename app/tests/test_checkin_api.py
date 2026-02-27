"""
CheckinAPI テストスクリプト

info@linode.buxbit.net ユーザーでログインし、
チケット画像APIからQRコードを取得して、
実際にチェックインAPIにアクセスするテスト
"""

import requests
import sys
import os

# Django設定を読み込む
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ticket_system.settings')

import django
django.setup()

from ticket_service.services.ticket_service import TicketService


# 設定
BASE_API_URL = "https://linode.buxbit.net"
TICKET_API_URL = "https://ticket.buxbit.net"

# テストユーザー（info@linode.buxbit.net）
TEST_USERNAME = "info@linode.buxbit.net"
TEST_PASSWORD = os.environ.get("TEST_PASSWORD", "")  # 環境変数から取得

# テスト用NFT Origin（info@linode.buxbit.netが所有するNFT）
TEST_NFT_ORIGIN = None  # 後で取得


def login_to_base_api(username: str, password: str) -> dict:
    """ベースAPIにログインしてセッションクッキーを取得"""
    session = requests.Session()
    
    response = session.post(
        f"{BASE_API_URL}/api/v1/auth/login",
        json={"username": username, "password": password},
        headers={"Content-Type": "application/json"}
    )
    
    if response.status_code != 200:
        print(f"Login failed: {response.status_code}")
        print(response.text)
        return {}
    
    print(f"Login successful: {response.json().get('message')}")
    
    # セッションクッキーを取得
    cookies = {}
    for cookie in session.cookies:
        cookies[cookie.name] = cookie.value
        print(f"  Cookie: {cookie.name}={cookie.value[:20]}...")
    
    return cookies


def login_to_ticket_api(username: str, password: str) -> requests.Session:
    """ticket_system APIにログインしてセッションを取得"""
    session = requests.Session()
    
    response = session.post(
        f"{TICKET_API_URL}/api/ext/v1/auth/login",
        json={"username": username, "password": password},
        headers={"Content-Type": "application/json"}
    )
    
    if response.status_code != 200:
        print(f"Ticket API Login failed: {response.status_code}")
        print(response.text)
        return None
    
    print(f"Ticket API Login successful")
    
    # セッションクッキーを表示
    for cookie in session.cookies:
        print(f"  Cookie: {cookie.name}={cookie.value[:20]}...")
    
    return session


def get_user_nfts(cookies: dict) -> list:
    """ユーザーのNFT一覧を取得"""
    session = requests.Session()
    for name, value in cookies.items():
        session.cookies.set(name, value)
    
    response = session.get(f"{BASE_API_URL}/api/v1/user/nfts/info")
    
    if response.status_code != 200:
        print(f"Failed to get NFTs: {response.status_code}")
        print(response.text)
        return []
    
    nfts = response.json()
    print(f"Found {len(nfts)} NFTs")
    return nfts


def get_ticket_image(session: requests.Session, nft_origin: str) -> bytes:
    """チケット画像を取得"""
    response = session.get(
        f"{TICKET_API_URL}/api/ext/v1/ticket/image/{nft_origin}",
        headers={"Accept": "image/png"}
    )
    
    if response.status_code != 200:
        print(f"Failed to get ticket image: {response.status_code}")
        print(response.text)
        return None
    
    print(f"Ticket image retrieved: {len(response.content)} bytes")
    return response.content


def generate_checkin_token(nft_origin: str) -> str:
    """チェックイントークンを生成（サーバー側と同じロジック）"""
    ticket_service = TicketService()
    token = ticket_service.build_checkin_token(nft_origin)
    print(f"Generated checkin token: {token[:50]}...")
    return token


def test_checkin_api(session: requests.Session, token: str) -> dict:
    """チェックインAPIをテスト"""
    # GETリクエスト（QRコードスキャン相当）
    response = session.get(
        f"{TICKET_API_URL}/api/ext/v1/ticket/checkin",
        params={"token": token}
    )
    
    print(f"Checkin API response: {response.status_code}")
    print(response.text)
    
    return response.json() if response.status_code in [200, 400, 401, 404] else {}


def main():
    print("=" * 60)
    print("CheckinAPI Test Script")
    print("=" * 60)
    
    if not TEST_PASSWORD:
        print("ERROR: TEST_PASSWORD environment variable is not set")
        print("Usage: TEST_PASSWORD='your_password' python test_checkin_api.py")
        return
    
    # 1. ベースAPIにログイン
    print("\n[1] Login to Base API")
    base_cookies = login_to_base_api(TEST_USERNAME, TEST_PASSWORD)
    if not base_cookies:
        return
    
    # 2. ユーザーのNFT一覧を取得
    print("\n[2] Get User NFTs")
    nfts = get_user_nfts(base_cookies)
    if not nfts:
        print("No NFTs found for this user")
        return
    
    # 最初のNFTを使用
    test_nft = nfts[0]
    nft_origin = test_nft.get('nft_origin')
    print(f"Using NFT: {nft_origin}")
    print(f"  Name: {test_nft.get('name')}")
    print(f"  Content Type: {test_nft.get('content_type')}")
    
    # 3. ticket_system APIにログイン
    print("\n[3] Login to Ticket API")
    ticket_session = login_to_ticket_api(TEST_USERNAME, TEST_PASSWORD)
    if not ticket_session:
        return
    
    # 4. チケット画像を取得
    print("\n[4] Get Ticket Image")
    image_data = get_ticket_image(ticket_session, nft_origin)
    if image_data:
        # 画像を保存（オプション）
        with open(f"/tmp/ticket_{nft_origin[:10]}.png", "wb") as f:
            f.write(image_data)
        print(f"  Saved to /tmp/ticket_{nft_origin[:10]}.png")
    
    # 5. チェックイントークンを生成
    print("\n[5] Generate Checkin Token")
    token = generate_checkin_token(nft_origin)
    
    # 6. チェックインAPIをテスト
    print("\n[6] Test Checkin API")
    result = test_checkin_api(ticket_session, token)
    
    print("\n" + "=" * 60)
    print("Test Complete")
    print("=" * 60)
    
    if result.get('used'):
        print(f"Result: Checkin {'already done' if result.get('message') == 'Already checked in' else 'successful'}")
        print(f"  used_at: {result.get('used_at')}")
    elif result.get('error'):
        print(f"Result: Error - {result.get('error')}")
    else:
        print(f"Result: {result}")


if __name__ == "__main__":
    main()

