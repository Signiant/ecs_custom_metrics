# ecs-custom-metrics
Report Custom ECS Metrics to AWS CloudWatch

## Variables

- VERBOSE - enable more logging if set to 1

## Example Docker run

This example mounts the local file '/script_to_source.sh' into the container at '/script_info.sh' (This is used
by one of the commands to be run) Verbose output is enabled by setting the VERBOSE environment variable. Finally
the commands to run are provided as input to the docker container using the -c option.


>
>docker run --rm \
> -e "VERBOSE=1" \
> -v /script_to_source.sh:/script_info.sh \
> signiant/ecs-custom-metrics \
> -c "python /report_task_count_metrics.py" \
> -c "source /sscript_info.sh && python /report_scale_down_metric.py --stack-name $stackName"
