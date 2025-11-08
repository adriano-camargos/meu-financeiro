# Dentro de lancamentos/admin.py
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
# Importação completa de todos os modelos
from .models import Categoria, Lancamento, CategoriaPadrao, Receita, Perfil, CartaoDeCredito

# --- FERRAMENTA DE MIGRAÇÃO DE DADOS (Usuário) ---
def criar_acao_de_migracao(nome_de_usuario_destino):
    def migrar_dados(modeladmin, request, queryset):
        try:
            novo_dono = User.objects.get(username=nome_de_usuario_destino)
            itens_atualizados = queryset.update(user=novo_dono)
            messages.success(request, f'{itens_atualizados} itens foram migrados com sucesso para o usuário "{novo_dono.username}".')
        except User.DoesNotExist:
            messages.error(request, f'ERRO: O usuário "{nome_de_usuario_destino}" não foi encontrado no banco de dados.')
        except Exception as e:
            messages.error(request, f'Ocorreu um erro inesperado durante a migração: {e}')
    migrar_dados.short_description = f"Migrar itens para o usuário '{nome_de_usuario_destino}'"
    return migrar_dados

NOME_DA_SUA_CONTA_PESSOAL = "adriano" 
acao_migrar_user = criar_acao_de_migracao(NOME_DA_SUA_CONTA_PESSOAL)

# --- NOVA FERRAMENTA DE MIGRAÇÃO (Lançamentos para Cartão - CORRIGIDA) ---

# !! IMPORTANTE !!
# COLOQUE AQUI O ID DO SEU CARTÃO PRINCIPAL (que você já verificou)
ID_DO_CARTAO_PRINCIPAL = 1 # <--- TROQUE ESTE NÚMERO SE FOR DIFERENTE

@admin.action(description=f"Migrar Lançamentos de Crédito (sem cartão) para o Cartão ID #{ID_DO_CARTAO_PRINCIPAL}")
def migrar_lancamentos_para_cartao(modeladmin, request, queryset):
    try:
        # CORREÇÃO AQUI: Removemos o filtro 'user=request.user'
        # O superusuário deve ser capaz de encontrar o cartão pelo ID,
        # independentemente de quem é o dono.
        cartao_destino = CartaoDeCredito.objects.get(pk=ID_DO_CARTAO_PRINCIPAL)
    except CartaoDeCredito.DoesNotExist:
        # A mensagem de erro agora é mais genérica
        messages.error(request, f"Erro! Cartão com ID {ID_DO_CARTAO_PRINCIPAL} não foi encontrado. Verifique o ID no topo do arquivo admin.py.")
        return

    # Filtra o queryset selecionado para pegar APENAS
    # lançamentos de 'Crédito' que ainda não têm 'cartao' (estão como None)
    lancamentos_para_migrar = queryset.filter(
        metodo_pagamento='Crédito',
        cartao__isnull=True
    )
    
    count = lancamentos_para_migrar.update(cartao=cartao_destino)
    
    if count > 0:
        messages.success(request, f"{count} lançamento(s) de crédito foi(ram) migrado(s) para o cartão '{cartao_destino.nome}'.")
    else:
        messages.info(request, "Nenhum lançamento precisou ser migrado (já estavam corretos ou não eram de crédito).")

# --- REGISTRO DOS NOSSOS MODELOS ---
@admin.register(CategoriaPadrao)
class CategoriaPadraoAdmin(admin.ModelAdmin):
    list_display = ['nome', 'macro_categoria', 'exemplos']
    list_filter = ['macro_categoria']
    search_fields = ['nome', 'exemplos']

@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ['nome', 'macro_categoria', 'exemplos', 'user']
    list_filter = ['macro_categoria', 'user']
    search_fields = ['nome', 'exemplos', 'user__username']
    actions = [acao_migrar_user]

@admin.register(Lancamento)
class LancamentoAdmin(admin.ModelAdmin):
    list_display = ['local_compra', 'data_compra', 'metodo_pagamento', 'cartao', 'valor_total', 'categoria', 'user']
    list_filter = ['metodo_pagamento', 'categoria', 'data_compra', 'user', 'cartao']
    search_fields = ['local_compra', 'descricao', 'user__username']
    actions = [acao_migrar_user, migrar_lancamentos_para_cartao] # Ação adicionada
    date_hierarchy = 'data_compra'

