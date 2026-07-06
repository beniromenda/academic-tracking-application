from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.utils import timezone

from .models import AssessmentResult, AssessmentTask, Competency, LearnerProfile, Subject, TeacherLearnerRecord, UserAccount


ACCOUNT_ROLE_CHOICES = [
    (UserAccount.ROLE_ADMINISTRATOR, 'Administrator'),
    (UserAccount.ROLE_TEACHER, 'Teacher'),
    (UserAccount.ROLE_LEARNER, 'Learner'),
]

CBC_RATING_CHOICES = [
    ('Exceeding Expectations', 'Exceeding Expectations'),
    ('Meeting Expectations', 'Meeting Expectations'),
    ('Approaching Expectations', 'Approaching Expectations'),
    ('Below Expectations', 'Below Expectations'),
]


class AccountAuthenticationForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].label = 'Email address or username'
        self.fields['username'].widget = forms.TextInput(attrs={
            'autocomplete': 'username',
            'placeholder': 'you@example.com or username',
        })
        self.fields['password'].widget = forms.PasswordInput(attrs={
            'autocomplete': 'current-password',
            'placeholder': 'Enter your password',
        })

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if user.is_superuser:
            return

        account = UserAccount.objects.filter(user=user).first()
        if not account:
            raise forms.ValidationError(
                'Your account is not provisioned yet. Please contact an administrator.',
                code='account_not_provisioned',
            )
        if account.status != UserAccount.STATUS_ACTIVE:
            raise forms.ValidationError(
                'Your account is inactive. Please contact an administrator.',
                code='account_inactive',
            )


class SubjectSelectionForm(forms.Form):
    subject = forms.ModelChoiceField(queryset=Subject.objects.none(), empty_label=None)

    def __init__(self, *args, subjects=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['subject'].queryset = subjects if subjects is not None else Subject.objects.none()


class SubjectForm(forms.ModelForm):
    class Meta:
        model = Subject
        fields = ['subject_code', 'subject_name']


class TeacherAccountCreateForm(forms.Form):
    full_name = forms.CharField(max_length=100)
    username = forms.CharField(max_length=150)
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'autocomplete': 'email'}),
    )
    password = forms.CharField(
        required=True,
        min_length=8,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
    )
    confirm_password = forms.CharField(
        required=True,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
    )
    status = forms.ChoiceField(
        choices=UserAccount.STATUS_CHOICES,
        initial=UserAccount.STATUS_ACTIVE,
    )

    def clean_username(self):
        username = self.cleaned_data['username'].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError('This username is already in use.')
        return username

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('This email address is already in use.')
        return email

    def clean_password(self):
        password = self.cleaned_data['password']
        if len(password) < 8:
            raise forms.ValidationError('Password must be at least 8 characters long.')
        return password

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')
        if password and confirm_password and password != confirm_password:
            self.add_error('confirm_password', 'Password and confirm password do not match.')
        return cleaned_data

    def save(self):
        full_name = self.cleaned_data['full_name'].strip()
        first_name, _, last_name = full_name.partition(' ')
        user = User.objects.create_user(
            username=self.cleaned_data['username'].strip(),
            password=self.cleaned_data['password'],
            first_name=first_name,
            last_name=last_name,
            email=self.cleaned_data['email'],
            is_active=self.cleaned_data['status'] == UserAccount.STATUS_ACTIVE,
            is_staff=True,
            is_superuser=False,
        )
        account = UserAccount.objects.create(
            user=user,
            teacher_id=user.pk,
            role=UserAccount.ROLE_TEACHER,
            status=self.cleaned_data['status'],
        )
        return account


