base="outputs/all/formalize/api_formalization"
seeds=(
    "42"
    "1234"
    "4321"
)
projects=(
    "BankAccount"
    "Email"
    "UserAuthentication"
    "Taxi"
)

for seed in ${seeds[@]}; do
    for project in ${projects[@]}; do
        source_name="${base}/${seed}/${project}/formalization/api_formalization.json"
        target_name="${base}/${seed}/${project}/formalization/completed.json"
        cp ${source_name} ${target_name}
    done
done

base="outputs"
for project in ${projects[@]}; do
    source_name="${base}/${project}/formalization/api_formalization.json"
    target_name="${base}/${project}/formalization/completed.json"
    cp ${source_name} ${target_name}
done

