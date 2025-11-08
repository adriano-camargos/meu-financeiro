# Dentro de lancamentos/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('', views.lista_lancamentos, name='fatura_cartao'),
    path('extrato/', views.extrato_completo, name='extrato_completo'),
    path('balanco/', views.balanco_mensal, name='balanco_mensal'),
    
    path('novo/', views.novo_lancamento, name='novo_lancamento'),
    path('editar/<int:pk>/', views.editar_lancamento, name='editar_lancamento'),
    path('deletar/<int:pk>/', views.deletar_lancamento, name='deletar_lancamento'),
    
    path('receitas/', views.lista_receitas, name='lista_receitas'),
    path('receitas/nova/', views.nova_receita, name='nova_receita'),
    path('receitas/editar/<int:pk>/', views.editar_receita, name='editar_receita'),
    path('receitas/deletar/<int:pk>/', views.deletar_receita, name='deletar_receita'),
    
    # --- NOVAS URLS PARA GERENCIAR CARTÕES ---
    path('cartoes/', views.lista_cartoes, name='lista_cartoes'),
    path('cartoes/novo/', views.novo_cartao, name='novo_cartao'),
    path('cartoes/editar/<int:pk>/', views.editar_cartao, name='editar_cartao'),
    path('cartoes/deletar/<int:pk>/', views.deletar_cartao, name='deletar_cartao'),
    
    path('cadastro/', views.registrar, name='registrar'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('dashboard-macro/', views.dashboard_macro, name='dashboard_macro'),
    path('api/detalhes-categoria/', views.api_detalhes_categoria, name='api_detalhes_categoria'),
    path('api/detalhes-macro-categoria/', views.api_detalhes_macro_categoria, name='api_detalhes_macro_categoria'),
]