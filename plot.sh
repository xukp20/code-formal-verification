# This script is used to plot the theorem statistics for the projects
# Tool named `visualization.py` in src/tools can take in any json file created from a project structure (see `src/types/project`)

# Add the path to the src directory to the PYTHONPATH
export PYTHONPATH=$(pwd)

# Base directory containing the seed directories
BASE_DIR="outputs/all/prove/table_theorems"

# Array of seed directories
SEEDS=($(ls "$BASE_DIR"))

# Array of projects (we'll get this from the first seed directory)
PROJECTS=($(ls "$BASE_DIR/${SEEDS[0]}"))

# Create output directory if it doesn't exist
mkdir -p visualization_output

# Process each project
INPUT_FILES=()
for PROJECT in "${PROJECTS[@]}"; do
    for SEED in "${SEEDS[@]}"; do
    # Run visualization on this project's api_requirements.json
        INPUT_FILE="${BASE_DIR}/${SEED}/${PROJECT}/prove/table_theorems.json"
        INPUT_FILES+=("$INPUT_FILE")
    done
done

python -m src.tools.visualization "${INPUT_FILES[@]}" -o visualization_output