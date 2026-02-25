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
    """
    Locação de uma ferramenta por um cliente.

    - Ao criar: baixa estoque (quantidade_disponivel - 1)
    - Ao marcar devolvida=True: devolve estoque (quantidade_disponivel + 1)
    - Ao criar: gera automaticamente ContaReceber
    """
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name='locacoes')
    ferramenta = models.ForeignKey(Ferramenta, on_delete=models.PROTECT, related_name='locacoes')

    data_inicio = models.DateField(default=timezone.now)
    data_fim = models.DateField()

    valor_total = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)

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

        # calcula sempre
        self.valor_total = self._calcular_valor_total()

        # estoque
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

        # cria conta a receber na criação
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
    """
    Conta a receber 1:1 com a Locacao.
    Status é atualizado automaticamente quando pagamentos são registrados.
    """
    class Status(models.TextChoices):
        PENDENTE = "PENDENTE", "Pendente"
        PARCIAL = "PARCIAL", "Parcial"
        PAGO = "PAGO", "Pago"
        CANCELADO = "CANCELADO", "Cancelado"

    locacao = models.OneToOneField(Locacao, on_delete=models.PROTECT, related_name='conta_receber')
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name='contas_receber')

    valor = models.DecimalField(max_digits=10, decimal_places=2)
    vencimento = models.DateField()

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDENTE)

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    def total_pago(self):
        return self.pagamentos.aggregate(total=Sum('valor'))['total'] or 0

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


# -------------------------------
# CAIXA DO DIA
# -------------------------------

class CaixaDia(models.Model):
    """
    Caixa do dia (1 por data).
    - ABERTO: aceita lançamentos
    - FECHADO: não aceita lançamentos (regra aplicada nas views)
    """
    class Status(models.TextChoices):
        ABERTO = "ABERTO", "Aberto"
        FECHADO = "FECHADO", "Fechado"

    data = models.DateField(default=timezone.localdate, unique=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ABERTO)

    saldo_inicial = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    saldo_final = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    aberto_em = models.DateTimeField(auto_now_add=True)
    fechado_em = models.DateTimeField(null=True, blank=True)

    usuario_abertura = models.ForeignKey(
        'auth.User', null=True, blank=True,
        related_name='caixas_abertos', on_delete=models.SET_NULL
    )
    usuario_fechamento = models.ForeignKey(
        'auth.User', null=True, blank=True,
        related_name='caixas_fechados', on_delete=models.SET_NULL
    )

    observacao = models.TextField(blank=True)

    class Meta:
        ordering = ["-data"]

    def __str__(self):
        return f"Caixa {self.data} ({self.status})"

    def total_entradas(self):
        return self.movimentos.filter(tipo=MovimentoCaixa.Tipo.ENTRADA).aggregate(total=Sum('valor'))['total'] or 0

    def total_saidas(self):
        return self.movimentos.filter(tipo=MovimentoCaixa.Tipo.SAIDA).aggregate(total=Sum('valor'))['total'] or 0

    def saldo_calculado(self):
        return (self.saldo_inicial or 0) + self.total_entradas() - self.total_saidas()


