"""
Name: test_request_files.py

Description:  Unit tests for request_files.py.
"""
import os
import unittest
from unittest.mock import Mock

import boto3
from botocore.exceptions import ClientError
from cumulus_logger import CumulusLogger

import requests_db
import database
from database import DbError
import request_files

from request_helpers import (REQUEST_GROUP_ID_EXP_1, REQUEST_GROUP_ID_EXP_2,
                             REQUEST_GROUP_ID_EXP_3, REQUEST_ID1, REQUEST_ID2,
                             REQUEST_ID3, REQUEST_ID4, LambdaContextMock,
                             create_handler_event, create_insert_request,
                             mock_ssm_get_parameter)


UTC_NOW_EXP_1 = requests_db.get_utc_now_iso()
FILE1 = "MOD09GQ___006/2017/MOD/MOD09GQ.A0219114.N5aUCG.006.0656338553321.h5"
FILE2 = "MOD09GQ___006/MOD/MOD09GQ.A0219114.N5aUCG.006.0656338553321.h5.met"
FILE3 = "MOD09GQ___006/MOD/MOD09GQ.A0219114.N5aUCG.006.0656338553321_ndvi.jpg"
FILE4 = "MOD09GQ___006/MOD/MOD09GQ.A0219114.N5aUCG.006.0656338553321.cmr.xml"
PROTECTED_BUCKET = "sndbx-cumulus-protected"
PUBLIC_BUCKET = "sndbx-cumulus-public"
KEY1 = {"key": FILE1, "dest_bucket": PROTECTED_BUCKET}
KEY2 = {"key": FILE2, "dest_bucket": PROTECTED_BUCKET}
KEY3 = {"key": FILE3, "dest_bucket": None}
KEY4 = {"key": FILE4, "dest_bucket": PUBLIC_BUCKET}

