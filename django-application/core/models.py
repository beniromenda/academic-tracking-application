from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


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
	teacher_id = models.PositiveIntegerField(unique=True, null=True, blank=True, editable=False)
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
	date_of_birth = models.DateField(null=True, blank=True)
	created_at = models.DateTimeField(default=timezone.now, editable=False)

	class Meta:
		ordering = ['full_name']

	def __str__(self):
		return f'{self.full_name} ({self.admission_number})'


class TeacherLearnerRecord(models.Model):
	teacher = models.ForeignKey(User, on_delete=models.CASCADE, related_name='teacher_learner_records')
	learner_profile = models.ForeignKey(LearnerProfile, on_delete=models.CASCADE, related_name='teacher_records')
	created_at = models.DateTimeField(default=timezone.now, editable=False)

	class Meta:
		ordering = ['learner_profile__full_name']
		constraints = [
			models.UniqueConstraint(fields=['teacher', 'learner_profile'], name='unique_teacher_learner_record'),
		]

	def __str__(self):
		return f'{self.teacher.username} - {self.learner_profile.full_name}'


class Competency(models.Model):
	competency_code = models.CharField(max_length=20, unique=True)
	competency_name = models.CharField(max_length=100)
	learning_outcome = models.TextField()
	created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='created_competencies')
	created_at = models.DateTimeField(default=timezone.now, editable=False)

	class Meta:
		ordering = ['competency_code']

	def __str__(self):
		return f'{self.competency_code} - {self.competency_name}'


class TeacherLearnerCompetencyAssignment(models.Model):
	teacher_learner_record = models.ForeignKey(
		TeacherLearnerRecord,
		on_delete=models.CASCADE,
		related_name='competency_assignments',
	)
	competency = models.ForeignKey(
		Competency,
		on_delete=models.CASCADE,
		related_name='teacher_assignments',
	)
	assigned_at = models.DateTimeField(default=timezone.now, editable=False)

	class Meta:
		ordering = ['competency__competency_code']
		constraints = [
			models.UniqueConstraint(
				fields=['teacher_learner_record', 'competency'],
				name='unique_teacher_learner_competency_assignment',
			),
		]

	def __str__(self):
		return f'{self.teacher_learner_record} - {self.competency.competency_code}'


class AssessmentTask(models.Model):
	subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name='assessment_tasks', null=True, blank=True)
	competency = models.ForeignKey(Competency, on_delete=models.CASCADE, related_name='tasks')
	created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='created_tasks')
	task_name = models.CharField(max_length=100, unique=True)
	description = models.TextField()
	task_date = models.DateField(default=timezone.localdate)
	created_at = models.DateTimeField(default=timezone.now, editable=False)

	class Meta:
		ordering = ['-created_at', 'task_name']

	def __str__(self):
		return f'{self.task_name} ({self.competency.competency_code})'


class AssessmentResult(models.Model):
	MASTERY_NOT_YET_DEMONSTRATED = 'Not Yet Demonstrated'
	MASTERY_DEVELOPING = 'Developing'
	MASTERY_PROFICIENT = 'Proficient'
	MASTERY_MASTERY = 'Mastery'
	MASTERY_STATUS_CHOICES = [
		(MASTERY_NOT_YET_DEMONSTRATED, 'Not Yet Demonstrated'),
		(MASTERY_DEVELOPING, 'Developing'),
		(MASTERY_PROFICIENT, 'Proficient'),
		(MASTERY_MASTERY, 'Mastery'),
	]

	learner = models.ForeignKey(LearnerProfile, on_delete=models.CASCADE, related_name='results')
	teacher_learner_record = models.ForeignKey(
		TeacherLearnerRecord,
		on_delete=models.CASCADE,
		related_name='results',
		null=True,
		blank=True,
	)
	task = models.ForeignKey(AssessmentTask, on_delete=models.CASCADE, related_name='results')
	created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='recorded_results')
	score = models.DecimalField(
		max_digits=5,
		decimal_places=2,
		validators=[MinValueValidator(0), MaxValueValidator(100)],
	)
	cbc_rating = models.CharField(max_length=30)
	assessment_date = models.DateField(default=timezone.localdate)
	mastery_status = models.CharField(
		max_length=50,
		choices=MASTERY_STATUS_CHOICES,
		default=MASTERY_DEVELOPING,
	)
	feedback = models.TextField()
	created_at = models.DateTimeField(default=timezone.now, editable=False)

	class Meta:
		ordering = ['-created_at']
		constraints = [
			models.UniqueConstraint(
				fields=['teacher_learner_record', 'task'],
				condition=models.Q(teacher_learner_record__isnull=False),
				name='unique_teacher_learner_task_result',
			),
		]

	def __str__(self):
		return f'{self.learner.full_name} - {self.task.task_name} ({self.score})'


class LearnerReportFeedback(models.Model):
	learner = models.ForeignKey(LearnerProfile, on_delete=models.CASCADE, related_name='report_feedbacks')
	teacher_learner_record = models.ForeignKey(
		TeacherLearnerRecord,
		on_delete=models.CASCADE,
		related_name='report_feedbacks',
		null=True,
		blank=True,
	)
	competency = models.ForeignKey(Competency, on_delete=models.CASCADE, related_name='report_feedbacks')
	teacher = models.ForeignKey(User, on_delete=models.PROTECT, related_name='written_report_feedbacks')
	feedback = models.TextField()
	overall_competency_status = models.CharField(
		max_length=50,
		choices=AssessmentResult.MASTERY_STATUS_CHOICES,
		default=AssessmentResult.MASTERY_DEVELOPING,
	)
	assessment_results = models.ManyToManyField(AssessmentResult, blank=True, related_name='saved_report_feedbacks')
	is_available_for_learner = models.BooleanField(default=False)
	created_at = models.DateTimeField(default=timezone.now, editable=False)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ['-updated_at']
		constraints = [
			models.UniqueConstraint(
				fields=['teacher_learner_record', 'competency'],
				condition=models.Q(teacher_learner_record__isnull=False),
				name='unique_teacher_learner_competency_report_feedback',
			),
		]

	def __str__(self):
		return f'Report: {self.learner.full_name} - {self.competency.competency_code}'
