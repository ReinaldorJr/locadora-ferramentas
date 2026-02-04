from django import forms
from .models import Locacao, Ferramenta

class LocacaoForm(forms.ModelForm):
    class Meta:
        model = Locacao
        fields = ['cliente', 'ferramenta', 'data_inicio', 'data_fim']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Só ferramentas com estoque
        self.fields['ferramenta'].queryset = Ferramenta.objects.filter(
            quantidade_disponivel__gt=0,
            ativa=True
        )
