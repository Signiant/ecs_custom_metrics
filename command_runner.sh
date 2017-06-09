#!/bin/bash

VERBOSE=0
SCRIPTS=()
while getopts ":c:h" OPT; do
    case $OPT in
        h)
            echo "Run the supplied commands"
            echo "Usage:"
            echo
            echo "   -c command_to_run"
            exit 0
            ;;
        c)
            SCRIPTS+=("$OPTARG")
            ;;
        \?)
            echo "Option -$OPTARG requires an argument." >&2
            exit 1
            ;;
        :)
            echo "Option -$OPTARG requires an argument." >&2
            exit 1
            ;;
    esac
done

echo "${SCRIPTS[@]}"

for command in "${SCRIPTS[@]}"
do
    echo "Running $command"
    eval "$command"
done