#!/bin/bash
# get project name from env
lean_project_name=${LEAN_PROJECT_NAME:-"./lean_project"}
file_name=${1:-example.lean}
lean_project_path=${2:-"$lean_project_name"}

cd $lean_project_path

output=$(lake env lean --json "$file_name" 2>&1)
status_code=$?

echo "$status_code|$output"