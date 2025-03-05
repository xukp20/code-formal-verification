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

model="qwen-max-latest"
# model="o1-mini"
# model="gpt-4o-mini"

add_mathlib=true


project_name="UserAuthenticationProject11"

project_base_path="../source_code"
lean_base_path="lean_project"
output_base_path="outputs"
doc_path=$project_base_path/$project_name/"doc.md"

log_level="DEBUG"

task="formalize"
# task="theorem_generate"
# task="prove"

prove_max_retries=3
prove_max_theorem_retries=4


if [ "$task" == "formalize" ]; then
    command="python src/pipelines/formalize_pipeline.py \
--project-name $project_name \
--project-base-path $project_base_path \
--lean-base-path $lean_base_path \
--output-base-path $output_base_path \
--log-level $log_level \
--log-model-io \
--model $model \
--continue "

    if [ "$add_mathlib" == "true" ]; then
        command="$command --add-mathlib"
    fi
elif [ "$task" == "theorem_generate" ]; then
    echo "TODO"
elif [ "$task" == "prove" ]; then
    echo "TODO"
else
    echo "Invalid task"
    exit 1
fi

eval $command