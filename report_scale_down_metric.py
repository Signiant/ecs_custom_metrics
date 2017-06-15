#!/usr/bin/env python

"""
Push a custom metric for scale down events to CloudWatch

Requires: boto3  - https://boto3.readthedocs.io/en/latest/index.html

"""

import argparse
import urllib2
import json
import boto3
import os
from datetime import datetime, timedelta
import logging, logging.handlers

SCALE_DOWN_CPU_RESERVATION = 'ScaleDownCPU'
SCALE_DOWN_MEM_RESERVATION = 'ScaleDownMemory'
CLUSTER_MIN_SIZE = 'ClusterMinSize'

logging.getLogger('botocore').setLevel(logging.CRITICAL)

def push_scale_down_metric(stack_name=None, cpu_threshold=None, mem_threshold=None, min_cluster_size=None, region=None, cluster_name=None, profile=None):
    '''
    For the ECS namespace, push a ScaleDown metric
    :param stack_name: Stack to query for CPU and MEM thresholds for scaling down
    :param cpu_threshold: CPU threshold for scaling down (must be BELOW this value)
    :param mem_threshold: MEM threshold for scaling down (must be BELOW this value)
    :param region: AWS Region to query, if none provied, use region for *this* instance
    :param cluster_name: Cluster to query, if none provided, use cluster *this* instance is in
    :param profile: aws cli profile to use, if none provided, use role credentials
    '''
    if not region or not cluster_name:
        instance_metadata = json.loads(urllib2.urlopen('http://localhost:51678/v1/metadata').read().decode())
        if not region:
            region = instance_metadata['ContainerInstanceArn'].split(':')[3]
        if not cluster_name:
            cluster_name = instance_metadata['Cluster']

    if not stack_name and ( not cpu_threshold or not mem_threshold or not min_cluster_size):
        logging.critical('Unable to proceed - need either stack_name OR cpu and mem thresholds and minimum cluster size')
        exit(1)

    if stack_name:
        logging.debug("Stack name provided: %s" % stack_name)
    else:
        logging.debug("CPU Threshold: %s " % cpu_threshold)
        logging.debug("Memory Threshold: %s " % mem_threshold)
        logging.debug("Min cluster size: %s " % min_cluster_size)

    session = boto3.session.Session(profile_name=profile, region_name=region)
    ecs = session.client('ecs')
    cloudwatch = session.client('cloudwatch')
    cloudformation = session.client('cloudformation')

    def put_cloudwatch_metric(scale_down):
        ''' Push the given metric (ScaleDown) to CloudWatch for this cluster '''
        namespace = "ECS"
        metric_name = "ScaleDown"
        metric_dimensions = [{ 'Name': 'Cluster', 'Value': cluster_name }]

        logging.debug("Pushing the following metric data to CloudWatch with dimensions: " + str(metric_dimensions))
        logging.debug("   ScaleDown: %d " % scale_down)
        response = cloudwatch.put_metric_data(
            Namespace=namespace,
            MetricData=[
                {
                    'MetricName': metric_name,
                    'Dimensions': metric_dimensions,
                    'Value': scale_down
                }
            ]
        )
        logging.debug(str(response))


    def get_cluster_cpu_and_mem_reservation(cluster_name, start_time, end_time):
        '''Get the current cluster CPU reservation'''
        dimensions = [{'Name': 'ClusterName', 'Value': cluster_name}]

        cpu_metrics = cloudwatch.get_metric_statistics(Namespace='AWS/ECS',
                                                       MetricName='CPUReservation',
                                                       Dimensions=dimensions,
                                                       StartTime=start_time,
                                                       EndTime=end_time,
                                                       Period=60,
                                                       Statistics=['Average'])

        mem_metrics = cloudwatch.get_metric_statistics(Namespace='AWS/ECS',
                                                       MetricName='MemoryReservation',
                                                       Dimensions=dimensions,
                                                       StartTime=start_time,
                                                       EndTime=end_time,
                                                       Period=60,
                                                       Statistics=['Average'])

        avg_cpu = 0
        if 'Datapoints' in cpu_metrics:
            total_cpu = 0
            for datapoint in cpu_metrics['Datapoints']:
                total_cpu += datapoint['Average']
            avg_cpu = total_cpu / len(cpu_metrics['Datapoints'])
        logging.debug('Average CPU over last 5 minutes = %8.2f' % avg_cpu)

        avg_mem = 0
        if 'Datapoints' in mem_metrics:
            total_mem = 0
            for datapoint in mem_metrics['Datapoints']:
                total_mem += datapoint['Average']
            avg_mem = total_mem / len(mem_metrics['Datapoints'])
        logging.debug('Average MEM over last 5 minutes = %8.2f' % avg_mem)

        result = {}
        result['CPU'] = avg_cpu
        result['Mem'] = avg_mem
        return result


    def get_current_cluster_size(cluster_name, next_token='', max_results=50):
        instance_count = 0
        lci_result = ecs.list_container_instances(cluster=cluster_name, nextToken=next_token, maxResults=max_results)
        if 'nextToken' in lci_result:
            instance_count += max_results
            instance_count += get_current_cluster_size(cluster_name, next_token=lci_result['nextToken'], max_results=max_results)
        else:
            if 'containerInstanceArns' in lci_result:
                instance_count = len(lci_result['containerInstanceArns'])
        return instance_count


    def get_stack_parameters(stack_name):
        '''Get the thresholds for CPU and Memory for scaling down from the stack'''
        ds_result = cloudformation.describe_stacks(StackName=stack_name)
        if 'Stacks' in ds_result:
            if 'Parameters' in ds_result['Stacks'][0]:
                return ds_result['Stacks'][0]['Parameters']

    min_cluster_size = 1
    if stack_name:
        stack_params = get_stack_parameters(stack_name)
        for param in stack_params:
            if param['ParameterKey'] == SCALE_DOWN_CPU_RESERVATION:
                cpu_threshold = int(param['ParameterValue'])
            elif param['ParameterKey'] == SCALE_DOWN_MEM_RESERVATION:
                mem_threshold = int(param['ParameterValue'])
            elif param['ParameterKey'] == CLUSTER_MIN_SIZE:
                min_cluster_size = int(param['ParameterValue'])

    if not cpu_threshold or not mem_threshold or not min_cluster_size:
        logging.critical('Not able to determine scale down CPU or Memory thresholds or Mimumum cluster size - aborting')
        exit(1)

    # Get end_time - now
    # Get start_time - 5 minutes ago
    end_time = datetime.utcnow()
    end_time_utc = end_time.isoformat()
    start_time = end_time - timedelta(minutes=5)
    start_time_utc = start_time.isoformat()

    avg_stats = get_cluster_cpu_and_mem_reservation(cluster_name, start_time_utc, end_time_utc)

    scale_down_cpu = False
    if 'CPU' in avg_stats:
        if int(avg_stats['CPU']) < int(cpu_threshold):
            logging.debug('Based on CPU, need a scale down')
            scale_down_cpu = True
        else:
            logging.debug('Based on CPU, DO NOT need a scale down')

    scale_down_mem = False
    if 'Mem' in avg_stats:
        if int(avg_stats['Mem']) < int(mem_threshold):
            logging.debug('Based on Memory, need a scale down')
            scale_down_mem = True
        else:
            logging.debug('Based on Memory, DO NOT need a scale down')

    current_cluster_size = get_current_cluster_size(cluster_name)

    scale_down_metric = 0
    if scale_down_cpu and scale_down_mem:
        if current_cluster_size > int(min_cluster_size):
            logging.info('Both CPU and Memory are below thresholds, and cluster size is above Min Cluster Size - post a scale down metric')
            scale_down_metric = 1
        else:
            logging.debug('Both CPU and Memory are below thresholds, but cluster size is already at Min Cluster Size')

    if not DRYRUN:
        #Report scale down metric to CloudWatch
        put_cloudwatch_metric(scale_down_metric)
    else:
        logging.info('Scale Down Metric: %s' % scale_down_metric)


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='Script to push custom ECS scale down metric to CloudWatch')

    parser.add_argument("--stack-name", help="Stack name to read from", dest='stack_name')
    parser.add_argument("--cpu", help="CPU Scale down threshold", dest='cpu_threshold')
    parser.add_argument("--mem", help="MEM Scale down threshold", dest='mem_threshold')
    parser.add_argument("--min-cluster-size", help="Minimum Cluster Size", dest='min_cluster_size')
    parser.add_argument("--profile", help="The name of a profile to use. If not given, instance role credentials will be used", dest='profile', required=False)
    parser.add_argument("--region", help="AWS Region to query, if not provided, will use region for *this* instance", dest='region', required=False)
    parser.add_argument("--cluster", help="Cluster to query, if not provided, will use cluster *this* instance is in", dest='cluster', required=False)
    parser.add_argument("--dryrun", help="dryrun mode - don't push any metrics to cloudwatch - print to console", action='store_true')
    parser.add_argument("--verbose", help="Turn on DEBUG logging", action='store_true', required=False)
    args = parser.parse_args()

    log_level = logging.INFO

    if args.verbose:
        print("Verbose logging selected")
        log_level = logging.DEBUG

    DRYRUN = False
    if args.dryrun:
        DRYRUN = True

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    # create console handler using level set in log_level
    ch = logging.StreamHandler()
    ch.setLevel(log_level)
    console_formatter = logging.Formatter('%(levelname)8s: %(message)s')
    ch.setFormatter(console_formatter)
    logger.addHandler(ch)

    if not args.stack_name and (not args.cpu_threshold or not args.mem_threshold or not args.min_cluster_size):
        logger.critical('Unable to proceed - please provide either a stack name OR CPU and Memory thresholds')
        exit(1)

    push_scale_down_metric(stack_name=args.stack_name,
                           cpu_threshold=args.cpu_threshold,
                           mem_threshold=args.mem_threshold,
                           min_cluster_size=args.min_cluster_size,
                           region=args.region,
                           cluster_name=args.cluster,
                           profile=args.profile)
