from datetime import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Sum, Q
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from .models import Cliente, Ferramenta, Locacao, ContaReceber, Pagamento


# ---- CONTROLE DE PERFIL (GRUPOS) ----
def is_admin(user):
    return user.is_authenticated and (user.is_superuser or user.groups.filter(name='Admin').exists())


def is_operador(user):
    return user.is_authenticated and user.groups.filter(name='Operador').exists()


def require_admin(view_func):
    def _wrapped(request, *args, **kwargs):
        if not is_admin(request.user):
            messages.error(request, "Acesso negado: apenas Admin pode acessar essa página.")
            return redirect('home')
        return view_func(request, *args, **kwargs)
    return _wrapped


def require_admin_or_operador(view_func):
    def _wrapped(request, *args, **kwargs):
        if not (is_admin(request.user) or is_operador(request.user)):
            messages.error(request, "Acesso negado: usuário sem perfil. Peça ao Admin para ajustar seu acesso.")
            return redirect('login')
        return view_func(request, *args, **kwargs)
    return _wrapped


def _menu_context(request):
    hoje = datetime.today().date()
    total_atrasadas = Locacao.objects.filter(devolvida=False, data_fim__lt=hoje).count()
    contas_em_aberto = ContaReceber.objects.filter(status__in=[
        ContaReceber.Status.PENDENTE,
        ContaReceber.Status.PARCIAL
    ]).count()

    return {
        'total_atrasadas': total_atrasadas,
        'contas_em_aberto': contas_em_aberto,
        'is_admin': is_admin(request.user),
        'is_operador': is_operador(request.user),
    }


# ---- HOME ----
@login_required
@require_admin_or_operador
def home(request):
    locacoes = Locacao.objects.select_related('cliente', 'ferramenta').order_by('-criado_em')

    total_ativas = Locacao.objects.filter(devolvida=False).count()
    total_devolvidas = Locacao.objects.filter(devolvida=True).count()
    ferramentas_disponiveis = Ferramenta.objects.filter(quantidade_disponivel__gt=0, ativa=True).count()
    faturamento = Locacao.objects.filter(devolvida=True).aggregate(total=Sum('valor_total'))['total'] or 0

    ctx = {
        'locacoes': locacoes[:15],
        'total_ativas': total_ativas,
        'total_devolvidas': total_devolvidas,
        'ferramentas_disponiveis': ferramentas_disponiveis,
        'faturamento': faturamento,
    }
    ctx.update(_menu_context(request))
    return render(request, 'ferramentas/home.html', ctx)


# ---- CLIENTES ----
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


# ---- FERRAMENTAS ----
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


# ---- LOCAÇÕES (ABA PRÓPRIA + FILTRO FINANCEIRO + BOTÃO RECEBER) ----
@login_required
@require_admin_or_operador
def listar_locacoes(request):
    q = (request.GET.get('q') or '').strip()
    status = (request.GET.get('status') or '').strip()  # ATIVAS / DEVOLVIDAS / ""
    financeiro = (request.GET.get('financeiro') or '').strip()  # PENDENTE/PARCIAL/PAGO/CANCELADO/""

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

    # aplica filtro financeiro (por conta)
    if financeiro:
        locacoes = locacoes.filter(conta_receber__status=financeiro)

    locacoes_lista = list(locacoes)
    ids = [l.id for l in locacoes_lista]

    contas = (
        ContaReceber.objects
        .filter(locacao_id__in=ids)
        .select_related('locacao', 'cliente')
    )
    conta_por_locacao = {c.locacao_id: c for c in contas}

    linhas = []
    for l in locacoes_lista:
        conta = conta_por_locacao.get(l.id)
        saldo = conta.saldo() if conta else None
        linhas.append({
            'locacao': l,
            'conta': conta,
            'saldo': saldo,
        })

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


# ---- RELATÓRIO DE ATRASOS ----
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


# ---- FINANCEIRO ----
@login_required
@require_admin_or_operador
def financeiro_contas(request):
    q = (request.GET.get('q') or '').strip()
    status = (request.GET.get('status') or '').strip()

    contas = ContaReceber.objects.select_related('cliente', 'locacao', 'locacao__ferramenta').order_by('-criado_em')

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
            valor = request.POST.get('valor')
            forma = request.POST.get('forma')
            observacao = (request.POST.get('observacao') or '').strip()

            Pagamento.objects.create(
                conta=conta,
                valor=valor,
                forma=forma,
                observacao=observacao
            )

            messages.success(request, "Pagamento registrado com sucesso!")
            return redirect('financeiro_conta_detalhe', conta_id=conta.id)

        except Exception as e:
            messages.error(request, f"Erro ao registrar pagamento: {e}")

    ctx = {'conta': conta, 'Formas': Pagamento.Forma, 'saldo': conta.saldo()}
    ctx.update(_menu_context(request))
    return render(request, 'ferramentas/financeiro_registrar_pagamento.html', ctx)