class LearnerAccountCreateForm(forms.Form):
    admission_number = forms.CharField(max_length=20)
    full_name = forms.CharField(max_length=100)
    gender = forms.ChoiceField(choices=LearnerProfile.GENDER_CHOICES)
    class_name = forms.CharField(max_length=50)
    username = forms.CharField(max_length=150)
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'autocomplete': 'email'}),
    )
    password = forms.CharField(
        required=True,
        min_length=8,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
    )
    confirm_password = forms.CharField(
        required=True,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
    )
    status = forms.ChoiceField(
        choices=UserAccount.STATUS_CHOICES,
        initial=UserAccount.STATUS_ACTIVE,
    )

    def clean_username(self):
        username = self.cleaned_data['username'].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError('This username is already in use.')
        return username

    def clean_admission_number(self):
        admission_number = self.cleaned_data['admission_number'].strip()
        if LearnerProfile.objects.filter(admission_number__iexact=admission_number).exists():
            raise forms.ValidationError('This admission number is already in use.')
        return admission_number

    def clean_full_name(self):
        full_name = self.cleaned_data['full_name'].strip()
        if not full_name:
            raise forms.ValidationError('Full name is required.')
        return full_name

    def clean_class_name(self):
        class_name = self.cleaned_data['class_name'].strip()
        if not class_name:
            raise forms.ValidationError('Class name is required.')
        return class_name

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('This email address is already in use.')
        return email

    def clean_password(self):
        password = self.cleaned_data['password']
        if len(password) < 8:
            raise forms.ValidationError('Password must be at least 8 characters long.')
        return password

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')
        if password and confirm_password and password != confirm_password:
            self.add_error('confirm_password', 'Password and confirm password do not match.')
        return cleaned_data

    def save(self, created_by=None):
        full_name = self.cleaned_data['full_name'].strip()
        first_name, _, last_name = full_name.partition(' ')
        user = User.objects.create_user(
            username=self.cleaned_data['username'].strip(),
            password=self.cleaned_data['password'],
            first_name=first_name,
            last_name=last_name,
            email=self.cleaned_data['email'],
            is_active=self.cleaned_data['status'] == UserAccount.STATUS_ACTIVE,
            is_staff=False,
            is_superuser=False,
        )
        account = UserAccount.objects.create(
            user=user,
            role=UserAccount.ROLE_LEARNER,
            status=self.cleaned_data['status'],
        )
        learner = LearnerProfile.objects.create(
            user_account=account,
            created_by=created_by,
            admission_number=self.cleaned_data['admission_number'],
            full_name=full_name,
            gender=self.cleaned_data['gender'],
            class_name=self.cleaned_data['class_name'],
        )
        return learner


class UserAccountCreateForm(forms.Form):
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'autocomplete': 'email'}),
    )
    password = forms.CharField(
        required=True,
        min_length=8,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
    )
    confirm_password = forms.CharField(
        required=True,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
    )
    full_name = forms.CharField(max_length=100)
    role = forms.ChoiceField(choices=ACCOUNT_ROLE_CHOICES)
    status = forms.ChoiceField(
        choices=UserAccount.STATUS_CHOICES,
        initial=UserAccount.STATUS_ACTIVE,
    )

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('This email address is already in use.')
        return email

    def clean_password(self):
        password = self.cleaned_data['password']
        if len(password) < 8:
            raise forms.ValidationError('Password must be at least 8 characters long.')
        return password

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')
        if password and confirm_password and password != confirm_password:
            self.add_error('confirm_password', 'Password and confirm password do not match.')
        return cleaned_data

    def save(self):
        full_name = self.cleaned_data['full_name'].strip()
        first_name, _, last_name = full_name.partition(' ')
        email = self.cleaned_data['email']
        role = self.cleaned_data['role']
        is_active = self.cleaned_data['status'] == UserAccount.STATUS_ACTIVE
        is_admin = role == UserAccount.ROLE_ADMINISTRATOR
        is_teacher = role == UserAccount.ROLE_TEACHER

        user = User.objects.create_user(
            username=email,
            password=self.cleaned_data['password'],
            first_name=first_name,
            last_name=last_name,
            email=email,
            is_active=is_active,
            is_staff=is_admin or is_teacher,
            is_superuser=False,
        )
        account = UserAccount.objects.create(
            user=user,
            role=role,
            status=self.cleaned_data['status'],
        )
        return user


