from django.contrib import admin

from .models import AssessmentResult, AssessmentTask, Competency, LearnerProfile, UserAccount


@admin.register(UserAccount)
class UserAccountAdmin(admin.ModelAdmin):
	list_display = ('user', 'role', 'status')
	list_filter = ('role', 'status')
	search_fields = ('user__username', 'user__first_name', 'user__last_name')


@admin.register(LearnerProfile)
class LearnerProfileAdmin(admin.ModelAdmin):
	list_display = ('admission_number', 'full_name', 'gender', 'class_name')
	list_filter = ('gender', 'class_name')
	search_fields = ('admission_number', 'full_name', 'class_name')


@admin.register(Competency)
class CompetencyAdmin(admin.ModelAdmin):
	list_display = ('competency_code', 'competency_name', 'created_by')
	search_fields = ('competency_code', 'competency_name')


@admin.register(AssessmentTask)
class AssessmentTaskAdmin(admin.ModelAdmin):
	list_display = ('task_title', 'competency', 'teacher', 'task_date')
	list_filter = ('task_date', 'competency')
	search_fields = ('task_title', 'competency__competency_code')


@admin.register(AssessmentResult)
class AssessmentResultAdmin(admin.ModelAdmin):
	list_display = ('learner', 'task', 'teacher', 'score', 'rating', 'assessment_date')
	list_filter = ('assessment_date', 'rating', 'task__competency')
	search_fields = ('learner__full_name', 'task__task_title', 'rating')
