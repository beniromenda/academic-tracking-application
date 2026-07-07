from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import IntegrityError, connection, transaction
from django.db.models import Avg, Count, Max, Min, Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.forms import formset_factory
from django.urls import reverse

from .forms import (
	BulkAssessmentResultEntryForm,
	AssessmentResultForm,
	AssessmentTaskForm,
	CompetencyForm,
	LearnerAccountCreateForm,
	TeacherLearnerCompetencyAssignmentForm,
	TeacherAccountCreateForm,
	SubjectForm,
	SubjectSelectionForm,
	UserAccountCreateForm,
	UserAccountUpdateForm,
)
from .models import AssessmentResult, AssessmentTask, Competency, LearnerProfile, LearnerReportFeedback, Subject, TeacherLearnerCompetencyAssignment, TeacherLearnerRecord, UserAccount


ACTIVE_SUBJECT_SESSION_KEY = 'active_subject_id'


def _default_role_for_user(user):
	if user.is_superuser:
		return UserAccount.ROLE_ADMINISTRATOR
	if user.is_staff:
		return UserAccount.ROLE_TEACHER
	return UserAccount.ROLE_LEARNER


def _ensure_account(user):
	account, _ = UserAccount.objects.get_or_create(
		user=user,
		defaults={
			'role': _default_role_for_user(user),
			'status': UserAccount.STATUS_ACTIVE if user.is_active else UserAccount.STATUS_INACTIVE,
		},
	)
	return account

def _role_for(user):
	if not user.is_authenticated:
		return None
	return getattr(getattr(user, 'account', None), 'role', UserAccount.ROLE_ADMINISTRATOR if user.is_superuser else None)


def _is_admin(user):
	return user.is_superuser or _role_for(user) == UserAccount.ROLE_ADMINISTRATOR


def _is_teacher_or_admin(user):
	role = _role_for(user)
	return user.is_superuser or role in {UserAccount.ROLE_ADMINISTRATOR, UserAccount.ROLE_TEACHER}


def _is_teacher(user):
	return _role_for(user) == UserAccount.ROLE_TEACHER and not user.is_superuser


def _deny_if_not(condition):
	if not condition:
		return HttpResponseForbidden('You are not allowed to access this page.')
	return None


def _teacher_owned(queryset, user, field_name='created_by'):
	if _is_teacher(user):
		return queryset.filter(**{field_name: user})
	return queryset


def _teacher_learner_records(user):
	queryset = TeacherLearnerRecord.objects.select_related('teacher', 'learner_profile', 'learner_profile__user_account__user')
	if _is_teacher(user):
		return queryset.filter(teacher=user)
	return queryset


def _teacher_owned_results(queryset, user):
	if _is_teacher(user):
		return queryset.filter(teacher_learner_record__teacher=user)
	return queryset


def _cbc_rating_from_average(score):
	if score is None:
		return '-'
	if score >= 80:
		return 'Exceeding Expectations'
	if score >= 60:
		return 'Meeting Expectations'
	if score >= 40:
		return 'Approaching Expectations'
	return 'Below Expectations'


def _teacher_subjects(user):
	if not user.is_authenticated:
		return Subject.objects.none()
	role = _role_for(user)
	if user.is_superuser or role == UserAccount.ROLE_ADMINISTRATOR:
		return Subject.objects.all()
	if role == UserAccount.ROLE_TEACHER:
		account = UserAccount.objects.filter(user=user).first()
		return account.subjects.all() if account else Subject.objects.none()
	return Subject.objects.none()


def _active_subject_for_request(request):
	subject_id = request.session.get(ACTIVE_SUBJECT_SESSION_KEY)
	if not subject_id:
		return None
	return _teacher_subjects(request.user).filter(pk=subject_id).first()


def _require_teacher_subject(request):
	if _role_for(request.user) != UserAccount.ROLE_TEACHER:
		return None
	if _active_subject_for_request(request):
		return None
	return redirect('subject_select')


def home(request):
	return redirect('login')


