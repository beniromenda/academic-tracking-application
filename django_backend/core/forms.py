from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User

from .models import AssessmentResult, AssessmentTask, Competency, LearnerProfile, Subject, UserAccount


class AccountAuthenticationForm(AuthenticationForm):
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


class UserAccountCreateForm(forms.Form):
    username = forms.CharField(max_length=150)
    password = forms.CharField(widget=forms.PasswordInput)
    full_name = forms.CharField(max_length=100)
    email = forms.EmailField()
    role = forms.ChoiceField(choices=UserAccount.ROLE_CHOICES)
    status = forms.ChoiceField(choices=UserAccount.STATUS_CHOICES)
    subjects = forms.ModelMultipleChoiceField(
        queryset=Subject.objects.all(),
        required=False,
        help_text='Assign one or more subjects for teacher accounts.',
    )

    def clean_username(self):
        username = self.cleaned_data['username']
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError('Username already exists.')
        return username

    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get('role')
        subjects = cleaned_data.get('subjects')
        if role == UserAccount.ROLE_TEACHER and not subjects:
            self.add_error('subjects', 'Select at least one subject for a teacher account.')
        return cleaned_data

    def save(self):
        full_name = self.cleaned_data['full_name'].strip()
        first_name, _, last_name = full_name.partition(' ')
        user = User.objects.create_user(
            username=self.cleaned_data['username'],
            password=self.cleaned_data['password'],
            first_name=first_name,
            last_name=last_name,
            email=self.cleaned_data['email'],
            is_active=self.cleaned_data['status'] == UserAccount.STATUS_ACTIVE,
        )
        account = UserAccount.objects.create(
            user=user,
            role=self.cleaned_data['role'],
            status=self.cleaned_data['status'],
        )
        if self.cleaned_data['role'] == UserAccount.ROLE_TEACHER:
            account.subjects.set(self.cleaned_data['subjects'])
        return user


class UserAccountUpdateForm(forms.Form):
    full_name = forms.CharField(max_length=100)
    email = forms.EmailField()
    role = forms.ChoiceField(choices=UserAccount.ROLE_CHOICES)
    status = forms.ChoiceField(choices=UserAccount.STATUS_CHOICES)
    subjects = forms.ModelMultipleChoiceField(
        queryset=Subject.objects.all(),
        required=False,
        help_text='Assign one or more subjects for teacher accounts.',
    )

    def __init__(self, *args, user_obj=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_obj = user_obj
        account = UserAccount.objects.filter(user=self.user_obj).first()
        if account and account.role == UserAccount.ROLE_TEACHER:
            self.fields['subjects'].initial = account.subjects.all()

    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get('role')
        subjects = cleaned_data.get('subjects')
        if role == UserAccount.ROLE_TEACHER and not subjects:
            self.add_error('subjects', 'Select at least one subject for a teacher account.')
        return cleaned_data

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
        if self.cleaned_data['role'] == UserAccount.ROLE_TEACHER:
            account.subjects.set(self.cleaned_data['subjects'])
        else:
            account.subjects.clear()
        return self.user_obj


class LearnerProfileForm(forms.ModelForm):
    class Meta:
        model = LearnerProfile
        fields = ['user_account', 'admission_number', 'full_name', 'gender', 'class_name', 'date_of_birth']
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        qs = UserAccount.objects.filter(role=UserAccount.ROLE_LEARNER, status=UserAccount.STATUS_ACTIVE)
        if self.instance and self.instance.pk:
            qs = qs | UserAccount.objects.filter(pk=self.instance.user_account_id)
        self.fields['user_account'].queryset = qs.distinct()
        self.fields['user_account'].required = False
        self.fields['user_account'].help_text = (
            'Optional. Link this learner to an existing learner account. '
            'Leave blank if no learner account has been created yet.'
        )

    def clean_user_account(self):
        user_account = self.cleaned_data.get('user_account')
        if not user_account:
            return None
        existing = LearnerProfile.objects.filter(user_account=user_account)
        if self.instance.pk:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise forms.ValidationError('This learner user account already has a profile.')
        return user_account


class CompetencyForm(forms.ModelForm):
    class Meta:
        model = Competency
        fields = ['competency_code', 'competency_name', 'description']


class AssessmentTaskForm(forms.ModelForm):
    def __init__(self, *args, active_subject=None, **kwargs):
        super().__init__(*args, **kwargs)
        if active_subject:
            self.fields['competency'].queryset = Competency.objects.all()
            self.fields['subject'].initial = active_subject
            self.fields['subject'].widget = forms.HiddenInput()
        else:
            self.fields['subject'].widget = forms.HiddenInput()

    class Meta:
        model = AssessmentTask
        fields = ['subject', 'competency', 'task_title', 'task_description', 'task_date']
        widgets = {
            'task_date': forms.DateInput(attrs={'type': 'date'}),
        }


class AssessmentResultForm(forms.ModelForm):
    def __init__(self, *args, active_subject=None, **kwargs):
        super().__init__(*args, **kwargs)
        if active_subject:
            tasks = AssessmentTask.objects.filter(subject=active_subject)
            if self.instance and self.instance.pk:
                tasks = tasks | AssessmentTask.objects.filter(pk=self.instance.task_id)
            self.fields['task'].queryset = tasks.distinct()

    class Meta:
        model = AssessmentResult
        fields = ['learner', 'task', 'score', 'rating', 'feedback', 'assessment_date']
        widgets = {
            'assessment_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        learner = cleaned_data.get('learner')
        task = cleaned_data.get('task')
        if learner and task:
            existing = AssessmentResult.objects.filter(learner=learner, task=task)
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise forms.ValidationError('A result for this learner and task already exists.')
        return cleaned_data
