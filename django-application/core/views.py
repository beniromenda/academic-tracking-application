from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Avg, Count, Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from .forms import (
	AssessmentResultForm,
	AssessmentTaskForm,
	CompetencyForm,
	LearnerProfileForm,
	SubjectForm,
	SubjectSelectionForm,
	UserAccountCreateForm,
	UserAccountUpdateForm,
)
from .models import AssessmentResult, AssessmentTask, Competency, LearnerProfile, Subject, UserAccount


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


def _deny_if_not(condition):
	if not condition:
		return HttpResponseForbidden('You are not allowed to access this page.')
	return None


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

	subject_required = _require_teacher_subject(request)
	if subject_required:
		return subject_required

	active_subject = _active_subject_for_request(request)
	competency_queryset = Competency.objects.all()
	task_queryset = AssessmentTask.objects.all()
	result_queryset = AssessmentResult.objects.all()
	learner_queryset = LearnerProfile.objects.all()
	if active_subject:
		task_queryset = task_queryset.filter(subject=active_subject)
		result_queryset = result_queryset.filter(task__subject=active_subject)

	learner_count = learner_queryset.count()
	competency_count = competency_queryset.count()
	task_count = task_queryset.count()
	result_count = result_queryset.count()
	overall_average = result_queryset.aggregate(avg=Avg('score'))['avg'] or 0

	if active_subject:
		# Only show competencies that have been assessed in this subject,
		# and calculate the average only from results for that subject's tasks.
		competency_data = list(
			Competency.objects
			.filter(tasks__subject=active_subject, tasks__results__isnull=False)
			.annotate(avg_score=Avg('tasks__results__score', filter=Q(tasks__subject=active_subject)))
			.values('competency_code', 'avg_score')
			.order_by('competency_code')
			.distinct()
		)
	else:
		# Admin / no-subject view: show all competencies that have any results.
		competency_data = list(
			competency_queryset
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
			'learner_count': learner_count,
			'competency_count': competency_count,
			'task_count': task_count,
			'result_count': result_count,
			'overall_average': round(overall_average, 2) if overall_average else 0,
			'competency_data': competency_data,
			'class_data': class_data,
		},
	)


@login_required
def user_list(request):
	access_denied = _deny_if_not(_is_admin(request.user))
	if access_denied:
		return access_denied
	users = User.objects.all().order_by('username')
	user_rows = []
	for user_obj in users:
		account = _ensure_account(user_obj)
		subjects = ', '.join(account.subjects.values_list('subject_name', flat=True))
		user_rows.append({'user_obj': user_obj, 'role': account.role, 'status': account.status, 'subjects': subjects})
	return render(request, 'core/user_list.html', {'user_rows': user_rows})


@login_required
def user_create(request):
	access_denied = _deny_if_not(_is_admin(request.user))
	if access_denied:
		return access_denied

	if request.method == 'POST':
		form = UserAccountCreateForm(request.POST)
		if form.is_valid():
			form.save()
			messages.success(request, 'User account created successfully.')
			return redirect('user_list')
	else:
		form = UserAccountCreateForm()
	return render(request, 'core/form.html', {'form': form, 'title': 'Create User Account'})


@login_required
def user_update(request, user_id):
	access_denied = _deny_if_not(_is_admin(request.user))
	if access_denied:
		return access_denied

	user_obj = get_object_or_404(User, pk=user_id)
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
			return redirect('user_list')
	else:
		form = UserAccountUpdateForm(initial=initial, user_obj=user_obj)
	return render(request, 'core/form.html', {'form': form, 'title': 'Update User Account'})


@login_required
def user_delete(request, user_id):
	access_denied = _deny_if_not(_is_admin(request.user))
	if access_denied:
		return access_denied

	user_obj = get_object_or_404(User, pk=user_id)
	if request.method == 'POST':
		user_obj.delete()
		messages.success(request, 'User account deleted successfully.')
		return redirect('user_list')
	return render(request, 'core/confirm_delete.html', {'title': 'Delete User Account', 'object': user_obj})


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
	learners = LearnerProfile.objects.select_related('user_account__user', 'created_by').all()
	if query:
		learners = learners.filter(
			full_name__icontains=query,
		) | learners.filter(admission_number__icontains=query) | learners.filter(class_name__icontains=query)
	learners = learners.order_by('full_name')
	return render(request, 'core/learner_list.html', {'learners': learners, 'query': query})


