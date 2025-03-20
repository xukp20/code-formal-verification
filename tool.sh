set -e
set -x

# Set proxy
export http_proxy="http://127.0.0.1:7890"
export https_proxy="http://127.0.0.1:7890"

# Set PYTHONPATH to include the src directory
export PYTHONPATH=$(pwd)

# create outputs and lean_project if not exists
mkdir -p outputs
mkdir -p lean_project

# model="qwen-max-latest"

# project_name="UserAuthenticationProject11"

# output_base_path="outputs"

# command="python src/tools/generate_api_doc.py \
#     --project-name $project_name \
#     --output-base-path $output_base_path \
#     --model $model"

# echo $command

# $command


python src/tools/theorem_analyzer.py -p outputs/EmailV3/prove/completed.json