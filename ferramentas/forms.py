from django import forms

from .models import Cliente, Ferramenta, Locacao


class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ["nome", "cpf_cnpj", "telefone", "email", "endereco"]


class FerramentaForm(forms.ModelForm):
    class Meta:
        model = Ferramenta
        fields = [
            "nome",
            "descricao",
            "categoria",
            "valor_diaria",
            "valor_semanal",
            "valor_mensal",
            "quantidade_total",
        ]


class LocacaoForm(forms.ModelForm):
    class Meta:
        model = Locacao
        fields = ["cliente", "ferramenta", "data_inicio", "data_fim"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # So ferramentas ativas com estoque.
        self.fields["ferramenta"].queryset = Ferramenta.objects.filter(
            quantidade_disponivel__gt=0,
            ativa=True,
        )
