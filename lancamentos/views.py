# Dentro de lancamentos/views.py
import datetime
import json
from decimal import Decimal
from dateutil.relativedelta import relativedelta
from django.shortcuts import render, redirect, get_object_or_404
# Importação completa de TODOS os modelos necessários
from .models import Lancamento, Categoria, CategoriaPadrao, Receita, Perfil, CartaoDeCredito
from django.contrib.auth.forms import UserCreationForm
from django.urls import reverse_lazy
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db.models import Sum, Q, F, Func, IntegerField
from django.db.models.functions import ExtractYear, ExtractMonth
from django.contrib import messages
import locale 

try:
    locale.setlocale(locale.LC_ALL, 'pt_BR.utf8') 
except locale.Error:
    try:
        locale.setlocale(locale.LC_ALL, 'Portuguese_Brazil.1252')
    except locale.Error:
        print("Aviso: Locale 'pt_BR.utf8' ou 'Portuguese_Brazil.1252' não encontrado.")

# --- FUNÇÃO AUXILIAR PARA CÁLCULO DE VENCIMENTO (ANTIGA/GLOBAL) ---
def calcular_data_primeiro_vencimento(data_compra):
    DIA_FECHAMENTO = 3
    DIA_VENCIMENTO = 10
    if isinstance(data_compra, datetime.datetime): data_compra_date = data_compra.date()
    elif isinstance(data_compra, datetime.date): data_compra_date = data_compra
    else:
        try: data_compra_date = datetime.datetime.strptime(str(data_compra), '%Y-%m-%d').date()
        except (ValueError, TypeError):
             print(f"Alerta: Formato de data inesperado em calcular_data_primeiro_vencimento: {data_compra}")
             hoje = datetime.date.today()
             try: return (hoje + relativedelta(months=1)).replace(day=DIA_VENCIMENTO)
             except ValueError: return (hoje + relativedelta(months=2)).replace(day=1) - relativedelta(days=1)
             
    if data_compra_date.day > DIA_FECHAMENTO:
        vencimento_base = data_compra_date + relativedelta(months=1)
    else:
        vencimento_base = data_compra_date
    try: vencimento = vencimento_base.replace(day=DIA_VENCIMENTO)
    except ValueError:
        primeiro_dia_mes_seguinte = vencimento_base.replace(day=1) + relativedelta(months=1)
        vencimento = primeiro_dia_mes_seguinte - relativedelta(days=1)
    return vencimento

# --- NOVA FUNÇÃO AUXILIAR DE VENCIMENTO (POR CARTÃO) ---
def calcular_vencimento_por_cartao(data_compra, cartao):
    dia_fechamento = cartao.dia_fechamento
    dia_vencimento = cartao.dia_vencimento
    
    if isinstance(data_compra, datetime.datetime): data_compra = data_compra.date()
    elif not isinstance(data_compra, datetime.date):
        try: data_compra = datetime.datetime.strptime(str(data_compra), '%Y-%m-%d').date()
        except (ValueError, TypeError):
             print(f"Alerta: Formato de data inesperado: {data_compra}")
             return None 
    
    vencimento_base = data_compra
    
    if dia_vencimento < dia_fechamento:
        if data_compra.day > dia_fechamento:
            vencimento_base = data_compra + relativedelta(months=2)
        else:
            vencimento_base = data_compra + relativedelta(months=1)
    else:
        if data_compra.day > dia_fechamento:
            vencimento_base = data_compra + relativedelta(months=1)
        else:
            vencimento_base = data_compra

    try:
        data_vencimento = vencimento_base.replace(day=dia_vencimento)
    except ValueError: 
        primeiro_dia_prox_mes = vencimento_base.replace(day=1) + relativedelta(months=1)
        data_vencimento = primeiro_dia_prox_mes - relativedelta(days=1)

    return data_vencimento


# --- FUNÇÃO AUXILIAR PARA OBTER ANOS E MESES COM DADOS ---
def get_anos_meses_disponiveis(user):
    all_relevant_dates = set()
    lancamentos_avista = Lancamento.objects.filter(user=user).exclude(metodo_pagamento='Crédito').values_list('data_compra', flat=True)
    receitas_datas = Receita.objects.filter(user=user).values_list('data_recebimento', flat=True)
    all_relevant_dates.update(lancamentos_avista)
    all_relevant_dates.update(receitas_datas)
    
    cartoes_usuario = {cartao.id: cartao for cartao in CartaoDeCredito.objects.filter(user=user)}
    lancamentos_credito = Lancamento.objects.filter(user=user, metodo_pagamento='Crédito')
    
    for lancamento in lancamentos_credito:
        if lancamento.cartao_id in cartoes_usuario:
            cartao = cartoes_usuario[lancamento.cartao_id]
            primeiro_vencimento = calcular_vencimento_por_cartao(lancamento.data_compra, cartao)
        else:
            primeiro_vencimento = calcular_data_primeiro_vencimento(lancamento.data_compra)
            
        if primeiro_vencimento: 
            for i in range(lancamento.num_parcelas or 1): 
                data_vencimento_parcela = primeiro_vencimento + relativedelta(months=i)
                all_relevant_dates.add(data_vencimento_parcela) 
                
    hoje = datetime.date.today()
    DIA_FECHAMENTO_GLOBAL = 3 

    if not all_relevant_dates:
        all_relevant_dates.add(hoje) 
        ano_default = hoje.year
        mes_default = hoje.month
    else:
        if hoje.day <= DIA_FECHAMENTO_GLOBAL:
            ano_default = hoje.year
            mes_default = hoje.month
        else:
            proximo_mes_data = hoje + relativedelta(months=1)
            ano_default = proximo_mes_data.year
            mes_default = proximo_mes_data.month

    sorted_dates = sorted([d for d in all_relevant_dates if isinstance(d, datetime.date)]) 
    
    if not sorted_dates:
         sorted_dates = [hoje]

    anos_meses = {}
    for data in sorted_dates:
        if data.year not in anos_meses:
            anos_meses[data.year] = []
        if data.month not in anos_meses[data.year]:
            anos_meses[data.year].append(data.month)
            
    if ano_default not in anos_meses:
        anos_meses[ano_default] = []
    if mes_default not in anos_meses[ano_default]:
        anos_meses[ano_default].append(mes_default)
        anos_meses[ano_default].sort()
        
    anos_ordenados = sorted(anos_meses.keys(), reverse=True)
    if ano_default not in anos_ordenados:
         anos_ordenados.insert(0, ano_default) 
    elif anos_ordenados[0] != ano_default:
         if ano_default in anos_ordenados: anos_ordenados.remove(ano_default)
         anos_ordenados.insert(0, ano_default)

    anos_meses_ordenado = {ano: sorted(anos_meses[ano]) for ano in anos_ordenados}

    return anos_meses_ordenado, ano_default, mes_default

