import json
import boto3
import uuid
import logging
import botocore.exceptions
import botocore.session
import decimal
import datetime
import amazondax
import time


#dbTable = boto3.resource('dynamodb').Table('occupancy-tracker')
region      = "us-east-1"
session     = botocore.session.get_session()
#dynamodb    = session.create_client('dynamodb', region_name=region) # low-level client
table_name  = "occupancy-tracker"
endpoint    = "occupancy-dax.riesva.clustercfg.dax.use1.cache.amazonaws.com:8111"
daxHandle   = amazondax.AmazonDaxClient(session, region_name=region, endpoints=[endpoint])

# TTL: 8 hours
ttlSeconds  = 60 * 60 * 8

logger = logging.getLogger()
logger.setLevel( logging.INFO )


def _createHandlerResponse( statusCode, body ):
    return {
        "statusCode": statusCode,
         "headers": {
            "Content-Type"                  : "application/json",
            "Access-Control-Allow-Origin"   : "*"
        },
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

    expirationSecondsSinceEpoch = time.time() + ttlSeconds
    
    try:
        daxHandle.put_item( 
            TableName       =  table_name,
            Item            = {
                'PK'            : { 'S': str(newRoomId) },
                'occupancy'     : { 'M': {
                        'current_occupancy': { 'N': str(0), },
                        'maximum_occupancy': { 'N': str(maxOccupancy) } 
                    }
                },

                'created'       : { 'S': nowTimestamp },
                'last_updated'  : { 'S': nowTimestamp },

                # Time to live
                'TTL'           : { 'N': str(expirationSecondsSinceEpoch) }
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
        occupancyInfo = daxHandle.get_item(
            TableName       = table_name,
            Key             = {
                'PK': { 'S': str(spaceId) } 
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

    logger.debug( json.dumps(occupancyInfo, indent=4, sort_keys=True) )

    return _createOccupancyResponse( 200, spaceId, 
        occupancyInfo['Item']['occupancy']['M']['current_occupancy']['N'],
        occupancyInfo['Item']['occupancy']['M']['maximum_occupancy']['N'],
        occupancyInfo['Item']['created']['S'],
        occupancyInfo['Item']['last_updated']['S'] )


def increment( event, content ):
    spaceId = event['pathParameters']['space_id']

    try:
        nowTimestamp = "{0}Z".format(datetime.datetime.utcnow().isoformat())
        expirationSecondsSinceEpoch = time.time() + ttlSeconds

        occupancyInfo = daxHandle.update_item(
            TableName       = table_name,
            Key             = {
                'PK': { 'S': str(spaceId) }
            },
            UpdateExpression            = "SET occupancy.current_occupancy = occupancy.current_occupancy + :one, " + \
                "last_updated = :updated_now, " + \
                "TTL = :ttl",
            
            ExpressionAttributeValues   = {
                ':one'          : { 'N': str(1) },
                ':updated_now'  : { 'S': nowTimestamp },
                ':ttl'          : { 'N': str(expirationSecondsSinceEpoch) }
            },

            ReturnValues="ALL_NEW"
        )

    except botocore.exceptions.ClientError as e:
        logger.error("Could not increment occupancy for space {0}: {1}".format(spaceId, e) )
        return _createHandlerResponse( 500, "DB increment fail for space {0}".format(spaceId) )

    logger.info( json.dumps(occupancyInfo, indent=4, sort_keys=True) )

    return _createOccupancyResponse( 200, spaceId, 
        occupancyInfo['Attributes']['occupancy']['M']['current_occupancy']['N'],
        occupancyInfo['Attributes']['occupancy']['M']['maximum_occupancy']['N'],
        occupancyInfo['Attributes']['created']['S'],
        occupancyInfo['Attributes']['last_updated']['S']
    ) 



def decrement( event, context ):
    spaceId = event['pathParameters']['space_id']

    try:
        nowTimestamp = "{0}Z".format(datetime.datetime.utcnow().isoformat())
        expirationSecondsSinceEpoch = time.time() + ttlSeconds
        occupancyInfo = daxHandle.update_item(
            TableName       = table_name,
            Key             = {
                'PK': { 'S': spaceId }
            },
            UpdateExpression = "SET occupancy.current_occupancy = occupancy.current_occupancy - :one, " + \
                "last_updated = :updated_now, " + \
                "TTL = :ttl",

            ExpressionAttributeValues={
                ':one'          : { 'N': str(1) },
                ':updated_now'  : { 'S': nowTimestamp },
                ':ttl'          : { 'N': str(expirationSecondsSinceEpoch) }
            },

            ReturnValues="ALL_NEW"
        )

    except botocore.exceptions.ClientError as e:
        logger.error("Could not decrement occupancy for space {0}: {1}".format(spaceId, e) )
        return _createHandlerResponse( 500, "DB decrement fail for space {0}".format(spaceId) )


    logger.info( json.dumps(occupancyInfo, indent=4, sort_keys=True) )

    return _createOccupancyResponse( 200, spaceId, 
        occupancyInfo['Attributes']['occupancy']['M']['current_occupancy']['N'],
        occupancyInfo['Attributes']['occupancy']['M']['maximum_occupancy']['N'],
        occupancyInfo['Attributes']['created']['S'],
        occupancyInfo['Attributes']['last_updated']['S']
    )
