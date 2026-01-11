"""
URL configuration for chat project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from users import views as user_views
urlpatterns = [
    path('admin/', admin.site.urls),
    path('register/', user_views.register, name = 'register'), 
    path('verify-email/', user_views.verify_email, name='verify_email'),
    path('chat/', include('room.urls')), 
    path('login/', auth_views.LoginView.as_view(template_name = 'users/login.html'), name = 'login'),
    path('logout/', auth_views.LogoutView.as_view(template_name = 'users/logout.html'), name = 'logout'), 
    path('matchmaking/', include('matchmaking.urls')), 
    path('', user_views.dashboard, name='dashboard'),
    path('profile/', user_views.profile, name='profile'),
    path('ajax/get-states/', user_views.get_states, name='get_states'),
    path('ajax/report-user/', user_views.report_user, name='report_user'),
    path('ajax/verify-gender/', user_views.verify_gender, name='verify_gender'),
    path('setup-admin/', user_views.create_superuser_temp, name='create_superuser_temp'), # Temp Admin Creation
]

from django.conf import settings
from django.conf.urls.static import static

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
