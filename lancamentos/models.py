# Dentro de lancamentos/models.py
from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal
from django.db.models.signals import post_save
from django.dispatch import receiver

# --- MODELO DE PERFIL (MODIFICADO) ---
# Removemos o campo 'limite_cartao'
class Perfil(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    # O campo de limite foi removido daqui

    def __str__(self):
        return f"Perfil de {self.user.username}"

# --- NOVO MODELO PARA CARTÃO DE CRÉDITO ---
class CartaoDeCredito(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='cartoes')
    nome = models.CharField("Nome do Cartão", max_length=100) # Ex: "Nubank", "Inter"
    limite = models.DecimalField("Limite", max_digits=10, decimal_places=2)
    dia_fechamento = models.IntegerField("Dia do Fechamento")
    dia_vencimento = models.IntegerField("Dia do Vencimento")

    def __str__(self):
        return f"{self.nome} (Usuário: {self.user.username})"
    
    class Meta:
        ordering = ['nome']
        verbose_name = "Cartão de Crédito"
        verbose_name_plural = "Cartões de Crédito"


# --- Modelos Existentes ---
class CategoriaPadrao(models.Model):
    MACRO_CATEGORIA_CHOICES = [('Essenciais', 'Essenciais'), ('Estilo de Vida', 'Estilo de Vida'), ('Prioridades', 'Prioridades'), ('Outras', 'Outras')]
    nome = models.CharField(max_length=100, unique=True)
    macro_categoria = models.CharField(max_length=50, choices=MACRO_CATEGORIA_CHOICES, default='Outras')
    exemplos = models.TextField("Exemplos", blank=True, null=True, help_text="Ex: Contas de luz, água, internet...")
    class Meta:
        verbose_name = "Categoria Padrão"
        verbose_name_plural = "Categorias Padrão"
    def __str__(self):
        return self.nome

class Categoria(models.Model):
    MACRO_CATEGORIA_CHOICES = [('Essenciais', 'Essenciais'), ('Estilo de Vida', 'Estilo de Vida'), ('Prioridades', 'Prioridades'), ('Outras', 'Outras')]
    nome = models.CharField(max_length=100)
    macro_categoria = models.CharField(max_length=50, choices=MACRO_CATEGORIA_CHOICES, default='Outras')
    exemplos = models.TextField("Exemplos", blank=True, null=True, help_text="Ex: Contas de luz, água, internet...")
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    def __str__(self):
        if self.user:
            return f"{self.nome} ({self.user.username})"
        return f"{self.nome} (Sem usuário)"

class Lancamento(models.Model):
    METODO_PAGAMENTO_CHOICES = [('Crédito', 'Crédito'), ('Débito', 'Débito'), ('PIX', 'PIX'), ('Dinheiro', 'Dinheiro')]
    local_compra = models.CharField("Local da Compra", max_length=200)
    descricao = models.TextField("Descrição", blank=True, null=True)
    data_compra = models.DateField("Data da Compra")
    valor_total = models.DecimalField("Valor Total", max_digits=10, decimal_places=2)
    metodo_pagamento = models.CharField(max_length=50, choices=METODO_PAGAMENTO_CHOICES, default='Crédito')
    
    # MUDANÇA: Adicionamos a ligação com o cartão de crédito
    cartao = models.ForeignKey(CartaoDeCredito, on_delete=models.PROTECT, null=True, blank=True)

    num_parcelas = models.IntegerField("Nº de Parcelas", default=1)
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    def __str__(self):
        data_formatada = self.data_compra.strftime('%d/%m/%Y')
        return f"{self.local_compra} em {data_formatada}"

class Receita(models.Model):
    descricao = models.CharField("Descrição", max_length=200)
    valor = models.DecimalField("Valor", max_digits=10, decimal_places=2)
    data_recebimento = models.DateField("Data de Recebimento")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    class Meta:
        ordering = ['-data_recebimento']
    def __str__(self):
        return f"{self.descricao} - R$ {self.valor}"

# --- SINAIS (Corrigidos para criar Perfil) ---
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """ Cria um Perfil apenas quando um novo User é criado. """
    if created:
        Perfil.objects.create(user=instance)

# Garantir que usuários existentes também tenham um perfil
@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    Perfil.objects.get_or_create(user=instance)