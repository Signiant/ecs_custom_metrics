#!/usr/bin/env python

"""
Push a custom metric for running tasks to CloudWatch

Requires: boto3  - https://boto3.readthedocs.io/en/latest/index.html

"""

import argparse
import urllib2
import json
import boto3


def push_task_count_metrics(region=None, cluster=None, profile=None):
    '''
    For the ECS namespace, push a TaskCount metric, both for *this* instance and the whole cluster
    :param region: AWS Region to query, if none provied, use region for *this* instance
    :param cluster: Cluster to query, if none provided, use cluster *this* instance is in
    :param profile: aws cli profile to use, if none provided, use role credentials
    '''
    if not region or not cluster:
        instance_metadata = json.loads(urllib2.urlopen('http://localhost:51678/v1/metadata').read().decode())
        instance_arn = instance_metadata['ContainerInstanceArn']
        if not region:
            region = instance_metadata['ContainerInstanceArn'].split(':')[3]
        if not cluster:
            cluster = instance_metadata['Cluster']

    session = boto3.session.Session(profile_name=profile, region_name=region)
    ecs = session.client('ecs')
    cloudwatch = session.client('cloudwatch')

    namespace = "ECS"
    metric_name = "TaskCount"

    instance_id = urllib2.urlopen('http://169.254.169.254/latest/meta-data/instance-id').read().decode()

    def put_cloudwatch_metric(task_family, count, instance=False):
        ''' Push the given metric (count) to CloudWatch for this task family '''
        if instance:
            metric_dimensions = [
                { 'Name': 'Cluster', 'Value': cluster },
                { 'Name': 'InstanceId', 'Value': instance_id },
                { 'Name': 'TaskFamily', 'Value': task_family } ]
        else:
            metric_dimensions = [
                { 'Name': 'Cluster', 'Value': cluster },
                { 'Name': 'TaskFamily', 'Value': task_family } ]

        print("Pushing the following metric data to CloudWatch with dimensions: " + str(metric_dimensions))
        print("   Task Family: %s " % task_family)
        print("   Count: %s " % str(count))
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


    def get_task_cluster_count(task_family, task_family_type):
        '''Get the count of running tasks for the given task family'''
        result = 0
        if task_family_type == 'service':
            query_result = ecs.list_tasks(cluster=cluster, serviceName=task_family)
        else:
            query_result = ecs.list_tasks(cluster=cluster, family=task_family)
        if 'taskArns' in query_result:
            result = len(query_result['taskArns'])
        return result


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


    # Get running tasks on this instance
    instance_task_list = get_task_list(instance=instance_arn)

    # Figure out task families from list of tasks
    query_result = ecs.describe_tasks(cluster=cluster, tasks=instance_task_list)
    instance_task_families = parse_tasks(query_result['tasks'])

    #Report instance task counts to CloudWatch
    for task_fam in instance_task_families:
        put_cloudwatch_metric(task_fam, instance_task_families[task_fam]['count'], instance=True)

    #Report cluster task counts to CloudWatch
    for task_fam in instance_task_families:
        put_cloudwatch_metric(task_fam, get_task_cluster_count(task_fam, instance_task_families[task_fam]['type']))


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='Script to get an encrypted parameter from AWS Parameter Store')

    parser.add_argument("--profile", help="The name of a profile to use. If not given, instance role credentials will be used", dest='profile', required=False)
    parser.add_argument("--region", help="AWS Region to query, if not provided, will use region for *this* instance", dest='region', required=False)
    parser.add_argument("--cluster", help="Cluster to query, if not provided, will use cluster *this* instance is in", dest='cluster', required=False)
    args = parser.parse_args()

    push_task_count_metrics(region=args.region, cluster=args.cluster, profile=args.profile)
