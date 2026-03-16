## Available Variants

{% for variant in variants.values() %}
### {{variant.name}}
{{variant.description}}

**Files:**

{% for output in variant.outputs %}
- {{output.filename}}
{% endfor %}

{% endfor %}