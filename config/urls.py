from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),

    # Rotas do app ferramentas
    path('', include('ferramentas.urls')),

    # Auth
    path('accounts/', include('django.contrib.auth.urls')),
]