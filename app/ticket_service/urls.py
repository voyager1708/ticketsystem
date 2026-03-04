from django.urls import path
from ticket_service.views import (
    AccountCreateAPIView,
    AuthLoginProxyAPIView,
    AuthLogoutProxyAPIView,
    AuthSignUpProxyAPIView,
    AuthUserProxyAPIView,
)

urlpatterns = [
    path(
        'accounts/create',
        AccountCreateAPIView.as_view(),
        name='account-create',
    ),
    path(
        'ext/v1/auth/sign-up',
        AuthSignUpProxyAPIView.as_view(),
        name='ext-auth-sign-up'
    ),
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

