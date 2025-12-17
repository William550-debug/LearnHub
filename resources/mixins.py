from django.shortcuts import get_object_or_404
from django.contrib.contenttypes.models import ContentType
from django.db import models
from .models import BaseResource, Book, Article, Course

def get_concrete_resource_type(base_resource_pk: int) -> BaseResource:
    """
    Given the primary key of a BaseResource, this function retrieves the
    actual concrete instance (Book, Article, or Course).

    :param base_resource_pk: The ID shared by the concrete resource.
    :return: The concrete instance of the resource.
    :raises Http404: If the resource does not exist.
    """
    # 1. Fetch the BaseResource object
    base_resource = get_object_or_404(BaseResource, pk=base_resource_pk)

    # 2. Determine the concrete type using Multi-Table Inheritance magic
    # Django assigns an attribute to the parent instance that points to the child instance.
    try:
        # Check for each concrete model attribute that links back to the parent
        if hasattr(base_resource, 'book'):
            return base_resource.book
        elif hasattr(base_resource, 'article'):
            return base_resource.article
        elif hasattr(base_resource, 'course'):
            return base_resource.course
    except (Book.DoesNotExist, Article.DoesNotExist, Course.DoesNotExist):
        # This should theoretically not happen if the object was created correctly
        pass

    # Fallback to the BaseResource if no concrete type is found (or raise 404)
    # Raising a 404 is more appropriate if we strictly expect a concrete type.
    raise models.ObjectDoesNotExist(f"No concrete resource type found for BaseResource PK: {base_resource_pk}")