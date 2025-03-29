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
