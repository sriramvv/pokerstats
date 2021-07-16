import json
import boto3 as b3
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Attr


def update_stats_by_date(merged_data, dynamodb):
    if not dynamodb:
        dynamodb = b3.resource('dynamodb', region_name='us-east-1')
        
    table = dynamodb.Table('stats_by_date')
    response = table.put_item(Item=merged_data)
    return response


def get_stats_by_date(file_dt, dynamodb):
    if not dynamodb:
        dynamodb = b3.resource('dynamodb', region_name='us-east-1')

    table = dynamodb.Table('stats_by_date')
    response = table.scan(
        FilterExpression=Attr('Date_Played').begins_with(f"{file_dt[0]}")
    )

    return response


def get_stats_by_month(file_dt, dynamodb):
    if not dynamodb:
        dynamodb = b3.resource('dynamodb', region_name='us-east-1')

    table = dynamodb.Table('stats_by_month')
    response = table.scan(
        FilterExpression=Attr('SK').begins_with(f"{file_dt}")
    )

    return response


def update_stats_by_month(file_dt, data, dynamodb):
    if not dynamodb:
        dynamodb = b3.resource('dynamodb', region_name='us-east-1')

    table = dynamodb.Table('stats_by_month')
    response = table.update_item(
        Key={
            'PK': data['PK'],
            'SK': file_dt
        },
        UpdateExpression="set Win_Percentage=:w, Rounds_Played=:rp, VPIP_Percentage=:vpip, Total_Rounds=:tr, Rounds_Raised=:rr, Showdowns_Won=:sw, Rounds_Limped=:rl, Showdowns_Faced=:sf, BuyIn=:bi, Rounds_Won=:rw, PFR_Percentage= :pfr",
        ExpressionAttributeValues={
            ':w': data['Win_Percentage'],
            ':rp': data['Rounds_Played'],
            ':vpip': data['VPIP_Percentage'],
            ':tr': data['Total_Rounds'],
            ':rr': data['Rounds_Raised'],
            ':rp': data['Rounds_Played'],
            ':sw': data['Showdowns_Won'],
            ':rl': data['Rounds_Limped'],
            ':sf': data['Showdowns_Faced'],
            ':bi': data['BuyIn'],
            ':rw': data['Rounds_Won'],
            ':pfr': data['PFR_Percentage']
        },
        ReturnValues="UPDATED_NEW"
    )

    return response


def insert_into_table(table_name, data, dynamodb):
    if not dynamodb:
        dynamodb = b3.resource('dynamodb', region_name='us-east-1')

    table = dynamodb.Table(table_name)
    response = table.put_item(Item=data)

    return response