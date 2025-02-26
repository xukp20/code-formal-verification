set -e
set -x

# Set proxy
export http_proxy="http://127.0.0.1:7890"
export https_proxy="http://127.0.0.1:7890"

# Set PYTHONPATH to include the src directory
export PYTHONPATH=$(pwd)

model="qwen-max-latest"

project_name="UserAuthenticationProject11"
# project_name="SimpleCalculatorBackend"

project_base_path="source_code"
lean_base_path="lean_project"
output_base_path="outputs"
doc_path=$project_base_path/$project_name/"doc.md"

log_level="DEBUG"

# task="formalization"
task="theorem_generation"

if [ "$task" == "formalization" ]; then
    python src/pipeline/formalization_pipeline.py \
        --project-name $project_name \
        --project-base-path $project_base_path \
        --lean-base-path $lean_base_path \
        --output-base-path $output_base_path \
        --log-level $log_level \
        --log-model-io
elif [ "$task" == "theorem_generation" ]; then
    python src/pipeline/theorem_generation_pipeline.py \
        --project-name $project_name \
        --doc-path $doc_path \
        --output-base-path $output_base_path \
        --log-level $log_level \
        --log-model-io \
        --continue
else
    echo "Invalid task: $task"
    exit 1
fi