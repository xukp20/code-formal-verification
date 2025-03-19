set -e
set -x

# Set proxy
export http_proxy="http://127.0.0.1:7890"
export https_proxy="http://127.0.0.1:7890"

# Set PYTHONPATH to include the src directory
export PYTHONPATH=$(pwd)

# pre download packages
export PACKAGE_PATH=".cache/packages"

# create outputs and lean_project if not exists
mkdir -p outputs
mkdir -p lean_project

model="qwen-max-latest"
# model="o1-mini"
# model="gpt-4o-mini"
# model="qwq-plus"
# model="deepseek-r1"
# model="qwq-32b"
# model="doubao-pro"

prover_model="deepseek-r1"
# prover_model="doubao-pro"

add_mathlib=false


project_name="Email"

# if has $1, load project_name from $1
if [ -n "$1" ]; then
    project_name=$1
fi


project_base_path="source_code"
lean_base_path="lean_project"
output_base_path="outputs"
doc_path=$project_base_path/$project_name/"doc.md"

log_level="INFO"
# log_level="DEBUG"

# task="formalize"
task="theorem_generate"
# task="prove"

max_theorem_retries=8
max_global_attempts=5
max_examples=3

max_workers=16

random_seed=1234

# continue=true
# start_state="API_THEOREMS"
# start_state="API_FORMALIZATION"
# start_state="TABLE_THEOREMS"

if [ "$task" == "formalize" ]; then
    command="python src/pipelines/formalize_pipeline.py \
--project-name $project_name \
--project-base-path $project_base_path \
--lean-base-path $lean_base_path \
--output-base-path $output_base_path \
--log-level $log_level \
--log-model-io \
--model $model \
--max-workers $max_workers"

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
--model $model \
--prover-model $prover_model \
--max-theorem-retries $max_theorem_retries \
--max-global-attempts $max_global_attempts \
--max-examples $max_examples"

else
    echo "Invalid task"
    exit 1
fi

command="$command --random-seed $random_seed \
 --max-workers $max_workers"

if [ "$continue" == "true" ]; then
    command="$command --continue"
fi

if [ "$start_state" != "" ]; then
    command="$command --start-state $start_state"
fi

eval $command