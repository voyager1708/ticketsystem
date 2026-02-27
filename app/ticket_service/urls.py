from django.urls import path
from ticket_service.views import (
    AuthLoginProxyAPIView,
    AuthLogoutProxyAPIView,
    AuthUserProxyAPIView,
)

urlpatterns = [
    path(
        'ext/v1/auth/login',
        AuthLoginProxyAPIView.as_view(),
        name='ext-auth-login'
    ),
    path(
        'ext/v1/auth/logout',
        AuthLogoutProxyAPIView.as_view(),
        name='ext-auth-logout'
    ),
    path(
        'ext/v1/auth/user',
        AuthUserProxyAPIView.as_view(),
        name='ext-auth-user'
    ),
]

