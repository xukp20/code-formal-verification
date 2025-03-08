set -e
set -x

# Set proxy
export http_proxy="http://127.0.0.1:7890"
export https_proxy="http://127.0.0.1:7890"

# Set PYTHONPATH to include the src directory
export PYTHONPATH=$(pwd)

# pre download packages
export PACKAGE_PATH=.cache/packages

# create outputs and lean_project if not exists
mkdir -p outputs
mkdir -p lean_project


# model="qwen-max-latest"
# model="o1-mini"
# model="gpt-4o-mini"
model="qwq-plus"

add_mathlib=true

# project_name="BankAccount8"
# project_name="SimpleCalculatorBackend"
project_name="UserAuthenticationProject11"


project_base_path="source_code"
lean_base_path="lean_project"
output_base_path="outputs"
doc_path=$project_base_path/$project_name/"doc.md"

log_level="DEBUG"

task="formalization"
# task="theorem_generation"
# task="prove"

prove_max_retries=3
prove_max_theorem_retries=4

if [ "$task" == "formalization" ]; then
    command="python src/pipeline/formalization_pipeline.py \
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
elif [ "$task" == "theorem_generation" ]; then
    command="python src/pipeline/theorem_generation_pipeline.py \
--project-name $project_name \
--doc-path $doc_path \
--output-base-path $output_base_path \
--log-level $log_level \
--log-model-io \
--model $model"

elif [ "$task" == "prove" ]; then
    command="python src/pipeline/prove_pipeline.py \
--project-name $project_name \
--project-base-path $project_base_path \
--output-base-path $output_base_path \
--log-level $log_level \
--log-model-io \
--api-prover-max-retries $prove_max_retries \
--table-prover-max-retries $prove_max_retries \
--api-prover-max-theorem-retries $prove_max_theorem_retries \
--table-prover-max-theorem-retries $prove_max_theorem_retries \
--model $model"
# --continue \
# --start-state TABLE_PROOFS"

else
    echo "Invalid task: $task"
    exit 1
fi

echo "Running task: $task"
echo "Command: $command"

$command