@login_required
def dashboard(request):
	access_denied = _deny_if_not(_is_teacher_or_admin(request.user) or _role_for(request.user) == UserAccount.ROLE_LEARNER)
	if access_denied:
		return access_denied
	if _is_admin(request.user):
		return redirect('admin_dashboard')

	current_role = _role_for(request.user)
	if current_role == UserAccount.ROLE_LEARNER:
		return redirect('my_reports')
	active_subject = _active_subject_for_request(request)
	teacher_subjects = _teacher_subjects(request.user)
	competency_queryset = Competency.objects.all()
	task_queryset = AssessmentTask.objects.all()
	result_queryset = AssessmentResult.objects.all()
	learner_queryset = LearnerProfile.objects.all()
	if _is_teacher(request.user):
		task_queryset = task_queryset.filter(created_by=request.user)
		result_queryset = result_queryset.filter(teacher_learner_record__teacher=request.user)
		learner_queryset = LearnerProfile.objects.filter(teacher_records__teacher=request.user).distinct()
	learner_profile = None
	if current_role == UserAccount.ROLE_LEARNER:
		learner_profile = LearnerProfile.objects.filter(user_account=request.user.account).first()
		if learner_profile:
			result_queryset = result_queryset.filter(learner=learner_profile)
	if active_subject:
		task_queryset = task_queryset.filter(subject=active_subject)
		result_queryset = result_queryset.filter(task__subject=active_subject)

	learner_count = learner_queryset.count() if current_role != UserAccount.ROLE_LEARNER else (1 if learner_profile else 0)
	competency_count = competency_queryset.count()
	task_count = task_queryset.count()
	result_count = result_queryset.count()
	overall_average = result_queryset.aggregate(avg=Avg('score'))['avg'] or 0

	if current_role == UserAccount.ROLE_LEARNER:
		competency_data = list(
			Competency.objects
			.filter(tasks__results__learner=learner_profile, tasks__results__isnull=False)
			.annotate(avg_score=Avg('tasks__results__score'))
			.values('competency_code', 'avg_score')
			.order_by('competency_code')
			.distinct()
		) if learner_profile else []
		class_data = []
	elif active_subject:
		# Only show competencies that have been assessed in this subject,
		# and calculate the average only from results for that subject's tasks.
		competency_filters = Q(tasks__subject=active_subject, tasks__results__isnull=False)
		if _is_teacher(request.user):
			competency_filters &= Q(tasks__created_by=request.user, tasks__results__created_by=request.user)
		competency_data = list(
			Competency.objects
			.filter(competency_filters)
			.annotate(avg_score=Avg('tasks__results__score', filter=Q(tasks__subject=active_subject)))
			.values('competency_code', 'avg_score')
			.order_by('competency_code')
			.distinct()
		)
	else:
		# Admin / no-subject view: show all competencies that have any results.
		base_competency_queryset = competency_queryset
		if _is_teacher(request.user):
			base_competency_queryset = base_competency_queryset.filter(tasks__created_by=request.user, tasks__results__created_by=request.user)
		competency_data = list(
			base_competency_queryset
			.filter(tasks__results__isnull=False)
			.annotate(avg_score=Avg('tasks__results__score'))
			.values('competency_code', 'avg_score')
			.order_by('competency_code')
			.distinct()
		)

	class_summary = (
		result_queryset.values('learner__class_name')
		.annotate(avg_score=Avg('score'), result_total=Count('id'))
		.order_by('learner__class_name')
	)
	class_data = [
		{
			'class_name': row['learner__class_name'],
			'avg_score': row['avg_score'],
			'result_total': row['result_total'],
		}
		for row in class_summary
	]

	return render(
		request,
		'core/dashboard.html',
		{
			'current_role': current_role,
			'learner_count': learner_count,
			'competency_count': competency_count,
			'task_count': task_count,
			'result_count': result_count,
			'overall_average': round(overall_average, 2) if overall_average else 0,
			'competency_data': competency_data,
			'class_data': class_data,
			'learner_profile': learner_profile,
			'teacher_subjects': teacher_subjects,
			'has_teacher_subjects': bool(teacher_subjects),
		},
	)

@login_required
def admin_dashboard(request):
	access_denied = _deny_if_not(_is_admin(request.user))
	if access_denied:
		return access_denied

	user_count = User.objects.count()
	active_user_count = User.objects.filter(is_active=True).count()
	inactive_user_count = User.objects.filter(is_active=False).count()
	teacher_count = UserAccount.objects.filter(role=UserAccount.ROLE_TEACHER).count()
	learner_count = UserAccount.objects.filter(role=UserAccount.ROLE_LEARNER).count()

	return render(
		request,
		'core/admin_dashboard.html',
		{
			'user_count': user_count,
			'active_user_count': active_user_count,
			'inactive_user_count': inactive_user_count,
			'teacher_count': teacher_count,
			'learner_count': learner_count,
		},
	)

@login_required
def user_list(request):
	access_denied = _deny_if_not(_is_admin(request.user))
	if access_denied:
		return access_denied
	query = request.GET.get('q', '').strip()
	users = User.objects.filter(is_superuser=False, account__role__in=[
		UserAccount.ROLE_ADMINISTRATOR,
		UserAccount.ROLE_TEACHER,
		UserAccount.ROLE_LEARNER,
	])
	if query:
		users = users.filter(
			Q(first_name__icontains=query)
			| Q(last_name__icontains=query)
			| Q(username__icontains=query)
			| Q(email__icontains=query)
		).distinct()
	users = users.order_by('username').select_related('account')
	user_rows = []
	for user_obj in users:
		account = _ensure_account(user_obj)
		user_rows.append({'user_obj': user_obj, 'role': account.role, 'status': account.status})
	return render(request, 'core/user_list.html', {'user_rows': user_rows, 'query': query})



def _user_list_redirect_with_query(request):
	query = request.GET.get('q', '').strip()
	base_url = reverse('user_list')
	if query:
		return redirect(f"{base_url}?q={query}")
	return redirect(base_url)


@login_required
def user_create(request):
	access_denied = _deny_if_not(_is_admin(request.user))
	if access_denied:
		return access_denied

	if request.method == 'POST':
		form = TeacherAccountCreateForm(request.POST)
		if form.is_valid():
			account = form.save()
			messages.success(request, f'Teacher account created successfully. Teacher ID: {account.teacher_id}.')
			return redirect('user_list')
	else:
		form = TeacherAccountCreateForm()
	return render(request, 'core/form.html', {'form': form, 'title': 'Create Teacher Account'})


@login_required
def learner_account_create(request):
	access_denied = _deny_if_not(_is_admin(request.user))
	if access_denied:
		return access_denied

	if request.method == 'POST':
		form = LearnerAccountCreateForm(request.POST)
		if form.is_valid():
			learner = form.save(created_by=request.user)
			messages.success(request, f'Learner account created successfully for {learner.full_name}.')
			return redirect('user_list')
	else:
		form = LearnerAccountCreateForm()

	return render(
		request,
		'core/learner_account_form.html',
		{
			'title': 'Create Learner Account',
			'form': form,
		},
	)


@login_required
def user_update(request, user_id):
	access_denied = _deny_if_not(_is_admin(request.user))
	if access_denied:
		return access_denied

	user_obj = get_object_or_404(User, pk=user_id)
	if user_obj.is_superuser:
		messages.error(request, 'Administrator accounts cannot be edited from this screen.')
		return _user_list_redirect_with_query(request)
	account = _ensure_account(user_obj)
	initial = {
		'full_name': f'{user_obj.first_name} {user_obj.last_name}'.strip() or user_obj.username,
		'email': user_obj.email,
		'role': account.role,
		'status': account.status,
	}
	if request.method == 'POST':
		form = UserAccountUpdateForm(request.POST, user_obj=user_obj)
		if form.is_valid():
			form.save()
			messages.success(request, 'User account updated successfully.')
			return _user_list_redirect_with_query(request)
	else:
		form = UserAccountUpdateForm(initial=initial, user_obj=user_obj)
	return render(request, 'core/form.html', {'form': form, 'title': 'Update User Account'})


