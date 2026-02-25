from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Sum, Q
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import (
    Cliente, Ferramenta, Locacao, ContaReceber, Pagamento,
    CaixaDia, MovimentoCaixa
)


# ------------------------------------------------------------
# CONTROLE DE PERFIL (GRUPOS)
# ------------------------------------------------------------

def is_admin(user):
    """Admin = superuser OU grupo Admin"""
    return user.is_authenticated and (user.is_superuser or user.groups.filter(name='Admin').exists())


def is_operador(user):
    """Operador = grupo Operador"""
    return user.is_authenticated and user.groups.filter(name='Operador').exists()


def require_admin(view_func):
    """Decorator: só Admin pode acessar"""
    def _wrapped(request, *args, **kwargs):
        if not is_admin(request.user):
            messages.error(request, "Acesso negado: apenas Admin pode acessar essa página.")
            return redirect('home')
        return view_func(request, *args, **kwargs)
    return _wrapped


def require_admin_or_operador(view_func):
    """Decorator: Admin ou Operador pode acessar"""
    def _wrapped(request, *args, **kwargs):
        if not (is_admin(request.user) or is_operador(request.user)):
            messages.error(request, "Acesso negado: usuário sem perfil. Peça ao Admin para ajustar seu acesso.")
            return redirect('login')
        return view_func(request, *args, **kwargs)
    return _wrapped


def _menu_context(request):
    """
    Contexto para o menu/topo:
    - total_atrasadas: locações em atraso (não devolvidas e vencidas)
    - contas_em_aberto: contas pendentes ou parciais
    """
    hoje = datetime.today().date()
    total_atrasadas = Locacao.objects.filter(devolvida=False, data_fim__lt=hoje).count()
    contas_em_aberto = ContaReceber.objects.filter(
        status__in=[ContaReceber.Status.PENDENTE, ContaReceber.Status.PARCIAL]
    ).count()

    return {
        'total_atrasadas': total_atrasadas,
        'contas_em_aberto': contas_em_aberto,
        'is_admin': is_admin(request.user),
        'is_operador': is_operador(request.user),
    }


# ------------------------------------------------------------
# HOME (DASHBOARD)
# ------------------------------------------------------------

@login_required
@require_admin_or_operador
def home(request):
    """Dashboard: apenas números/resumo."""
    total_ativas = Locacao.objects.filter(devolvida=False).count()
    total_devolvidas = Locacao.objects.filter(devolvida=True).count()
    ferramentas_disponiveis = Ferramenta.objects.filter(quantidade_disponivel__gt=0, ativa=True).count()
    faturamento = Locacao.objects.filter(devolvida=True).aggregate(total=Sum('valor_total'))['total'] or 0

    ctx = {
        'total_ativas': total_ativas,
        'total_devolvidas': total_devolvidas,
        'ferramentas_disponiveis': ferramentas_disponiveis,
        'faturamento': faturamento,
    }
    ctx.update(_menu_context(request))
    return render(request, 'ferramentas/home.html', ctx)


# ------------------------------------------------------------
# CLIENTES
# ------------------------------------------------------------

@login_required
@require_admin
def cadastrar_cliente(request):
    if request.method == 'POST':
        try:
            Cliente.objects.create(
                nome=request.POST.get('nome', '').strip(),
                cpf_cnpj=request.POST.get('cpf_cnpj', '').strip(),
                telefone=request.POST.get('telefone', '').strip(),
                email=(request.POST.get('email') or '').strip(),
                endereco=(request.POST.get('endereco') or '').strip(),
                ativo=True
            )
            messages.success(request, "Cliente cadastrado com sucesso!")
            return redirect('listar_clientes')
        except Exception as e:
            messages.error(request, f"Erro ao cadastrar cliente: {e}")

    ctx = {}
    ctx.update(_menu_context(request))
    return render(request, 'ferramentas/cadastrar_cliente.html', ctx)


@login_required
@require_admin
def listar_clientes(request):
    q = (request.GET.get('q') or '').strip()

    clientes = Cliente.objects.all().order_by('nome')
    if q:
        clientes = clientes.filter(
            Q(nome__icontains=q) |
            Q(cpf_cnpj__icontains=q) |
            Q(telefone__icontains=q) |
            Q(email__icontains=q)
        )

    ctx = {'clientes': clientes, 'q': q}
    ctx.update(_menu_context(request))
    return render(request, 'ferramentas/listar_clientes.html', ctx)


