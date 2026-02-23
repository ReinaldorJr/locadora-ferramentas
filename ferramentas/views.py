# ferramentas/views.py

from datetime import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from .models import Cliente, Ferramenta, Locacao


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


# ---- VIEWS ----
@login_required
@require_admin_or_operador
def home(request):
    locacoes = Locacao.objects.select_related('cliente', 'ferramenta').order_by('-criado_em')

    total_ativas = Locacao.objects.filter(devolvida=False).count()
    total_devolvidas = Locacao.objects.filter(devolvida=True).count()
    ferramentas_disponiveis = Ferramenta.objects.filter(quantidade_disponivel__gt=0, ativa=True).count()

    faturamento = Locacao.objects.filter(devolvida=True).aggregate(total=Sum('valor_total'))['total'] or 0

    # atrasos (pra badge/contagem)
    hoje = datetime.today().date()
    total_atrasadas = Locacao.objects.filter(devolvida=False, data_fim__lt=hoje).count()

    return render(request, 'ferramentas/home.html', {
        'locacoes': locacoes,
        'total_ativas': total_ativas,
        'total_devolvidas': total_devolvidas,
        'ferramentas_disponiveis': ferramentas_disponiveis,
        'faturamento': faturamento,
        'total_atrasadas': total_atrasadas,
        'is_admin': is_admin(request.user),
        'is_operador': is_operador(request.user),
    })


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
                endereco=(request.POST.get('endereco') or '').strip()
            )
            messages.success(request, "Cliente cadastrado com sucesso!")
            return redirect('home')
        except Exception as e:
            messages.error(request, f"Erro ao cadastrar cliente: {e}")

    return render(request, 'ferramentas/cadastrar_cliente.html')


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
            )
            messages.success(request, "Ferramenta cadastrada com sucesso!")
            return redirect('home')
        except Exception as e:
            messages.error(request, f"Erro ao cadastrar ferramenta: {e}")

    return render(request, 'ferramentas/cadastrar_ferramenta.html')


@login_required
@require_admin_or_operador
def nova_locacao(request):
    clientes = Cliente.objects.filter(ativo=True).order_by('nome')
    ferramentas = Ferramenta.objects.filter(ativa=True, quantidade_disponivel__gt=0).order_by('nome')

    if request.method == 'POST':
        cliente_id = request.POST.get('cliente')
        ferramenta_id = request.POST.get('ferramenta')
        data_inicio_str = request.POST.get('data_inicio')
        data_fim_str = request.POST.get('data_fim')

        if not cliente_id or not ferramenta_id:
            messages.error(request, "Selecione um cliente e uma ferramenta.")
            return render(request, 'ferramentas/nova_locacao.html', {
                'clientes': clientes,
                'ferramentas': ferramentas
            })

        if not data_inicio_str or not data_fim_str:
            messages.error(request, "Preencha a data de início e a data de fim.")
            return render(request, 'ferramentas/nova_locacao.html', {
                'clientes': clientes,
                'ferramentas': ferramentas
            })

        try:
            data_inicio = datetime.strptime(data_inicio_str, "%Y-%m-%d").date()
            data_fim = datetime.strptime(data_fim_str, "%Y-%m-%d").date()

            Locacao.objects.create(
                cliente_id=cliente_id,
                ferramenta_id=ferramenta_id,
                data_inicio=data_inicio,
                data_fim=data_fim
            )

            messages.success(request, "Locação criada com sucesso!")
            return redirect('home')

        except ValueError:
            messages.error(request, "Formato de data inválido. Use o seletor de data do formulário.")
        except ValidationError as ve:
            messages.error(request, f"Erro de validação: {ve}")
        except Exception as e:
            messages.error(request, f"Erro ao criar locação: {e}")

    return render(request, 'ferramentas/nova_locacao.html', {
        'clientes': clientes,
        'ferramentas': ferramentas
    })


@login_required
@require_admin_or_operador
@require_POST
def devolver_locacao(request, locacao_id):
    locacao = get_object_or_404(Locacao, id=locacao_id)

    if locacao.devolvida:
        messages.info(request, "Essa locação já está devolvida.")
        return redirect('home')

    try:
        locacao.devolvida = True
        locacao.save()
        messages.success(request, "Devolução registrada com sucesso!")
    except ValidationError as ve:
        messages.error(request, f"Erro de validação: {ve}")
    except Exception as e:
        messages.error(request, f"Erro ao devolver locação: {e}")

    return redirect('home')


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

    return render(request, 'ferramentas/relatorio_atrasos.html', {
        'hoje': hoje,
        'atrasadas': atrasadas,
    })