@login_required
def user_deactivate(request, user_id):
	access_denied = _deny_if_not(_is_admin(request.user))
	if access_denied:
		return access_denied

	user_obj = get_object_or_404(User, pk=user_id)
	if user_obj.is_superuser:
		messages.error(request, 'Administrator accounts cannot be deactivated from this screen.')
		return _user_list_redirect_with_query(request)
	account = _ensure_account(user_obj)
	if request.method == 'POST':
		user_obj.is_active = False
		user_obj.save(update_fields=['is_active'])
		account.status = UserAccount.STATUS_INACTIVE
		account.save(update_fields=['status'])
		messages.success(request, 'User account deactivated successfully.')
		return _user_list_redirect_with_query(request)
	return render(request, 'core/confirm_delete.html', {'title': 'Deactivate User Account', 'object': user_obj})


@login_required
def user_activate(request, user_id):
	access_denied = _deny_if_not(_is_admin(request.user))
	if access_denied:
		return access_denied

	user_obj = get_object_or_404(User, pk=user_id)
	if user_obj.is_superuser:
		messages.error(request, 'Administrator accounts cannot be activated from this screen.')
		return _user_list_redirect_with_query(request)

	account = _ensure_account(user_obj)
	if request.method == 'POST':
		user_obj.is_active = True
		user_obj.save(update_fields=['is_active'])
		account.status = UserAccount.STATUS_ACTIVE
		account.save(update_fields=['status'])
		messages.success(request, 'User account activated successfully.')
		return _user_list_redirect_with_query(request)
	return render(request, 'core/confirm_delete.html', {'title': 'Activate User Account', 'object': user_obj})


@login_required
def subject_list(request):
	access_denied = _deny_if_not(_is_admin(request.user))
	if access_denied:
		return access_denied
	subjects = Subject.objects.all()
	return render(request, 'core/subject_list.html', {'subjects': subjects})


@login_required
def subject_create(request):
	access_denied = _deny_if_not(_is_admin(request.user))
	if access_denied:
		return access_denied
	if request.method == 'POST':
		form = SubjectForm(request.POST)
		if form.is_valid():
			form.save()
			messages.success(request, 'Subject created successfully.')
			return redirect('subject_list')
	else:
		form = SubjectForm()
	return render(request, 'core/form.html', {'form': form, 'title': 'Create Subject'})


@login_required
def subject_update(request, pk):
	access_denied = _deny_if_not(_is_admin(request.user))
	if access_denied:
		return access_denied
	subject = get_object_or_404(Subject, pk=pk)
	if request.method == 'POST':
		form = SubjectForm(request.POST, instance=subject)
		if form.is_valid():
			form.save()
			messages.success(request, 'Subject updated successfully.')
			return redirect('subject_list')
	else:
		form = SubjectForm(instance=subject)
	return render(request, 'core/form.html', {'form': form, 'title': 'Update Subject'})


@login_required
def subject_delete(request, pk):
	access_denied = _deny_if_not(_is_admin(request.user))
	if access_denied:
		return access_denied
	subject = get_object_or_404(Subject, pk=pk)
	if request.method == 'POST':
		subject.delete()
		messages.success(request, 'Subject deleted successfully.')
		return redirect('subject_list')
	return render(request, 'core/confirm_delete.html', {'title': 'Delete Subject', 'object': subject})


@login_required
def learner_list(request):
	access_denied = _deny_if_not(_is_teacher_or_admin(request.user))
	if access_denied:
		return access_denied

	query = request.GET.get('q', '').strip()
	learners = _teacher_learner_records(request.user).annotate(assignment_count=Count('competency_assignments'))
	if query:
		learners = learners.filter(
			Q(learner_profile__full_name__icontains=query)
			| Q(learner_profile__admission_number__icontains=query)
			| Q(learner_profile__class_name__icontains=query)
		)
	learners = learners.order_by('learner_profile__full_name')
	return render(request, 'core/learner_list.html', {'learners': learners, 'query': query})


@login_required
def learner_create(request):
	access_denied = _deny_if_not(_is_teacher(request.user))
	if access_denied:
		return access_denied

	admission_number = request.POST.get('admission_number', '').strip() if request.method == 'POST' else request.GET.get('admission_number', '').strip()
	learner = None
	existing_record = None

	if admission_number:
		learner = LearnerProfile.objects.select_related('user_account__user').filter(admission_number__iexact=admission_number).first()
		if learner:
			existing_record = TeacherLearnerRecord.objects.filter(teacher=request.user, learner_profile=learner).first()
		elif request.method == 'GET':
			messages.error(request, 'No learner was found with that admission number.')

	if request.method == 'POST':
		if not learner:
			messages.error(request, 'Search for a valid admission number before saving the learner to your records.')
		elif existing_record:
			messages.info(request, 'This learner is already saved in your records.')
		else:
			record = TeacherLearnerRecord.objects.create(teacher=request.user, learner_profile=learner)
			messages.success(request, 'Learner record saved successfully. You can now assign competencies.')
			return redirect('learner_competency_assign', pk=record.pk)
	return render(
		request,
		'core/teacher_learner_record_form.html',
		{
			'title': 'Add Learner Record',
			'admission_number': admission_number,
			'learner': learner,
			'existing_record': existing_record,
		},
	)


@login_required
def learner_update(request, pk):
	access_denied = _deny_if_not(_is_teacher_or_admin(request.user))
	if access_denied:
		return access_denied
	messages.info(request, 'Teacher learner records are based on existing admin-created learner accounts and cannot be edited here.')
	return redirect('learner_list')


