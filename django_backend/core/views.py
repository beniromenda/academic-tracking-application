from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Avg, Count
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from .forms import (
	AssessmentResultForm,
	AssessmentTaskForm,
	CompetencyForm,
	LearnerProfileForm,
	UserAccountCreateForm,
	UserAccountUpdateForm,
)
from .models import AssessmentResult, AssessmentTask, Competency, LearnerProfile, UserAccount


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


def home(request):
	if request.user.is_authenticated:
		return redirect('dashboard')
	return redirect('login')


@login_required
def dashboard(request):
	access_denied = _deny_if_not(_is_teacher_or_admin(request.user) or _role_for(request.user) == UserAccount.ROLE_LEARNER)
	if access_denied:
		return access_denied

	learner_count = LearnerProfile.objects.count()
	competency_count = Competency.objects.count()
	task_count = AssessmentTask.objects.count()
	result_count = AssessmentResult.objects.count()
	overall_average = AssessmentResult.objects.aggregate(avg=Avg('score'))['avg'] or 0

	competency_data = list(
		Competency.objects.annotate(avg_score=Avg('tasks__results__score'))
		.values('competency_code', 'avg_score')
		.order_by('competency_code')
	)

	class_data = list(
		LearnerProfile.objects.annotate(avg_score=Avg('results__score'), result_total=Count('results'))
		.values('class_name', 'avg_score', 'result_total')
		.order_by('class_name')
	)

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
	users = User.objects.select_related('account').all().order_by('username')
	return render(request, 'core/user_list.html', {'users': users})


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
	initial = {
		'full_name': f'{user_obj.first_name} {user_obj.last_name}'.strip() or user_obj.username,
		'email': user_obj.email,
		'role': user_obj.account.role,
		'status': user_obj.account.status,
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
def learner_list(request):
	access_denied = _deny_if_not(_is_teacher_or_admin(request.user))
	if access_denied:
		return access_denied

	query = request.GET.get('q', '').strip()
	learners = LearnerProfile.objects.select_related('user_account__user').all()
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
			form.save()
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

	if request.method == 'POST':
		form = CompetencyForm(request.POST)
		if form.is_valid():
			competency = form.save(commit=False)
			competency.created_by = request.user
			competency.save()
			messages.success(request, 'Competency created successfully.')
			return redirect('competency_list')
	else:
		form = CompetencyForm()
	return render(request, 'core/form.html', {'form': form, 'title': 'Create Competency'})


@login_required
def competency_update(request, pk):
	access_denied = _deny_if_not(_is_teacher_or_admin(request.user))
	if access_denied:
		return access_denied

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

	tasks = AssessmentTask.objects.select_related('competency', 'teacher').all()
	return render(request, 'core/task_list.html', {'tasks': tasks})


@login_required
def task_create(request):
	access_denied = _deny_if_not(_is_teacher_or_admin(request.user))
	if access_denied:
		return access_denied

	if request.method == 'POST':
		form = AssessmentTaskForm(request.POST)
		if form.is_valid():
			task = form.save(commit=False)
			task.teacher = request.user
			task.save()
			messages.success(request, 'Assessment task created successfully.')
			return redirect('task_list')
	else:
		form = AssessmentTaskForm()
	return render(request, 'core/form.html', {'form': form, 'title': 'Create Assessment Task'})


@login_required
def task_update(request, pk):
	access_denied = _deny_if_not(_is_teacher_or_admin(request.user))
	if access_denied:
		return access_denied

	task = get_object_or_404(AssessmentTask, pk=pk)
	if request.method == 'POST':
		form = AssessmentTaskForm(request.POST, instance=task)
		if form.is_valid():
			form.save()
			messages.success(request, 'Assessment task updated successfully.')
			return redirect('task_list')
	else:
		form = AssessmentTaskForm(instance=task)
	return render(request, 'core/form.html', {'form': form, 'title': 'Update Assessment Task'})


@login_required
def task_delete(request, pk):
	access_denied = _deny_if_not(_is_teacher_or_admin(request.user))
	if access_denied:
		return access_denied

	task = get_object_or_404(AssessmentTask, pk=pk)
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

	results = AssessmentResult.objects.select_related('learner', 'task', 'task__competency', 'teacher').all()
	return render(request, 'core/result_list.html', {'results': results})


@login_required
def result_create(request):
	access_denied = _deny_if_not(_is_teacher_or_admin(request.user))
	if access_denied:
		return access_denied

	if request.method == 'POST':
		form = AssessmentResultForm(request.POST)
		if form.is_valid():
			result = form.save(commit=False)
			result.teacher = request.user
			result.save()
			messages.success(request, 'Assessment result recorded successfully.')
			return redirect('result_list')
	else:
		form = AssessmentResultForm()
	return render(request, 'core/form.html', {'form': form, 'title': 'Record Assessment Result'})


@login_required
def result_update(request, pk):
	access_denied = _deny_if_not(_is_teacher_or_admin(request.user))
	if access_denied:
		return access_denied

	result = get_object_or_404(AssessmentResult, pk=pk)
	if request.method == 'POST':
		form = AssessmentResultForm(request.POST, instance=result)
		if form.is_valid():
			updated = form.save(commit=False)
			updated.teacher = request.user
			updated.save()
			messages.success(request, 'Assessment result updated successfully.')
			return redirect('result_list')
	else:
		form = AssessmentResultForm(instance=result)
	return render(request, 'core/form.html', {'form': form, 'title': 'Update Assessment Result'})


@login_required
def result_delete(request, pk):
	access_denied = _deny_if_not(_is_teacher_or_admin(request.user))
	if access_denied:
		return access_denied

	result = get_object_or_404(AssessmentResult, pk=pk)
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

	class_filter = request.GET.get('class_name', '').strip()
	competency_filter = request.GET.get('competency', '').strip()
	rating_filter = request.GET.get('rating', '').strip()

	results = AssessmentResult.objects.select_related('learner', 'task', 'task__competency').all()
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
		results = AssessmentResult.objects.filter(learner=learner).select_related('task', 'task__competency') if learner else []
	else:
		results = AssessmentResult.objects.select_related('learner', 'task', 'task__competency').all()

	return render(request, 'core/feedback.html', {'results': results, 'role': role})
