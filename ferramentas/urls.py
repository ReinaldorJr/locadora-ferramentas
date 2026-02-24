from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),

    # Clientes
    path('clientes/', views.listar_clientes, name='listar_clientes'),
    path('clientes/novo/', views.cadastrar_cliente, name='cadastrar_cliente'),
    path('clientes/<int:cliente_id>/', views.detalhe_cliente, name='detalhe_cliente'),

    # Ferramentas
    path('ferramentas/', views.listar_ferramentas, name='listar_ferramentas'),
    path('ferramentas/nova/', views.cadastrar_ferramenta, name='cadastrar_ferramenta'),

    # Locações (aba)
    path('locacoes/', views.listar_locacoes, name='listar_locacoes'),
    path('locacoes/nova/', views.nova_locacao, name='nova_locacao'),
    path('locacoes/devolver/<int:locacao_id>/', views.devolver_locacao, name='devolver_locacao'),

    # Relatórios
    path('relatorios/atrasos/', views.relatorio_atrasos, name='relatorio_atrasos'),

    # Financeiro
    path('financeiro/contas/', views.financeiro_contas, name='financeiro_contas'),
    path('financeiro/contas/<int:conta_id>/', views.financeiro_conta_detalhe, name='financeiro_conta_detalhe'),
    path('financeiro/contas/<int:conta_id>/pagar/', views.financeiro_registrar_pagamento, name='financeiro_registrar_pagamento'),
]