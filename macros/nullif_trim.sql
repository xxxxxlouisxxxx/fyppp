{% macro nullif_trim(column_name) %}
  nullif(trim(cast({{ column_name }} as varchar)), '')
{% endmacro %}