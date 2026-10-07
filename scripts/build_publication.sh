#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
publication_dir="$project_root/publication"
command -v pdflatex >/dev/null || {
  echo "Falta pdflatex. Instala una distribución TeX Live o MacTeX." >&2
  exit 1
}

cd "$project_root"

for source in "$publication_dir"/*.tex; do
  if ! rg -q -F '\documentclass' "$source"; then
    continue
  fi
  name="$(basename "$source" .tex)"
  log_file="$publication_dir/$name.build.log"
  if ! pdflatex -interaction=nonstopmode -halt-on-error \
      -output-directory "$publication_dir" "$source" >"$log_file" 2>&1; then
    echo "Error al compilar $name.tex. Consulta $log_file" >&2
    exit 1
  fi
  echo "Generado: publication/$name.pdf"
done