@admin.register(Receita)
class ReceitaAdmin(admin.ModelAdmin):
    list_display = ['descricao', 'data_recebimento', 'valor', 'user']
    list_filter = ['data_recebimento', 'user']
    search_fields = ['descricao', 'user__username']
    date_hierarchy = 'data_recebimento'
    
@admin.register(CartaoDeCredito)
class CartaoDeCreditoAdmin(admin.ModelAdmin):
    list_display = ('nome', 'user', 'limite', 'dia_fechamento', 'dia_vencimento')
    list_filter = ('user',)
    search_fields = ('nome', 'user__username')

# --- FERRAMENTAS DE GERENCIAMENTO DE USUÁRIOS ---
@admin.action(description='Popular com categorias padrão (apenas as que faltam)')
def popular_categorias_padrao(modeladmin, request, queryset):
    categorias_padrao = CategoriaPadrao.objects.all()
    if not categorias_padrao.exists():
        messages.warning(request, 'Nenhuma Categoria Padrão foi cadastrada para popular.')
        return
    usuarios_atualizados = 0
    categorias_criadas_total = 0
    for user in queryset:
        categorias_criadas_para_usuario = 0
        for cat_padrao in categorias_padrao:
            if not Categoria.objects.filter(user=user, nome=cat_padrao.nome).exists():
                try:
                    Categoria.objects.create(nome=cat_padrao.nome, macro_categoria=cat_padrao.macro_categoria, exemplos=cat_padrao.exemplos, user=user)
                    categorias_criadas_para_usuario += 1
                except Exception as e:
                     messages.error(request, f'Erro ao criar categoria {cat_padrao.nome} para {user.username}: {e}')
        if categorias_criadas_para_usuario > 0:
            usuarios_atualizados += 1
            categorias_criadas_total += categorias_criadas_para_usuario
    if usuarios_atualizados > 0:
        messages.success(request, f'{usuarios_atualizados} usuário(s) atualizado(s). Total de {categorias_criadas_total} nova(s) categoria(s) criada(s).')
    else:
        messages.info(request, 'Nenhuma categoria precisou ser adicionada para os usuários selecionados (eles já estavam atualizados ou não havia categorias padrão).')

@admin.action(description='Atualizar categorias existentes com os dados padrão')
def atualizar_categorias_com_padrao(modeladmin, request, queryset):
    categorias_padrao = CategoriaPadrao.objects.all()
    mapa_padrao = {cat.nome: cat for cat in categorias_padrao}
    if not mapa_padrao:
        messages.warning(request, 'Nenhuma Categoria Padrão foi cadastrada para usar como base.')
        return
    categorias_atualizadas_count = 0
    usuarios_processados = 0
    for user in queryset:
        usuarios_processados += 1
        categorias_do_usuario = Categoria.objects.filter(user=user)
        for cat_usuario in categorias_do_usuario:
            if cat_usuario.nome in mapa_padrao:
                cat_padrao_correspondente = mapa_padrao[cat_usuario.nome]
                atualizou = False
                if cat_usuario.macro_categoria != cat_padrao_correspondente.macro_categoria:
                    cat_usuario.macro_categoria = cat_padrao_correspondente.macro_categoria
                    atualizou = True
                if cat_usuario.exemplos != cat_padrao_correspondente.exemplos:
                    cat_usuario.exemplos = cat_padrao_correspondente.exemplos
                    atualizou = True
                if atualizou:
                    try:
                        cat_usuario.save()
                        categorias_atualizadas_count += 1
                    except Exception as e:
                        messages.error(request, f'Erro ao atualizar categoria {cat_usuario.nome} para {user.username}: {e}')
    if categorias_atualizadas_count > 0:
        messages.success(request, f'{categorias_atualizadas_count} categoria(s) foram atualizada(s) com sucesso nos {usuarios_processados} usuário(s) selecionado(s).')
    else:
        messages.info(request, 'Nenhuma categoria correspondente foi encontrada para ser atualizada nos usuários selecionados.')

# --- PERSONALIZAÇÃO DO ADMIN DE USUÁRIOS ---
class CustomUserAdmin(BaseUserAdmin):
    inlines = () 
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'date_joined')
    actions = [popular_categorias_padrao, atualizar_categorias_com_padrao]

admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)