from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('clientes/novo/', views.cadastrar_cliente, name='cadastrar_cliente'),
    path('ferramentas/nova/', views.cadastrar_ferramenta, name='cadastrar_ferramenta'),
    path('locacoes/nova/', views.nova_locacao, name='nova_locacao'),
]
