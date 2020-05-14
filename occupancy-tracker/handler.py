import json
import boto3
import uuid


def _createHandlerResponse( statusCode, body ):
    return {
        "statusCode": statusCode,
        "body": "{0}\n".format( json.dumps(body, indent=4, sort_keys=True) )
    }


def create_space(event, context):
    newRoomId = uuid.uuid4() 
    return _createHandlerResponse( 200, { "space_id": str(newRoomId) } )


def get_occupancy(event, context):
    spaceId = event['pathParameters']['space_id']
    return _createHandlerResponse( 200, 
        { 
            "space_id": spaceId,
            "occupancy": 10
        }
    )


def increment( event, content ):
    spaceId = event['pathParameters']['space_id']
    return _createHandlerResponse( 200, 
        { 
            "space_id": spaceId,
            "occupancy": 11
        }
    )


def decrement( event, context ):
    spaceId = event['pathParameters']['space_id']
    return _createHandlerResponse( 200, 
        { 
            "space_id": spaceId,
            "occupancy": 9
        } 
    )


