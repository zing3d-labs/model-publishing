{% if profiles %}
## Available Print Profiles

{% for profile in profiles %}
### {{profile.name}}
{{profile.description}}

{% endfor %}
{% endif %}