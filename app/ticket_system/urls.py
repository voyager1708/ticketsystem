"""
URL configuration for ticket_system project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.http import HttpResponse
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView
from drf_yasg import openapi
from drf_yasg.views import get_schema_view
from rest_framework import permissions
from ticket_service.views import CustomLoginView, LogoutRedirectView

def healthz(request):
    """Step 0: ヘルスチェック用。200 を返す。"""
    return HttpResponse(status=200)


urlpatterns = [
    path('admin/', admin.site.urls),
    path('healthz', healthz),
    path('', RedirectView.as_view(url='/swagger/', permanent=False), name='root-redirect'),
    path('api/', include('ticket_service.urls')),
    # Custom login/logout placed BEFORE contrib auth include
    path('accounts/login/', CustomLoginView.as_view(), name='login'),
    path('accounts/logout/', LogoutRedirectView.as_view(), name='logout'),
    # Django authentication (login/logout/password management)
    path('accounts/', include('django.contrib.auth.urls')),
]

schema_view = get_schema_view(
    openapi.Info(
        title="Ticket Extension API",
        default_version='v1',
        description="API for ticket image generation and check-in.",
        terms_of_service="https://www.google.com/policies/terms/",
        contact=openapi.Contact(name="Support"),
    ),
    public=True,
    permission_classes=[permissions.AllowAny],
    url="https://ticket.buxbit.net",
)

urlpatterns += [
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    path('swagger.json', schema_view.without_ui(cache_timeout=0), name='schema-json'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
