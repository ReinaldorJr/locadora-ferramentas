from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from .models import Cliente, Ferramenta, Locacao


class LocacaoFlowTests(TestCase):
    def setUp(self):
        self.cliente_obj = Cliente.objects.create(
            nome="Joao Silva",
            cpf_cnpj="12345678900",
            telefone="11999999999",
            email="joao@example.com",
            endereco="Rua A, 123",
        )
        self.ferramenta_obj = Ferramenta.objects.create(
            nome="Furadeira",
            descricao="Furadeira de impacto",
            categoria="Eletrica",
            valor_diaria=Decimal("10.00"),
            valor_semanal=Decimal("50.00"),
            valor_mensal=Decimal("150.00"),
            quantidade_total=2,
            quantidade_disponivel=2,
            ativa=True,
        )

    def test_nova_locacao_post_cria_locacao_e_baixa_estoque(self):
        response = self.client.post(
            reverse("nova_locacao"),
            data={
                "cliente": self.cliente_obj.id,
                "ferramenta": self.ferramenta_obj.id,
                "data_inicio": "2026-02-01",
                "data_fim": "2026-02-03",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("home"))
        self.assertEqual(Locacao.objects.count(), 1)

        locacao = Locacao.objects.get()
        self.ferramenta_obj.refresh_from_db()

        self.assertEqual(locacao.valor_total, Decimal("20.00"))
        self.assertEqual(self.ferramenta_obj.quantidade_disponivel, 1)

    def test_locacao_com_data_fim_menor_que_inicio_levanta_erro(self):
        locacao = Locacao(
            cliente=self.cliente_obj,
            ferramenta=self.ferramenta_obj,
            data_inicio=date(2026, 2, 10),
            data_fim=date(2026, 2, 5),
        )

        with self.assertRaises(ValidationError):
            locacao.save()

        self.ferramenta_obj.refresh_from_db()
        self.assertEqual(self.ferramenta_obj.quantidade_disponivel, 2)
        self.assertEqual(Locacao.objects.count(), 0)

    def test_locacao_sem_estoque_levanta_erro(self):
        self.ferramenta_obj.quantidade_disponivel = 0
        self.ferramenta_obj.save()

        locacao = Locacao(
            cliente=self.cliente_obj,
            ferramenta=self.ferramenta_obj,
            data_inicio=date(2026, 2, 1),
            data_fim=date(2026, 2, 2),
        )

        with self.assertRaises(ValidationError):
            locacao.save()

        self.assertEqual(Locacao.objects.count(), 0)

    def test_devolver_locacao_post_marca_devolvida_e_replica_estoque(self):
        locacao = Locacao.objects.create(
            cliente=self.cliente_obj,
            ferramenta=self.ferramenta_obj,
            data_inicio=date(2026, 2, 1),
            data_fim=date(2026, 2, 2),
        )
        self.ferramenta_obj.refresh_from_db()
        self.assertEqual(self.ferramenta_obj.quantidade_disponivel, 1)

        response = self.client.post(reverse("devolver_locacao", args=[locacao.id]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("home"))

        locacao.refresh_from_db()
        self.ferramenta_obj.refresh_from_db()
        self.assertTrue(locacao.devolvida)
        self.assertEqual(self.ferramenta_obj.quantidade_disponivel, 2)

        self.client.post(reverse("devolver_locacao", args=[locacao.id]))
        self.ferramenta_obj.refresh_from_db()
        self.assertEqual(self.ferramenta_obj.quantidade_disponivel, 2)

    def test_nova_locacao_data_invalida_retorna_form_com_erro(self):
        response = self.client.post(
            reverse("nova_locacao"),
            data={
                "cliente": self.cliente_obj.id,
                "ferramenta": self.ferramenta_obj.id,
                "data_inicio": "2026-02-10",
                "data_fim": "2026-02-05",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Locacao.objects.count(), 0)
        self.assertTrue(response.context["form"].errors)

    def test_cadastrar_cliente_cpf_duplicado_retorna_form_com_erro(self):
        response = self.client.post(
            reverse("cadastrar_cliente"),
            data={
                "nome": "Maria",
                "cpf_cnpj": "12345678900",
                "telefone": "11911111111",
                "email": "maria@example.com",
                "endereco": "Rua B, 456",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Cliente.objects.count(), 1)
        self.assertTrue(response.context["form"].errors)
