from django import forms
from .models import Book, Article, Course, Tag
from core.models import Category


class TagsMixin:
    """Handles the M2M logic for the 'tags' field using a CharField input."""

    def __init__(self, *args, **kwargs):
        """Initialize the form and handle initial tags data."""
        instance = kwargs.get('instance')

        # 1. PRE-POPULATE INITIAL TAGS (for Edit Mode)
        if instance and instance.pk:
            initial = kwargs.setdefault('initial', {})

            # Check if tags relationship is available before querying
            try:
                tags = instance.tags.all()
                tag_names = ','.join(tag.name for tag in tags)
                initial['tags_string'] = tag_names
            except Exception as e:
                # Log or handle gracefully
                print(f"Warning: Could not set initial tags for instance: {e}")
                initial['tags_string'] = ''
        else:
            # Ensure initial dict exists for new instances
            kwargs.setdefault('initial', {})
            kwargs['initial'].setdefault('tags_string', '')

        # 2. Call super().__init__ to finalize form construction

        super().__init__(*args, **kwargs)



        # 3. Now that the form is initialized, we can safely customize the widget
        if 'tags_string' in self.fields:
            common_attrs = {
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent',
                'placeholder': 'Add tags separated by commas'
            }
            self.fields['tags_string'].widget.attrs.update(common_attrs)


    def clean_tags_string(self):
        """Cleans and validates the tags input."""
        tags_input = self.cleaned_data.get('tags_string', '')
        tags_list = tags_input.split(',')
        cleaned_tags = {
            tag.strip().lower() for tag in tags_list if tag.strip()
        }
        return cleaned_tags

    def save_tags(self, resource_instance):
        """Finds or creates tags and sets them on the resource instance."""
        cleaned_tags = self.cleaned_data.get('tags_string')
        if cleaned_tags is not None:
            tag_objects = []
            for tag_name in cleaned_tags:
                tag_obj, created = Tag.objects.get_or_create(name=tag_name)
                tag_objects.append(tag_obj)
            resource_instance.tags.set(tag_objects)


class BaseResourceForm(TagsMixin, forms.ModelForm):
    """Base form with common fields and widgets for all resources."""

    # Define tags_string as a form field here
    tags_string = forms.CharField(
        required=False,
        label='Tags (Comma Separated)',
        help_text='Add relevant tags to help others find your resource',
    )

    class Meta:
        # Abstract base - will be overridden in child classes
        model = None
        fields = ['title', 'description', 'category', 'difficulty', 'url']
        exclude = ['tags']

    def __init__(self, *args, **kwargs):
        # Call TagsMixin.__init__ first, then forms.ModelForm.__init__
        super().__init__(*args, **kwargs)

        #Apply widgets to fields that exist
        #... (title, description, category, difficulty widget updates remain the same) ...

        common_attrs = {
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent',
        }

        # Apply widgets to fields that exist
        if 'title' in self.fields:
            self.fields['title'].widget.attrs.update({
                **common_attrs,
                'placeholder': 'Resource Title'
            })

        if 'description' in self.fields:
            self.fields['description'].widget.attrs.update({
                **common_attrs,
                'rows': 4,
                'placeholder': 'Describe the resource'
            })
        # --- ADD the tags_string widget application here in BaseResourceForm: ---
        if 'tags_string' in self.fields:
            common_attrs = {
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent',
                'placeholder': 'Add tags separated by commas'
            }
            # Use update for consistency
            self.fields['tags_string'].widget.attrs.update(common_attrs)

        if 'category' in self.fields:
            self.fields['category'].widget.attrs.update(common_attrs)
            self.fields['category'].queryset = Category.objects.all()
            self.fields['category'].empty_label = "Select a category"

        if 'difficulty' in self.fields:
            self.fields['difficulty'].widget.attrs.update({'class': 'hidden'})

        # Custom attribute for difficulty choices
        self.difficulty_choices = self._get_difficulty_choices()

    def _get_difficulty_choices(self):
        """Helper to format difficulty choices for radio buttons in the template."""
        choices = []
        if 'difficulty' in self.fields:
            for value, label in self.fields['difficulty'].choices:
                if value:  # Skip empty choice
                    icon = {'B': '🟢', 'I': '🟡', 'A': '🔴'}.get(value, '')
                    description = {
                        'B': 'No prior experience needed',
                        'I': 'Some basic knowledge required',
                        'A': 'For experienced developers'
                    }.get(value, '')

                    # Check if this choice is selected
                    current_value = self.initial.get('difficulty', '')
                    is_selected = str(value) == str(current_value)

                    choices.append({
                        'value': value,
                        'label': f"{icon} {label}",
                        'description': description,
                        'selected': is_selected
                    })
        return choices

    def save(self, commit=True):
        """Handles saving the resource and its tags."""
        resource = super().save(commit=False)

        if commit:
            resource.save()

            # Save tags from TagsMixin
            self.save_tags(resource)

            # Save other M2M if needed
            self.save_m2m()

        return resource


# Concrete Forms
class BookForm(BaseResourceForm):
    class Meta(BaseResourceForm.Meta):
        model = Book
        fields = BaseResourceForm.Meta.fields + ['file', 'pages']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Apply book-specific widgets
        if 'file' in self.fields:
            self.fields['file'].widget.attrs.update({
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg'
            })

        if 'pages' in self.fields:
            self.fields['pages'].widget.attrs.update({
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg',
                'placeholder': 'Number of pages (optional)'
            })


class ArticleForm(BaseResourceForm):
    class Meta(BaseResourceForm.Meta):
        model = Article
        fields = BaseResourceForm.Meta.fields + ['content', 'banner_image']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Apply article-specific widgets
        if 'content' in self.fields:
            self.fields['content'].widget.attrs.update({
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg',
                'rows': 8,
                'placeholder': 'Write your article content here'
            })

        if 'banner_image' in self.fields:
            self.fields['banner_image'].widget.attrs.update({
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg'
            })


class CourseForm(BaseResourceForm):
    class Meta(BaseResourceForm.Meta):
        model = Course
        fields = BaseResourceForm.Meta.fields + ['estimated_duration']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Apply course-specific widgets
        if 'estimated_duration' in self.fields:
            self.fields['estimated_duration'].widget.attrs.update({
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg',
                'placeholder': 'e.g., 7 days'
            })