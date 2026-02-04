from django.shortcuts import render, redirect
from .models import Cliente, Ferramenta, Locacao
from django.utils import timezone


def home(request):
    locacoes = Locacao.objects.select_related('cliente', 'ferramenta')
    return render(request, 'ferramentas/home.html', {'locacoes': locacoes})


def cadastrar_cliente(request):
    if request.method == 'POST':
        Cliente.objects.create(
            nome=request.POST.get('nome'),
            cpf_cnpj=request.POST.get('cpf_cnpj'),
            telefone=request.POST.get('telefone'),
            email=request.POST.get('email'),
            endereco=request.POST.get('endereco')
        )
        return redirect('home')

    return render(request, 'ferramentas/cadastrar_cliente.html')


def cadastrar_ferramenta(request):
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
        return redirect('home')

    return render(request, 'ferramentas/cadastrar_ferramenta.html')


def nova_locacao(request):
    clientes = Cliente.objects.all()
    ferramentas = Ferramenta.objects.filter(quantidade_disponivel__gt=0)

    if request.method == 'POST':
        cliente_id = request.POST.get('cliente')
        ferramenta_id = request.POST.get('ferramenta')
        data_inicio = request.POST.get('data_inicio')
        data_fim = request.POST.get('data_fim')

        Locacao.objects.create(
            cliente_id=cliente_id,
            ferramenta_id=ferramenta_id,
            data_inicio=data_inicio,
            data_fim=data_fim
        )

        return redirect('home')

    return render(request, 'ferramentas/nova_locacao.html', {
        'clientes': clientes,
        'ferramentas': ferramentas
    })