@login_required
@require_admin
def detalhe_cliente(request, cliente_id):
    cliente = get_object_or_404(Cliente, id=cliente_id)
    ctx = {'cliente': cliente}
    ctx.update(_menu_context(request))
    return render(request, 'ferramentas/detalhe_cliente.html', ctx)


@login_required
@require_admin
def editar_cliente(request, cliente_id):
    """Edita cliente (reaproveita cadastrar_cliente.html)."""
    cliente = get_object_or_404(Cliente, id=cliente_id)

    if request.method == 'POST':
        try:
            cliente.nome = request.POST.get('nome', '').strip()
            cliente.cpf_cnpj = request.POST.get('cpf_cnpj', '').strip()
            cliente.telefone = request.POST.get('telefone', '').strip()
            cliente.email = (request.POST.get('email') or '').strip()
            cliente.endereco = (request.POST.get('endereco') or '').strip()
            cliente.save()

            messages.success(request, "Cliente atualizado com sucesso!")
            return redirect('listar_clientes')
        except Exception as e:
            messages.error(request, f"Erro ao atualizar cliente: {e}")

    ctx = {'cliente': cliente}
    ctx.update(_menu_context(request))
    return render(request, 'ferramentas/cadastrar_cliente.html', ctx)


@login_required
@require_admin
@require_POST
def toggle_cliente(request, cliente_id):
    """Ativa/desativa cliente."""
    cliente = get_object_or_404(Cliente, id=cliente_id)
    cliente.ativo = not cliente.ativo
    cliente.save(update_fields=['ativo'])
    return redirect('listar_clientes')


# ------------------------------------------------------------
# FERRAMENTAS
# ------------------------------------------------------------

@login_required
@require_admin
def cadastrar_ferramenta(request):
    if request.method == 'POST':
        try:
            quantidade_total = int(request.POST.get('quantidade_total') or 0)

            Ferramenta.objects.create(
                nome=request.POST.get('nome', '').strip(),
                descricao=(request.POST.get('descricao') or '').strip(),
                categoria=request.POST.get('categoria', '').strip(),
                valor_diaria=request.POST.get('valor_diaria'),
                valor_semanal=request.POST.get('valor_semanal'),
                valor_mensal=request.POST.get('valor_mensal'),
                quantidade_total=quantidade_total,
                quantidade_disponivel=quantidade_total,
                ativa=True
            )
            messages.success(request, "Ferramenta cadastrada com sucesso!")
            return redirect('listar_ferramentas')
        except Exception as e:
            messages.error(request, f"Erro ao cadastrar ferramenta: {e}")

    ctx = {}
    ctx.update(_menu_context(request))
    return render(request, 'ferramentas/cadastrar_ferramenta.html', ctx)


@login_required
@require_admin
def listar_ferramentas(request):
    q = (request.GET.get('q') or '').strip()

    ferramentas = Ferramenta.objects.all().order_by('nome')
    if q:
        ferramentas = ferramentas.filter(
            Q(nome__icontains=q) |
            Q(categoria__icontains=q) |
            Q(descricao__icontains=q)
        )

    ctx = {'ferramentas': ferramentas, 'q': q}
    ctx.update(_menu_context(request))
    return render(request, 'ferramentas/listar_ferramentas.html', ctx)


# ------------------------------------------------------------
# LOCAÇÕES
# ------------------------------------------------------------

