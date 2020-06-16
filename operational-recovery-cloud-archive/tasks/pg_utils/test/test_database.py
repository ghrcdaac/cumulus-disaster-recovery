"""
Name: test_requests.py

Description:  Unit tests for requests_db.py.
"""

import datetime
import os
import unittest
from unittest.mock import Mock
import uuid

import boto3
import psycopg2.extras

import database
from database import DbError

UUID1 = str(uuid.uuid4())

class TestDatabase(unittest.TestCase):  #pylint: disable-msg=too-many-public-methods
    """
    TestDatabase.
    """

    def setUp(self):

        os.environ["DATABASE_HOST"] = "my.db.host.gov"
        os.environ["DATABASE_PORT"] = "50"
        os.environ["DATABASE_NAME"] = "sndbx"
        os.environ["DATABASE_USER"] = "unittestdbuser"
        os.environ["DATABASE_PW"] = "unittestdbpw"

        self.mock_single_query = database.single_query
        self.mock_utcnow = database.get_utc_now_iso
        self.mock_uuid = database.uuid_generator
        self.mock_boto3 = boto3.client
        boto3.client = Mock()
        s3_cli = boto3.client('ssm')
        db_host = {"Parameter": {"Value": os.environ['DATABASE_HOST']}}
        db_pw = {"Parameter": {"Value": os.environ['DATABASE_PW']}}
        s3_cli.get_parameter = Mock(side_effect=[db_host,
                                                 db_pw])
        db_params = {}
        db_params["db_host"] = {"ssm": "drdb-host"}
        db_params["db_port"] = {"env": "DATABASE_PORT"}
        db_params["db_name"] = {"env": "DATABASE_NAME"}
        db_params["db_user"] = {"env": "DATABASE_USER"}
        db_params["db_pw"] = {"ssm": "drdb-user-pass"}
        self.dbconnect_info = database.read_db_connect_info(db_params)

    def tearDown(self):
        boto3.client = self.mock_boto3
        database.single_query = self.mock_single_query
        database.get_utc_now_iso = self.mock_utcnow
        database.uuid_generator = self.mock_uuid
        del os.environ["DATABASE_HOST"]
        del os.environ["DATABASE_PORT"]
        del os.environ["DATABASE_NAME"]
        del os.environ["DATABASE_USER"]
        del os.environ["DATABASE_PW"]

    def test_get_utc_now_iso(self):
        """
        Tests the get_utc_now_iso function
        """
        utc_now_exp = "2019-07-17T17:36:38.494918"
        utc_now_exp = datetime.datetime.utcnow().isoformat()
        database.get_utc_now_iso = Mock(return_value=utc_now_exp)
        self.assertEqual(utc_now_exp, database.get_utc_now_iso())

    def test_uuid_generator(self):
        """
        Tests the uuid_generator function
        """
        database.uuid_generator = Mock(return_value=UUID1)
        self.assertEqual(UUID1, database.uuid_generator())

    def test_get_connection(self):
        """
        Tests getting a database connection
        """
        db_connect_info = {}
        db_connect_info["db_host"] = os.environ["DATABASE_HOST"]
        db_connect_info["db_port"] = os.environ["DATABASE_PORT"]
        db_connect_info["db_name"] = os.environ["DATABASE_NAME"]
        db_connect_info["db_user"] = os.environ["DATABASE_USER"]
        db_connect_info["db_pw"] = os.environ["DATABASE_PW"]
        con = database.get_connection(db_connect_info)
        self.assertIsNotNone(con)


    def test_return_connection(self):
        """
        Tests getting a database connection
        """
        db_connect_info = {}
        db_connect_info["db_host"] = os.environ["DATABASE_HOST"]
        db_connect_info["db_port"] = os.environ["DATABASE_PORT"]
        db_connect_info["db_name"] = os.environ["DATABASE_NAME"]
        db_connect_info["db_user"] = os.environ["DATABASE_USER"]
        db_connect_info["db_pw"] = os.environ["DATABASE_PW"]
        exp_err = ('Database Error. could not translate host name '
                   '"my.db.host.gov" to address: Unknown host\n')
        try:
            con = database.return_connection(db_connect_info)
            self.assertIsNotNone(con)
        except DbError as err:
            self.assertEqual(exp_err, str(err))

    def test_single_query(self):
        """
        Tests the single_query function
        """
        qresult = []
        row = self.build_row('key1', 'value2', 'value3')
        qresult.append(psycopg2.extras.RealDictRow(row))

        row = self.build_row('key2', 'value4', 'value5')
        qresult.append(psycopg2.extras.RealDictRow(row))

        empty_result = []
        database.single_query = Mock(
            side_effect=[qresult, empty_result])
        sql_stmt = 'Select * from mytable'
        rows = database.single_query(sql_stmt, self.dbconnect_info)
        self.assertEqual(qresult, rows)
        rows = database.single_query(sql_stmt, self.dbconnect_info)
        self.assertEqual(empty_result, rows)
        database.single_query.assert_called()

    def test_single_query_ssm(self):
        """
        Tests the single_query function
        """
        boto3.client = Mock()
        s3_cli = boto3.client('ssm')
        s3_cli.get_parameter = Mock(side_effect=[os.environ["DATABASE_HOST"],
                                                 os.environ["DATABASE_PW"]])
        qresult = []
        row = self.build_row('key1', 'value2', 'value3')
        qresult.append(psycopg2.extras.RealDictRow(row))

        row = self.build_row('key2', 'value4', 'value5')
        qresult.append(psycopg2.extras.RealDictRow(row))

        sql_stmt = 'Select * from mytable'
        exp_err = ('Database Error. could not translate host name'
                   ' "my.db.host.gov" to address: Unknown host\n')
        try:
            database.single_query(sql_stmt, self.dbconnect_info)
        except DbError as err:
            self.assertEqual(exp_err, str(err))


    @staticmethod
    def build_row(column1, column2, column3):
        """
        builds a row mimicing what would be returned from a call to the db
        """
        row = []
        row.append(('column1', column1))
        row.append(('column2', column2))
        row.append(('column3', column3))
        return row
