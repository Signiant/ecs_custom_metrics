#!/usr/bin/env python

"""
Push a custom metric for running tasks to CloudWatch

Requires: boto3  - https://boto3.readthedocs.io/en/latest/index.html

"""

import argparse
import urllib2
import json
import boto3
import os
import logging, logging.handlers

logging.getLogger('botocore').setLevel(logging.CRITICAL)

def push_task_count_metrics(region=None, cluster=None, profile=None):
    '''
    For the ECS namespace, push a TaskCount metric, both for *this* instance and the whole cluster
    :param region: AWS Region to query, if none provied, use region for *this* instance
    :param cluster: Cluster to query, if none provided, use cluster *this* instance is in
    :param profile: aws cli profile to use, if none provided, use role credentials
    '''
    # Can get the cluster and region from the metadata service if we don't have it
    if not region or not cluster:
        instance_metadata = json.loads(urllib2.urlopen('http://localhost:51678/v1/metadata').read().decode())
        instance_arn = instance_metadata['ContainerInstanceArn']
        if not region:
            region = instance_arn.split(':')[3]
        if not cluster:
            cluster = instance_metadata['Cluster']

    namespace = "ECS"
    metric_name = "TaskCount"

    def get_cluster_instances(next_token=None):
        '''Get the cluster instances in this cluster'''
        instance_list = {}
        if next_token:
            query_result = ecs.list_container_instances(cluster=cluster, status='ACTIVE', nextToken=next_token)
        else:
            query_result = ecs.list_container_instances(cluster=cluster, status='ACTIVE')

        if 'ResponseMetadata' in query_result:
            if 'HTTPStatusCode' in query_result['ResponseMetadata']:
                if query_result['ResponseMetadata']['HTTPStatusCode'] == 200:
                    if 'nextToken' in query_result:
                        instance_list.extend(get_cluster_instances(next_token=query_result['nextToken']))
                    else:
                        for inst in query_result['containerInstanceArns']:
                            inst_id = 'Unknown'
                            dci_result = ecs.describe_container_instances(cluster=cluster, containerInstances=[inst])
                            if 'containerInstances' in dci_result:
                                if 'ec2InstanceId' in dci_result['containerInstances'][0]:
                                    inst_id = dci_result['containerInstances'][0]['ec2InstanceId']
                            instance_list[inst] = inst_id
        return instance_list


    def put_cloudwatch_metric(task_family, count, instance_id=None):
        ''' Push the given metric (count) to CloudWatch for this task family '''
        if instance_id:
            metric_dimensions = [
                { 'Name': 'Cluster', 'Value': cluster },
                { 'Name': 'InstanceId', 'Value': instance_id },
                { 'Name': 'TaskFamily', 'Value': task_family } ]
        else:
            metric_dimensions = [
                { 'Name': 'Cluster', 'Value': cluster },
                { 'Name': 'TaskFamily', 'Value': task_family } ]

        logging.debug("Pushing the following metric data to CloudWatch with dimensions: " + str(metric_dimensions))
        logging.debug("   Task Family: %s " % task_family)
        logging.debug("   Count: %s " % str(count))
        # Do the put
        response = cloudwatch.put_metric_data(
            Namespace=namespace,
            MetricData=[
                {
                    'MetricName': metric_name,
                    'Dimensions': metric_dimensions,
                    'Value': count,
                    'Unit': 'Count'
                },
            ]
        )


    def get_task_cluster_count(task_name, task_type, next_token=None):
        '''Get the count of running tasks for the given task'''
        task_count = 0
        if task_type == 'service':
            if next_token:
                query_result = ecs.list_tasks(cluster=cluster, serviceName=task_name, nextToken=next_token)
            else:
                query_result = ecs.list_tasks(cluster=cluster, serviceName=task_name)
        else:
            if next_token:
                query_result = ecs.list_tasks(cluster=cluster, family=task_name, nextToken=next_token)
            else:
                query_result = ecs.list_tasks(cluster=cluster, family=task_name)

        if 'ResponseMetadata' in query_result:
            if 'HTTPStatusCode' in query_result['ResponseMetadata']:
                if query_result['ResponseMetadata']['HTTPStatusCode'] == 200:
                    if 'nextToken' in query_result:
                        task_count += get_task_list(task_name, task_type, next_token=query_result['nextToken'])
                    else:
                        task_count += len(query_result['taskArns'])
        return task_count


    def get_task_list(instance=None, next_token=None):
        ''' Get the running tasks '''
        running_tasks = []
        if instance:
            # Get tasks on this instance
            if next_token:
                query_result = ecs.list_tasks(cluster=cluster, containerInstance=instance, nextToken=next_token)
            else:
                query_result = ecs.list_tasks(cluster=cluster, containerInstance=instance)
        else:
            # Get tasks in this cluster
            if next_token:
                query_result = ecs.list_tasks(cluster=cluster, nextToken=next_token)
            else:
                query_result = ecs.list_tasks(cluster=cluster)
        if 'ResponseMetadata' in query_result:
            if 'HTTPStatusCode' in query_result['ResponseMetadata']:
                if query_result['ResponseMetadata']['HTTPStatusCode'] == 200:
                    if 'nextToken' in query_result:
                        running_tasks.extend(get_task_list(instance=instance, next_token=query_result['nextToken']))
                    else:
                        running_tasks.extend(query_result['taskArns'])
        return running_tasks


    def parse_tasks(task_list):
        ''' Parse task_list and return a dict containing family:count'''
        task_families = {}
        for task in task_list:
            # Get the task type (service or family)
            type = task['group'].split(':')[0]
            # Get the task family for this task
            family = task['group'].split(':')[-1]
            if family not in task_families:
                task_families[family] = {}
                task_families[family]['type'] = type
                task_families[family]['count'] = 1
            else:
                task_families[family]['count'] = task_families[family]['count'] + 1
        return task_families

    session = boto3.session.Session(profile_name=profile, region_name=region)
    ecs = session.client('ecs')
    cloudwatch = session.client('cloudwatch')

    instances_to_check = get_cluster_instances()

    cluster_task_families = {}
    for instance in instances_to_check:
        # Get running tasks on this instance
        instance_task_list = get_task_list(instance=instance)

        # Figure out task families from list of tasks
        query_result = ecs.describe_tasks(cluster=cluster, tasks=instance_task_list)
        instance_task_families = parse_tasks(query_result['tasks'])

        if DRYRUN:
            logging.info('Instance task counts for instance ID %s:' % instances_to_check[instance])
        for task_fam in instance_task_families:
            # Add this task family to the list if not already there
            if task_fam not in cluster_task_families:
                cluster_task_families[task_fam] = instance_task_families[task_fam]['type']
            if not DRYRUN:
                # Report instance task counts to CloudWatch
                put_cloudwatch_metric(task_fam, instance_task_families[task_fam]['count'], instances_to_check[instance])
            else:
                logging.info('   Task Family: %s, Count: %s, Instance: %s' % (task_fam, instance_task_families[task_fam]['count'], instances_to_check[instance]))

    if DRYRUN:
        logging.info('Cluster task counts:')
    for task_fam in cluster_task_families:
        task_cluster_count = get_task_cluster_count(task_fam, cluster_task_families[task_fam])
        if not DRYRUN:
            # Report cluster task counts to CloudWatch
            put_cloudwatch_metric(task_fam, task_cluster_count)
        else:
            logging.info('   Task Family: %s, Count: %s' % (task_fam, task_cluster_count))


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='Script to push custom ECS metrics to CloudWatch')

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

    push_task_count_metrics(region=args.region, cluster=args.cluster, profile=args.profile)
