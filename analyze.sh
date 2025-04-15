#!/bin/bash
# This script is used to compute the theorem statistics for the projects
# Tool named `theorem_analyzer` in src/tools can take in any json file created from a project structure (see `src/types/project`)

# Base directory containing the seed directories
# BASE_DIR="outputs/all/prove/api_theorems"
BASE_DIR="outputs/all/prove/table_theorems"

# Array of seed directories
SEEDS=($(ls "$BASE_DIR"))

# Array of projects (we'll get this from the first seed directory)
PROJECTS=($(ls "$BASE_DIR/${SEEDS[0]}"))
# PROJECTS=("Email")

# Create output directory if it doesn't exist
mkdir -p theorem_stats

# Process each project
for PROJECT in "${PROJECTS[@]}"; do
    # Create/clear output file for this project
    OUTPUT_FILE="theorem_stats/${PROJECT}.txt"
    echo "Theorem Statistics for ${PROJECT}" > "$OUTPUT_FILE"
    echo "=================================" >> "$OUTPUT_FILE"
    
    # Process each seed for this project
    for SEED in "${SEEDS[@]}"; do
        echo -e "\nSeed: ${SEED}" >> "$OUTPUT_FILE"
        echo "----------------" >> "$OUTPUT_FILE"
        
        # Run theorem analyzer on this project's api_requirements.json
        INPUT_FILE="${BASE_DIR}/${SEED}/${PROJECT}/prove/table_theorems.json"
        if [ -f "$INPUT_FILE" ]; then
            python -m src.tools.theorem_analyzer -p "$INPUT_FILE" >> "$OUTPUT_FILE"
        else
            echo "File not found: $INPUT_FILE" >> "$OUTPUT_FILE"
        fi
    done
done

echo "Analysis complete! Results are in the theorem_stats directory."