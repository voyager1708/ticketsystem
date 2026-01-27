import requests
import json
import logging
from typing import Optional, Dict, Any
from django.conf import settings

logger = logging.getLogger(__name__)


class BaseAPIClient:
    """
    ベースAPI (betawallet-dev) を呼び出すクライアント
    
    このクラスは、拡張APIからベースAPIのエンドポイントを
    HTTP経由で呼び出すためのラッパーです。
    """
    
    def __init__(self, base_url: str = None):
        """
        Args:
            base_url: ベースAPIのベースURL（例: https://api.example.com）
                     省略時はsettings.BASE_API_URLを使用（.envファイルから読み込み）
        """
        self.base_url = base_url or settings.BASE_API_URL
        if not self.base_url:
            raise ValueError(
                "BASE_API_URL must be set in settings or .env file. "
                "Please add BASE_API_URL=http://localhost:8000 to your .env file."
            )
        self.base_url = self.base_url.rstrip('/')
    
    def _get_headers(self, session_cookies: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """リクエストヘッダーを生成"""
        headers = {'Content-Type': 'application/json'}
        # セッション認証の場合は、クッキーをヘッダーに含める必要はない
        # requests.Session()が自動的にクッキーを管理する
        return headers
    
    def get_nft(
        self, 
        nft_origin: str, 
        session_cookies: Dict[str, str]
    ) -> Optional[Dict[str, Any]]:
        """
        ベースAPIからNFT情報を取得
        
        GET /api/v1/nft/data/{nft_origin}
        
        Args:
            nft_origin: NFTのオリジンID
            session_cookies: セッションクッキーの辞書（例: {'sessionid': '...', 'csrftoken': '...'}）
        
        Returns:
            NFT情報の辞書、またはNone（エラー時）
        """
        # data_format=base64を指定してJSON形式で取得（binaryだと画像データが返される）
        url = f"{self.base_url}/api/v1/nft/data/{nft_origin}?data_format=base64"
        headers = self._get_headers()
        
        # セッションクッキーを設定
        session = requests.Session()
        cookie_domain = self._get_cookie_domain()
        for cookie_name, cookie_value in session_cookies.items():
            if cookie_domain:
                session.cookies.set(cookie_name, cookie_value, domain=cookie_domain)
            else:
                session.cookies.set(cookie_name, cookie_value)
        
        try:
            print(f"get_nft: Requesting {url} with cookies: {list(session_cookies.keys())}", flush=True)
            print(f"get_nft: Cookie values: sessionid={session_cookies.get('sessionid', 'N/A')[:20]}..., csrftoken={session_cookies.get('csrftoken', 'N/A')[:20]}...", flush=True)
            response = session.get(url, headers=headers, timeout=10)
            print(f"get_nft: Response status: {response.status_code}", flush=True)
            print(f"get_nft: Response content-type: {response.headers.get('Content-Type', 'N/A')}", flush=True)
            print(f"get_nft: Response body (first 200 chars): {response.text[:200] if response.text else 'EMPTY'}", flush=True)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            print(f"get_nft: HTTP error {e.response.status_code}: {e.response.text[:200]}", flush=True)
            if e.response.status_code == 404:
                logger.warning(f"NFT not found: {nft_origin}")
            else:
                logger.error(f"HTTP error fetching NFT {nft_origin}: {e}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch NFT {nft_origin}: {e}")
            return None
        except Exception as e:
            print(f"get_nft: Unexpected error: {e}, response text: {response.text[:200] if response else 'No response'}", flush=True)
            logger.error(f"Failed to fetch NFT {nft_origin}: {e}")
            return None
    
    def _get_cookie_domain(self) -> str:
        """クッキーのドメインを取得（設定から、またはデフォルト）"""
        from django.conf import settings
        # 同じドメインの場合はNoneを返す（クッキーが自動的に送信される）
        # 異なるドメインの場合は、設定から取得
        return getattr(settings, 'SESSION_COOKIE_DOMAIN', None)
    
    def get_user_nfts(
        self, 
        session_cookies: Dict[str, str], 
        wallet_type: str = "BSV"
    ) -> list:
        """
        ユーザーのNFT一覧を取得
        
        GET /api/v1/user/nfts/info
        
        Args:
            session_cookies: セッションクッキーの辞書
            wallet_type: ウォレットタイプ（デフォルト: BSV）
        
        Returns:
            NFT一覧のリスト
        """
        url = f"{self.base_url}/api/v1/user/nfts/info"
        headers = self._get_headers()
        
        # セッションクッキーを設定
        session = requests.Session()
        cookie_domain = self._get_cookie_domain()
        for cookie_name, cookie_value in session_cookies.items():
            if cookie_domain:
                session.cookies.set(cookie_name, cookie_value, domain=cookie_domain)
            else:
                session.cookies.set(cookie_name, cookie_value)
        
        try:
            response = session.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            # レスポンスは直接NFTのリスト
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch user NFTs: {e}")
            return []
    
    def get_nft_from_user_list(
        self, 
        nft_origin: str, 
        session_cookies: Dict[str, str]
    ) -> Optional[Dict[str, Any]]:
        """
        ユーザーのNFT一覧から特定のNFTを取得
        
        GetNFTDataAPIViewがcurrent_utxoの条件でフィルタリングするため、
        NFT一覧から取得する方法を使用する。
        
        Args:
            nft_origin: NFTのオリジンID
            session_cookies: セッションクッキーの辞書
        
        Returns:
            NFT情報の辞書、またはNone（見つからない場合）
        """
        nfts = self.get_user_nfts(session_cookies)
        for nft in nfts:
            if nft.get('nft_origin') == nft_origin:
                logger.debug(f"Found NFT {nft_origin} in user's NFT list")
                return nft
        logger.warning(f"NFT {nft_origin} not found in user's NFT list")
        return None
    
    def get_nft_metadata(
        self, 
        nft_origin: str, 
        session_cookies: Dict[str, str]
    ) -> Optional[Dict[str, Any]]:
        """
        NFTのメタデータを取得
        
        GET /api/v1/nft/meta/{nft_origin}
        
        Args:
            nft_origin: NFTのオリジンID
            session_cookies: セッションクッキーの辞書
        
        Returns:
            メタデータの辞書、またはNone（エラー時）
        """
        url = f"{self.base_url}/api/v1/nft/meta/{nft_origin}"
        headers = self._get_headers()
        
        # セッションクッキーを設定
        session = requests.Session()
        cookie_domain = self._get_cookie_domain()
        for cookie_name, cookie_value in session_cookies.items():
            if cookie_domain:
                session.cookies.set(cookie_name, cookie_value, domain=cookie_domain)
            else:
                session.cookies.set(cookie_name, cookie_value)
        
        try:
            print(f"get_nft_metadata: GET {url}", flush=True)
            response = session.get(url, headers=headers, timeout=10)
            print(f"get_nft_metadata: Response status={response.status_code}", flush=True)
            response.raise_for_status()
            data = response.json()
            print(f"get_nft_metadata: Response data keys={list(data.keys()) if isinstance(data, dict) else 'not dict'}", flush=True)
            if data.get('status') == 'success':
                return data.get('metadata', {})
            return None
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.warning(f"NFT metadata not found: {nft_origin}")
            else:
                logger.error(f"HTTP error fetching NFT metadata {nft_origin}: {e}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch NFT metadata {nft_origin}: {e}")
            return None
    
    def update_nft_metadata(
        self, 
        nft_origin: str, 
        metadata_updates: Dict, 
        session_cookies: Dict[str, str]
    ) -> bool:
        """
        NFTのメタデータを更新（チェックイン状態など）
        
        PATCH /api/v1/nft/meta/{nft_origin}
        
        Args:
            nft_origin: NFTのオリジンID
            metadata_updates: 更新するメタデータの辞書（{"metadata": {...}}形式）
            session_cookies: セッションクッキーの辞書
        
        Returns:
            更新成功時True、失敗時False
        """
        url = f"{self.base_url}/api/v1/nft/meta/{nft_origin}"
        headers = self._get_headers()
        
        # セッションクッキーを設定
        session = requests.Session()
        cookie_domain = self._get_cookie_domain()
        for cookie_name, cookie_value in session_cookies.items():
            if cookie_domain:
                session.cookies.set(cookie_name, cookie_value, domain=cookie_domain)
            else:
                session.cookies.set(cookie_name, cookie_value)
        
        # CSRFトークンが必要な場合は、ヘッダーに追加
        if 'csrftoken' in session_cookies:
            headers['X-CSRFToken'] = session_cookies['csrftoken']
        
        # Refererヘッダーを追加（CSRF対策のため必要）
        headers['Referer'] = self.base_url + '/'
        
        # リクエストボディは {"metadata": {...}} 形式
        request_body = {"metadata": metadata_updates}
        
        try:
            print(f"update_nft_metadata: PATCH {url}", flush=True)
            print(f"update_nft_metadata: body={request_body}", flush=True)
            response = session.patch(
                url, 
                json=request_body, 
                headers=headers, 
                timeout=10
            )
            print(f"update_nft_metadata: Response status={response.status_code}", flush=True)
            print(f"update_nft_metadata: Response body={response.text[:200] if response.text else 'EMPTY'}", flush=True)
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to update NFT metadata {nft_origin}: {e}")
            return False
    
    def create_reward_nft(
        self,
        image_file: bytes,
        image_filename: str,
        metadata: Dict,
        recipient_paymail: str,
        session_cookies: Dict[str, str]
    ) -> Optional[Dict[str, Any]]:
        """
        報酬NFTを作成（チェックイン報酬用）
        
        POST /api/v1/nft/create
        
        Args:
            image_file: 画像ファイルのバイトデータ
            image_filename: 画像ファイル名
            metadata: NFTメタデータ
            recipient_paymail: 受領者のpaymail
            session_cookies: セッションクッキーの辞書
        
        Returns:
            作成されたNFT情報の辞書、またはNone（エラー時）
        """
        url = f"{self.base_url}/api/v1/nft/create"
        headers = {}
        
        # セッションクッキーを設定
        session = requests.Session()
        cookie_domain = self._get_cookie_domain()
        for cookie_name, cookie_value in session_cookies.items():
            if cookie_domain:
                session.cookies.set(cookie_name, cookie_value, domain=cookie_domain)
            else:
                session.cookies.set(cookie_name, cookie_value)
        
        # CSRFトークンが必要な場合は、ヘッダーに追加
        if 'csrftoken' in session_cookies:
            headers['X-CSRFToken'] = session_cookies['csrftoken']
        
        # Refererヘッダーを追加（CSRF対策のため必要・チケットNFT作成と同様）
        headers['Referer'] = self.base_url + '/'
        
        files = {
            'file': (image_filename, image_file, 'image/png')
        }
        data = {
            'app': 'Ticket System',
            'name': 'Check-in Reward',
            'additional_info': json.dumps(metadata),
            'recipient_paymail': recipient_paymail
        }
        
        try:
            response = session.post(
                url, 
                files=files, 
                data=data, 
                headers=headers, 
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(
                "Failed to create reward NFT: %s | status=%s | body=%s",
                e,
                getattr(e.response, "status_code", None) if hasattr(e, "response") else None,
                (e.response.text[:500] if hasattr(e, "response") and e.response is not None and e.response.text else None),
            )
            return None
    
    def get_nft_admin(self, nft_origin: str) -> Optional[Dict[str, Any]]:
        """
        管理者用エンドポイントからNFT情報を取得（認証不要）
        
        GET /api/v1/admin/nft/data/{nft_origin}
        
        Args:
            nft_origin: NFTのオリジンID
        
        Returns:
            NFT情報の辞書、またはNone（エラー時）
        """
        url = f"{self.base_url}/api/v1/admin/nft/data/{nft_origin}"
        headers = self._get_headers()
        
        try:
            logger.info(f"get_nft_admin: GET {url}")
            response = requests.get(url, headers=headers, timeout=10)
            logger.info(f"get_nft_admin: Response status={response.status_code}")
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.warning(f"NFT not found (admin): {nft_origin}")
            else:
                logger.error(f"HTTP error fetching NFT (admin) {nft_origin}: {e}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch NFT (admin) {nft_origin}: {e}")
            return None

    def get_user_info(self, session_cookies: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """
        セッションからユーザー情報を取得
        
        GET /api/v1/user/info
        
        Args:
            session_cookies: セッションクッキーの辞書
        
        Returns:
            ユーザー情報の辞書、またはNone（エラー時）
        """
        url = f"{self.base_url}/api/v1/user/info"
        headers = self._get_headers()
        
        # セッションクッキーを設定
        session = requests.Session()
        cookie_domain = self._get_cookie_domain()
        for cookie_name, cookie_value in session_cookies.items():
            if cookie_domain:
                session.cookies.set(cookie_name, cookie_value, domain=cookie_domain)
            else:
                session.cookies.set(cookie_name, cookie_value)
        
        try:
            response = session.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get user info: {e}")
            return None
    
    def create_ticket_nft(
        self,
        image_file: bytes,
        image_filename: str,
        nft_name: str,
        metadata: Dict,
        session_cookies: Dict[str, str],
        recipient_paymail: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        チケットNFTを作成
        
        POST /api/v1/nft/create
        
        Args:
            image_file: チケット画像のバイトデータ
            image_filename: 画像ファイル名
            nft_name: NFT名（例: "Summer Festival 2026 Ticket"）
            metadata: NFTメタデータ（additional_infoに格納）
            session_cookies: セッションクッキーの辞書
            recipient_paymail: 受領者のpaymail（省略時は自分）
        
        Returns:
            作成されたNFT情報の辞書、またはNone（エラー時）
            
            成功時のレスポンス例:
            {
                "message": "Successfully created NFT",
                "transaction_id": "abc123...",
                "transaction_hex": "...",
                "nft_information": {
                    "nft_id": 123,
                    "nft_origin": "abc123..._0",
                    ...
                }
            }
        """
        url = f"{self.base_url}/api/v1/nft/create"
        headers = {}
        
        # セッションクッキーを設定
        session = requests.Session()
        cookie_domain = self._get_cookie_domain()
        for cookie_name, cookie_value in session_cookies.items():
            if cookie_domain:
                session.cookies.set(cookie_name, cookie_value, domain=cookie_domain)
            else:
                session.cookies.set(cookie_name, cookie_value)
        
        # CSRFトークンが必要な場合は、ヘッダーに追加
        if 'csrftoken' in session_cookies:
            headers['X-CSRFToken'] = session_cookies['csrftoken']
        
        # Refererヘッダーを追加（CSRF対策のため必要）
        headers['Referer'] = self.base_url + '/'
        
        files = {
            'file': (image_filename, image_file, 'image/png')
        }
        data = {
            'app': 'Ticket System',
            'name': nft_name,
            'additional_info': json.dumps(metadata),
        }
        
        # 受領者が指定されている場合は追加
        if recipient_paymail:
            data['recipient_paymail'] = recipient_paymail
        
        try:
            logger.info(f"Creating ticket NFT: name={nft_name}, recipient={recipient_paymail}")
            print(f"create_ticket_nft: POST {url}", flush=True)
            print(f"create_ticket_nft: data={data}", flush=True)
            
            response = session.post(
                url, 
                files=files, 
                data=data, 
                headers=headers, 
                timeout=60  # NFT作成は時間がかかる場合がある
            )
            
            print(f"create_ticket_nft: Response status={response.status_code}", flush=True)
            print(f"create_ticket_nft: Response body (first 500 chars)={response.text[:500] if response.text else 'EMPTY'}", flush=True)
            
            response.raise_for_status()
            result = response.json()
            logger.info(f"Ticket NFT created successfully: nft_origin={result.get('nft_information', {}).get('nft_origin')}")
            return result
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error creating ticket NFT: {e.response.status_code} - {e.response.text[:200]}")
            print(f"create_ticket_nft: HTTP error {e.response.status_code}: {e.response.text[:500]}", flush=True)
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to create ticket NFT: {e}")
            return None