class UserAccountUpdateForm(forms.Form):
    full_name = forms.CharField(max_length=100)
    email = forms.EmailField()
    role = forms.ChoiceField(choices=ACCOUNT_ROLE_CHOICES)
    status = forms.ChoiceField(choices=UserAccount.STATUS_CHOICES)

    def __init__(self, *args, user_obj=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_obj = user_obj

    def clean(self):
        return super().clean()

    def save(self):
        full_name = self.cleaned_data['full_name'].strip()
        first_name, _, last_name = full_name.partition(' ')
        self.user_obj.first_name = first_name
        self.user_obj.last_name = last_name
        self.user_obj.email = self.cleaned_data['email']
        self.user_obj.is_active = self.cleaned_data['status'] == UserAccount.STATUS_ACTIVE
        self.user_obj.save()

        default_role = UserAccount.ROLE_ADMINISTRATOR if self.user_obj.is_superuser else (
            UserAccount.ROLE_TEACHER if self.user_obj.is_staff else UserAccount.ROLE_LEARNER
        )
        account, _ = UserAccount.objects.get_or_create(
            user=self.user_obj,
            defaults={
                'role': default_role,
                'status': UserAccount.STATUS_ACTIVE if self.user_obj.is_active else UserAccount.STATUS_INACTIVE,
            },
        )
        account.role = self.cleaned_data['role']
        account.status = self.cleaned_data['status']
        account.save()
        return self.user_obj


class LearnerProfileForm(forms.ModelForm):
    class Meta:
        model = LearnerProfile
        fields = ['admission_number', 'full_name', 'gender', 'class_name']
        labels = {
            'admission_number': 'Admission Number',
            'full_name': 'Full Name',
            'gender': 'Gender',
            'class_name': 'Class Name',
        }
        widgets = {
            'admission_number': forms.TextInput(attrs={'placeholder': 'Admission number'}),
            'full_name': forms.TextInput(attrs={'placeholder': 'Full name'}),
            'class_name': forms.TextInput(attrs={'placeholder': 'Class 7A'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def clean_admission_number(self):
        admission_number = self.cleaned_data['admission_number'].strip()
        existing = LearnerProfile.objects.filter(admission_number__iexact=admission_number)
        if self.instance.pk:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise forms.ValidationError('This admission number is already in use.')
        return admission_number

    def clean_full_name(self):
        return self.cleaned_data['full_name'].strip()

    def clean_class_name(self):
        return self.cleaned_data['class_name'].strip()


class CompetencyForm(forms.ModelForm):
    class Meta:
        model = Competency
        fields = ['competency_code', 'competency_name', 'learning_outcome']
        labels = {
            'competency_code': 'Competency Code',
            'competency_name': 'Competency Name',
            'learning_outcome': 'Learning Outcome',
        }
        widgets = {
            'competency_code': forms.TextInput(attrs={'placeholder': 'MATH-001'}),
            'competency_name': forms.TextInput(attrs={'placeholder': 'Number Sense'}),
            'learning_outcome': forms.Textarea(attrs={'rows': 5, 'placeholder': 'Describe what learners should be able to do'}),
        }

    def clean_competency_code(self):
        competency_code = self.cleaned_data['competency_code'].strip()
        existing = Competency.objects.filter(competency_code__iexact=competency_code)
        if self.instance.pk:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise forms.ValidationError('Competency code must be unique.')
        return competency_code

    def clean_competency_name(self):
        competency_name = self.cleaned_data['competency_name'].strip()
        if not competency_name:
            raise forms.ValidationError('Competency name is required.')
        return competency_name

    def clean_learning_outcome(self):
        learning_outcome = self.cleaned_data['learning_outcome'].strip()
        if len(learning_outcome) < 10:
            raise forms.ValidationError('Learning Outcome must be at least 10 characters long.')
        return learning_outcome


class AssessmentTaskForm(forms.ModelForm):
    def __init__(self, *args, active_subject=None, current_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if current_user and hasattr(current_user, 'account') and getattr(current_user.account, 'role', None) == UserAccount.ROLE_TEACHER:
            competencies = Competency.objects.filter(created_by=current_user)
            if self.instance and self.instance.pk:
                competencies = competencies | Competency.objects.filter(pk=self.instance.competency_id)
            self.fields['competency'].queryset = competencies.distinct().order_by('competency_code')
        if active_subject:
            self.fields['subject'].initial = active_subject
            self.fields['subject'].widget = forms.HiddenInput()
        else:
            self.fields['subject'].widget = forms.HiddenInput()
        if not self.instance.pk and not self.initial.get('task_date'):
            self.fields['task_date'].initial = timezone.localdate()

    class Meta:
        model = AssessmentTask
        fields = ['subject', 'competency', 'task_name', 'description', 'task_date']
        labels = {
            'task_name': 'Task Name',
            'competency': 'Competency',
            'description': 'Description',
            'task_date': 'Task Date',
        }
        error_messages = {
            'competency': {
                'required': 'Competency must be selected.',
            },
            'task_name': {
                'required': 'Task Name is required.',
            },
            'description': {
                'required': 'Description is required.',
            },
        }
        widgets = {
            'task_name': forms.TextInput(attrs={'placeholder': 'Addition Problems Test'}),
            'description': forms.Textarea(attrs={'rows': 5, 'placeholder': 'What the task is about'}),
            'task_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def clean_task_name(self):
        task_name = self.cleaned_data['task_name'].strip()
        existing = AssessmentTask.objects.filter(task_name__iexact=task_name)
        if self.instance.pk:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise forms.ValidationError('Task name must be unique.')
        return task_name

    def clean_description(self):
        description = self.cleaned_data['description'].strip()
        if not description:
            raise forms.ValidationError('Description is required.')
        return description


class AssessmentResultForm(forms.ModelForm):
    def __init__(self, *args, active_subject=None, current_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        learner_records = TeacherLearnerRecord.objects.select_related('learner_profile').order_by('learner_profile__full_name')
        tasks = AssessmentTask.objects.select_related('competency').order_by('task_name')
        if current_user and hasattr(current_user, 'account') and getattr(current_user.account, 'role', None) == UserAccount.ROLE_TEACHER:
            learner_records = learner_records.filter(teacher=current_user)
            tasks = tasks.filter(created_by=current_user)
            if self.instance and self.instance.pk:
                learner_records = learner_records | TeacherLearnerRecord.objects.filter(pk=self.instance.teacher_learner_record_id)
                tasks = tasks | AssessmentTask.objects.filter(pk=self.instance.task_id)
        self.fields['teacher_learner_record'].queryset = learner_records.distinct()
        self.fields['teacher_learner_record'].label = 'Learner'
        self.fields['task'].queryset = tasks.distinct()
        if active_subject:
            tasks = AssessmentTask.objects.filter(subject=active_subject)
            if current_user and hasattr(current_user, 'account') and getattr(current_user.account, 'role', None) == UserAccount.ROLE_TEACHER:
                tasks = tasks.filter(created_by=current_user)
            if self.instance and self.instance.pk:
                tasks = tasks | AssessmentTask.objects.filter(pk=self.instance.task_id)
            self.fields['task'].queryset = tasks.distinct()

    class Meta:
        model = AssessmentResult
        fields = ['teacher_learner_record', 'task', 'score', 'cbc_rating', 'mastery_status']
        labels = {
            'cbc_rating': 'CBC Rating',
            'mastery_status': 'Mastery Status',
        }
        widgets = {
            'cbc_rating': forms.Select(choices=CBC_RATING_CHOICES),
        }

    def clean(self):
        cleaned_data = super().clean()
        teacher_learner_record = cleaned_data.get('teacher_learner_record')
        task = cleaned_data.get('task')
        if teacher_learner_record and task:
            existing = AssessmentResult.objects.filter(teacher_learner_record=teacher_learner_record, task=task)
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise forms.ValidationError('A result for this learner and task already exists.')
        return cleaned_data

    def clean_cbc_rating(self):
        cbc_rating = self.cleaned_data['cbc_rating']
        if not cbc_rating:
            raise forms.ValidationError('CBC Rating is required.')
        return cbc_rating

class BulkAssessmentResultEntryForm(forms.Form):
    task_id = forms.IntegerField(widget=forms.HiddenInput())
    score = forms.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=100)
    cbc_rating = forms.ChoiceField(choices=CBC_RATING_CHOICES)
    mastery_status = forms.ChoiceField(choices=AssessmentResult.MASTERY_STATUS_CHOICES)
    feedback = forms.CharField(widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'Teacher feedback'}))

    def clean_cbc_rating(self):
        cbc_rating = self.cleaned_data['cbc_rating']
        if not cbc_rating:
            raise forms.ValidationError('CBC Rating is required.')
        return cbc_rating

    def clean_feedback(self):
        feedback = self.cleaned_data['feedback'].strip()
        if not feedback:
            raise forms.ValidationError('Feedback is required.')
        return feedback
