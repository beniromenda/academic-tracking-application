from django.contrib import admin

from .models import AssessmentResult, AssessmentTask, Competency, LearnerProfile, LearnerReportFeedback, TeacherLearnerRecord, UserAccount


@admin.register(UserAccount)
class UserAccountAdmin(admin.ModelAdmin):
	list_display = ('user', 'teacher_id', 'role', 'status')
	list_filter = ('role', 'status')
	search_fields = ('user__username', 'user__first_name', 'user__last_name')


@admin.register(LearnerProfile)
class LearnerProfileAdmin(admin.ModelAdmin):
	list_display = ('admission_number', 'full_name', 'gender', 'class_name')
	list_filter = ('gender', 'class_name')
	search_fields = ('admission_number', 'full_name', 'class_name')


@admin.register(TeacherLearnerRecord)
class TeacherLearnerRecordAdmin(admin.ModelAdmin):
	list_display = ('teacher', 'learner_profile', 'created_at')
	list_filter = ('teacher',)
	search_fields = ('teacher__username', 'learner_profile__full_name', 'learner_profile__admission_number')


@admin.register(Competency)
class CompetencyAdmin(admin.ModelAdmin):
	list_display = ('competency_code', 'competency_name', 'created_by', 'created_at')
	search_fields = ('competency_code', 'competency_name', 'learning_outcome')


@admin.register(AssessmentTask)
class AssessmentTaskAdmin(admin.ModelAdmin):
	list_display = ('task_name', 'competency', 'created_by', 'created_at')
	list_filter = ('created_at', 'competency')
	search_fields = ('task_name', 'competency__competency_code', 'competency__competency_name', 'description')


@admin.register(AssessmentResult)
class AssessmentResultAdmin(admin.ModelAdmin):
	list_display = ('learner', 'teacher_learner_record', 'task', 'created_by', 'score', 'cbc_rating', 'mastery_status', 'created_at')
	list_filter = ('mastery_status', 'cbc_rating', 'task__competency')
	search_fields = ('learner__full_name', 'task__task_name', 'cbc_rating')


@admin.register(LearnerReportFeedback)
class LearnerReportFeedbackAdmin(admin.ModelAdmin):
	list_display = ('learner', 'teacher_learner_record', 'competency', 'teacher', 'overall_competency_status', 'is_available_for_learner', 'updated_at')
	list_filter = ('overall_competency_status', 'is_available_for_learner', 'competency')
	search_fields = ('learner__full_name', 'competency__competency_code', 'competency__competency_name', 'teacher__username')
