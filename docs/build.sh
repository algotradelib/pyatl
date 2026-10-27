#!/bin/sh
# Renders the site into docs/_site. Needs pyatl installed with its doc extra (pip install ".[doc]") and Quarto.
set -e
cd "$(dirname "$0")"
# Beside the installed extension, griffe may load pyatl._core by inspecting it, which loses the signatures. With only
# the sources and the generated stub of pyatl._core first on the path, it reads them statically instead.
rm -rf _api && mkdir -p _api/pyatl
cp ../src/pyatl/*.py _api/pyatl/
python -c "import os, shutil, pyatl; shutil.copy(os.path.join(os.path.dirname(pyatl.__file__), '_core.pyi'), '_api/pyatl/')"
python -c "import importlib.metadata as m; print('version: ' + m.version('quartodoc'))" > _variables.yml
PYTHONPATH=_api quartodoc build
quarto render