@login_required
def learner_delete(request, pk):
	access_denied = _deny_if_not(_is_teacher_or_admin(request.user))
	if access_denied:
		return access_denied

	learner = get_object_or_404(_teacher_learner_records(request.user), pk=pk)
	if request.method == 'POST':
		learner.delete()
		messages.success(request, 'Learner record removed from your workspace successfully.')
		return redirect('learner_list')
	return render(request, 'core/learner_confirm_delete.html', {'object': learner})


@login_required
def learner_competency_assign(request, pk):
	access_denied = _deny_if_not(_is_teacher(request.user))
	if access_denied:
		return access_denied

	teacher_learner_record = get_object_or_404(_teacher_learner_records(request.user), pk=pk)
	if request.method == 'POST':
		form = TeacherLearnerCompetencyAssignmentForm(
			request.POST,
			teacher_learner_record=teacher_learner_record,
			current_user=request.user,
		)
		if form.is_valid():
			selected_competencies = list(form.cleaned_data['competencies'])
			selected_ids = {competency.id for competency in selected_competencies}

			TeacherLearnerCompetencyAssignment.objects.filter(
				teacher_learner_record=teacher_learner_record
			).exclude(competency_id__in=selected_ids).delete()

			existing_ids = set(
				TeacherLearnerCompetencyAssignment.objects.filter(
					teacher_learner_record=teacher_learner_record,
					competency_id__in=selected_ids,
				).values_list('competency_id', flat=True)
			)
			TeacherLearnerCompetencyAssignment.objects.bulk_create(
				[
					TeacherLearnerCompetencyAssignment(
						teacher_learner_record=teacher_learner_record,
						competency=competency,
					)
					for competency in selected_competencies
					if competency.id not in existing_ids
				],
				ignore_conflicts=True,
			)

			messages.success(request, 'Competency assignments updated successfully.')
			return redirect('learner_list')
	else:
		form = TeacherLearnerCompetencyAssignmentForm(
			teacher_learner_record=teacher_learner_record,
			current_user=request.user,
		)

	assigned_competencies = Competency.objects.filter(
		teacher_assignments__teacher_learner_record=teacher_learner_record
	).order_by('competency_code')

	return render(
		request,
		'core/learner_competency_assignment_form.html',
		{
			'form': form,
			'teacher_learner_record': teacher_learner_record,
			'assigned_competencies': assigned_competencies,
		},
	)


@login_required
def competency_list(request):
	access_denied = _deny_if_not(_is_teacher_or_admin(request.user))
	if access_denied:
		return access_denied
	query = request.GET.get('q', '').strip()
	competencies = Competency.objects.select_related('created_by').all()
	is_teacher_view = _is_teacher(request.user)
	if is_teacher_view:
		competencies = competencies.annotate(
			assigned_learner_count=Count(
				'teacher_assignments__teacher_learner_record',
				filter=Q(teacher_assignments__teacher_learner_record__teacher=request.user),
				distinct=True,
			)
		)
	if query:
		competencies = competencies.filter(
			Q(competency_code__icontains=query)
			| Q(competency_name__icontains=query)
			| Q(learning_outcome__icontains=query)
		)
	competencies = competencies.order_by('competency_code')
	return render(
		request,
		'core/competency_list.html',
		{
			'competencies': competencies,
			'query': query,
			'can_manage_competencies': _is_admin(request.user),
			'is_teacher_view': is_teacher_view,
		},
	)


@login_required
def competency_assigned_learners(request, pk):
	access_denied = _deny_if_not(_is_teacher(request.user))
	if access_denied:
		return access_denied

	competency = get_object_or_404(Competency.objects.all(), pk=pk)
	assigned_records = (
		TeacherLearnerRecord.objects
		.select_related('learner_profile')
		.filter(
			teacher=request.user,
			competency_assignments__competency=competency,
		)
		.distinct()
		.order_by('learner_profile__full_name')
	)

	return render(
		request,
		'core/competency_assigned_learners.html',
		{
			'competency': competency,
			'assigned_records': assigned_records,
			'assigned_count': assigned_records.count(),
		},
	)


@login_required
def competency_create(request):
	access_denied = _deny_if_not(_is_admin(request.user))
	if access_denied:
		return access_denied

	if request.method == 'POST':
		form = CompetencyForm(request.POST)
		if form.is_valid():
			competency = form.save(commit=False)
			competency.created_by = request.user
			competency.save()
			return redirect('competency_list')
	else:
		form = CompetencyForm()
	return render(request, 'core/competency_form.html', {'form': form, 'title': 'Create Competency - Define Learning Outcome', 'submit_label': 'Save', 'cancel_url': 'competency_list'})


@login_required
def competency_update(request, pk):
	access_denied = _deny_if_not(_is_admin(request.user))
	if access_denied:
		return access_denied
	competency = get_object_or_404(Competency.objects.all(), pk=pk)
	if request.method == 'POST':
		form = CompetencyForm(request.POST, instance=competency)
		if form.is_valid():
			form.save()
			messages.success(request, 'Competency updated successfully.')
			return redirect('competency_list')
	else:
		form = CompetencyForm(instance=competency)
	return render(request, 'core/competency_form.html', {'form': form, 'title': 'Edit Competency', 'submit_label': 'Save', 'cancel_url': 'competency_list'})


@login_required
def competency_delete(request, pk):
	access_denied = _deny_if_not(_is_admin(request.user))
	if access_denied:
		return access_denied
	competency = get_object_or_404(Competency.objects.all(), pk=pk)
	if request.method == 'POST':
		competency.delete()
		messages.success(request, 'Competency deleted successfully.')
		return redirect('competency_list')
	return render(request, 'core/competency_confirm_delete.html', {'object': competency})