# --- VIEW DA LISTA PRINCIPAL (FATURA MENSAL) ---
@login_required
def lista_lancamentos(request):
    user = request.user
    anos_meses_disponiveis, ano_default, mes_default = get_anos_meses_disponiveis(user)
    
    cartoes_usuario = CartaoDeCredito.objects.filter(user=user)
    cartao_padrao_obj = cartoes_usuario.first()
    filtro_cartao_id = request.GET.get('cartao_id', cartao_padrao_obj.id if cartao_padrao_obj else None)
    
    ano_selecionado = int(request.GET.get('ano', ano_default))
    mes_selecionado = int(request.GET.get('mes', mes_default))

    if ano_selecionado not in anos_meses_disponiveis:
        ano_selecionado = ano_default
        mes_selecionado = mes_default 
    meses_do_ano_selecionado = anos_meses_disponiveis.get(ano_selecionado, [mes_default])
    if mes_selecionado not in meses_do_ano_selecionado:
        mes_selecionado = meses_do_ano_selecionado[0] if meses_do_ano_selecionado else mes_default

    filtro_local = request.GET.get('local', '')
    filtro_categoria_id = request.GET.get('categoria', '')
    filtro_descricao = request.GET.get('descricao', '') 
    
    lancamentos_do_mes = []
    total_fatura = Decimal('0.0')
    cartao_selecionado = None

    if filtro_cartao_id:
        try:
            cartao_selecionado = CartaoDeCredito.objects.get(id=filtro_cartao_id, user=user)
            todos_lancamentos = Lancamento.objects.filter(user=user, cartao=cartao_selecionado)
            
            fatura_bruta = []
            for lancamento in todos_lancamentos:
                if lancamento.num_parcelas > 0: valor_parcela = lancamento.valor_total / lancamento.num_parcelas
                else: valor_parcela = lancamento.valor_total
                
                primeiro_vencimento = calcular_vencimento_por_cartao(lancamento.data_compra, cartao_selecionado)
                    
                if primeiro_vencimento:
                    for i in range(lancamento.num_parcelas or 1):
                        data_vencimento_parcela = primeiro_vencimento + relativedelta(months=i)
                        if data_vencimento_parcela.month == mes_selecionado and data_vencimento_parcela.year == ano_selecionado:
                            item_fatura = {'original': lancamento, 'valor_parcela': valor_parcela, 'numero_parcela': f"{i + 1}/{lancamento.num_parcelas or 1}"}
                            fatura_bruta.append(item_fatura)
                            break
            
            for item in fatura_bruta:
                if filtro_local and filtro_local.lower() not in item['original'].local_compra.lower():
                    continue
                if filtro_categoria_id and item['original'].categoria.id != int(filtro_categoria_id):
                    continue
                descricao_original = item['original'].descricao or "" 
                if filtro_descricao and filtro_descricao.lower() not in descricao_original.lower():
                     continue
                lancamentos_do_mes.append(item)
                total_fatura += item['valor_parcela']

            lancamentos_do_mes.sort(key=lambda item: item['original'].data_compra)
        
        except CartaoDeCredito.DoesNotExist:
            messages.error(request, "Cartão selecionado não foi encontrado.")
    else:
        if cartoes_usuario.exists():
             messages.info(request, "Selecione um cartão para visualizar a fatura.")
        else:
             messages.warning(request, "Você ainda não cadastrou nenhum cartão de crédito. Vá em 'Meus Cartões' para adicionar um.")

    meses_nomes = {1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril', 5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto', 9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'}
    meses_para_filtro = {num: meses_nomes[num] for num in sorted(meses_do_ano_selecionado)}
    
    # --- MUDANÇA AQUI ---
    # Aplicamos a ordenação por macro_categoria e depois por nome
    todas_categorias = Categoria.objects.filter(user=request.user).order_by('macro_categoria', 'nome')
    
    context = {
        'lancamentos_do_mes': lancamentos_do_mes, 
        'total_fatura': total_fatura, 
        'anos': sorted(anos_meses_disponiveis.keys(), reverse=True), 
        'meses': meses_para_filtro.items(), 
        'mes_selecionado': mes_selecionado, 
        'ano_selecionado': ano_selecionado, 
        'mes_selecionado_nome': meses_nomes.get(mes_selecionado),
        'todas_categorias': todas_categorias,
        'cartoes_usuario': cartoes_usuario, 
        'cartao_selecionado': cartao_selecionado, 
        'cartao_selecionado_id': int(filtro_cartao_id) if filtro_cartao_id else None,
        'filtros': {
            'local': filtro_local,
            'categoria': int(filtro_categoria_id) if filtro_categoria_id else None,
            'descricao': filtro_descricao 
        }
    }
    return render(request, 'lancamentos/lista_lancamentos.html', context)

# --- VIEW DO EXTRATO COMPLETO ---
@login_required
def extrato_completo(request):
    user = request.user
    anos_meses_disponiveis, ano_default, mes_default = get_anos_meses_disponiveis(user)
    ano_selecionado = int(request.GET.get('ano', ano_default))
    mes_selecionado = int(request.GET.get('mes', mes_default))
    if ano_selecionado not in anos_meses_disponiveis:
        ano_selecionado = ano_default
    meses_do_ano_selecionado = anos_meses_disponiveis.get(ano_selecionado, [mes_default])
    if mes_selecionado not in meses_do_ano_selecionado:
        mes_selecionado = meses_do_ano_selecionado[0] if meses_do_ano_selecionado else mes_default
    filtro_local = request.GET.get('local', '')
    filtro_descricao = request.GET.get('descricao', '')
    filtro_categoria_id = request.GET.get('categoria', '')
    filtro_metodo = request.GET.get('metodo', '')
    lancamentos_qs = Lancamento.objects.filter(user=user, data_compra__year=ano_selecionado, data_compra__month=mes_selecionado)
    if filtro_local:
        lancamentos_qs = lancamentos_qs.filter(local_compra__icontains=filtro_local)
    if filtro_descricao:
        lancamentos_qs = lancamentos_qs.filter(descricao__icontains=filtro_descricao)
    if filtro_categoria_id:
        lancamentos_qs = lancamentos_qs.filter(categoria_id=filtro_categoria_id)
    if filtro_metodo:
        lancamentos_qs = lancamentos_qs.filter(metodo_pagamento=filtro_metodo)
    lancamentos = lancamentos_qs.order_by('data_compra')
    total_gastos = sum(l.valor_total for l in lancamentos)
    meses_nomes = {1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril', 5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto', 9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'}
    meses_para_filtro = {num: meses_nomes[num] for num in sorted(meses_do_ano_selecionado)}
    todas_categorias = Categoria.objects.filter(user=request.user).order_by('nome')
    todos_metodos = Lancamento.METODO_PAGAMENTO_CHOICES
    context = {'lancamentos': lancamentos, 'total_gastos': total_gastos, 'anos': sorted(anos_meses_disponiveis.keys(), reverse=True), 'meses': meses_para_filtro.items(), 'mes_selecionado': mes_selecionado, 'ano_selecionado': ano_selecionado, 'mes_selecionado_nome': meses_nomes.get(mes_selecionado), 'todas_categorias': todas_categorias, 'todos_metodos': todos_metodos, 'filtros': {'local': filtro_local, 'descricao': filtro_descricao, 'categoria': int(filtro_categoria_id) if filtro_categoria_id else None, 'metodo': filtro_metodo}}
    return render(request, 'lancamentos/extrato_completo.html', context)

# --- CRUD de Lançamentos ---
@login_required
def novo_lancamento(request):
    user = request.user
    if request.method == 'POST':
        local = request.POST.get('local')
        descricao = request.POST.get('descricao')
        data = request.POST.get('data')
        valor = request.POST.get('valor')
        parcelas_str = request.POST.get('parcelas', '1')
        categoria_id = request.POST.get('categoria')
        metodo_pagamento = request.POST.get('metodo_pagamento')
        cartao_id = request.POST.get('cartao_id') 
        
        try:
            parcelas = int(parcelas_str) if parcelas_str else 1
            if parcelas < 1: parcelas = 1
        except ValueError: parcelas = 1
        
        cartao_obj = None
        if metodo_pagamento == 'Crédito':
            if not cartao_id:
                messages.error(request, 'Para pagamentos no Crédito, você deve selecionar um cartão.')
                categorias = Categoria.objects.filter(user=user)
                cartoes = CartaoDeCredito.objects.filter(user=user)
                context = {'categorias': categorias, 'cartoes': cartoes, 'form_data': request.POST}
                return render(request, 'lancamentos/novo_lancamento.html', context)
            try:
                cartao_obj = CartaoDeCredito.objects.get(id=cartao_id, user=user)
            except CartaoDeCredito.DoesNotExist:
                messages.error(request, 'Cartão de crédito selecionado é inválido.')
                categorias = Categoria.objects.filter(user=user)
                cartoes = CartaoDeCredito.objects.filter(user=user)
                context = {'categorias': categorias, 'cartoes': cartoes, 'form_data': request.POST}
                return render(request, 'lancamentos/novo_lancamento.html', context)
            
        if metodo_pagamento != 'Crédito':
            parcelas = 1

        Lancamento.objects.create(
            local_compra=local, 
            descricao=descricao, 
            data_compra=data, 
            valor_total=valor, 
            num_parcelas=parcelas, 
            categoria_id=categoria_id, 
            metodo_pagamento=metodo_pagamento, 
            cartao=cartao_obj, 
            user=user
        )
        messages.success(request, 'Lançamento adicionado com sucesso!')
        next_url = request.POST.get('next', 'fatura_cartao')
        if 'extrato' in next_url:
             return redirect('extrato_completo')
        return redirect('fatura_cartao')
    else:
        categorias = Categoria.objects.filter(user=user)
        cartoes = CartaoDeCredito.objects.filter(user=user) 
        context = {'categorias': categorias, 'cartoes': cartoes} 
        context['next_page'] = request.META.get('HTTP_REFERER', 'fatura_cartao')
        return render(request, 'lancamentos/novo_lancamento.html', context)

@login_required
def editar_lancamento(request, pk):
    user = request.user
    lancamento = get_object_or_404(Lancamento, pk=pk, user=user)
    if request.method == 'POST':
        lancamento.local_compra = request.POST.get('local')
        lancamento.descricao = request.POST.get('descricao')
        lancamento.data_compra = request.POST.get('data')
        lancamento.valor_total = request.POST.get('valor')
        parcelas_str = request.POST.get('parcelas', '1')
        lancamento.categoria_id = request.POST.get('categoria')
        lancamento.metodo_pagamento = request.POST.get('metodo_pagamento')
        cartao_id = request.POST.get('cartao_id')
        
        try:
            parcelas = int(parcelas_str) if parcelas_str else 1
            if parcelas < 1: parcelas = 1
        except ValueError: parcelas = 1 
        lancamento.num_parcelas = parcelas

        if lancamento.metodo_pagamento != 'Crédito':
            lancamento.num_parcelas = 1
            lancamento.cartao = None
        else:
            cartao_obj = None
            if not cartao_id:
                messages.error(request, 'Para pagamentos no Crédito, você deve selecionar um cartão.')
                categorias = Categoria.objects.filter(user=user)
                cartoes = CartaoDeCredito.objects.filter(user=user)
                context = {'lancamento': lancamento, 'categorias': categorias, 'cartoes': cartoes}
                return render(request, 'lancamentos/novo_lancamento.html', context)
            if cartao_id:
                try:
                    cartao_obj = CartaoDeCredito.objects.get(id=cartao_id, user=user)
                except CartaoDeCredito.DoesNotExist:
                    messages.error(request, 'Cartão de crédito selecionado é inválido.')
                    categorias = Categoria.objects.filter(user=user)
                    cartoes = CartaoDeCredito.objects.filter(user=user)
                    context = {'lancamento': lancamento, 'categorias': categorias, 'cartoes': cartoes}
                    return render(request, 'lancamentos/novo_lancamento.html', context)
            lancamento.cartao = cartao_obj 

        lancamento.save()
        messages.success(request, 'Lançamento atualizado com sucesso!')
        next_url = request.POST.get('next', 'fatura_cartao')
        if 'extrato' in next_url:
             return redirect('extrato_completo')
        return redirect('fatura_cartao')
    else:
        categorias = Categoria.objects.filter(user=user)
        cartoes = CartaoDeCredito.objects.filter(user=user)
        context = {'lancamento': lancamento, 'categorias': categorias, 'cartoes': cartoes}
        context['next_page'] = request.META.get('HTTP_REFERER', 'fatura_cartao')
        return render(request, 'lancamentos/novo_lancamento.html', context)

@login_required
def deletar_lancamento(request, pk):
    lancamento = get_object_or_404(Lancamento, pk=pk, user=request.user)
    redirect_url_name = 'fatura_cartao' 
    referer = request.META.get('HTTP_REFERER')
    if referer:
        if 'extrato' in referer:
            redirect_url_name = 'extrato_completo'
            
    if request.method == 'POST':
        lancamento.delete()
        messages.success(request, 'Lançamento deletado com sucesso.')
        return redirect(redirect_url_name)
        
    context = {'lancamento': lancamento}
    return render(request, 'lancamentos/deletar_confirm.html', context)

# --- CRUD de Receitas ---
@login_required
def lista_receitas(request):
    user = request.user
    anos_meses_disponiveis, ano_default, mes_default = get_anos_meses_disponiveis(user)
    ano_selecionado = int(request.GET.get('ano', ano_default))
    mes_selecionado = int(request.GET.get('mes', mes_default))
    if ano_selecionado not in anos_meses_disponiveis:
        ano_selecionado = ano_default
    meses_do_ano_selecionado = anos_meses_disponiveis.get(ano_selecionado, [mes_default])
    if mes_selecionado not in meses_do_ano_selecionado:
        mes_selecionado = meses_do_ano_selecionado[0] if meses_do_ano_selecionado else mes_default
    receitas = Receita.objects.filter(user=user, data_recebimento__year=ano_selecionado, data_recebimento__month=mes_selecionado).order_by('data_recebimento')
    total_receitas = sum(r.valor for r in receitas) if receitas else Decimal('0.0')
    meses_nomes = {1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril', 5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto', 9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'}
    meses_para_filtro = {num: meses_nomes[num] for num in sorted(meses_do_ano_selecionado)}
    context = {'receitas': receitas, 'total_receitas': total_receitas, 'anos': sorted(anos_meses_disponiveis.keys(), reverse=True), 'meses': meses_para_filtro.items(), 'mes_selecionado': mes_selecionado, 'ano_selecionado': ano_selecionado, 'mes_selecionado_nome': meses_nomes.get(mes_selecionado)}
    return render(request, 'lancamentos/lista_receitas.html', context)

@login_required
def nova_receita(request):
    user = request.user
    if request.method == 'POST':
        descricao = request.POST.get('descricao')
        valor = request.POST.get('valor')
        data_recebimento = request.POST.get('data_recebimento')
        Receita.objects.create(descricao=descricao, valor=valor, data_recebimento=data_recebimento, user=user)
        messages.success(request, 'Receita adicionada com sucesso!')
        return redirect('lista_receitas')
    return render(request, 'lancamentos/receita_form.html')

@login_required
def editar_receita(request, pk):
    user = request.user
    receita = get_object_or_404(Receita, pk=pk, user=user)
    if request.method == 'POST':
        receita.descricao = request.POST.get('descricao')
        receita.valor = request.POST.get('valor')
        receita.data_recebimento = request.POST.get('data_recebimento')
        receita.save()
        messages.success(request, 'Receita atualizada com sucesso!')
        return redirect('lista_receitas')
    else:
        context = {'receita': receita}
        return render(request, 'lancamentos/receita_form.html', context)

@login_required
def deletar_receita(request, pk):
    user = request.user
    receita = get_object_or_404(Receita, pk=pk, user=user)
    if request.method == 'POST':
        receita.delete()
        messages.success(request, 'Receita deletada com sucesso!')
        return redirect('lista_receitas')
    context = {'receita': receita}
    return render(request, 'lancamentos/receita_deletar_confirm.html', context)

# --- View de Registro ---
def registrar(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            novo_usuario = form.save()
            # Perfil.objects.create(user=novo_usuario) # Sinal cuida disso
            categorias_padrao = CategoriaPadrao.objects.all()
            for cat_padrao in categorias_padrao:
                Categoria.objects.create(nome=cat_padrao.nome, macro_categoria=cat_padrao.macro_categoria, exemplos=cat_padrao.exemplos, user=novo_usuario)
            return redirect('login') 
    else:
        form = UserCreationForm()
    context = {'form': form}
    return render(request, 'registration/registrar.html', context)

# --- DASHBOARDS ---
@login_required
def dashboard(request):
    user = request.user
    anos_meses_disponiveis, ano_default, mes_default = get_anos_meses_disponiveis(user)
    ano_selecionado = int(request.GET.get('ano', ano_default))
    mes_selecionado = int(request.GET.get('mes', mes_default))
    metodos_selecionados = request.GET.getlist('metodos')
    if ano_selecionado not in anos_meses_disponiveis:
        ano_selecionado = ano_default
    meses_do_ano_selecionado = anos_meses_disponiveis.get(ano_selecionado, [mes_default])
    if mes_selecionado not in meses_do_ano_selecionado:
        mes_selecionado = meses_do_ano_selecionado[0] if meses_do_ano_selecionado else mes_default
    if not metodos_selecionados:
        metodos_considerados = ['Crédito', 'Débito', 'PIX', 'Dinheiro']
    else:
        metodos_considerados = metodos_selecionados
    gastos_agrupados = {}
    metodos_avista = [m for m in metodos_considerados if m != 'Crédito']
    if metodos_avista:
        gastos_avista = Lancamento.objects.filter(user=user, data_compra__year=ano_selecionado, data_compra__month=mes_selecionado, metodo_pagamento__in=metodos_avista).values('categoria__nome').annotate(total=Sum('valor_total'))
        for item in gastos_avista:
            gastos_agrupados[item['categoria__nome']] = Decimal(item['total'] or '0.0') 
    if 'Crédito' in metodos_considerados:
        lancamentos_credito = Lancamento.objects.filter(user=user, metodo_pagamento='Crédito', cartao__isnull=False).select_related('cartao', 'categoria')
        for lancamento in lancamentos_credito:
            if lancamento.num_parcelas > 0: valor_parcela = lancamento.valor_total / lancamento.num_parcelas
            else: valor_parcela = lancamento.valor_total
            primeiro_vencimento = calcular_vencimento_por_cartao(lancamento.data_compra, lancamento.cartao)
            if primeiro_vencimento:
                for i in range(lancamento.num_parcelas or 1):
                    data_vencimento_parcela = primeiro_vencimento + relativedelta(months=i)
                    if data_vencimento_parcela.month == mes_selecionado and data_vencimento_parcela.year == ano_selecionado:
                        categoria_nome = lancamento.categoria.nome
                        gastos_agrupados[categoria_nome] = gastos_agrupados.get(categoria_nome, Decimal('0.0')) + valor_parcela
                        break
    labels = list(gastos_agrupados.keys())
    data = [float(valor) for valor in gastos_agrupados.values()]
    meses_nomes = {1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril', 5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto', 9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'}
    meses_para_filtro = {num: meses_nomes[num] for num in sorted(meses_do_ano_selecionado)}
    context = {'labels': json.dumps(labels), 'data': json.dumps(data), 'anos': sorted(anos_meses_disponiveis.keys(), reverse=True), 'meses': meses_para_filtro.items(), 'mes_selecionado': mes_selecionado, 'ano_selecionado': ano_selecionado, 'mes_selecionado_nome': meses_nomes.get(mes_selecionado), 'metodos_selecionados': metodos_considerados}
    return render(request, 'lancamentos/dashboard.html', context)

@login_required
def dashboard_macro(request):
    user = request.user
    anos_meses_disponiveis, ano_default, mes_default = get_anos_meses_disponiveis(user)
    ano_selecionado = int(request.GET.get('ano', ano_default))
    mes_selecionado = int(request.GET.get('mes', mes_default))
    metodos_selecionados = request.GET.getlist('metodos')
    if ano_selecionado not in anos_meses_disponiveis:
        ano_selecionado = ano_default
    meses_do_ano_selecionado = anos_meses_disponiveis.get(ano_selecionado, [mes_default])
    if mes_selecionado not in meses_do_ano_selecionado:
        mes_selecionado = meses_do_ano_selecionado[0] if meses_do_ano_selecionado else mes_default
    if not metodos_selecionados:
        metodos_considerados = ['Crédito', 'Débito', 'PIX', 'Dinheiro']
    else:
        metodos_considerados = metodos_selecionados
    gastos_agrupados = {}
    metodos_avista = [m for m in metodos_considerados if m != 'Crédito']
    if metodos_avista:
        gastos_avista = Lancamento.objects.filter(user=user, data_compra__year=ano_selecionado, data_compra__month=mes_selecionado, metodo_pagamento__in=metodos_avista).values('categoria__macro_categoria').annotate(total=Sum('valor_total'))
        for item in gastos_avista:
            gastos_agrupados[item['categoria__macro_categoria']] = Decimal(item['total'] or '0.0')
    if 'Crédito' in metodos_considerados:
        lancamentos_credito = Lancamento.objects.filter(user=user, metodo_pagamento='Crédito', cartao__isnull=False).select_related('cartao', 'categoria')
        for lancamento in lancamentos_credito:
            if lancamento.num_parcelas > 0: valor_parcela = lancamento.valor_total / lancamento.num_parcelas
            else: valor_parcela = lancamento.valor_total
            primeiro_vencimento = calcular_vencimento_por_cartao(lancamento.data_compra, lancamento.cartao)
            if primeiro_vencimento:
                for i in range(lancamento.num_parcelas or 1):
                    data_vencimento_parcela = primeiro_vencimento + relativedelta(months=i)
                    if data_vencimento_parcela.month == mes_selecionado and data_vencimento_parcela.year == ano_selecionado:
                        macro_nome = lancamento.categoria.macro_categoria
                        gastos_agrupados[macro_nome] = gastos_agrupados.get(macro_nome, Decimal('0.0')) + valor_parcela
                        break
    labels = list(gastos_agrupados.keys())
    data = [float(valor) for valor in gastos_agrupados.values()]
    meses_nomes = {1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril', 5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto', 9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'}
    meses_para_filtro = {num: meses_nomes[num] for num in sorted(meses_do_ano_selecionado)}
    context = {'labels': json.dumps(labels), 'data': json.dumps(data), 'anos': sorted(anos_meses_disponiveis.keys(), reverse=True), 'meses': meses_para_filtro.items(), 'mes_selecionado': mes_selecionado, 'ano_selecionado': ano_selecionado, 'mes_selecionado_nome': meses_nomes.get(mes_selecionado), 'metodos_selecionados': metodos_considerados}
    return render(request, 'lancamentos/dashboard_macro.html', context)

# --- APIs ---
@login_required
def api_detalhes_categoria(request):
    user = request.user
    mes = int(request.GET.get('mes'))
    ano = int(request.GET.get('ano'))
    categoria_nome = request.GET.get('categoria')
    metodos_query = request.GET.get('metodos', '') 
    metodos = metodos_query.split(',') if metodos_query else ['Crédito', 'Débito', 'PIX', 'Dinheiro']
    try:
        categoria = Categoria.objects.get(user=user, nome=categoria_nome)
    except Categoria.DoesNotExist:
        return JsonResponse({'error': 'Categoria não encontrada'}, status=404)
    detalhes_lancamentos = []
    metodos_avista = [m for m in metodos if m != 'Crédito']
    if metodos_avista:
        lancamentos_avista = Lancamento.objects.filter(user=user, categoria=categoria, data_compra__year=ano, data_compra__month=mes, metodo_pagamento__in=metodos_avista)
        for lancamento in lancamentos_avista:
             detalhes_lancamentos.append({'local': lancamento.local_compra, 'data_compra': lancamento.data_compra.strftime('%d/%m/%Y'), 'descricao': lancamento.descricao, 'valor_total': f'{lancamento.valor_total:.2f}'.replace('.', ',')})
    if 'Crédito' in metodos:
        lancamentos_credito = Lancamento.objects.filter(user=user, categoria=categoria, metodo_pagamento='Crédito', cartao__isnull=False).select_related('cartao')
        for lancamento in lancamentos_credito:
            if lancamento.num_parcelas > 0: valor_parcela = lancamento.valor_total / lancamento.num_parcelas
            else: valor_parcela = lancamento.valor_total
            primeiro_vencimento = calcular_vencimento_por_cartao(lancamento.data_compra, lancamento.cartao)
            if primeiro_vencimento:
                for i in range(lancamento.num_parcelas or 1):
                    data_vencimento_parcela = primeiro_vencimento + relativedelta(months=i)
                    if data_vencimento_parcela.month == mes and data_vencimento_parcela.year == ano:
                        detalhes_lancamentos.append({'local': lancamento.local_compra, 'data_compra': lancamento.data_compra.strftime('%d/%m/%Y'), 'descricao': lancamento.descricao, 'valor_parcela': f'{valor_parcela:.2f}'.replace('.', ',')})
                        break
    detalhes_lancamentos.sort(key=lambda x: datetime.datetime.strptime(x['data_compra'], '%d/%m/%Y').date())
    return JsonResponse({'lancamentos': detalhes_lancamentos})

@login_required
def api_detalhes_macro_categoria(request):
    user = request.user
    mes = int(request.GET.get('mes'))
    ano = int(request.GET.get('ano'))
    macro_categoria_nome = request.GET.get('macro_categoria')
    metodos_query = request.GET.get('metodos', '')
    metodos = metodos_query.split(',') if metodos_query else ['Crédito', 'Débito', 'PIX', 'Dinheiro']
    detalhes_lancamentos = []
    metodos_avista = [m for m in metodos if m != 'Crédito']
    if metodos_avista:
         lancamentos_avista = Lancamento.objects.filter(user=user, categoria__macro_categoria=macro_categoria_nome, data_compra__year=ano, data_compra__month=mes, metodo_pagamento__in=metodos_avista)
         for lancamento in lancamentos_avista:
             detalhes_lancamentos.append({'local': lancamento.local_compra, 'data_compra': lancamento.data_compra.strftime('%d/%m/%Y'), 'descricao': lancamento.descricao, 'valor_total': f'{lancamento.valor_total:.2f}'.replace('.', ',')})
    if 'Crédito' in metodos:
        lancamentos_credito = Lancamento.objects.filter(user=user, categoria__macro_categoria=macro_categoria_nome, metodo_pagamento='Crédito', cartao__isnull=False).select_related('cartao')
        for lancamento in lancamentos_credito:
            if lancamento.num_parcelas > 0: valor_parcela = lancamento.valor_total / lancamento.num_parcelas
            else: valor_parcela = lancamento.valor_total
            primeiro_vencimento = calcular_vencimento_por_cartao(lancamento.data_compra, lancamento.cartao)
            if primeiro_vencimento:
                for i in range(lancamento.num_parcelas or 1):
                    data_vencimento_parcela = primeiro_vencimento + relativedelta(months=i)
                    if data_vencimento_parcela.month == mes and data_vencimento_parcela.year == ano:
                        detalhes_lancamentos.append({'local': lancamento.local_compra, 'data_compra': lancamento.data_compra.strftime('%d/%m/%Y'), 'descricao': lancamento.descricao, 'valor_parcela': f'{valor_parcela:.2f}'.replace('.', ',')})
                        break
    detalhes_lancamentos.sort(key=lambda x: datetime.datetime.strptime(x['data_compra'], '%d/%m/%Y').date())
    return JsonResponse({'lancamentos': detalhes_lancamentos})

# --- VIEW DO BALANÇO MENSAL (ATUALIZADA) ---
@login_required
def balanco_mensal(request):
    user = request.user
    anos_meses_disponiveis, ano_default, mes_default = get_anos_meses_disponiveis(user)
    ano_selecionado = int(request.GET.get('ano', ano_default))
    mes_selecionado = int(request.GET.get('mes', mes_default))
    if ano_selecionado not in anos_meses_disponiveis:
        ano_selecionado = ano_default
    meses_do_ano_selecionado = anos_meses_disponiveis.get(ano_selecionado, [mes_default])
    if mes_selecionado not in meses_do_ano_selecionado:
        mes_selecionado = meses_do_ano_selecionado[0] if meses_do_ano_selecionado else mes_default
    receitas_mes = Receita.objects.filter(user=user, data_recebimento__year=ano_selecionado, data_recebimento__month=mes_selecionado)
    total_receitas = sum(r.valor for r in receitas_mes) if receitas_mes else Decimal('0.0')
    
    # MUDANÇA: Lógica de faturas agora soma TODAS as faturas de TODOS os cartões que vencem no mês
    lancamentos_credito = Lancamento.objects.filter(user=user, metodo_pagamento='Crédito', cartao__isnull=False).select_related('cartao')
    total_fatura_mes = Decimal('0.0')
    for lancamento in lancamentos_credito:
        if lancamento.num_parcelas > 0: valor_parcela = lancamento.valor_total / lancamento.num_parcelas
        else: valor_parcela = lancamento.valor_total
        
        primeiro_vencimento = calcular_vencimento_por_cartao(lancamento.data_compra, lancamento.cartao)
        
        if primeiro_vencimento:
            for i in range(lancamento.num_parcelas or 1):
                data_vencimento_parcela = primeiro_vencimento + relativedelta(months=i)
                if data_vencimento_parcela.month == mes_selecionado and data_vencimento_parcela.year == ano_selecionado:
                    total_fatura_mes += valor_parcela
                    break
                    
    despesas_avista = Lancamento.objects.filter(user=user, data_compra__year=ano_selecionado, data_compra__month=mes_selecionado).exclude(metodo_pagamento='Crédito')
    total_despesas_avista = sum(d.valor_total for d in despesas_avista) if despesas_avista else Decimal('0.0')
    total_despesas = total_fatura_mes + total_despesas_avista
    saldo = total_receitas - total_despesas
    meses_nomes = {1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril', 5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto', 9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'}
    meses_para_filtro = {num: meses_nomes[num] for num in sorted(meses_do_ano_selecionado)}
    context = {'total_receitas': total_receitas, 'total_despesas': total_despesas, 'saldo': saldo, 'anos': sorted(anos_meses_disponiveis.keys(), reverse=True), 'meses': meses_para_filtro.items(), 'mes_selecionado': mes_selecionado, 'ano_selecionado': ano_selecionado, 'mes_selecionado_nome': meses_nomes.get(mes_selecionado), 'total_fatura_mes': total_fatura_mes, 'total_despesas_avista': total_despesas_avista}
    return render(request, 'lancamentos/balanco_mensal.html', context)

# --- VIEWS PARA O CRUD DE CARTÕES ---
@login_required
def lista_cartoes(request):
    user = request.user
    cartoes = CartaoDeCredito.objects.filter(user=user)
    
    cartoes_com_limite = []
    hoje = datetime.date.today()
    
    for cartao in cartoes:
        try: 
            vencimento_este_mes = hoje.replace(day=cartao.dia_vencimento)
        except ValueError:
             primeiro_dia_proximo_mes_temp = hoje.replace(day=1) + relativedelta(months=1)
             vencimento_este_mes = primeiro_dia_proximo_mes_temp - relativedelta(days=1)
         
        if hoje.day > cartao.dia_vencimento:
            data_referencia = vencimento_este_mes + relativedelta(months=1)
        else:
            data_referencia = vencimento_este_mes
        
        lancamentos_credito = Lancamento.objects.filter(user=user, cartao=cartao)
        faturas_por_mes = {} 
        total_faturas_futuras = Decimal('0.0')

        for lancamento in lancamentos_credito:
            if lancamento.num_parcelas > 0: valor_parcela = lancamento.valor_total / lancamento.num_parcelas
            else: valor_parcela = lancamento.valor_total
                 
            primeiro_vencimento = calcular_vencimento_por_cartao(lancamento.data_compra, cartao) 
            if primeiro_vencimento:
                for i in range(lancamento.num_parcelas or 1): 
                    data_vencimento_parcela = primeiro_vencimento + relativedelta(months=i)
                    
                    if data_vencimento_parcela >= data_referencia:
                        total_faturas_futuras += valor_parcela
                        
                        mes_key = data_vencimento_parcela.strftime('%Y-%m')
                        faturas_por_mes[mes_key] = faturas_por_mes.get(mes_key, Decimal('0.0')) + valor_parcela
        
        limite_disponivel = cartao.limite - total_faturas_futuras
        
        # MUDANÇA: Formata o resumo das faturas para o template
        meses_nomes_map = {1: 'Jan', 2: 'Fev', 3: 'Mar', 4: 'Abr', 5: 'Maio', 6: 'Jun', 7: 'Jul', 8: 'Ago', 9: 'Set', 10: 'Out', 11: 'Nov', 12: 'Dez'}
        resumo_faturas = []
        for mes_key, total in sorted(faturas_por_mes.items()): 
            try:
                ano, mes = map(int, mes_key.split('-'))
                resumo_faturas.append({
                    'mes_ano_str': f"{meses_nomes_map.get(mes, '?')}/{ano}", 
                    'total': total
                })
            except ValueError:
                 print(f"Erro ao processar chave de mês: {mes_key}") 

        cartao.total_faturas_futuras = total_faturas_futuras
        cartao.limite_disponivel = limite_disponivel
        cartao.resumo_faturas = resumo_faturas # Anexa o resumo
        
        cartoes_com_limite.append(cartao)

    context = {
        'cartoes_com_limite': cartoes_com_limite
    }
    return render(request, 'lancamentos/lista_cartoes.html', context)

@login_required
def novo_cartao(request):
    if request.method == 'POST':
        nome = request.POST.get('nome')
        limite = request.POST.get('limite')
        dia_vencimento = request.POST.get('dia_vencimento')
        dia_fechamento = request.POST.get('dia_fechamento')
        
        if not all([nome, limite, dia_vencimento, dia_fechamento]):
            messages.error(request, 'Todos os campos são obrigatórios.')
            return render(request, 'lancamentos/cartao_form.html', {'form_data': request.POST})
        
        try:
            CartaoDeCredito.objects.create(
                user=request.user,
                nome=nome,
                limite=Decimal(limite.replace(',', '.')),
                dia_vencimento=int(dia_vencimento),
                dia_fechamento=int(dia_fechamento)
            )
            messages.success(request, 'Cartão de crédito adicionado com sucesso!')
            return redirect('lista_cartoes')
        except (ValueError, Decimal.InvalidOperation):
            messages.error(request, 'Valores de limite, dia de vencimento ou fechamento são inválidos.')
            return render(request, 'lancamentos/cartao_form.html', {'form_data': request.POST})
        
    return render(request, 'lancamentos/cartao_form.html')

@login_required
def editar_cartao(request, pk):
    cartao = get_object_or_404(CartaoDeCredito, pk=pk, user=request.user)
    if request.method == 'POST':
        try:
            cartao.nome = request.POST.get('nome')
            cartao.limite = Decimal(request.POST.get('limite').replace(',', '.'))
            cartao.dia_vencimento = int(request.POST.get('dia_vencimento'))
            cartao.dia_fechamento = int(request.POST.get('dia_fechamento'))
            
            if not all([cartao.nome, cartao.limite, cartao.dia_vencimento, cartao.dia_fechamento]):
                 messages.error(request, 'Todos os campos são obrigatórios.')
                 context = {'cartao': cartao} 
                 return render(request, 'lancamentos/cartao_form.html', context)
                 
            cartao.save()
            messages.success(request, 'Cartão de crédito atualizado com sucesso!')
            return redirect('lista_cartoes')
        except (ValueError, Decimal.InvalidOperation):
            messages.error(request, 'Valores de limite, dia de vencimento ou fechamento são inválidos.')
            context = {'cartao': cartao}
            return render(request, 'lancamentos/cartao_form.html', context)
    else:
        context = {'cartao': cartao}
        return render(request, 'lancamentos/cartao_form.html', context)

@login_required
def deletar_cartao(request, pk):
    cartao = get_object_or_404(CartaoDeCredito, pk=pk, user=request.user)
    
    lancamentos_count = Lancamento.objects.filter(cartao=cartao).count()
    if lancamentos_count > 0:
        messages.error(request, f'Não é possível deletar este cartão. Ele está associado a {lancamentos_count} lançamento(s). Por favor, edite esses lançamentos e associe-os a outro cartão antes de deletar.')
        context = {'cartao': cartao, 'erro_lancamentos': True, 'lancamentos_count': lancamentos_count}
        return render(request, 'lancamentos/cartao_deletar_confirm.html', context)

    if request.method == 'POST':
        cartao.delete()
        messages.success(request, 'Cartão de crédito deletado com sucesso.')
        return redirect('lista_cartoes')
        
    context = {'cartao': cartao, 'erro_lancamentos': False}
    return render(request, 'lancamentos/cartao_deletar_confirm.html', context)