class MovimentoCaixa(models.Model):
    """
    Lançamento no caixa:
    - ENTRADA ou SAIDA
    - categoria (pagamento, despesa, etc)
    - forma (dinheiro/pix/cartão...)
    - referencia: usado pra evitar duplicidade (ex: PG10)
    """
    class Tipo(models.TextChoices):
        ENTRADA = "ENTRADA", "Entrada"
        SAIDA = "SAIDA", "Saída"

    class Categoria(models.TextChoices):
        ALUGUEL = "ALUGUEL", "Aluguel"
        PAGAMENTO = "PAGAMENTO", "Pagamento"
        DESPESA = "DESPESA", "Despesa"
        SANGRIA = "SANGRIA", "Sangria"
        REFORCO = "REFORCO", "Reforço"
        AJUSTE = "AJUSTE", "Ajuste"

    class Forma(models.TextChoices):
        DINHEIRO = "DINHEIRO", "Dinheiro"
        PIX = "PIX", "Pix"
        CARTAO = "CARTAO", "Cartão"
        TRANSFERENCIA = "TRANSFERENCIA", "Transferência"
        OUTRO = "OUTRO", "Outro"

    caixa = models.ForeignKey(CaixaDia, related_name='movimentos', on_delete=models.CASCADE)

    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    categoria = models.CharField(max_length=20, choices=Categoria.choices)
    forma = models.CharField(max_length=20, choices=Forma.choices, default=Forma.DINHEIRO)

    valor = models.DecimalField(max_digits=12, decimal_places=2)
    descricao = models.CharField(max_length=255, blank=True)

    # Ex.: PG12 = pagamento 12 (isso evita duplicidade)
    referencia = models.CharField(max_length=50, blank=True)

    criado_em = models.DateTimeField(auto_now_add=True)

    usuario = models.ForeignKey('auth.User', null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-criado_em"]

    def __str__(self):
        return f"{self.tipo} {self.valor} ({self.categoria})"


class Pagamento(models.Model):
    """
    Pagamento em cima de uma ContaReceber.

    Regras:
    - valida valor > 0
    - salva o pagamento
    - atualiza o status da ContaReceber automaticamente
    - se existir Caixa do Dia ABERTO, cria automaticamente uma ENTRADA no caixa
      com referencia PG{id_do_pagamento} (não duplica)
    """
    class Forma(models.TextChoices):
        DINHEIRO = "DINHEIRO", "Dinheiro"
        PIX = "PIX", "PIX"
        CARTAO_CREDITO = "CARTAO_CREDITO", "Cartão de Crédito"
        CARTAO_DEBITO = "CARTAO_DEBITO", "Cartão de Débito"
        BOLETO = "BOLETO", "Boleto"
        TRANSFERENCIA = "TRANSFERENCIA", "Transferência"

    conta = models.ForeignKey(ContaReceber, on_delete=models.PROTECT, related_name='pagamentos')

    data_pagamento = models.DateTimeField(default=timezone.now)
    valor = models.DecimalField(max_digits=10, decimal_places=2)

    forma = models.CharField(max_length=30, choices=Forma.choices, default=Forma.PIX)

    observacao = models.CharField(max_length=255, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.valor is None or self.valor <= 0:
            raise ValidationError("O valor do pagamento deve ser maior que zero.")

    def _mapear_forma_para_caixa(self):
        """
        Converte a forma do Pagamento para uma forma do MovimentoCaixa.
        """
        mapa = {
            self.Forma.DINHEIRO: MovimentoCaixa.Forma.DINHEIRO,
            self.Forma.PIX: MovimentoCaixa.Forma.PIX,
            self.Forma.TRANSFERENCIA: MovimentoCaixa.Forma.TRANSFERENCIA,
            self.Forma.CARTAO_CREDITO: MovimentoCaixa.Forma.CARTAO,
            self.Forma.CARTAO_DEBITO: MovimentoCaixa.Forma.CARTAO,
            self.Forma.BOLETO: MovimentoCaixa.Forma.OUTRO,
        }
        return mapa.get(self.forma, MovimentoCaixa.Forma.OUTRO)

    def save(self, *args, **kwargs):
        """
        Esse save é o “coração” da integração Pagamento -> Caixa.

        Importante:
        - A view (views.py) vai colocar: pagamento._usuario = request.user
          antes de salvar. Aqui nós usamos isso.
        """
        self.clean()
        criando = self.pk is None

        super().save(*args, **kwargs)

        # Atualiza status da conta sempre que existir pagamento novo/alterado
        self.conta.atualizar_status(salvar=True)

        # Só lança no caixa na criação do pagamento (pra não duplicar em edição)
        if not criando:
            return

        hoje = timezone.localdate()

        # Precisa existir caixa ABERTO no dia
        caixa_aberto = CaixaDia.objects.filter(data=hoje, status=CaixaDia.Status.ABERTO).first()
        if not caixa_aberto:
            return

        # Referência única do lançamento no caixa para esse pagamento
        referencia = f"PG{self.id}"

        # Se já existir movimento com essa referência, não cria de novo (anti-duplicidade)
        if MovimentoCaixa.objects.filter(caixa=caixa_aberto, referencia=referencia).exists():
            return

        # Quem recebeu (se a view passou)
        usuario = getattr(self, "_usuario", None)

        cliente = self.conta.cliente
        locacao = self.conta.locacao
        ferramenta = locacao.ferramenta if locacao else None

        descricao_padrao = f"Recebimento Pagamento #{self.id} (Conta #{self.conta.id})"
        if cliente:
            descricao_padrao += f" - {cliente.nome}"
        if ferramenta:
            descricao_padrao += f" - {ferramenta.nome}"

        MovimentoCaixa.objects.create(
            caixa=caixa_aberto,
            tipo=MovimentoCaixa.Tipo.ENTRADA,
            categoria=MovimentoCaixa.Categoria.PAGAMENTO,
            forma=self._mapear_forma_para_caixa(),
            valor=self.valor,
            descricao=(self.observacao.strip() if self.observacao.strip() else descricao_padrao),
            referencia=referencia,
            usuario=usuario
        )

    def __str__(self):
        return f"Pagamento #{self.id} - {self.conta} - R$ {self.valor}"