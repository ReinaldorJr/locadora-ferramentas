from django.contrib import admin
from .models import Ferramenta, Cliente, Locacao


@admin.register(Ferramenta)
class FerramentaAdmin(admin.ModelAdmin):
    list_display = (
        'nome',
        'categoria',
        'quantidade_total',
        'quantidade_disponivel',
        'valor_diaria',
        'ativa'
    )
    list_filter = ('categoria', 'ativa')
    search_fields = ('nome',)


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ('nome', 'cpf_cnpj', 'telefone', 'ativo')
    search_fields = ('nome', 'cpf_cnpj')
    list_filter = ('ativo',)


@admin.register(Locacao)
class LocacaoAdmin(admin.ModelAdmin):
    list_display = (
        'cliente',
        'ferramenta',
        'data_inicio',
        'data_fim',
        'valor_total',
        'devolvida'
    )
    list_filter = ('devolvida',)
    autocomplete_fields = ('cliente', 'ferramenta')
