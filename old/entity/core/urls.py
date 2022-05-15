from django.urls import path
from . import views

app_name = "entity"

urlpatterns = [
    path('', views.view),
    path('comments/<int:pk>', views.comment_thread),
    path('comments/<int:pk>/delete', views.comment_delete, name="delete_comment"),
]