@login_required
def task_list(request):
	access_denied = _deny_if_not(_is_teacher_or_admin(request.user))
	if access_denied:
		return access_denied
	active_subject = _active_subject_for_request(request)
	query = request.GET.get('q', '').strip()
	tasks = _teacher_owned(AssessmentTask.objects.select_related('subject', 'competency', 'created_by').all(), request.user)
	if query:
		tasks = tasks.filter(
			Q(task_name__icontains=query) | Q(competency__competency_name__icontains=query) | Q(competency__competency_code__icontains=query)
		)
	if active_subject:
		tasks = tasks.filter(subject=active_subject)
	tasks = tasks.order_by('task_name')
	return render(request, 'core/task_list.html', {'tasks': tasks, 'query': query})


@login_required
def task_create(request):
	access_denied = _deny_if_not(_is_teacher_or_admin(request.user))
	if access_denied:
		return access_denied
	active_subject = _active_subject_for_request(request)

	if request.method == 'POST':
		form = AssessmentTaskForm(request.POST, active_subject=active_subject, current_user=request.user)
		if form.is_valid():
			task = form.save(commit=False)
			task.subject = active_subject or task.subject
			task.created_by = request.user
			task.save()
			messages.success(request, 'Assessment task created successfully.')
			return redirect('task_list')
	else:
		form = AssessmentTaskForm(active_subject=active_subject, current_user=request.user)
	return render(request, 'core/task_form.html', {'form': form, 'title': 'Create Assessment Task - Link to Competency', 'submit_label': 'Save', 'cancel_url': 'task_list'})


@login_required
def task_update(request, pk):
	access_denied = _deny_if_not(_is_teacher_or_admin(request.user))
	if access_denied:
		return access_denied
	active_subject = _active_subject_for_request(request)
	task_filters = {'pk': pk}
	if active_subject:
		task_filters['subject'] = active_subject
	task_queryset = _teacher_owned(AssessmentTask.objects.all(), request.user)
	task = get_object_or_404(task_queryset, **task_filters)
	if request.method == 'POST':
		form = AssessmentTaskForm(request.POST, instance=task, active_subject=active_subject, current_user=request.user)
		if form.is_valid():
			updated_task = form.save(commit=False)
			updated_task.subject = active_subject or updated_task.subject
			updated_task.save()
			messages.success(request, 'Assessment task updated successfully.')
			return redirect('task_list')
	else:
		form = AssessmentTaskForm(instance=task, active_subject=active_subject, current_user=request.user)
	return render(request, 'core/task_form.html', {'form': form, 'title': 'Edit Assessment Task', 'submit_label': 'Save', 'cancel_url': 'task_list'})


@login_required
def task_delete(request, pk):
	access_denied = _deny_if_not(_is_teacher_or_admin(request.user))
	if access_denied:
		return access_denied
	active_subject = _active_subject_for_request(request)
	task_filters = {'pk': pk}
	if active_subject:
		task_filters['subject'] = active_subject
	task_queryset = _teacher_owned(AssessmentTask.objects.all(), request.user)
	task = get_object_or_404(task_queryset, **task_filters)
	if request.method == 'POST':
		task.delete()
		messages.success(request, 'Assessment task deleted successfully.')
		return redirect('task_list')
	return render(request, 'core/task_confirm_delete.html', {'object': task})


@login_required
def result_list(request):
	access_denied = _deny_if_not(_is_teacher_or_admin(request.user))
	if access_denied:
		return access_denied
	active_subject = _active_subject_for_request(request)
	query = request.GET.get('q', '').strip()
	results = _teacher_owned_results(AssessmentResult.objects.select_related('learner', 'teacher_learner_record__learner_profile', 'task', 'task__competency', 'task__subject', 'created_by').all(), request.user)
	if query:
		results = results.filter(Q(learner__full_name__icontains=query) | Q(task__task_name__icontains=query))
	if active_subject:
		results = results.filter(task__subject=active_subject)
	results = results.order_by('learner__full_name', 'task__task_name', '-created_at')
	return render(request, 'core/result_list.html', {'results': results, 'query': query})


@login_required
def result_create(request):
	access_denied = _deny_if_not(_is_teacher_or_admin(request.user))
	if access_denied:
		return access_denied
	active_subject = _active_subject_for_request(request)
	selected_learner_id = request.POST.get('learner') if request.method == 'POST' else request.GET.get('learner', '').strip()
	selected_task_id = request.POST.get('task') if request.method == 'POST' else request.GET.get('task', '').strip()
	selected_learner_queryset = _teacher_learner_records(request.user)
	selected_task_queryset = AssessmentTask.objects.select_related('competency', 'subject').all()
	selected_learner = selected_learner_queryset.filter(pk=selected_learner_id).first() if selected_learner_id else None
	if selected_learner:
		assigned_competency_ids = TeacherLearnerCompetencyAssignment.objects.filter(
			teacher_learner_record=selected_learner
		).values_list('competency_id', flat=True)
		selected_task_queryset = selected_task_queryset.filter(competency_id__in=assigned_competency_ids)
	selected_task = selected_task_queryset.filter(pk=selected_task_id).first() if selected_task_id else None
	if active_subject:
		if selected_task and selected_task.subject_id != active_subject.id:
			selected_task = None
		if request.method != 'POST' and (not selected_learner or not selected_task):
			return redirect('result_bulk_entry')
	if request.method != 'POST' and (not selected_learner or not selected_task):
		return redirect('result_bulk_entry')

	if request.method == 'POST':
		form = AssessmentResultForm(
			request.POST,
			active_subject=active_subject,
			current_user=request.user,
			teacher_learner_record=selected_learner,
		)
		form.fields['teacher_learner_record'].widget = forms.HiddenInput()
		form.fields['task'].widget = forms.HiddenInput()
		if form.is_valid():
			result = form.save(commit=False)
			result.learner = result.teacher_learner_record.learner_profile
			result.created_by = request.user
			result.feedback = result.feedback or ''
			result.save()
			messages.success(request, 'Assessment result recorded successfully.')
			return redirect('result_list')
	else:
		form = AssessmentResultForm(
			active_subject=active_subject,
			current_user=request.user,
			teacher_learner_record=selected_learner,
			initial={'teacher_learner_record': selected_learner.id if selected_learner else None, 'task': selected_task.id if selected_task else None},
		)
		form.fields['teacher_learner_record'].widget = forms.HiddenInput()
		form.fields['task'].widget = forms.HiddenInput()
		if selected_learner:
			form.fields['teacher_learner_record'].initial = selected_learner.pk
		if selected_task:
			form.fields['task'].initial = selected_task.pk
	return render(
		request,
		'core/result_form.html',
		{
			'form': form,
			'title': 'Record Assessment Result',
			'submit_label': 'Save Result',
			'cancel_url': 'result_list',
			'selected_learner': selected_learner.learner_profile if selected_learner else None,
			'selected_task': selected_task,
		},
	)

