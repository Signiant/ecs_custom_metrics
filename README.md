# ecs-custom-metrics
Report Custom ECS Metrics to AWS CloudWatch. The idea is to run a container on an ECS instance in a cluster to report
the custom metrics for that cluster.

## Variables

- FREQUENCY - how often to report metrics (defaults to 300 seconds if not specified)

## Example Docker run

This example runs the metrics collection report scripts (report_task_count_metrics.py and report_scale_down_metric.py)
every 60 seconds. The scripts to run are passed in via the -c option. In this case, the two scripts are contained in
the docker image, but there is no reason why more scripts couldn't be mounted into the container and run as well (see
example 2).

Example 1:

>docker run -d \
> -e "FREQUENCY=60" \
> signiant/ecs_custom_metrics \
> -c "python /report_task_count_metrics.py" \
> -c "python /report_scale_down_metric.py --cpu 40 --mem 40 --min-cluster-size 1"

Example 2:

>docker run -d \
> -e "FREQUENCY=60" \
> -v /path/to/additional_script_to_run.sh:/another_report_script.sh \
> signiant/ecs_custom_metrics \
> -c "python /report_task_count_metrics.py" \
> -c "/bin/bash /another_report_script.sh"
