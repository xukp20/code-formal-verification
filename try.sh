set -e
set -x

# Set proxy
export http_proxy="http://127.0.0.1:7890"
export https_proxy="http://127.0.0.1:7890"

# Set PYTHONPATH to include the src directory
export PYTHONPATH=$(pwd)


# python src/trying/parse_db_operations.py --model gpt-4o-mini --scala_path source_code/register --db_impl_file Common/DBAPI/package.scala --output_dir outputs --output_file db_operations.json
# python src/trying/parse_apis.py --model gpt-4o-mini --scala_path source_code/register --init_impl_file Process/Init.scala --apis_dir Impl --output_dir outputs --db_operations_file db_operations.json --output_file apis.json

# python src/trying/formalize_db.py --model deepseek-r1 --output_dir outputs --apis_file apis.json

# python src/trying/formalize_apis.py --model gpt-4o-mini --output_dir outputs --apis_file apis.json --db_lean_file db.lean

# python src/utils/parse_project/lean_handler.py

# python src/utils/parse_project/parser.py --base_path source_code/UserAuthenticationProject11 --project_name UserAuthenticationProject11 --lean_base_path lean_project



export MDOEL="qwen-max-latest"

# python src/pipeline/table/test_analyzer.py

# python src/pipeline/table/test_formalizer.py

# python src/pipeline/api/test_table_analyzer.py

# python src/pipeline/api/test_api_analyzer.py

# python src/pipeline/api/test_formalizer.py

# python src/utils/lean/build_parser.py

export PACKAGE_PATH=.cache/packages
python src/utils/parse_project/parser.py