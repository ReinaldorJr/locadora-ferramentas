from django.contrib import admin
from .models import Ferramenta, Cliente, Locacao
from django.core.exceptions import ValidationError



@admin.register(Ferramenta)
class FerramentaAdmin(admin.ModelAdmin):
    list_display = (
        'nome',
        'categoria',
        'valor_diaria',
        'valor_semanal',
        'valor_mensal',
        'quantidade_disponivel',
        'ativa'
    )
    list_filter = ('categoria', 'ativa')
    search_fields = ('nome',)

@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = (
        'nome',
        'cpf_cnpj',
        'telefone',
        'email',
        'ativo',
    )
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
        'devolvida',
    )
    def save_model(self, request, obj, form, change):
        if obj.data_fim < obj.data_inicio:
          raise ValidationError("A data final não pode ser menor que a data inicial.")
        
        super().save_model(request, obj, form, change)

    list_filter = ('devolvida',)
    search_fields = ('cliente__nome', 'ferramenta__nome')