@login_required
@require_admin_or_operador
def listar_locacoes(request):
    q = (request.GET.get('q') or '').strip()
    status = (request.GET.get('status') or '').strip()
    financeiro = (request.GET.get('financeiro') or '').strip()

    locacoes = Locacao.objects.select_related('cliente', 'ferramenta').order_by('-criado_em')

    if status == 'ATIVAS':
        locacoes = locacoes.filter(devolvida=False)
    elif status == 'DEVOLVIDAS':
        locacoes = locacoes.filter(devolvida=True)

    if q:
        locacoes = locacoes.filter(
            Q(cliente__nome__icontains=q) |
            Q(cliente__cpf_cnpj__icontains=q) |
            Q(ferramenta__nome__icontains=q)
        )

    # garante ContaReceber para locações antigas
    locacoes_sem_conta = Locacao.objects.filter(conta_receber__isnull=True)
    if locacoes_sem_conta.exists():
        novas = []
        for l in locacoes_sem_conta.select_related('cliente'):
            novas.append(ContaReceber(
                locacao=l,
                cliente=l.cliente,
                valor=l.valor_total or 0,
                vencimento=l.data_fim,
                status=ContaReceber.Status.PENDENTE
            ))
        ContaReceber.objects.bulk_create(novas, ignore_conflicts=True)

    if financeiro:
        locacoes = locacoes.filter(conta_receber__status=financeiro)

    locacoes_lista = list(locacoes)
    ids = [l.id for l in locacoes_lista]

    contas = ContaReceber.objects.filter(locacao_id__in=ids).select_related('locacao', 'cliente')
    conta_por_locacao = {c.locacao_id: c for c in contas}

    linhas = []
    for l in locacoes_lista:
        conta = conta_por_locacao.get(l.id)
        saldo = conta.saldo() if conta else None
        linhas.append({'locacao': l, 'conta': conta, 'saldo': saldo})

    ctx = {
        'linhas': linhas,
        'q': q,
        'status': status,
        'financeiro': financeiro,
        'StatusConta': ContaReceber.Status,
    }
    ctx.update(_menu_context(request))
    return render(request, 'ferramentas/listar_locacoes.html', ctx)


@login_required
@require_admin_or_operador
def nova_locacao(request):
    clientes = Cliente.objects.filter(ativo=True).order_by('nome')
    ferramentas = Ferramenta.objects.filter(ativa=True, quantidade_disponivel__gt=0).order_by('nome')

    if request.method == 'POST':
        try:
            cliente_id = request.POST.get('cliente')
            ferramenta_id = request.POST.get('ferramenta')
            data_inicio_str = request.POST.get('data_inicio')
            data_fim_str = request.POST.get('data_fim')

            data_inicio = datetime.strptime(data_inicio_str, "%Y-%m-%d").date()
            data_fim = datetime.strptime(data_fim_str, "%Y-%m-%d").date()

            Locacao.objects.create(
                cliente_id=cliente_id,
                ferramenta_id=ferramenta_id,
                data_inicio=data_inicio,
                data_fim=data_fim
            )

            messages.success(request, "Locação criada com sucesso!")
            return redirect('listar_locacoes')

        except Exception as e:
            messages.error(request, f"Erro ao criar locação: {e}")

    ctx = {'clientes': clientes, 'ferramentas': ferramentas}
    ctx.update(_menu_context(request))
    return render(request, 'ferramentas/nova_locacao.html', ctx)


@login_required
@require_admin_or_operador
@require_POST
def devolver_locacao(request, locacao_id):
    locacao = get_object_or_404(Locacao, id=locacao_id)

    if locacao.devolvida:
        messages.info(request, "Essa locação já está devolvida.")
        return redirect('listar_locacoes')

    try:
        locacao.devolvida = True
        locacao.save()
        messages.success(request, "Devolução registrada com sucesso!")
    except Exception as e:
        messages.error(request, f"Erro ao devolver locação: {e}")

    return redirect('listar_locacoes')


# ------------------------------------------------------------
# RELATÓRIO DE ATRASOS
# ------------------------------------------------------------

@login_required
@require_admin
def relatorio_atrasos(request):
    hoje = datetime.today().date()
    atrasadas = (
        Locacao.objects
        .select_related('cliente', 'ferramenta')
        .filter(devolvida=False, data_fim__lt=hoje)
        .order_by('data_fim')
    )

    dados = []
    for l in atrasadas:
        dias = (hoje - l.data_fim).days
        dados.append({'locacao': l, 'dias_atraso': dias})

    ctx = {'hoje': hoje, 'dados': dados}
    ctx.update(_menu_context(request))
    return render(request, 'ferramentas/relatorio_atrasos.html', ctx)


# ------------------------------------------------------------
# FINANCEIRO (HUB + CONTAS)
# ------------------------------------------------------------

