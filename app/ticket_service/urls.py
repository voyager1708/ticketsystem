from django.urls import path
from ticket_service.views import (
    TicketImageAPIView,
    TicketCheckinAPIView,
    TicketCreateAPIView,
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
    path(
        'ext/v1/ticket/create',
        TicketCreateAPIView.as_view(),
        name='ext-ticket-create'
    ),
    path(
        'ext/v1/ticket/image/<str:nft_origin>', 
        TicketImageAPIView.as_view(), 
        name='ext-ticket-image'
    ),
    path(
        'ext/v1/ticket/checkin', 
        TicketCheckinAPIView.as_view(), 
        name='ext-ticket-checkin'
    ),
]

