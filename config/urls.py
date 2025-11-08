# Dentro de config/urls.py
from django.contrib import admin
from django.urls import path, include # Adicione 'include'

urlpatterns = [
    path('admin/', admin.site.urls),

    # 1. Adiciona as URLs de login/logout (ex: /accounts/login/)
    path('accounts/', include('django.contrib.auth.urls')), 
    
    # 2. Esta linha diz: "Qualquer outra URL (representada pelo ' '), 
    #    vá procurar as regras dentro do arquivo 'lancamentos.urls' "
    path('', include('lancamentos.urls')), 
]