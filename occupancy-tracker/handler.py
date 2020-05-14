import json
import boto3
import uuid
import logging
import botocore
import decimal
import datetime


dbTable = boto3.resource('dynamodb').Table('occupancy-tracker')

logger = logging.getLogger()
logger.setLevel( logging.INFO )


def _createHandlerResponse( statusCode, body ):
    return {
        "statusCode": statusCode,
        "body": "{0}\n".format( json.dumps(body, indent=4, sort_keys=True) )
    }


def _createOccupancyResponse( statusCode, spaceId, current, maximum, created, lastUpdated ):
    return _createHandlerResponse( 
        statusCode,
        {
            'space_id'  : str(spaceId),
            'occupancy' : {
                'current'   : int( current ),
                'maximum'   : int( maximum )
            },
            'created'       : created,
            'last_updated'  : lastUpdated
        }
    )


def create_space(event, context):
    try:
        maxOccupancy = int( event['pathParameters']['max_occupancy'] )
    except:
        logger.error("Could not parse {0} as integer".format( event['pathParameters']['max_occupancy']) )
        return _createHandlerResponse( 400, "Passed occupancy value of {0} cannot be parsed as an integer".format(
            event['pathParameters']['max_occupancy']) )

    # Sanity check occupancy
    if maxOccupancy < 1 or maxOccupancy > 100000:
        return _createHandlerResponse( 400, 
            "Invalid occupancy value: {0}, passed value must be 1 <= max_occupancy <= 100000".format(maxOccupancy) )

    newRoomId = uuid.uuid4() 

    # May want a transaction at some point?

    nowTimestamp = "{0}Z".format(datetime.datetime.utcnow().isoformat())
    
    try:
        dbTable.put_item(
            Item={
                'PK': str( newRoomId ),
                'occupancy': {
                    'current_occupancy' : 0,
                    'maximum_occupancy' : maxOccupancy,
                },
                'created'               : nowTimestamp,
                'last_updated'          : nowTimestamp 
            }
        )
    except botocore.exceptions.ClientError as e:
        logger.error("Could not add new values to Dynamo: {0}".format(e) )
        return _createHandlerResponse( 500, "DB write fail" )
  

    logger.info("Created new space {0} w/ max occupancy {1}".format(newRoomId, maxOccupancy) )

    return _createOccupancyResponse( 200, newRoomId, 0, maxOccupancy, nowTimestamp, nowTimestamp )


def get_occupancy(event, context):
    spaceId = event['pathParameters']['space_id']

    try:
        occupancyInfo = dbTable.get_item(
            Key={
                'PK': spaceId    
            }
        ) 
    
    except botocore.exceptions.ClientError as e:
        logger.error("Could not read DB stats for space {0}: {1}".format(spaceId, e) )
        return _createHandlerResponse( 500, "DB read fail for space {0}".format(spaceId) )

    if 'Item' not in occupancyInfo:
        return _createHandlerResponse( 400, 
            { 
                "error": "no information for space with ID {0}".format(spaceId) 
            }
        )

    return _createOccupancyResponse( 200, spaceId, occupancyInfo['Item']['occupancy']['current_occupancy'],
         occupancyInfo['Item']['occupancy']['maximum_occupancy'],
         occupancyInfo['Item']['created'],
         occupancyInfo['Item']['last_updated'] )


def increment( event, content ):
    spaceId = event['pathParameters']['space_id']

    try:
        nowTimestamp = "{0}Z".format(datetime.datetime.utcnow().isoformat())
        occupancyInfo = dbTable.update_item(
            Key={
                'PK': spaceId
            },
            UpdateExpression = "SET occupancy.current_occupancy = occupancy.current_occupancy + :one, " + \
                "last_updated = :updated_now",
            
            ExpressionAttributeValues={
                ':one'          : decimal.Decimal(1),
                ':updated_now'  : nowTimestamp
            },

            ReturnValues="ALL_NEW"
        )

    except botocore.exceptions.ClientError as e:
        logger.error("Could not increment occupancy for space {0}: {1}".format(spaceId, e) )
        return _createHandlerResponse( 500, "DB increment fail for space {0}".format(spaceId) )

    logger.info(occupancyInfo)

    return _createOccupancyResponse( 200, spaceId, occupancyInfo['Attributes']['occupancy']['current_occupancy'],
         occupancyInfo['Attributes']['occupancy']['maximum_occupancy'],
         occupancyInfo['Attributes']['created'],
         occupancyInfo['Attributes']['last_updated'] 
    ) 



def decrement( event, context ):
    spaceId = event['pathParameters']['space_id']

    try:
        nowTimestamp = "{0}Z".format(datetime.datetime.utcnow().isoformat())
        occupancyInfo = dbTable.update_item(
            Key={
                'PK': spaceId
            },
            UpdateExpression = "SET occupancy.current_occupancy = occupancy.current_occupancy - :one, " + \
                "last_updated = :updated_now",

            ExpressionAttributeValues={
                ':one'          : decimal.Decimal(1),
                ':updated_now'  : nowTimestamp 
            },

            ReturnValues="ALL_NEW"
        )

    except botocore.exceptions.ClientError as e:
        logger.error("Could not decrement occupancy for space {0}: {1}".format(spaceId, e) )
        return _createHandlerResponse( 500, "DB decrement fail for space {0}".format(spaceId) )

    return _createOccupancyResponse( 200, spaceId, occupancyInfo['Attributes']['occupancy']['current_occupancy'],
         occupancyInfo['Attributes']['occupancy']['maximum_occupancy'],
         occupancyInfo['Attributes']['created'],
         occupancyInfo['Attributes']['last_updated']
    )
