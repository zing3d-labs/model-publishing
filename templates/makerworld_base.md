=== MODEL NAME ===
{{project.name}}

=== LICENSE ===
{{project.license}}

{% if site.model_type == "remix" and site.source_urls %}
=== SOURCE MODEL URLS ===
{% for url in site.source_urls %}
- {{url}}
{% endfor %}
{% endif %}
=== CATEGORY ===
{{site.category}}

=== TAGS ===
{{site.tags}}

=== DESCRIPTION ===
{% if sections.model_description is defined and sections.model_description %}
{{sections.model_description}}

{% endif %}
{% if sections.intro is defined and sections.intro %}
{{sections.intro}}

{% endif %}
{% if sections.variants is defined and sections.variants %}
{{sections.variants}}

{% endif %}
{% if sections.print_settings is defined and sections.print_settings %}
{{sections.print_settings}}

{% endif %}
{% if sections.downloads is defined and sections.downloads %}
{{sections.downloads}}

{% endif %}
{% if sections.assembly is defined and sections.assembly %}
{{sections.assembly}}

{% endif %}
{% if sections.print_profile is defined and sections.print_profile %}
{{sections.print_profile}}

{% endif %}
{% if sections.collection is defined and sections.collection %}
{{sections.collection}}

{% endif %}
{% if sections.support_project is defined and sections.support_project %}
{{sections.support_project}}

{% endif %}
{% if sections.related_models is defined and sections.related_models %}
{{sections.related_models}}

{% endif %}
{% if site.print_profile is defined and site.print_profile %}
=== PRINT PROFILE NAME ===
{{site.print_profile.name}}

=== PRINT PROFILE DESCRIPTION ===
{% for line in site.print_profile.settings %}
· {{line}}
{% endfor %}
{% if site.print_profile.notes %}
{{site.print_profile.notes}}
{% endif %}

{% endif %}