@login_required
def learner_create(request):
	access_denied = _deny_if_not(_is_teacher_or_admin(request.user))
	if access_denied:
		return access_denied

	if request.method == 'POST':
		form = LearnerProfileForm(request.POST)
		if form.is_valid():
			learner = form.save(commit=False)
			learner.created_by = request.user
			learner.save()
			messages.success(request, 'Learner profile created successfully.')
			return redirect('learner_list')
	else:
		form = LearnerProfileForm()
	return render(request, 'core/form.html', {'form': form, 'title': 'Create Learner Profile'})


@login_required
def learner_update(request, pk):
	access_denied = _deny_if_not(_is_teacher_or_admin(request.user))
	if access_denied:
		return access_denied

	learner = get_object_or_404(LearnerProfile, pk=pk)
	if request.method == 'POST':
		form = LearnerProfileForm(request.POST, instance=learner)
		if form.is_valid():
			form.save()
			messages.success(request, 'Learner profile updated successfully.')
			return redirect('learner_list')
	else:
		form = LearnerProfileForm(instance=learner)
	return render(request, 'core/form.html', {'form': form, 'title': 'Update Learner Profile'})


@login_required
def learner_delete(request, pk):
	access_denied = _deny_if_not(_is_teacher_or_admin(request.user))
	if access_denied:
		return access_denied

	learner = get_object_or_404(LearnerProfile, pk=pk)
	if request.method == 'POST':
		learner.delete()
		messages.success(request, 'Learner profile deleted successfully.')
		return redirect('learner_list')
	return render(request, 'core/confirm_delete.html', {'title': 'Delete Learner Profile', 'object': learner})


@login_required
def competency_list(request):
	access_denied = _deny_if_not(_is_teacher_or_admin(request.user))
	if access_denied:
		return access_denied
	competencies = Competency.objects.select_related('created_by').all()
	return render(request, 'core/competency_list.html', {'competencies': competencies})


@login_required
def competency_create(request):
	access_denied = _deny_if_not(_is_teacher_or_admin(request.user))
	if access_denied:
		return access_denied
	active_subject = _active_subject_for_request(request)

	if request.method == 'POST':
		form = CompetencyForm(request.POST)
		if form.is_valid():
			competency = form.save(commit=False)
			competency.created_by = request.user
			competency.save()
			return redirect('competency_list')
	else:
		form = CompetencyForm()
	return render(request, 'core/form.html', {'form': form, 'title': 'Create Competency'})


@login_required
def competency_update(request, pk):
	access_denied = _deny_if_not(_is_teacher_or_admin(request.user))
	if access_denied:
		return access_denied
	active_subject = _active_subject_for_request(request)
	competency = get_object_or_404(Competency, pk=pk)
	if request.method == 'POST':
		form = CompetencyForm(request.POST, instance=competency)
		if form.is_valid():
			form.save()
			messages.success(request, 'Competency updated successfully.')
			return redirect('competency_list')
	else:
		form = CompetencyForm(instance=competency)
	return render(request, 'core/form.html', {'form': form, 'title': 'Update Competency'})


@login_required
def competency_delete(request, pk):
	access_denied = _deny_if_not(_is_teacher_or_admin(request.user))
	if access_denied:
		return access_denied
	competency = get_object_or_404(Competency, pk=pk)
	if request.method == 'POST':
		competency.delete()
		messages.success(request, 'Competency deleted successfully.')
		return redirect('competency_list')
	return render(request, 'core/confirm_delete.html', {'title': 'Delete Competency', 'object': competency})


