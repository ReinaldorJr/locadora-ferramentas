from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),

    # Clientes
    path('clientes/novo/', views.cadastrar_cliente, name='cadastrar_cliente'),
    path('clientes/', views.listar_clientes, name='listar_clientes'),
    path('clientes/<int:cliente_id>/', views.detalhe_cliente, name='detalhe_cliente'),
    path('clientes/<int:cliente_id>/editar/', views.editar_cliente, name='editar_cliente'),
    path('clientes/<int:cliente_id>/toggle/', views.toggle_cliente, name='toggle_cliente'),

    # Ferramentas
    path('ferramentas/nova/', views.cadastrar_ferramenta, name='cadastrar_ferramenta'),
    path('ferramentas/', views.listar_ferramentas, name='listar_ferramentas'),
    path('ferramentas/<int:ferramenta_id>/editar/', views.editar_ferramenta, name='editar_ferramenta'),
    path('ferramentas/<int:ferramenta_id>/toggle/', views.toggle_ferramenta, name='toggle_ferramenta'),

    # Locações
    path('locacoes/nova/', views.nova_locacao, name='nova_locacao'),
    path('locacoes/devolver/<int:locacao_id>/', views.devolver_locacao, name='devolver_locacao'),

    # Relatórios
    path('relatorios/atrasos/', views.relatorio_atrasos, name='relatorio_atrasos'),
]