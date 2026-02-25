from django import template

register = template.Library()

@register.filter
def get_item(queryset, status):
    # usage: queryset|get_item:'approved'
    # We need to handle this efficiently. In the template we used event.registrations.filter.status...
    # Actually, Django doesn't allow method calls with arguments in templates easily.
    # Let's use a simpler approach for the template stats:
    return queryset.filter(status=status).count()