@login_required
@require_admin_or_operador
def financeiro_home(request):
    pendentes = ContaReceber.objects.filter(status=ContaReceber.Status.PENDENTE).count()
    parciais = ContaReceber.objects.filter(status=ContaReceber.Status.PARCIAL).count()

    total_aberto = ContaReceber.objects.filter(
        status__in=[ContaReceber.Status.PENDENTE, ContaReceber.Status.PARCIAL]
    ).aggregate(total=Sum('valor'))['total'] or 0

    hoje = timezone.localdate()
    caixa = CaixaDia.objects.filter(data=hoje).first()

    caixa_status = None
    saldo_atual = 0
    if caixa and caixa.status == CaixaDia.Status.ABERTO:
        caixa_status = "ABERTO"
        saldo_atual = caixa.saldo_calculado()
    elif caixa and caixa.status == CaixaDia.Status.FECHADO:
        caixa_status = "FECHADO"
        saldo_atual = caixa.saldo_final or 0

    ctx = {
        'pendentes': pendentes,
        'parciais': parciais,
        'total_aberto': total_aberto,
        'caixa_status': caixa_status,
        'saldo_atual': saldo_atual,
        'hoje': hoje,
    }
    ctx.update(_menu_context(request))
    return render(request, 'ferramentas/financeiro_home.html', ctx)


@login_required
@require_admin_or_operador
def financeiro_contas(request):
    q = (request.GET.get('q') or '').strip()
    status = (request.GET.get('status') or '').strip()

    contas = ContaReceber.objects.select_related(
        'cliente', 'locacao', 'locacao__ferramenta'
    ).order_by('-criado_em')

    if status:
        contas = contas.filter(status=status)

    if q:
        contas = contas.filter(
            Q(cliente__nome__icontains=q) |
            Q(cliente__cpf_cnpj__icontains=q) |
            Q(locacao__ferramenta__nome__icontains=q)
        )

    ctx = {'contas': contas, 'q': q, 'status': status, 'Status': ContaReceber.Status}
    ctx.update(_menu_context(request))
    return render(request, 'ferramentas/financeiro_contas.html', ctx)


@login_required
@require_admin_or_operador
def financeiro_conta_detalhe(request, conta_id):
    conta = get_object_or_404(
        ContaReceber.objects.select_related('cliente', 'locacao', 'locacao__ferramenta'),
        id=conta_id
    )
    pagamentos = Pagamento.objects.filter(conta=conta).order_by('-data_pagamento')

    ctx = {
        'conta': conta,
        'pagamentos': pagamentos,
        'total_pago': conta.total_pago(),
        'saldo': conta.saldo(),
    }
    ctx.update(_menu_context(request))
    return render(request, 'ferramentas/financeiro_conta_detalhe.html', ctx)


@login_required
@require_admin_or_operador
def financeiro_registrar_pagamento(request, conta_id):
    conta = get_object_or_404(
        ContaReceber.objects.select_related('cliente', 'locacao', 'locacao__ferramenta'),
        id=conta_id
    )

    if request.method == 'POST':
        try:
            valor_str = (request.POST.get('valor') or '0').strip().replace(',', '.')
            try:
                valor = Decimal(valor_str)
            except InvalidOperation:
                messages.error(request, "Valor inválido.")
                return redirect('financeiro_registrar_pagamento', conta_id=conta.id)

            if valor <= 0:
                messages.error(request, "O valor deve ser maior que zero.")
                return redirect('financeiro_registrar_pagamento', conta_id=conta.id)

            saldo_atual = conta.saldo()
            if valor > saldo_atual:
                messages.error(request, "Valor maior que o saldo da conta.")
                return redirect('financeiro_registrar_pagamento', conta_id=conta.id)

            forma = request.POST.get('forma')
            observacao = (request.POST.get('observacao') or '').strip()

            pagamento = Pagamento(
                conta=conta,
                valor=valor,
                forma=forma,
                observacao=observacao
            )

            # Passa o usuário para o models.py criar o movimento do caixa com usuario correto
            pagamento._usuario = request.user
            pagamento.save()

            messages.success(request, "Pagamento registrado com sucesso!")
            return redirect('financeiro_conta_detalhe', conta_id=conta.id)

        except Exception as e:
            messages.error(request, f"Erro ao registrar pagamento: {e}")

    ctx = {'conta': conta, 'Formas': Pagamento.Forma, 'saldo': conta.saldo()}
    ctx.update(_menu_context(request))
    return render(request, 'ferramentas/financeiro_registrar_pagamento.html', ctx)


# ------------------------------------------------------------
# CAIXA DO DIA (ABRIR / LANÇAR / FECHAR / HISTÓRICO)
# ------------------------------------------------------------

