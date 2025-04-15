# NOTE: Add projects to be processed here
# Caution: This will run them sequentially, not in parallel
# If you want to run them in parallel, just use run_parallel.sh with the project name for each project

PROJECTS=(
    "UserAuthentication"
    "BankAccount"
    "Email"
    "Taxi"
)

for project in "${PROJECTS[@]}"; do
    echo "Running $project"
    bash run_parallel.sh $project
done
