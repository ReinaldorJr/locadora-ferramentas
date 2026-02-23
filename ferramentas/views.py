from datetime import datetime, date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import render, redirect, get_object_or_404

from .models import Cliente, Ferramenta, Locacao


@login_required
def home(request):
    locacoes = Locacao.objects.select_related('cliente', 'ferramenta').order_by('-criado_em')

    total_ativas = Locacao.objects.filter(devolvida=False).count()
    total_devolvidas = Locacao.objects.filter(devolvida=True).count()
    ferramentas_disponiveis = Ferramenta.objects.filter(quantidade_disponivel__gt=0).count()

    faturamento = Locacao.objects.filter(devolvida=True).aggregate(total=Sum('valor_total'))['total'] or 0

    # Admin: pode ver botões de cadastro/estoque/atrasos
    is_admin = request.user.is_superuser or request.user.is_staff

    # Contagem de atrasadas (não devolvidas e com data_fim < hoje)
    total_atrasadas = Locacao.objects.filter(devolvida=False, data_fim__lt=date.today()).count()

    return render(request, 'ferramentas/home.html', {
        'locacoes': locacoes,
        'total_ativas': total_ativas,
        'total_devolvidas': total_devolvidas,
        'ferramentas_disponiveis': ferramentas_disponiveis,
        'faturamento': faturamento,
        'is_admin': is_admin,
        'total_atrasadas': total_atrasadas,
        'hoje': date.today(),
    })


@login_required
def cadastrar_cliente(request):
    # Só admin cadastra
    if not (request.user.is_superuser or request.user.is_staff):
        messages.error(request, "Você não tem permissão para cadastrar clientes.")
        return redirect('home')

    if request.method == 'POST':
        Cliente.objects.create(
            nome=request.POST.get('nome'),
            cpf_cnpj=request.POST.get('cpf_cnpj'),
            telefone=request.POST.get('telefone'),
            email=request.POST.get('email'),
            endereco=request.POST.get('endereco')
        )
        messages.success(request, "Cliente cadastrado com sucesso.")
        return redirect('home')

    return render(request, 'ferramentas/cadastrar_cliente.html')


@login_required
def cadastrar_ferramenta(request):
    # Só admin cadastra
    if not (request.user.is_superuser or request.user.is_staff):
        messages.error(request, "Você não tem permissão para cadastrar ferramentas.")
        return redirect('home')

    if request.method == 'POST':
        Ferramenta.objects.create(
            nome=request.POST.get('nome'),
            descricao=request.POST.get('descricao'),
            categoria=request.POST.get('categoria'),
            valor_diaria=request.POST.get('valor_diaria'),
            valor_semanal=request.POST.get('valor_semanal'),
            valor_mensal=request.POST.get('valor_mensal'),
            quantidade_total=request.POST.get('quantidade_total'),
            quantidade_disponivel=request.POST.get('quantidade_total'),
        )
        messages.success(request, "Ferramenta cadastrada com sucesso.")
        return redirect('home')

    return render(request, 'ferramentas/cadastrar_ferramenta.html')


@login_required
def nova_locacao(request):
    clientes = Cliente.objects.all().order_by('nome')
    ferramentas = Ferramenta.objects.filter(quantidade_disponivel__gt=0).order_by('nome')

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

            messages.success(request, "Locação criada com sucesso.")
            return redirect('home')

        except Exception as e:
            messages.error(request, f"Erro ao criar locação: {e}")

    return render(request, 'ferramentas/nova_locacao.html', {
        'clientes': clientes,
        'ferramentas': ferramentas
    })


@login_required
def devolver_locacao(request, locacao_id):
    if request.method != 'POST':
        return redirect('home')

    locacao = get_object_or_404(Locacao, id=locacao_id)

    if locacao.devolvida:
        return redirect('home')

    locacao.devolvida = True
    locacao.save()

    messages.success(request, "Locação devolvida com sucesso.")
    return redirect('home')