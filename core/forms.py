from django import forms
from django.contrib.auth.forms import UserCreationForm,AuthenticationForm
from django.utils.text import slugify

from .models import CustomUser, UserProfile, Skill
from django.contrib.auth import get_user_model


class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(required=True, label='Email Address')
    first_name = forms.CharField(required=True, max_length=30)

    class Meta:
        model = CustomUser
        fields = ('email', 'first_name', 'password1', 'password2')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Hide username field instead of deleting it
        if 'username' in self.fields:
            self.fields['username'].widget = forms.HiddenInput()
            self.fields['username'].required = False

    def save(self, commit=True):
        user = super().save(commit=False)

        # Set email as username for compatibility
        user.username = self.cleaned_data['email'].split('@')[0]
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']

        if commit:
            user.save()

            # Create profile
            profile, created = UserProfile.objects.get_or_create(
                user=user,
                defaults={'bio': self.cleaned_data.get('bio', '')}
            )

            # Handle skills
            if self.cleaned_data.get('skills'):
                skills_input = self.cleaned_data['skills']
                skill_names = [s.strip() for s in skills_input.split(',') if s.strip()]

                for skill_name in skill_names:
                    skill, skill_created = Skill.objects.get_or_create(
                        name=skill_name,
                        defaults={'slug': slugify(skill_name)}
                    )
                    profile.skills.add(skill)

        return user


class EmailAuthenticationForm(AuthenticationForm):
    """
    Custom authentication form that uses email instead of username

    """
    username = forms.EmailField(
        label='Email Address',
        widget=forms.EmailInput(attrs={'autofocus': True, 'class': 'form-control'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].label = 'Email'



