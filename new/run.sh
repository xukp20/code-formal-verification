set -e
set -x

# Set proxy
export http_proxy="http://127.0.0.1:7890"
export https_proxy="http://127.0.0.1:7890"

# Set PYTHONPATH to include the src directory
export PYTHONPATH=$(pwd)

# pre download packages
export PACKAGE_PATH=../.cache/packages

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

# task="formalize"
task="theorem_generate"
# task="prove"

max_theorem_retries=5
max_global_attempts=3
max_examples=3

# continue=true
# start_state="TABLE_DEPENDENCY"

if [ "$task" == "formalize" ]; then
    command="python src/pipelines/formalize_pipeline.py \
--project-name $project_name \
--project-base-path $project_base_path \
--lean-base-path $lean_base_path \
--output-base-path $output_base_path \
--log-level $log_level \
--log-model-io \
--model $model"

    if [ "$add_mathlib" == "true" ]; then
        command="$command --add-mathlib"
    fi
elif [ "$task" == "theorem_generate" ]; then
    command="python src/pipelines/generate_theorems_pipeline.py \
--project-name $project_name \
--output-base-path $output_base_path \
--doc-path $doc_path \
--project-base-path $project_base_path \
--log-level $log_level \
--log-model-io \
--model $model"

elif [ "$task" == "prove" ]; then
    command="python src/pipelines/prove_pipeline.py \
--project-name $project_name \
--output-base-path $output_base_path \
--log-level $log_level \
--log-model-io \
--model $model"

else
    echo "Invalid task"
    exit 1
fi

if [ "$continue" == "true" ]; then
    command="$command --continue"
fi

if [ "$start_state" != "" ]; then
    command="$command --start-state $start_state"
fi

eval $command