@login_required
@require_admin_or_operador
def caixa_dia(request):
    hoje = timezone.localdate()
    caixa = CaixaDia.objects.filter(data=hoje).first()

    movimentos = []
    total_entradas = 0
    total_saidas = 0
    saldo_atual = 0

    if caixa:
        movimentos = list(caixa.movimentos.all())
        total_entradas = caixa.total_entradas()
        total_saidas = caixa.total_saidas()
        saldo_atual = caixa.saldo_calculado() if caixa.status == CaixaDia.Status.ABERTO else (caixa.saldo_final or 0)

    ctx = {
        'hoje': hoje,
        'caixa': caixa,
        'movimentos': movimentos,
        'total_entradas': total_entradas,
        'total_saidas': total_saidas,
        'saldo_atual': saldo_atual,
    }
    ctx.update(_menu_context(request))
    return render(request, 'ferramentas/caixa_dia.html', ctx)


@login_required
@require_admin_or_operador
@require_POST
def caixa_abrir(request):
    """
    Abre o caixa do dia.

    Regra segura:
    - Se já existe e está ABERTO -> não abre outro
    - Se já existe e está FECHADO -> não abre novamente
    - Se não existe -> cria
    """
    hoje = timezone.localdate()
    caixa_hoje = CaixaDia.objects.filter(data=hoje).first()

    if caixa_hoje and caixa_hoje.status == CaixaDia.Status.ABERTO:
        messages.info(request, "O caixa de hoje já está aberto.")
        return redirect('caixa_dia')

    if caixa_hoje and caixa_hoje.status == CaixaDia.Status.FECHADO:
        messages.error(request, "O caixa de hoje já foi FECHADO. Não é possível abrir novamente no mesmo dia.")
        return redirect('caixa_dia')

    try:
        saldo_inicial_str = (request.POST.get('saldo_inicial') or '0').strip().replace(',', '.')
        try:
            saldo_inicial = Decimal(saldo_inicial_str)
        except InvalidOperation:
            messages.error(request, "Saldo inicial inválido.")
            return redirect('caixa_dia')

        observacao = (request.POST.get('observacao') or '').strip()

        CaixaDia.objects.create(
            data=hoje,
            status=CaixaDia.Status.ABERTO,
            saldo_inicial=saldo_inicial,
            usuario_abertura=request.user,
            observacao=observacao
        )

        messages.success(request, "Caixa aberto com sucesso!")
        return redirect('caixa_dia')

    except Exception as e:
        messages.error(request, f"Erro ao abrir caixa: {e}")
        return redirect('caixa_dia')


@login_required
@require_admin_or_operador
def caixa_lancar(request):
    hoje = timezone.localdate()
    caixa = CaixaDia.objects.filter(data=hoje, status=CaixaDia.Status.ABERTO).first()

    if not caixa:
        messages.error(request, "Não há caixa aberto hoje. Abra o caixa antes de lançar movimentos.")
        return redirect('caixa_dia')

    tipo = (request.GET.get('tipo') or '').strip().upper()
    if tipo not in [MovimentoCaixa.Tipo.ENTRADA, MovimentoCaixa.Tipo.SAIDA]:
        tipo = MovimentoCaixa.Tipo.ENTRADA

    if request.method == 'POST':
        try:
            categoria = request.POST.get('categoria')
            forma = request.POST.get('forma')

            valor_str = (request.POST.get('valor') or '0').strip().replace(',', '.')
            try:
                valor = Decimal(valor_str)
            except InvalidOperation:
                messages.error(request, "Valor inválido.")
                return redirect('caixa_lancar')

            if valor <= 0:
                messages.error(request, "O valor deve ser maior que zero.")
                return redirect('caixa_lancar')

            descricao = (request.POST.get('descricao') or '').strip()
            referencia = (request.POST.get('referencia') or '').strip()

            MovimentoCaixa.objects.create(
                caixa=caixa,
                tipo=tipo,
                categoria=categoria,
                forma=forma,
                valor=valor,
                descricao=descricao,
                referencia=referencia,
                usuario=request.user
            )

            messages.success(request, "Movimento lançado com sucesso!")
            return redirect('caixa_dia')

        except Exception as e:
            messages.error(request, f"Erro ao lançar movimento: {e}")

    ctx = {
        'tipo': tipo,
        'Categorias': MovimentoCaixa.Categoria.choices,
        'Formas': MovimentoCaixa.Forma.choices,
    }
    ctx.update(_menu_context(request))
    return render(request, 'ferramentas/caixa_lancar.html', ctx)


