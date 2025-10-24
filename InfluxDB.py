import os
from dotenv import load_dotenv
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from datetime import datetime

load_dotenv()

# Load environment variables 
token = os.getenv("INFLUXDB_TOKEN")
org = os.getenv("INFLUXDB_ORG")
url = os.getenv("INFLUXDB_URL")
bucket = os.getenv("INFLUXDB_BUCKET")


class InfluxDBManager:
    """Manager class for InfluxDB operations"""
    
    def __init__(self, url=url, token=token, org=org, bucket=bucket):
        """
        Initialize InfluxDB client
        
        Args:
            url: InfluxDB URL
            token: Authentication token
            org: Organization name
            bucket: Bucket name
        """
        self.url = url
        self.token = token
        self.org = org
        self.bucket = bucket
        self.client = InfluxDBClient(url=url, token=token, org=org)
        self.write_api = self.client.write_api(write_options=SYNCHRONOUS)

    def insert_into_influxdb(self, measurement, tags, fields, timestamp=None):
        """
        Insert data point into InfluxDB
        
        Args:
            measurement: Measurement name
            tags: Dictionary of tags
            fields: Dictionary of fields
            timestamp: Timestamp (string, datetime, or None for current time)
            
        Returns:
            bool: True if successful, False otherwise
        """
        if timestamp and isinstance(timestamp, str):
            dt = datetime.strptime(timestamp, '%d-%m-%Y %H:%M:%S')
        elif isinstance(timestamp, datetime):
            dt = timestamp
        else:
            dt = datetime.utcnow()

        try:
            point = (
                Point(measurement)
                .tag("device_id", tags.get("device_id"))
                .field("priority", fields.get("priority"))
                .field("latitude", fields.get("latitude"))
                .field("longitude", fields.get("longitude"))
                .field("altitude", fields.get("altitude", 0.0))
                .field("sos_signal", fields.get("sos_signal"))
                .time(dt, WritePrecision.NS)
            )
            self.write_api.write(bucket=self.bucket, org=self.org, record=point)
            return True
        except Exception as e:
            raise e
    
    def close(self):
        """Close InfluxDB client and write API"""
        self.client.close()
        self.write_api.close()