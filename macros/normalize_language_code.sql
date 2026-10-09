{% macro normalize_language_code(expression) -%}
  {# Conservative canonicalization only; do not infer language from text. #}
  nullif(lower(replace(trim(cast({{ expression }} as varchar)), '_', '-')), '')
{%- endmacro %}