from django import forms
from .models import LearningGoal, GoalMilestone


class LearningGoalForm(forms.ModelForm):
    """
    Form for creating and editing the main LearningGoal object.

    Uses custom widgets for a cleaner integration with Tailwind CSS/HTML5 inputs.
    """
    # Use a date input widget for better browser compatibility
    due_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg'})
    )

    class Meta:
        model = LearningGoal
        fields = ['title', 'description', 'due_date', 'status']
        # Customize other widgets for Tailwind styling
        widgets = {
            'title': forms.TextInput(attrs={'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg',
                                            'placeholder': 'e.g., Master React Hooks'}),
            'description': forms.Textarea(
                attrs={'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg', 'rows': 3,
                       'placeholder': 'Describe what you want to achieve...'}),
            # Status can be hidden in the UI but required for the model
            'status': forms.Select(attrs={'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg'}),
        }


class GoalMilestoneForm(forms.ModelForm):
    """
    Simple form for adding new milestones to an existing goal.
    """

    class Meta:
        model = GoalMilestone
        fields = ['title']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg',
                                            'placeholder': 'New milestone title...'}),
        }