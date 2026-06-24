from django import forms
from django.contrib.auth.models import User

from .models import AssessmentResult, AssessmentTask, Competency, LearnerProfile, UserAccount


class UserAccountCreateForm(forms.Form):
    username = forms.CharField(max_length=150)
    password = forms.CharField(widget=forms.PasswordInput)
    full_name = forms.CharField(max_length=100)
    email = forms.EmailField()
    role = forms.ChoiceField(choices=UserAccount.ROLE_CHOICES)
    status = forms.ChoiceField(choices=UserAccount.STATUS_CHOICES)

    def clean_username(self):
        username = self.cleaned_data['username']
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError('Username already exists.')
        return username

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
        UserAccount.objects.create(
            user=user,
            role=self.cleaned_data['role'],
            status=self.cleaned_data['status'],
        )
        return user


class UserAccountUpdateForm(forms.Form):
    full_name = forms.CharField(max_length=100)
    email = forms.EmailField()
    role = forms.ChoiceField(choices=UserAccount.ROLE_CHOICES)
    status = forms.ChoiceField(choices=UserAccount.STATUS_CHOICES)

    def __init__(self, *args, user_obj=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_obj = user_obj

    def save(self):
        full_name = self.cleaned_data['full_name'].strip()
        first_name, _, last_name = full_name.partition(' ')
        self.user_obj.first_name = first_name
        self.user_obj.last_name = last_name
        self.user_obj.email = self.cleaned_data['email']
        self.user_obj.is_active = self.cleaned_data['status'] == UserAccount.STATUS_ACTIVE
        self.user_obj.save()

        account = self.user_obj.account
        account.role = self.cleaned_data['role']
        account.status = self.cleaned_data['status']
        account.save()
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

    def clean_user_account(self):
        user_account = self.cleaned_data['user_account']
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
    class Meta:
        model = AssessmentTask
        fields = ['competency', 'task_title', 'task_description', 'task_date']
        widgets = {
            'task_date': forms.DateInput(attrs={'type': 'date'}),
        }


class AssessmentResultForm(forms.ModelForm):
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
