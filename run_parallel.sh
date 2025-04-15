set -e
set -x

# Set proxy if needed
export http_proxy="http://127.0.0.1:7890"
export https_proxy="http://127.0.0.1:7890"

# Set PYTHONPATH to include the src directory
export PYTHONPATH=$(pwd)

# pre download packages if you need to include mathlib as the dependecies
# export PACKAGE_PATH=".cache/packages"

# create outputs and lean_project if not exists
mkdir -p outputs
mkdir -p lean_project


# NOTE: choose the model for the formalization or analysis tasks
model="qwen-max-latest"
# model="deepseek-v3"
# model="o1-mini"
# model="gpt-4o-mini"
# model="qwq-plus"
# model="deepseek-r1"
# model="qwq-32b"
# model="doubao-pro"

# NOTE: choose the model for the proof task
prover_model="deepseek-r1"
# prover_model="doubao-pro"

# NOTE: whether to add mathlib as the dependecies
# default to false
add_mathlib=false

# NOTE: choose the project to run
project_name="UserAuthentication"

# Or provide the project name as the first argument
# if has $1, load project_name from $1
if [ -n "$1" ]; then
    project_name=$1
fi

# Default directories, can be changed by the following variables
project_base_path="source_code"
lean_base_path="lean_project"
output_base_path="outputs"
doc_path=$project_base_path/$project_name/"doc.md"

# NOTE: log level, default to INFO, can be changed to be DEBUG if more details are needed
# log_level="INFO"
# log_level="DEBUG"

# NOTE: choose the stage to run, one of the following:
# This version of pipeline must follow the order: formalize -> theorem_generate -> prove
# Or you can change modify the pipeline_state.json file to skip some of the tasks.
task="formalize"
# task="theorem_generate"
# task="prove"

# NOTE: max number of retries for compiler retry, default to 8
# This is used for all tasks related to the Lean compiler
max_theorem_retries=8

# NOTE: max number of global attempts for the proof task, default to 5
max_global_attempts=5

# NOTE: max number of examples for the proof task, default to 3
max_examples=3

# NOTE: max number of workers to call LLMS in parallel, default to 16
max_workers=16

# NOTE: random seed, default to 4321
random_seed=4321
# random_seed=42
# random_seed=1234

# Or provide the random seed as the second argument
if [ -n "$2" ]; then
    random_seed=$2
fi


# NOTE: Optional, continue from the last state
# continue=true

# NOTE: Optional, can manually set the start and end state
# Look at the pipeline files in src/pipelines to see the available states (as enums)
# start_state="TABLE_FORMALIZATION"
# start_state="API_TABLE_DEPENDENCY"
# start_state="API_FORMALIZATION"

# start_state="API_THEOREMS"
# start_state="TABLE_PROPERTIES"
# start_state="TABLE_THEOREMS"

# start_state="TABLE_THEOREMS"

# end_state="TABLE_DEPENDENCY"
# end_state="TABLE_FORMALIZATION"
# end_state="API_DEPENDENCY"
# end_state="API_FORMALIZATION"

# end_state="API_REQUIREMENTS"
# end_state="API_THEOREMS"
# end_state="TABLE_PROPERTIES"

# end_state="API_THEOREMS"


# Run command for the three stages
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

if [ "$end_state" != "" ]; then
    command="$command --end-state $end_state"
fi

eval $command