@login_required
def task_list(request):
	access_denied = _deny_if_not(_is_teacher_or_admin(request.user))
	if access_denied:
		return access_denied

	subject_required = _require_teacher_subject(request)
	if subject_required:
		return subject_required
	active_subject = _active_subject_for_request(request)
	tasks = AssessmentTask.objects.select_related('subject', 'competency', 'teacher').all()
	if active_subject:
		tasks = tasks.filter(subject=active_subject)
	return render(request, 'core/task_list.html', {'tasks': tasks})


@login_required
def task_create(request):
	access_denied = _deny_if_not(_is_teacher_or_admin(request.user))
	if access_denied:
		return access_denied

	subject_required = _require_teacher_subject(request)
	if subject_required:
		return subject_required
	active_subject = _active_subject_for_request(request)

	if request.method == 'POST':
		form = AssessmentTaskForm(request.POST, active_subject=active_subject)
		if form.is_valid():
			task = form.save(commit=False)
			task.subject = active_subject or task.subject
			task.teacher = request.user
			task.save()
			messages.success(request, 'Assessment task created successfully.')
			return redirect('task_list')
	else:
		form = AssessmentTaskForm(active_subject=active_subject)
	return render(request, 'core/form.html', {'form': form, 'title': 'Create Assessment Task'})


@login_required
def task_update(request, pk):
	access_denied = _deny_if_not(_is_teacher_or_admin(request.user))
	if access_denied:
		return access_denied

	subject_required = _require_teacher_subject(request)
	if subject_required:
		return subject_required
	active_subject = _active_subject_for_request(request)
	task_filters = {'pk': pk}
	if active_subject:
		task_filters['subject'] = active_subject
	task = get_object_or_404(AssessmentTask, **task_filters)
	if request.method == 'POST':
		form = AssessmentTaskForm(request.POST, instance=task, active_subject=active_subject)
		if form.is_valid():
			updated_task = form.save(commit=False)
			updated_task.subject = active_subject or updated_task.subject
			updated_task.save()
			messages.success(request, 'Assessment task updated successfully.')
			return redirect('task_list')
	else:
		form = AssessmentTaskForm(instance=task, active_subject=active_subject)
	return render(request, 'core/form.html', {'form': form, 'title': 'Update Assessment Task'})


@login_required
def task_delete(request, pk):
	access_denied = _deny_if_not(_is_teacher_or_admin(request.user))
	if access_denied:
		return access_denied

	subject_required = _require_teacher_subject(request)
	if subject_required:
		return subject_required
	active_subject = _active_subject_for_request(request)
	task_filters = {'pk': pk}
	if active_subject:
		task_filters['subject'] = active_subject
	task = get_object_or_404(AssessmentTask, **task_filters)
	if request.method == 'POST':
		task.delete()
		messages.success(request, 'Assessment task deleted successfully.')
		return redirect('task_list')
	return render(request, 'core/confirm_delete.html', {'title': 'Delete Assessment Task', 'object': task})


@login_required
def result_list(request):
	access_denied = _deny_if_not(_is_teacher_or_admin(request.user))
	if access_denied:
		return access_denied

	subject_required = _require_teacher_subject(request)
	if subject_required:
		return subject_required
	active_subject = _active_subject_for_request(request)
	results = AssessmentResult.objects.select_related('learner', 'task', 'task__competency', 'task__subject', 'teacher').all()
	if active_subject:
		results = results.filter(task__subject=active_subject)
	return render(request, 'core/result_list.html', {'results': results})


@login_required
def result_create(request):
	access_denied = _deny_if_not(_is_teacher_or_admin(request.user))
	if access_denied:
		return access_denied

	subject_required = _require_teacher_subject(request)
	if subject_required:
		return subject_required
	active_subject = _active_subject_for_request(request)

	if request.method == 'POST':
		form = AssessmentResultForm(request.POST, active_subject=active_subject)
		if form.is_valid():
			result = form.save(commit=False)
			result.teacher = request.user
			result.save()
			messages.success(request, 'Assessment result recorded successfully.')
			return redirect('result_list')
	else:
		form = AssessmentResultForm(active_subject=active_subject)
	return render(request, 'core/form.html', {'form': form, 'title': 'Record Assessment Result'})


