from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Subject(models.Model):
	subject_code = models.CharField(max_length=20, unique=True)
	subject_name = models.CharField(max_length=100, unique=True)

	class Meta:
		ordering = ['subject_name']

	def __str__(self):
		return f'{self.subject_code} - {self.subject_name}'


class UserAccount(models.Model):
	ROLE_ADMINISTRATOR = 'Administrator'
	ROLE_TEACHER = 'Teacher'
	ROLE_LEARNER = 'Learner'
	ROLE_CHOICES = [
		(ROLE_ADMINISTRATOR, 'Administrator'),
		(ROLE_TEACHER, 'Teacher'),
		(ROLE_LEARNER, 'Learner'),
	]

	STATUS_ACTIVE = 'Active'
	STATUS_INACTIVE = 'Inactive'
	STATUS_CHOICES = [
		(STATUS_ACTIVE, 'Active'),
		(STATUS_INACTIVE, 'Inactive'),
	]

	user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='account')
	role = models.CharField(max_length=20, choices=ROLE_CHOICES)
	status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
	subjects = models.ManyToManyField(Subject, blank=True, related_name='teachers')

	class Meta:
		ordering = ['user__username']

	def __str__(self):
		return f'{self.user.username} ({self.role})'


class LearnerProfile(models.Model):
	GENDER_MALE = 'Male'
	GENDER_FEMALE = 'Female'
	GENDER_OTHER = 'Other'
	GENDER_CHOICES = [
		(GENDER_MALE, 'Male'),
		(GENDER_FEMALE, 'Female'),
		(GENDER_OTHER, 'Other'),
	]

	user_account = models.OneToOneField(
		UserAccount,
		on_delete=models.CASCADE,
		related_name='learner_profile',
		null=True,
		blank=True,
	)
	created_by = models.ForeignKey(
		User,
		on_delete=models.PROTECT,
		related_name='created_learners',
		null=True,
		blank=True,
	)
	admission_number = models.CharField(max_length=20, unique=True)
	full_name = models.CharField(max_length=100)
	gender = models.CharField(max_length=10, choices=GENDER_CHOICES)
	class_name = models.CharField(max_length=50)
	date_of_birth = models.DateField()

	class Meta:
		ordering = ['full_name']

	def __str__(self):
		return f'{self.full_name} ({self.admission_number})'


class Competency(models.Model):
	competency_code = models.CharField(max_length=20, unique=True)
	competency_name = models.CharField(max_length=100)
	description = models.TextField(blank=True)
	created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='created_competencies')

	class Meta:
		ordering = ['competency_code']

	def __str__(self):
		return f'{self.competency_code} - {self.competency_name}'


class AssessmentTask(models.Model):
	subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name='assessment_tasks', null=True, blank=True)
	competency = models.ForeignKey(Competency, on_delete=models.CASCADE, related_name='tasks')
	teacher = models.ForeignKey(User, on_delete=models.PROTECT, related_name='created_tasks')
	task_title = models.CharField(max_length=100)
	task_description = models.TextField(blank=True)
	task_date = models.DateField()

	class Meta:
		ordering = ['-task_date', 'task_title']

	def __str__(self):
		return f'{self.task_title} ({self.subject.subject_name if self.subject else self.competency.competency_code})'


class AssessmentResult(models.Model):
	learner = models.ForeignKey(LearnerProfile, on_delete=models.CASCADE, related_name='results')
	task = models.ForeignKey(AssessmentTask, on_delete=models.CASCADE, related_name='results')
	teacher = models.ForeignKey(User, on_delete=models.PROTECT, related_name='recorded_results')
	score = models.DecimalField(
		max_digits=5,
		decimal_places=2,
		validators=[MinValueValidator(0), MaxValueValidator(100)],
	)
	rating = models.CharField(max_length=30)
	feedback = models.TextField(blank=True)
	assessment_date = models.DateField()

	class Meta:
		ordering = ['-assessment_date']
		constraints = [
			models.UniqueConstraint(fields=['learner', 'task'], name='unique_learner_task_result'),
		]

	def __str__(self):
		return f'{self.learner.full_name} - {self.task.task_title} ({self.score})'