class TestRequestFiles(unittest.TestCase):
    """
    TestRequestFiles.
    """
    def setUp(self):
        self.mock_boto3_client = boto3.client
        self.mock_info = CumulusLogger.info
        self.mock_error = CumulusLogger.error
        self.mock_single_query = database.single_query
        self.mock_generator = requests_db.request_id_generator
        os.environ["DATABASE_HOST"] = "my.db.host.gov"
        os.environ["DATABASE_PORT"] = "54"
        os.environ["DATABASE_NAME"] = "sndbx"
        os.environ["DATABASE_USER"] = "unittestdbuser"
        os.environ["DATABASE_PW"] = "unittestdbpw"
        os.environ['RESTORE_EXPIRE_DAYS'] = '5'
        os.environ['RESTORE_REQUEST_RETRIES'] = '3'
        self.context = LambdaContextMock()

    def tearDown(self):
        requests_db.request_id_generator = self.mock_generator
        database.single_query = self.mock_single_query
        CumulusLogger.error = self.mock_error
        CumulusLogger.info = self.mock_info
        boto3.client = self.mock_boto3_client
        del os.environ['RESTORE_EXPIRE_DAYS']
        del os.environ['RESTORE_REQUEST_RETRIES']
        del os.environ["DATABASE_HOST"]
        del os.environ["DATABASE_NAME"]
        del os.environ["DATABASE_USER"]
        del os.environ["DATABASE_PW"]
        del os.environ["DATABASE_PORT"]


    def test_handler(self):
        """
        Tests the handler
        """
        input_event = create_handler_event()
        task_input = {}
        task_input["input"] = input_event["payload"]
        task_input["config"] = {}
        exp_err = f'request: {task_input} does not contain a config value for glacier-bucket'
        CumulusLogger.error = Mock()
        try:
            request_files.handler(input_event, self.context)
        except request_files.RestoreRequestError as roe:
            self.assertEqual(exp_err, str(roe))

    def test_task_one_granule_4_files_success(self):
        """
        Test four files for one granule - successful
        """
        granule_id = "MOD09GQ.A0219114.N5aUCG.006.0656338553321"
        files = [KEY1, KEY2, KEY3, KEY4]
        input_event = {
            "input": {
                "granules": [
                    {
                        "granuleId": granule_id,
                        "keys": files
                    }
                ]
            },
            "config": {
                "glacier-bucket": "my-dr-fake-glacier-bucket"
            }
        }

        boto3.client = Mock()
        s3_cli = boto3.client('s3')
        s3_cli.restore_object = Mock(side_effect=[None,
                                                  None,
                                                  None,
                                                  None
                                                  ])
        s3_cli.head_object = Mock()
        CumulusLogger.info = Mock()
        qresult_1_inprogress, _ = create_insert_request(
            REQUEST_ID1, REQUEST_GROUP_ID_EXP_1, granule_id, files[0],
            "restore", "some_bucket", "inprogress",
            UTC_NOW_EXP_1, None, None)
        qresult_3_inprogress, _ = create_insert_request(
            REQUEST_ID1, REQUEST_GROUP_ID_EXP_1, granule_id, files[2],
            "restore", "some_bucket", "inprogress",
            UTC_NOW_EXP_1, None, None)
        qresult_4_inprogress, _ = create_insert_request(
            REQUEST_ID1, REQUEST_GROUP_ID_EXP_1, granule_id, files[3],
            "restore", "some_bucket", "inprogress",
            UTC_NOW_EXP_1, None, None)

        requests_db.request_id_generator = Mock(side_effect=[REQUEST_GROUP_ID_EXP_1,
                                                             REQUEST_ID1,
                                                             REQUEST_ID2,
                                                             REQUEST_ID3,
                                                             REQUEST_ID4])
        database.single_query = Mock(
            side_effect=[qresult_1_inprogress, qresult_1_inprogress,
                         qresult_3_inprogress, qresult_4_inprogress])
        mock_ssm_get_parameter(4)

        try:
            result = request_files.task(input_event, self.context)
        except requests_db.DatabaseError as err:
            self.fail(str(err))

        boto3.client.assert_called_with('ssm')
        s3_cli.head_object.assert_any_call(Bucket='my-dr-fake-glacier-bucket',
                                           Key=FILE1)
        s3_cli.head_object.assert_any_call(Bucket='my-dr-fake-glacier-bucket',
                                           Key=FILE2)
        s3_cli.head_object.assert_any_call(Bucket='my-dr-fake-glacier-bucket',
                                           Key=FILE3)
        s3_cli.head_object.assert_any_call(Bucket='my-dr-fake-glacier-bucket',
                                           Key=FILE4)
        restore_req_exp = {'Days': 5, 'GlacierJobParameters': {'Tier': 'Standard'}}

        s3_cli.restore_object.assert_any_call(
            Bucket='my-dr-fake-glacier-bucket',
            Key=FILE1,
            RestoreRequest=restore_req_exp)
        s3_cli.restore_object.assert_any_call(
            Bucket='my-dr-fake-glacier-bucket',
            Key=FILE2,
            RestoreRequest=restore_req_exp)
        s3_cli.restore_object.assert_any_call(
            Bucket='my-dr-fake-glacier-bucket',
            Key=FILE3,
            RestoreRequest=restore_req_exp)
        s3_cli.restore_object.assert_called_with(
            Bucket='my-dr-fake-glacier-bucket',
            Key=FILE4,
            RestoreRequest=restore_req_exp)

        exp_gran = {}
        exp_gran['granuleId'] = granule_id

        exp_files = self.get_expected_files()
        exp_gran['files'] = exp_files
        self.assertEqual(exp_gran, result)
        database.single_query.assert_called()  #called 4 times

    @staticmethod
    def get_expected_files():
        """
        builds a list of expected files
        """
        exp_files = []

        exp_file = {}
        exp_file['key'] = FILE1
        exp_file['dest_bucket'] = PROTECTED_BUCKET
        exp_file['success'] = True
        exp_file['err_msg'] = ''
        exp_files.append(exp_file)

        exp_file = {}
        exp_file['key'] = FILE2
        exp_file['dest_bucket'] = PROTECTED_BUCKET
        exp_file['success'] = True
        exp_file['err_msg'] = ''
        exp_files.append(exp_file)

        exp_file = {}
        exp_file['key'] = FILE3
        exp_file['dest_bucket'] = None
        exp_file['success'] = True
        exp_file['err_msg'] = ''
        exp_files.append(exp_file)

        exp_file = {}
        exp_file['key'] = FILE4
        exp_file['dest_bucket'] = PUBLIC_BUCKET
        exp_file['success'] = True
        exp_file['err_msg'] = ''
        exp_files.append(exp_file)
        return exp_files

    def test_task_one_granule_1_file_db_error(self):
        """
        Test one file for one granule - db error inserting status
        """
        granule_id = "MOD09GQ.A0219114.N5aUCG.006.0656338553321"
        input_event = {
            "input": {
                "granules": [
                    {
                        "granuleId": granule_id,
                        "keys": [
                            KEY1
                        ]
                    }
                ]
            },
            "config": {
                "glacier-bucket": "my-dr-fake-glacier-bucket"
            }
        }

        boto3.client = Mock()
        s3_cli = boto3.client('s3')
        s3_cli.restore_object = Mock(side_effect=[None
                                                  ])
        s3_cli.head_object = Mock()
        CumulusLogger.info = Mock()
        CumulusLogger.error = Mock()
        requests_db.request_id_generator = Mock(side_effect=[REQUEST_GROUP_ID_EXP_1,
                                                             REQUEST_ID1])
        database.single_query = Mock(
            side_effect=[DbError("mock insert failed error")])
        mock_ssm_get_parameter(1)
        exp_result = {'granuleId': granule_id, 'files': [{'key': FILE1,
                                                          'dest_bucket': PROTECTED_BUCKET,
                                                          'success': True,
                                                          'err_msg': ''}]}
        try:
            result = request_files.task(input_event, self.context)
            self.assertEqual(exp_result, result)
        except requests_db.DatabaseError as err:
            self.fail(f"failed insert does not throw exception. {str(err)}")

        boto3.client.assert_called_with('ssm')
        s3_cli.head_object.assert_any_call(Bucket='my-dr-fake-glacier-bucket',
                                           Key=FILE1)
        restore_req_exp = {'Days': 5, 'GlacierJobParameters': {'Tier': 'Standard'}}
        s3_cli.restore_object.assert_any_call(
            Bucket='my-dr-fake-glacier-bucket',
            Key=FILE1,
            RestoreRequest=restore_req_exp)

        exp_gran = {}
        exp_gran['granuleId'] = granule_id
        exp_files = []

        exp_file = {}
        exp_file['key'] = FILE1
        exp_file['dest_bucket'] = PROTECTED_BUCKET
        exp_file['success'] = True
        exp_file['err_msg'] = ''
        exp_files.append(exp_file)

        exp_gran['files'] = exp_files
        self.assertEqual(exp_gran, result)
        database.single_query.assert_called()  #called 1 times

    def test_task_two_granules(self):
        """
        Test two granules with one file each - successful.
        """
        granule_id = "MOD09GQ.A0219114.N5aUCG.006.0656338553321"
        exp_event = {}
        exp_event["input"] = {
            "granules": [{"granuleId": granule_id,
                          "keys": [KEY1]},
                         {"granuleId": granule_id,
                          "keys": [KEY2]}]}
        exp_event["config"] = {"glacier-bucket": "my-bucket"}

        exp_err = "request_files can only accept 1 granule in the list. This input contains 2"
        try:
            request_files.task(exp_event, self.context)
            self.fail("RestoreRequestError expected")
        except request_files.RestoreRequestError as roe:
            self.assertEqual(exp_err, str(roe))

    def test_task_file_not_in_glacier(self):
        """
        Test a file that is not in glacier.
        """
        file1 = "MOD09GQ___006/2017/MOD/MOD09GQ.A0219114.N5aUCG.006.0656338553321.xyz"
        exp_event = {}
        granule_id = "MOD09GQ.A0219114.N5aUCG.006.0656338553321"
        exp_event["input"] = {
            "granules": [{"granuleId": granule_id,
                          "keys": [{"key": file1, "dest_bucket": None}]}]}
        exp_event["config"] = {"glacier-bucket": "my-bucket"}
        os.environ['RESTORE_RETRIEVAL_TYPE'] = 'BadTypeUseDefault'
        boto3.client = Mock()
        s3_cli = boto3.client('s3')
        s3_cli.head_object = Mock(
            side_effect=[ClientError({'Error': {'Code': 'NotFound'}}, 'head_object')])
        CumulusLogger.info = Mock()
        requests_db.request_id_generator = Mock(return_value=REQUEST_GROUP_ID_EXP_1)
        try:
            result = request_files.task(exp_event, self.context)

            self.assertEqual({'files': [], 'granuleId': granule_id}, result)
            boto3.client.assert_called_with('s3')
            s3_cli.head_object.assert_called_with(Bucket='my-bucket', Key=file1)
        except requests_db.DatabaseError as err:
            self.fail(str(err))
        del os.environ['RESTORE_RETRIEVAL_TYPE']

    def test_task_no_retries_env_var(self):
        """
        Test environment var RESTORE_REQUEST_RETRIES not set - use default.
        """
        del os.environ['RESTORE_REQUEST_RETRIES']
        exp_event = {}
        granule_id = "MOD09GQ.A0219114.N5aUCG.006.0656338553321"
        exp_event["input"] = {
            "granules": [{"granuleId": granule_id,
                          "keys": [KEY1]}]}
        exp_event["config"] = {"glacier-bucket": "some_bucket"}

        boto3.client = Mock()
        s3_cli = boto3.client('s3')
        s3_cli.head_object = Mock()
        s3_cli.restore_object = Mock(side_effect=[None])
        CumulusLogger.info = Mock()
        requests_db.request_id_generator = Mock(return_value=REQUEST_ID1)
        exp_gran = {}
        exp_gran['granuleId'] = granule_id
        exp_files = []

        exp_file = {}
        exp_file['key'] = FILE1
        exp_file['dest_bucket'] = PROTECTED_BUCKET
        exp_file['success'] = True
        exp_file['err_msg'] = ''
        exp_files.append(exp_file)

        exp_gran['files'] = exp_files
        qresult_1_inprogress, _ = create_insert_request(
            REQUEST_ID1, REQUEST_GROUP_ID_EXP_1, granule_id, FILE1, "restore", "some_bucket",
            "inprogress", UTC_NOW_EXP_1, None, None)
        database.single_query = Mock(side_effect=[qresult_1_inprogress])
        mock_ssm_get_parameter(1)
        try:
            result = request_files.task(exp_event, self.context)
            os.environ['RESTORE_REQUEST_RETRIES'] = '3'
            self.assertEqual(exp_gran, result)

            boto3.client.assert_called_with('ssm')
            s3_cli.head_object.assert_called_with(Bucket='some_bucket',
                                                  Key=FILE1)
            restore_req_exp = {'Days': 5, 'GlacierJobParameters': {'Tier': 'Standard'}}
            s3_cli.restore_object.assert_called_with(
                Bucket='some_bucket',
                Key=FILE1,
                RestoreRequest=restore_req_exp)
            database.single_query.assert_called_once()
        except request_files.RestoreRequestError as err:
            os.environ['RESTORE_REQUEST_RETRIES'] = '3'
            self.fail(str(err))


    def test_task_no_expire_days_env_var(self):
        """
        Test environment var RESTORE_EXPIRE_DAYS not set - use default.
        """
        del os.environ['RESTORE_EXPIRE_DAYS']
        os.environ['RESTORE_RETRIEVAL_TYPE'] = 'Expedited'
        exp_event = {}
        granule_id = "MOD09GQ.A0219114.N5aUCG.006.0656338553321"
        exp_event["config"] = {"glacier-bucket": "some_bucket"}
        exp_event["input"] = {
            "granules": [{"granuleId": granule_id,
                          "keys": [KEY1]}]}

        boto3.client = Mock()
        s3_cli = boto3.client('s3')
        s3_cli.head_object = Mock()
        s3_cli.restore_object = Mock(side_effect=[None])
        CumulusLogger.info = Mock()
        requests_db.request_id_generator = Mock(return_value=REQUEST_ID1)
        exp_gran = {}
        exp_gran['granuleId'] = granule_id
        exp_files = []

        exp_file = {}
        exp_file['key'] = FILE1
        exp_file['dest_bucket'] = PROTECTED_BUCKET
        exp_file['success'] = True
        exp_file['err_msg'] = ''
        exp_files.append(exp_file)

        exp_gran['files'] = exp_files

        qresult_1_inprogress, _ = create_insert_request(
            REQUEST_ID1, REQUEST_GROUP_ID_EXP_1, granule_id, FILE1, "restore", "some_bucket",
            "inprogress", UTC_NOW_EXP_1, None, None)
        database.single_query = Mock(side_effect=[qresult_1_inprogress])
        mock_ssm_get_parameter(1)

        try:
            result = request_files.task(exp_event, self.context)
            self.assertEqual(exp_gran, result)
            os.environ['RESTORE_EXPIRE_DAYS'] = '3'
            del os.environ['RESTORE_RETRIEVAL_TYPE']
            boto3.client.assert_called_with('ssm')
            s3_cli.head_object.assert_called_with(Bucket='some_bucket',
                                                  Key=FILE1)
            restore_req_exp = {'Days': 5, 'GlacierJobParameters': {'Tier': 'Expedited'}}
            s3_cli.restore_object.assert_called_with(
                Bucket='some_bucket',
                Key=FILE1,
                RestoreRequest=restore_req_exp)
        except request_files.RestoreRequestError as err:
            self.fail(str(err))
        database.single_query.assert_called_once()

    def test_task_no_glacier_bucket(self):
        """
        Test for missing glacier-bucket in config.
        """
        exp_event = {}
        exp_event["input"] = {
            "granules": [{"granuleId": "MOD09GQ.A0219114.N5aUCG.006.0656338553321",
                          "keys": [KEY1]}]}

        exp_err = f"request: {exp_event} does not contain a config value for glacier-bucket"
        CumulusLogger.error = Mock()
        try:
            request_files.task(exp_event, self.context)
            self.fail("RestoreRequestError expected")
        except request_files.RestoreRequestError as err:
            self.assertEqual(exp_err, str(err))

    def test_task_client_error_one_file(self):
        """
        Test retries for restore error for one file.
        """
        exp_event = {}
        exp_event["config"] = {"glacier-bucket": "some_bucket"}
        exp_event["input"] = {
            "granules": [{"granuleId": "MOD09GQ.A0219114.N5aUCG.006.0656338553321",
                          "keys": [KEY1]}]}

        os.environ['RESTORE_RETRY_SLEEP_SECS'] = '.5'
        requests_db.request_id_generator = Mock(side_effect=[REQUEST_GROUP_ID_EXP_1,
                                                             REQUEST_ID1,
                                                             REQUEST_ID2,
                                                             REQUEST_ID3])
        boto3.client = Mock()
        s3_cli = boto3.client('s3')
        s3_cli.head_object = Mock()
        s3_cli.restore_object = Mock(
            side_effect=[ClientError({'Error': {'Code': 'NoSuchBucket'}}, 'restore_object'),
                         ClientError({'Error': {'Code': 'NoSuchBucket'}}, 'restore_object'),
                         ClientError({'Error': {'Code': 'NoSuchBucket'}}, 'restore_object')])
        CumulusLogger.info = Mock()
        CumulusLogger.error = Mock()
        mock_ssm_get_parameter(1)
        os.environ['RESTORE_RETRIEVAL_TYPE'] = 'Standard'
        exp_gran = {}
        exp_gran['granuleId'] = 'MOD09GQ.A0219114.N5aUCG.006.0656338553321'
        exp_files = []

        exp_file = {}
        exp_file['key'] = FILE1
        exp_file['dest_bucket'] = PROTECTED_BUCKET
        exp_file['success'] = False
        exp_files.append(exp_file)

        exp_gran = {'granuleId': 'MOD09GQ.A0219114.N5aUCG.006.0656338553321', 'files': [
            {'key': FILE1,
             'dest_bucket': PROTECTED_BUCKET,
             'success': False,
             'err_msg': 'An error occurred (NoSuchBucket) when calling the restore_object '
                        'operation: Unknown'}]}
        exp_err = f"One or more files failed to be requested. {exp_gran}"
        try:
            request_files.task(exp_event, self.context)
            self.fail("RestoreRequestError expected")
        except request_files.RestoreRequestError as err:
            self.assertEqual(exp_err, str(err))
        del os.environ['RESTORE_RETRY_SLEEP_SECS']
        del os.environ['RESTORE_RETRIEVAL_TYPE']
        boto3.client.assert_called_with('ssm')
        s3_cli.head_object.assert_called_with(Bucket='some_bucket',
                                              Key=FILE1)
        restore_req_exp = {'Days': 5, 'GlacierJobParameters': {'Tier': 'Standard'}}
        s3_cli.restore_object.assert_any_call(
            Bucket='some_bucket',
            Key=FILE1,
            RestoreRequest=restore_req_exp)

    def test_task_client_error_3_times(self):
        """
        Test three files, two successful, one errors on all retries and fails.
        """
        keys = [KEY1, KEY3, KEY4]

        exp_event = {}
        exp_event["config"] = {"glacier-bucket": "some_bucket"}
        gran = {}
        gran["granuleId"] = "MOD09GQ.A0219114.N5aUCG.006.0656338553321"

        gran["keys"] = keys
        exp_event["input"] = {
            "granules": [gran]}

        requests_db.request_id_generator = Mock(side_effect=[REQUEST_GROUP_ID_EXP_1,
                                                             REQUEST_ID1,
                                                             REQUEST_GROUP_ID_EXP_3,
                                                             REQUEST_ID2,
                                                             REQUEST_ID3,
                                                             REQUEST_ID4
                                                             ])
        boto3.client = Mock()
        s3_cli = boto3.client('s3')
        s3_cli.head_object = Mock()
        s3_cli.restore_object = Mock(side_effect=[None,
                                                  ClientError({'Error': {'Code': 'NoSuchBucket'}},
                                                              'restore_object'),
                                                  None,
                                                  ClientError({'Error': {'Code': 'NoSuchBucket'}},
                                                              'restore_object'),
                                                  ClientError({'Error': {'Code': 'NoSuchKey'}},
                                                              'restore_object')
                                                  ])
        CumulusLogger.info = Mock()
        CumulusLogger.error = Mock()
        exp_gran = {}
        exp_gran['granuleId'] = gran["granuleId"]

        exp_files = self.get_exp_files_3_errs()

        exp_gran['files'] = exp_files
        exp_err = f"One or more files failed to be requested. {exp_gran}"
        qresult_1_inprogress, _ = create_insert_request(
            REQUEST_ID1, REQUEST_GROUP_ID_EXP_1, gran["granuleId"], FILE1,
            "restore", "some_bucket",
            "inprogress", UTC_NOW_EXP_1, None, None)
        qresult_1_error, _ = create_insert_request(
            REQUEST_ID1, REQUEST_GROUP_ID_EXP_1, gran["granuleId"], FILE1,
            "restore", "some_bucket",
            "error", UTC_NOW_EXP_1, None, "'Code': 'NoSuchBucket'")
        qresult_3_inprogress, _ = create_insert_request(
            REQUEST_ID1, REQUEST_GROUP_ID_EXP_3, gran["granuleId"], FILE2,
            "restore", "some_bucket",
            "inprogress", UTC_NOW_EXP_1, None, None)
        qresult_3_error, _ = create_insert_request(
            REQUEST_ID1, REQUEST_GROUP_ID_EXP_3, gran["granuleId"], FILE2,
            "restore", "some_bucket",
            "error", UTC_NOW_EXP_1, None, "'Code': 'NoSuchBucket'")
        database.single_query = Mock(side_effect=[qresult_1_inprogress,
                                                  qresult_1_error,
                                                  qresult_3_inprogress,
                                                  qresult_1_error,
                                                  qresult_3_error])
        mock_ssm_get_parameter(5)
        try:
            request_files.task(exp_event, self.context)
            self.fail("RestoreRequestError expected")
        except request_files.RestoreRequestError as err:
            self.assertEqual(exp_err, str(err))

        boto3.client.assert_called_with('ssm')
        s3_cli.head_object.assert_any_call(Bucket='some_bucket',
                                           Key=FILE1)
        s3_cli.restore_object.assert_any_call(
            Bucket='some_bucket',
            Key=FILE1,
            RestoreRequest={'Days': 5, 'GlacierJobParameters': {'Tier': 'Standard'}})
        database.single_query.assert_called()  # 5 times

    @staticmethod
    def get_exp_files_3_errs():
        """
        builds list of expected files for test case
        """
        exp_files = []

        exp_file = {}
        exp_file['key'] = FILE1
        exp_file['dest_bucket'] = PROTECTED_BUCKET
        exp_file['success'] = True
        exp_file['err_msg'] = ''
        exp_files.append(exp_file)

        exp_file = {}
        exp_file['key'] = FILE3
        exp_file['dest_bucket'] = None
        exp_file['success'] = False
        exp_file['err_msg'] = 'An error occurred (NoSuchKey) when calling the restore_object ' \
                              'operation: Unknown'
        exp_files.append(exp_file)

        exp_file = {}
        exp_file['key'] = FILE4
        exp_file['dest_bucket'] = PUBLIC_BUCKET
        exp_file['success'] = True
        exp_file['err_msg'] = ''
        exp_files.append(exp_file)
        return exp_files

    def test_task_client_error_2_times(self):
        """
        Test two files, first successful, second has two errors, then success.
        """
        exp_event = {}
        exp_event["config"] = {"glacier-bucket": "some_bucket"}
        gran = {}
        granule_id = "MOD09GQ.A0219114.N5aUCG.006.0656338553321"
        gran["granuleId"] = granule_id
        keys = [KEY1, KEY2]
        gran["keys"] = keys
        exp_event["input"] = {
            "granules": [gran]}
        requests_db.request_id_generator = Mock(side_effect=[REQUEST_GROUP_ID_EXP_1,
                                                             REQUEST_ID1,
                                                             REQUEST_GROUP_ID_EXP_2,
                                                             REQUEST_ID2,
                                                             REQUEST_ID3])
        boto3.client = Mock()
        s3_cli = boto3.client('s3')
        s3_cli.head_object = Mock()

        s3_cli.restore_object = Mock(side_effect=[None,
                                                  ClientError({'Error': {'Code': 'NoSuchBucket'}},
                                                              'restore_object'),
                                                  ClientError({'Error': {'Code': 'NoSuchBucket'}},
                                                              'restore_object'),
                                                  None
                                                  ])
        CumulusLogger.info = Mock()
        CumulusLogger.error = Mock()
        exp_gran = {}
        exp_gran['granuleId'] = granule_id
        exp_files = []

        exp_file = {}
        exp_file['key'] = FILE1
        exp_file['dest_bucket'] = PROTECTED_BUCKET
        exp_file['success'] = True
        exp_file['err_msg'] = ''
        exp_files.append(exp_file)

        exp_file = {}
        exp_file['key'] = FILE2
        exp_file['dest_bucket'] = PROTECTED_BUCKET
        exp_file['success'] = True
        exp_file['err_msg'] = ''
        exp_files.append(exp_file)

        exp_gran['files'] = exp_files

        qresult1, _ = create_insert_request(
            REQUEST_ID1, REQUEST_GROUP_ID_EXP_1, granule_id, keys[0], "restore", "some_bucket",
            "inprogress", UTC_NOW_EXP_1, None, None)
        qresult2, _ = create_insert_request(
            REQUEST_ID2, REQUEST_GROUP_ID_EXP_1, granule_id, keys[0], "restore", "some_bucket",
            "error", UTC_NOW_EXP_1, None, "'Code': 'NoSuchBucket'")
        qresult3, _ = create_insert_request(
            REQUEST_ID3, REQUEST_GROUP_ID_EXP_1, granule_id, keys[1], "restore", "some_bucket",
            "inprogress", UTC_NOW_EXP_1, None, None)
        database.single_query = Mock(side_effect=[qresult1, qresult2, qresult2, qresult3])
        mock_ssm_get_parameter(4)

        result = request_files.task(exp_event, self.context)
        self.assertEqual(exp_gran, result)

        boto3.client.assert_called_with('ssm')
        s3_cli.restore_object.assert_any_call(
            Bucket='some_bucket',
            Key=FILE1,
            RestoreRequest={'Days': 5, 'GlacierJobParameters': {'Tier': 'Standard'}})
        database.single_query.assert_called()  # 4 times

if __name__ == '__main__':
    unittest.main(argv=['start'])
