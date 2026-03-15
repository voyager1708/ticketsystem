"""
REST Framework 用のカスタム例外ハンドラと、403→401 正規化ミドルウェア。

未認証（認証情報なし）時に DRF やミドルウェアが 403 を返す場合があるため、
「Authentication credentials were not provided」の 403 を 401 に統一する。
"""
from rest_framework.views import exception_handler as drf_exception_handler

_UNAUTH_MSG = "Authentication credentials were not provided"


def exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is None:
        return None
    if response.status_code == 403:
        detail = getattr(response, "data", None) or {}
        if isinstance(detail, dict) and "detail" in detail:
            msg = str(detail.get("detail", ""))
            if _UNAUTH_MSG in msg:
                response.status_code = 401
    return response


class NormalizeUnauthorizedMiddleware:
    """
    レスポンスが 403 かつ body に「Authentication credentials were not provided」を
    含む場合、ステータスを 401 に変更する。REST の慣習（認証なし＝401）に合わせる。
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if response.status_code == 403 and getattr(response, "content", b""):
            try:
                body = response.content.decode("utf-8", errors="replace")
                if _UNAUTH_MSG in body:
                    response.status_code = 401
            except Exception:
                pass
        return response