@login_required
def result_update(request, pk):
	access_denied = _deny_if_not(_is_teacher_or_admin(request.user))
	if access_denied:
		return access_denied
	active_subject = _active_subject_for_request(request)
	result_filters = {'pk': pk}
	if active_subject:
		result_filters['task__subject'] = active_subject
	result_queryset = _teacher_owned_results(AssessmentResult.objects.all(), request.user)
	result = get_object_or_404(result_queryset, **result_filters)
	if request.method == 'POST':
		form = AssessmentResultForm(
			request.POST,
			instance=result,
			active_subject=active_subject,
			current_user=request.user,
			teacher_learner_record=result.teacher_learner_record,
		)
		form.fields['teacher_learner_record'].widget = forms.HiddenInput()
		form.fields['task'].widget = forms.HiddenInput()
		if form.is_valid():
			updated = form.save(commit=False)
			updated.learner = updated.teacher_learner_record.learner_profile
			updated.created_by = request.user
			updated.feedback = updated.feedback or result.feedback or ''
			updated.save()
			messages.success(request, 'Assessment result updated successfully.')
			return redirect('result_list')
	else:
		form = AssessmentResultForm(
			instance=result,
			active_subject=active_subject,
			current_user=request.user,
			teacher_learner_record=result.teacher_learner_record,
		)
		form.fields['teacher_learner_record'].widget = forms.HiddenInput()
		form.fields['task'].widget = forms.HiddenInput()
	return render(
		request,
		'core/result_form.html',
		{
			'form': form,
			'title': 'Edit Assessment Result',
			'submit_label': 'Save Result',
			'cancel_url': 'result_list',
			'selected_learner': result.teacher_learner_record.learner_profile if result.teacher_learner_record else result.learner,
			'selected_task': result.task,
		},
	)


@login_required
def result_delete(request, pk):
	access_denied = _deny_if_not(_is_teacher_or_admin(request.user))
	if access_denied:
		return access_denied
	active_subject = _active_subject_for_request(request)
	result_filters = {'pk': pk}
	if active_subject:
		result_filters['task__subject'] = active_subject
	result_queryset = _teacher_owned_results(AssessmentResult.objects.all(), request.user)
	result = get_object_or_404(result_queryset, **result_filters)
	if request.method == 'POST':
		result.delete()
		messages.success(request, 'Assessment result deleted successfully.')
		return redirect('result_list')
	return render(request, 'core/result_confirm_delete.html', {'object': result})


@login_required
def result_bulk_entry(request):
	access_denied = _deny_if_not(_is_teacher_or_admin(request.user))
	if access_denied:
		return access_denied

	active_subject = _active_subject_for_request(request)
	learners = _teacher_learner_records(request.user).order_by('learner_profile__full_name')
	tasks = AssessmentTask.objects.select_related('competency', 'subject').all()
	if active_subject:
		tasks = tasks.filter(subject=active_subject)
	tasks = tasks.order_by('task_name')
	selected_learner_id = request.GET.get('learner', '').strip()
	selected_task_id = request.GET.get('task', '').strip()
	selected_learner = learners.filter(pk=selected_learner_id).first() if selected_learner_id else None
	if selected_learner:
		assigned_competency_ids = TeacherLearnerCompetencyAssignment.objects.filter(
			teacher_learner_record=selected_learner
		).values_list('competency_id', flat=True)
		tasks = tasks.filter(competency_id__in=assigned_competency_ids)
	selected_task = tasks.filter(pk=selected_task_id).first() if selected_task_id else None

	return render(
		request,
		'core/bulk_result_entry.html',
		{
			'learners': learners,
			'competencies': Competency.objects.order_by('competency_code'),
			'selected_learner': selected_learner,
			'selected_learner_id': selected_learner_id,
			'tasks': tasks,
			'selected_task': selected_task,
			'selected_task_id': selected_task_id,
		},
	)