@login_required
@require_admin_or_operador
def caixa_fechar(request):
    hoje = timezone.localdate()
    caixa = CaixaDia.objects.filter(data=hoje, status=CaixaDia.Status.ABERTO).first()

    if not caixa:
        messages.error(request, "Não há caixa aberto hoje.")
        return redirect('caixa_dia')

    total_entradas = caixa.total_entradas()
    total_saidas = caixa.total_saidas()
    saldo_calculado = caixa.saldo_calculado()

    if request.method == 'POST':
        try:
            saldo_conferido_str = (request.POST.get('saldo_conferido') or '0').strip().replace(',', '.')
            try:
                saldo_conferido = Decimal(saldo_conferido_str)
            except InvalidOperation:
                messages.error(request, "Saldo conferido inválido.")
                return redirect('caixa_fechar')

            observacao = (request.POST.get('observacao') or '').strip()

            caixa.saldo_final = saldo_conferido
            caixa.status = CaixaDia.Status.FECHADO
            caixa.fechado_em = timezone.now()
            caixa.usuario_fechamento = request.user

            if observacao:
                caixa.observacao = (caixa.observacao + "\n" + observacao).strip() if caixa.observacao else observacao

            caixa.save(update_fields=['saldo_final', 'status', 'fechado_em', 'usuario_fechamento', 'observacao'])

            messages.success(request, "Caixa fechado com sucesso!")
            return redirect('caixa_dia')

        except Exception as e:
            messages.error(request, f"Erro ao fechar caixa: {e}")

    ctx = {
        'caixa': caixa,
        'total_entradas': total_entradas,
        'total_saidas': total_saidas,
        'saldo_calculado': saldo_calculado,
    }
    ctx.update(_menu_context(request))
    return render(request, 'ferramentas/caixa_fechar.html', ctx)


@login_required
@require_admin_or_operador
def caixa_historico(request):
    de = (request.GET.get('de') or '').strip()
    ate = (request.GET.get('ate') or '').strip()

    caixas = CaixaDia.objects.all()

    if de:
        try:
            dt_de = datetime.strptime(de, "%Y-%m-%d").date()
            caixas = caixas.filter(data__gte=dt_de)
        except Exception:
            messages.error(request, "Data 'De' inválida.")
            de = ""

    if ate:
        try:
            dt_ate = datetime.strptime(ate, "%Y-%m-%d").date()
            caixas = caixas.filter(data__lte=dt_ate)
        except Exception:
            messages.error(request, "Data 'Até' inválida.")
            ate = ""

    itens = []
    for c in caixas.order_by('-data'):
        itens.append({
            'caixa': c,
            'entradas': c.total_entradas(),
            'saidas': c.total_saidas(),
        })

    ctx = {'itens': itens, 'de': de, 'ate': ate}
    ctx.update(_menu_context(request))
    return render(request, 'ferramentas/caixa_historico.html', ctx)


# ------------------------------------------------------------
# RESET DO CAIXA DE HOJE (ADMIN) - SEGURO
# ------------------------------------------------------------

@login_required
@require_admin
@require_POST
def caixa_resetar_hoje(request):
    """
    Zera (apaga) o registro do caixa de hoje e seus movimentos.

    REGRA DE SEGURANÇA:
    - Só Admin
    - Só permite resetar se o caixa estiver FECHADO
      (porque resetar um caixa aberto pode causar bagunça)
    """
    hoje = timezone.localdate()
    caixa = CaixaDia.objects.filter(data=hoje).first()

    if not caixa:
        messages.info(request, "Não existe caixa cadastrado para hoje.")
        return redirect('caixa_dia')

    if caixa.status != CaixaDia.Status.FECHADO:
        messages.error(request, "Só é permitido resetar o caixa se ele estiver FECHADO.")
        return redirect('caixa_dia')

    # Transação: ou apaga tudo, ou não apaga nada (segurança)
    try:
        with transaction.atomic():
            # apaga movimentos
            MovimentoCaixa.objects.filter(caixa=caixa).delete()
            # apaga o caixa
            caixa.delete()

        messages.success(request, "Caixa de hoje foi resetado (apagado) com sucesso. Agora você pode abrir novamente.")
    except Exception as e:
        messages.error(request, f"Erro ao resetar caixa: {e}")

    return redirect('caixa_dia')