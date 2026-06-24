from django.urls import path

from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('dashboard/', views.dashboard, name='dashboard'),

    path('users/', views.user_list, name='user_list'),
    path('users/create/', views.user_create, name='user_create'),
    path('users/<int:user_id>/edit/', views.user_update, name='user_update'),
    path('users/<int:user_id>/delete/', views.user_delete, name='user_delete'),

    path('learners/', views.learner_list, name='learner_list'),
    path('learners/create/', views.learner_create, name='learner_create'),
    path('learners/<int:pk>/edit/', views.learner_update, name='learner_update'),
    path('learners/<int:pk>/delete/', views.learner_delete, name='learner_delete'),

    path('competencies/', views.competency_list, name='competency_list'),
    path('competencies/create/', views.competency_create, name='competency_create'),
    path('competencies/<int:pk>/edit/', views.competency_update, name='competency_update'),
    path('competencies/<int:pk>/delete/', views.competency_delete, name='competency_delete'),

    path('tasks/', views.task_list, name='task_list'),
    path('tasks/create/', views.task_create, name='task_create'),
    path('tasks/<int:pk>/edit/', views.task_update, name='task_update'),
    path('tasks/<int:pk>/delete/', views.task_delete, name='task_delete'),

    path('results/', views.result_list, name='result_list'),
    path('results/create/', views.result_create, name='result_create'),
    path('results/<int:pk>/edit/', views.result_update, name='result_update'),
    path('results/<int:pk>/delete/', views.result_delete, name='result_delete'),

    path('reports/', views.report_view, name='report_view'),
    path('feedback/', views.feedback_view, name='feedback_view'),
]
