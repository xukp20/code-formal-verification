set -e
set -x

# Set proxy
export http_proxy="http://127.0.0.1:7890"
export https_proxy="http://127.0.0.1:7890"

# Set PYTHONPATH to include the src directory
export PYTHONPATH=$(pwd)

# pre download packages
export PACKAGE_PATH=../.cache/packages

python src/formalize/init_project.py