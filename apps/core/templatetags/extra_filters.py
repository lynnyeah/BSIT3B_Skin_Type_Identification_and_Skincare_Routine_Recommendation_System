from django import template

register = template.Library()


@register.filter
def get_item(mapping, key):
    """Get an item from a mapping by key inside templates."""
    if mapping is None:
        return ''
    try:
        return mapping.get(str(key), '')
    except (AttributeError, TypeError):
        return ''