@login_required
def report_view(request):
	access_denied = _deny_if_not(_is_teacher_or_admin(request.user) or _role_for(request.user) == UserAccount.ROLE_LEARNER)
	if access_denied:
		return access_denied
	current_role = _role_for(request.user)
	active_subject = _active_subject_for_request(request)
	learner_profile = LearnerProfile.objects.filter(user_account=request.user.account).first() if current_role == UserAccount.ROLE_LEARNER else None
	report_id = request.POST.get('report') if request.method == 'POST' else request.GET.get('report', '').strip()
	selected_learner_id = '' if current_role == UserAccount.ROLE_LEARNER else (request.POST.get('learner') if request.method == 'POST' else request.GET.get('learner', '').strip())
	view_requested = request.POST.get('view_report') == '1' if request.method == 'POST' else request.GET.get('view_report') == '1'
	if current_role == UserAccount.ROLE_LEARNER and report_id:
		view_requested = True

	learners = TeacherLearnerRecord.objects.none() if learner_profile else _teacher_learner_records(request.user).order_by('learner_profile__full_name')
	competencies = Competency.objects.none()
	if current_role == UserAccount.ROLE_LEARNER and learner_profile:
		competencies = Competency.objects.filter(report_feedbacks__learner=learner_profile, report_feedbacks__is_available_for_learner=True).distinct().order_by('competency_code')

	selected_learner_record = learners.filter(pk=selected_learner_id).first() if selected_learner_id else None
	selected_learner = selected_learner_record.learner_profile if selected_learner_record else learner_profile
	selected_competency = None
	selected_competency_id = ''

	results = AssessmentResult.objects.none()
	report_feedback = None
	report_already_saved = False
	teacher_feedback_text = ''
	task_rows = []
	assigned_competencies = Competency.objects.none()
	validation = {
		'required_fields_ok': True,
		'duplicate_ok': True,
		'missing_count': 0,
		'duplicate_count': 0,
	}
	total_results = 0
	term_average_score = 0
	highest_score = None
	lowest_score = None
	rating_breakdown = []
	average_cbc_rating = '-'

	if current_role == UserAccount.ROLE_LEARNER and report_id:
		report_feedback = LearnerReportFeedback.objects.filter(
			pk=report_id,
			learner=learner_profile,
			is_available_for_learner=True,
		).prefetch_related('assessment_results__task__competency', 'assessment_results__task__subject').select_related('competency', 'teacher_learner_record').first()
		if report_feedback:
			selected_competency = report_feedback.competency
			selected_competency_id = str(report_feedback.competency_id)
			selected_learner = learner_profile
			competency_feedbacks = LearnerReportFeedback.objects.filter(
				learner=learner_profile,
				competency=selected_competency,
				is_available_for_learner=True,
			).order_by('-updated_at')
			report_feedback = competency_feedbacks.first()
			results = AssessmentResult.objects.select_related('learner', 'task', 'task__competency', 'created_by').filter(
				learner=learner_profile,
				task__competency=selected_competency,
				saved_report_feedbacks__in=competency_feedbacks,
			).distinct().order_by('task__task_name')
			report_already_saved = bool(report_feedback)
			teacher_feedback_text = report_feedback.feedback if report_feedback else ''
			task_rows = [{'task': result.task, 'competency': result.task.competency, 'result': result} for result in results]

	if current_role != UserAccount.ROLE_LEARNER and selected_learner_record:
		assigned_competencies = Competency.objects.filter(
			teacher_assignments__teacher_learner_record=selected_learner_record,
		).distinct().order_by('competency_code')

		tasks_queryset = AssessmentTask.objects.select_related('competency').filter(competency__in=assigned_competencies)
		if active_subject:
			tasks_queryset = tasks_queryset.filter(subject=active_subject)
		tasks_queryset = tasks_queryset.order_by('competency__competency_code', 'task_name')

		results = AssessmentResult.objects.select_related('learner', 'teacher_learner_record', 'task', 'task__competency', 'created_by').filter(
			teacher_learner_record=selected_learner_record,
			task__in=tasks_queryset,
		).order_by('task__competency__competency_code', 'task__task_name')

		results_by_task = {result.task_id: result for result in results}
		task_rows = [
			{
				'task': task,
				'competency': task.competency,
				'result': results_by_task.get(task.id),
			}
			for task in tasks_queryset
		]

		report_feedback = LearnerReportFeedback.objects.filter(
			teacher_learner_record=selected_learner_record,
			competency__in=assigned_competencies,
		).order_by('-updated_at').first()
		if report_feedback:
			report_already_saved = True
			teacher_feedback_text = report_feedback.feedback

	if selected_learner and (current_role == UserAccount.ROLE_LEARNER or selected_learner_record):
		results_for_summary = results.exclude(score__isnull=True)

		missing_required_results = results_for_summary.filter(
			Q(score__isnull=True)
			| Q(cbc_rating__isnull=True)
			| Q(cbc_rating='')
			| Q(mastery_status__isnull=True)
			| Q(mastery_status='')
		)
		duplicate_results = (
			results_for_summary.values('learner_id', 'task_id')
			.annotate(total=Count('id'))
			.filter(total__gt=1)
		)

		validation['missing_count'] = missing_required_results.count()
		validation['duplicate_count'] = duplicate_results.count()
		validation['required_fields_ok'] = validation['missing_count'] == 0
		validation['duplicate_ok'] = validation['duplicate_count'] == 0

		total_results = results_for_summary.count()
		score_summary = results_for_summary.aggregate(avg=Avg('score'), highest=Max('score'), lowest=Min('score'))
		term_average_score = score_summary['avg'] or 0
		highest_score = score_summary['highest']
		lowest_score = score_summary['lowest']
		average_cbc_rating = _cbc_rating_from_average(score_summary['avg'])

		rating_choices = (
			results_for_summary.exclude(cbc_rating__isnull=True)
			.exclude(cbc_rating='')
			.values_list('cbc_rating', flat=True)
			.distinct()
			.order_by('cbc_rating')
		)
		for rating in rating_choices:
			rating_breakdown.append({'rating': rating, 'count': results_for_summary.filter(cbc_rating=rating).count()})

	if current_role != UserAccount.ROLE_LEARNER and request.method == 'POST' and request.POST.get('save_report') == '1':
		view_requested = True
		teacher_feedback_text = request.POST.get('teacher_feedback', '').strip()
		if not selected_learner_record:
			messages.error(request, 'Select a learner before saving the report.')
		elif not assigned_competencies.exists():
			messages.error(request, 'Assign at least one competency to this learner record before saving the report.')
		elif not teacher_feedback_text:
			messages.error(request, 'Teacher feedback is required before saving the report.')
		elif not results.exists():
			messages.error(request, 'No assessment results found for the selected learner record.')
		else:
			created_report_count = 0
			skipped_report_count = 0
			for competency in assigned_competencies:
				competency_results = results.filter(task__competency=competency)
				status_counts = (
					competency_results.values('mastery_status')
					.annotate(total=Count('id'))
					.order_by('-total', 'mastery_status')
				)
				overall_status = status_counts[0]['mastery_status'] if status_counts else AssessmentResult.MASTERY_DEVELOPING
				report_feedback, created = LearnerReportFeedback.objects.get_or_create(
					teacher_learner_record=selected_learner_record,
					competency=competency,
					defaults={
						'learner': selected_learner_record.learner_profile,
						'teacher': request.user,
						'feedback': teacher_feedback_text,
						'overall_competency_status': overall_status,
						'is_available_for_learner': True,
					},
				)
				if created:
					report_feedback.assessment_results.set(competency_results)
					created_report_count += 1
				else:
					skipped_report_count += 1

			if created_report_count and not skipped_report_count:
				messages.success(request, 'Report saved successfully.')
			elif created_report_count and skipped_report_count:
				messages.warning(request, 'Some reports were already saved and were skipped. New reports were saved for the remaining competencies.')
			else:
				messages.info(request, 'Report already saved for this learner record. Save-only mode does not allow updates.')
			return redirect(f"{reverse('report_view')}?learner={selected_learner_record.id}&view_report=1")

	return render(
		request,
		'core/report.html',
		{
			'results': results,
			'task_rows': task_rows,
			'assigned_competencies': assigned_competencies,
			'learners': learners,
			'current_role': current_role,
			'learner_profile': learner_profile,
			'selected_learner': selected_learner,
			'view_requested': view_requested,
			'total_results': total_results,
			'term_average_score': term_average_score,
			'highest_score': highest_score,
			'lowest_score': lowest_score,
			'validation': validation,
			'competencies': competencies,
			'selected_learner_id': selected_learner_id,
			'selected_competency': selected_competency_id,
			'selected_competency_obj': selected_competency,
			'teacher_feedback_text': teacher_feedback_text,
			'report_feedback': report_feedback,
			'report_already_saved': report_already_saved,
			'rating_breakdown': rating_breakdown,
			'average_cbc_rating': average_cbc_rating,
		},
	)


