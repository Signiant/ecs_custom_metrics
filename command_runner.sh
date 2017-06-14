#!/bin/bash

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

# Set a default frequency of 300 seconds (5 minutes) if not set in the env
if [ -z "$FREQUENCY" ]; then
    echo "FREQUENCY not set - defaulting to 300 seconds"
    FREQUENCY=300
fi

echo "Will run the following commands every ${FREQUENCY} seconds:"
printf '%s\n' "${SCRIPTS[@]}"
echo

# Loop forever, sleeping for our frequency
while true
do
    echo "Awoke to post ECS custom metrics"

    for command in "${SCRIPTS[@]}"
    do
        echo "Running $command"
        eval "$command"
    done

    echo "Sleeping for $FREQUENCY seconds"
    sleep $FREQUENCY
    echo
done

exit 0
