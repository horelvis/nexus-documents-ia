## {{ query }}

*Documento generado con {{ claims | length }} claims verificados.*

{% for claim in claims %}
{{ loop.index }}. {{ claim.text }}{% if claim.confidence > 0 %} (confianza: {{ "%.0f"|format(claim.confidence * 100) }}%){% endif %}{% if claim.status == "corrected" and claim.original_text %} *(corregido de: {{ claim.original_text[:50] }}...)*{% endif %}
{% endfor %}