@login_required
def feedback_view(request):
	role = _role_for(request.user)
	access_denied = _deny_if_not(role in {UserAccount.ROLE_LEARNER, UserAccount.ROLE_TEACHER, UserAccount.ROLE_ADMINISTRATOR})
	if access_denied:
		return access_denied

	if role == UserAccount.ROLE_LEARNER:
		learner = LearnerProfile.objects.filter(user_account=request.user.account).first()
		results = AssessmentResult.objects.filter(learner=learner).select_related('task', 'task__subject', 'task__competency') if learner else []
		feedback_message = 'Showing your personal assessment feedback.'
	else:
		subject_required = _require_teacher_subject(request)
		if subject_required:
			return subject_required
		active_subject = _active_subject_for_request(request)
		results = _teacher_owned_results(AssessmentResult.objects.select_related('learner', 'task', 'task__subject', 'task__competency', 'created_by').all(), request.user)
		if active_subject:
			results = results.filter(task__subject=active_subject)
		feedback_message = 'Showing your learner assessment feedback.'

	return render(
		request,
		'core/feedback.html',
		{'results': results, 'role': role, 'feedback_message': feedback_message},
	)


@login_required
def my_reports_view(request):
	access_denied = _deny_if_not(_role_for(request.user) == UserAccount.ROLE_LEARNER)
	if access_denied:
		return access_denied

	learner = LearnerProfile.objects.filter(user_account=request.user.account).first()
	report_rows = []

	if learner:
		reports = (
			LearnerReportFeedback.objects
			.filter(learner=learner, is_available_for_learner=True)
			.select_related('competency', 'teacher_learner_record')
			.prefetch_related('assessment_results__task__subject')
			.order_by('-updated_at', '-created_at')
		)

		grouped_reports = {}
		for report in reports:
			entry = grouped_reports.get(report.competency_id)
			if entry is None:
				entry = {'report': report, 'subject_names': set()}
				grouped_reports[report.competency_id] = entry
			for result in report.assessment_results.all():
				if result.task.subject:
					entry['subject_names'].add(result.task.subject.subject_name)

		report_rows = [
			{
				'report': entry['report'],
				'subject_name': ', '.join(sorted(entry['subject_names'])) if entry['subject_names'] else '-',
			}
			for _, entry in sorted(
				grouped_reports.items(),
				key=lambda item: item[1]['report'].updated_at,
				reverse=True,
			)
		]

	return render(
		request,
		'core/my_reports.html',
		{
			'learner': learner,
			'report_rows': report_rows,
		},
	)


@login_required
def subject_select(request):
	if _role_for(request.user) != UserAccount.ROLE_TEACHER:
		return redirect('dashboard')

	subjects = _teacher_subjects(request.user)
	no_subjects_assigned = not subjects.exists()

	if request.method == 'POST':
		if no_subjects_assigned:
			messages.error(request, 'No subjects are assigned to your account. Contact an administrator.')
			return redirect('dashboard')
		form = SubjectSelectionForm(request.POST, subjects=subjects)
		if form.is_valid():
			subject = form.cleaned_data['subject']
			request.session[ACTIVE_SUBJECT_SESSION_KEY] = subject.id
			messages.success(request, f'You are now working in {subject.subject_name}.')
			return redirect('dashboard')
		messages.error(request, 'Please select a valid subject.')
	else:
		form = SubjectSelectionForm(subjects=subjects)

	active_subject = _active_subject_for_request(request)
	return render(
		request,
		'core/subject_select.html',
		{
			'form': form,
			'active_subject': active_subject,
			'no_subjects_assigned': no_subjects_assigned,
			'subjects': subjects,
		},
	)
