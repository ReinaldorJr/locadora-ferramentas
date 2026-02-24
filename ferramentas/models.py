from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.models import Sum


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
        blank=True,
        null=True
    )

    devolvida = models.BooleanField(default=False)
    criado_em = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.data_fim < self.data_inicio:
            raise ValidationError("A data final não pode ser menor que a inicial.")

    def _calcular_valor_total(self):
        dias = (self.data_fim - self.data_inicio).days
        if dias <= 0:
            dias = 1

        if dias <= 7:
            return dias * self.ferramenta.valor_diaria
        elif dias <= 30:
            return self.ferramenta.valor_mensal
        else:
            meses = max(1, dias // 30)
            return meses * self.ferramenta.valor_mensal

    def save(self, *args, **kwargs):
        self.clean()

        criando = self.pk is None

        # calcula valor total sempre que salva
        self.valor_total = self._calcular_valor_total()

        # controle de estoque
        if criando:
            if self.ferramenta.quantidade_disponivel <= 0:
                raise ValidationError("Ferramenta sem estoque disponível.")
            self.ferramenta.quantidade_disponivel -= 1
            self.ferramenta.save()
        else:
            locacao_antiga = Locacao.objects.get(pk=self.pk)
            if not locacao_antiga.devolvida and self.devolvida:
                self.ferramenta.quantidade_disponivel += 1
                self.ferramenta.save()

        super().save(*args, **kwargs)

        # FINANCEIRO: cria Conta a Receber automaticamente ao criar a locação
        if criando:
            ContaReceber.objects.create(
                locacao=self,
                cliente=self.cliente,
                valor=self.valor_total,
                vencimento=self.data_fim,
                status=ContaReceber.Status.PENDENTE
            )

    def __str__(self):
        return f"{self.cliente} - {self.ferramenta}"


class ContaReceber(models.Model):
    class Status(models.TextChoices):
        PENDENTE = "PENDENTE", "Pendente"
        PARCIAL = "PARCIAL", "Parcial"
        PAGO = "PAGO", "Pago"
        CANCELADO = "CANCELADO", "Cancelado"

    locacao = models.OneToOneField(
        Locacao,
        on_delete=models.PROTECT,
        related_name='conta_receber'
    )

    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.PROTECT,
        related_name='contas_receber'
    )

    valor = models.DecimalField(max_digits=10, decimal_places=2)
    vencimento = models.DateField()

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDENTE
    )

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    def total_pago(self):
        total = self.pagamentos.aggregate(total=Sum('valor'))['total'] or 0
        return total

    def saldo(self):
        return (self.valor or 0) - self.total_pago()

    def atualizar_status(self, salvar=True):
        if self.status == self.Status.CANCELADO:
            return

        pago = self.total_pago()
        valor = self.valor or 0

        if pago <= 0:
            novo = self.Status.PENDENTE
        elif pago < valor:
            novo = self.Status.PARCIAL
        else:
            novo = self.Status.PAGO

        if novo != self.status:
            self.status = novo
            if salvar:
                self.save(update_fields=['status', 'atualizado_em'])

    def __str__(self):
        return f"ContaReceber #{self.id} - {self.cliente} - {self.get_status_display()}"


class Pagamento(models.Model):
    class Forma(models.TextChoices):
        DINHEIRO = "DINHEIRO", "Dinheiro"
        PIX = "PIX", "PIX"
        CARTAO_CREDITO = "CARTAO_CREDITO", "Cartão de Crédito"
        CARTAO_DEBITO = "CARTAO_DEBITO", "Cartão de Débito"
        BOLETO = "BOLETO", "Boleto"
        TRANSFERENCIA = "TRANSFERENCIA", "Transferência"

    conta = models.ForeignKey(
        ContaReceber,
        on_delete=models.PROTECT,
        related_name='pagamentos'
    )

    data_pagamento = models.DateTimeField(default=timezone.now)
    valor = models.DecimalField(max_digits=10, decimal_places=2)

    forma = models.CharField(
        max_length=30,
        choices=Forma.choices,
        default=Forma.PIX
    )

    observacao = models.CharField(max_length=255, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.valor is None or self.valor <= 0:
            raise ValidationError("O valor do pagamento deve ser maior que zero.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)
        self.conta.atualizar_status(salvar=True)

    def __str__(self):
        return f"Pagamento #{self.id} - {self.conta} - R$ {self.valor}"