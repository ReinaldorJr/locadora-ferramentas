from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from datetime import date
from decimal import Decimal 
from django.core.exceptions import ValidationError



class Ferramenta(models.Model):
    nome = models.CharField(max_length=200)
    descricao = models.TextField(blank=True)
    categoria = models.CharField(max_length=100)
    valor_diaria = models.DecimalField(max_digits=8, decimal_places=2)
    valor_semanal = models.DecimalField(max_digits=8, decimal_places=2)
    valor_mensal = models.DecimalField(max_digits=8, decimal_places=2)
    quantidade_total = models.PositiveIntegerField(default=1)
    quantidade_disponivel = models.PositiveIntegerField(default=1)
    ativa = models.BooleanField(default=True)

    def __str__(self):
        return self.nome


class Cliente(models.Model):
    nome = models.CharField(max_length=200)
    cpf_cnpj = models.CharField(max_length=20, unique=True)
    telefone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    endereco = models.TextField(blank=True)
    ativo = models.BooleanField(default=True)

    def __str__(self):
        return self.nome
    
    
class Locacao(models.Model):
    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.PROTECT,
        related_name='locacoes'
    )

    ferramenta = models.ForeignKey(
        Ferramenta,
        on_delete=models.PROTECT,
        related_name='locacoes'
    )

    data_inicio = models.DateField(default=timezone.now)
    data_fim = models.DateField()

    valor_total = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        editable=False  
    )

    devolvida = models.BooleanField(default=False)
    criado_em = models.DateTimeField(auto_now_add=True)
def save(self, *args, **kwargs):
    criando = self.pk is None

    dias = (self.data_fim - self.data_inicio).days
    if dias <= 0:
        dias = 1

    mudou_mes = (
        self.data_inicio.year != self.data_fim.year or
        self.data_inicio.month != self.data_fim.month
    )

    if dias <= 7:
        self.valor_total = dias * self.ferramenta.valor_diaria
    elif mudou_mes:
        self.valor_total = self.ferramenta.valor_mensal
    else:
        self.valor_total = dias * self.ferramenta.valor_diaria

    if criando:
        if self.ferramenta.quantidade_disponivel <= 0:
            raise ValidationError("Ferramenta sem estoque disponível")

        self.ferramenta.quantidade_disponivel -= 1
        self.ferramenta.save()

    if not criando and self.devolvida:
        locacao_antiga = Locacao.objects.get(pk=self.pk)
        if not locacao_antiga.devolvida:
            self.ferramenta.quantidade_disponivel += 1
            self.ferramenta.save()

    super().save(*args, **kwargs)




