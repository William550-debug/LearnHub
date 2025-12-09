from django import forms
from .models import Resource, Tag
from core.models import Category  # Make sure this import exists


class ResourceForm(forms.ModelForm):
    # Custom Field: Accept tags as a comma-separated string from the template
    tags_string = forms.CharField(
        required=False,
        label='Tags (Comma Separated)',
        help_text='Add relevant tags to help others find your resource',
    )

    class Meta:
        model = Resource

        # Includes all the necessary fields from the Resource Model
        fields = [
            'title', 'url', 'description', 'category',
            'difficulty', 'tags_string',  # We handle tags via tags_string
        ]

        # Customize form widgets to match the required HTML structure for Tailwind
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent',
                'placeholder': 'eg., Complete React Hooks Tutorial with coding walkthrough',
            }),
            'url': forms.URLInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent',
                'placeholder': 'eg. https://example.com/tutorial',
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent',
                'rows': 5,
                'placeholder': 'Describe what this resource entails',
            }),
            'category': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent',
                # Fixed typo
            }),
            # Difficulty is handled by the template's radio buttons
            # using Select is cleaner for ModelForm initial Setup
            'difficulty': forms.Select(attrs={
                'class': 'hidden'
            })
        }

    # Add a custom method to render difficulty as radio buttons
    def get_difficulty_choices(self):
        """Return formatted difficulty choices for radio buttons"""
        choices = []
        for value, label in self.fields['difficulty'].choices:
            if value:  # Skip empty choice
                icon = {
                    'B': '🟢',
                    'I': '🟡',
                    'A': '🔴'
                }.get(value, '')
                description = {
                    'B': 'No prior experience needed',
                    'I': 'Some basic knowledge required',
                    'A': 'For experienced developers'
                }.get(value, '')

                choices.append({
                    'value': value,
                    'label': f"{icon} {label}",
                    'description': description,
                    'selected': str(value) == str(self.initial.get('difficulty', ''))
                })
        return choices

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Populate the tags_string field if the form is bound to an existing instance
        if self.instance and self.instance.pk:
            tags = self.instance.tags.all()
            self.initial['tags_string'] = ','.join(tag.name for tag in tags)

        # FIX: Ensure category field uses the correct queryset
        self.fields['category'].queryset = Category.objects.all()

        # FIX: Add empty label for better UX
        self.fields['category'].empty_label = "Select a category"

        # Custom attribute for difficulty choices
        self.difficulty_choices = self.get_difficulty_choices()

    def save(self, commit=True):
        # 1. Save the resource instance first
        resource = super().save(commit=False)

        if commit:
            # We assume the author is set in the view before this save is called
            resource.save()

            # 2. Handle Tags (M2M)
            tags_list = self.cleaned_data.get('tags_string', '').split(',')
            # Clean up and get unique and non-empty tags
            cleaned_tags = {
                tag.strip().lower() for tag in tags_list if tag.strip()
            }

            # Find or create tag instances
            tag_objects = []
            for tag_name in cleaned_tags:
                tag_obj, created = Tag.objects.get_or_create(name=tag_name)
                tag_objects.append(tag_obj)

            # Update the M2M field
            resource.tags.set(tag_objects)

        return resource