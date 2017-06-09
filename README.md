# ecs-custom-metrics
Report Custom ECS Metrics to AWS CloudWatch

## Variables

- VERBOSE - enable more logging if set to 1

## Example Docker run

This example mounts the local file '/env_var_script.sh' into the container at '/env_var_script.sh' (This is used
by the commands to be run) Verbose output is enabled by setting the VERBOSE environment variable. Finally
the commands to run are provided as input to the docker container using the -c option.

>docker run --rm \
> -e "VERBOSE=1" \
> -v /env_var_script.sh:/env_var_script.sh signiant/ecs_custom_metrics \
> -c 'source /env_var_script.sh && python /report_task_count_metrics.py --region $regionName --cluster $clusterName --instance-id $instanceId --instance-arn $instanceArn' \
> -c 'source /env_var_script.sh && python /report_scale_down_metric.py --region $regionName --cluster $clusterName --stack-name $stackName'