@login_required
def result_update(request, pk):
	access_denied = _deny_if_not(_is_teacher_or_admin(request.user))
	if access_denied:
		return access_denied

	subject_required = _require_teacher_subject(request)
	if subject_required:
		return subject_required
	active_subject = _active_subject_for_request(request)
	result_filters = {'pk': pk}
	if active_subject:
		result_filters['task__subject'] = active_subject
	result = get_object_or_404(AssessmentResult, **result_filters)
	if request.method == 'POST':
		form = AssessmentResultForm(request.POST, instance=result, active_subject=active_subject)
		if form.is_valid():
			updated = form.save(commit=False)
			updated.teacher = request.user
			updated.save()
			messages.success(request, 'Assessment result updated successfully.')
			return redirect('result_list')
	else:
		form = AssessmentResultForm(instance=result, active_subject=active_subject)
	return render(request, 'core/form.html', {'form': form, 'title': 'Update Assessment Result'})


@login_required
def result_delete(request, pk):
	access_denied = _deny_if_not(_is_teacher_or_admin(request.user))
	if access_denied:
		return access_denied

	subject_required = _require_teacher_subject(request)
	if subject_required:
		return subject_required
	active_subject = _active_subject_for_request(request)
	result_filters = {'pk': pk}
	if active_subject:
		result_filters['task__subject'] = active_subject
	result = get_object_or_404(AssessmentResult, **result_filters)
	if request.method == 'POST':
		result.delete()
		messages.success(request, 'Assessment result deleted successfully.')
		return redirect('result_list')
	return render(request, 'core/confirm_delete.html', {'title': 'Delete Assessment Result', 'object': result})


@login_required
def report_view(request):
	access_denied = _deny_if_not(_is_teacher_or_admin(request.user))
	if access_denied:
		return access_denied

	subject_required = _require_teacher_subject(request)
	if subject_required:
		return subject_required
	active_subject = _active_subject_for_request(request)

	class_filter = request.GET.get('class_name', '').strip()
	competency_filter = request.GET.get('competency', '').strip()
	rating_filter = request.GET.get('rating', '').strip()

	results = AssessmentResult.objects.select_related('learner', 'task', 'task__competency').all()
	if active_subject:
		results = results.filter(task__subject=active_subject)
	if class_filter:
		results = results.filter(learner__class_name=class_filter)
	if competency_filter:
		results = results.filter(task__competency__id=competency_filter)
	if rating_filter:
		results = results.filter(rating__icontains=rating_filter)

	summary = (
		results.values('task__competency__competency_name')
		.annotate(avg_score=Avg('score'), total=Count('id'))
		.order_by('task__competency__competency_name')
	)

	class_choices = LearnerProfile.objects.values_list('class_name', flat=True).distinct().order_by('class_name')
	competencies = Competency.objects.all().order_by('competency_code')

	return render(
		request,
		'core/report.html',
		{
			'results': results,
			'summary': summary,
			'class_choices': class_choices,
			'competencies': competencies,
			'selected_class': class_filter,
			'selected_competency': competency_filter,
			'selected_rating': rating_filter,
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
		results = AssessmentResult.objects.select_related('learner', 'task', 'task__subject', 'task__competency').all()
		if active_subject:
			results = results.filter(task__subject=active_subject)
		feedback_message = 'Showing all learner assessment feedback.'

	return render(
		request,
		'core/feedback.html',
		{'results': results, 'role': role, 'feedback_message': feedback_message},
	)


@login_required
def subject_select(request):
	if _role_for(request.user) != UserAccount.ROLE_TEACHER:
		return redirect('dashboard')

	subjects = _teacher_subjects(request.user)
	if not subjects.exists():
		return HttpResponseForbidden('No subjects are assigned to your account. Contact an administrator.')

	if request.method == 'POST':
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
		},
	)
