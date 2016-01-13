import yaml
from lxml import etree
from jnpr.jsnapy.testop import Operator
import os
import sys
from jnpr.jsnapy.sqlite_get import SqliteExtractXml
import jnpr.jsnapy.snap_diff
from jnpr.jsnapy.xml_comparator import XmlComparator
import colorama
import logging
from jnpr.jsnapy import get_path


class Comparator:

    def __init__(self):
        colorama.init(autoreset=True)
        self.logger_check = logging.getLogger(__name__)
        self.log_detail = {'hostname': None}


    def __del__(self):
        colorama.init(autoreset=True)

    def generate_snap_file(self, device, prefix, cmd_rpc_name, reply_format):
        if os.path.isfile(prefix):
            return prefix
        else:
            sfile = str(device) + '_' + prefix + '_' + cmd_rpc_name + '.' + reply_format
            snapfile = os.path.join(get_path('DEFAULT', 'snapshot_path'), sfile)
            return snapfile

    def get_err_mssg(self, path, ele_list):
        err_mssg = path.get('err', "Test FAILED: " +
                            ele_list[0] + " before was < {{pre['" +ele_list[0] +"']}} >"
                                                                                " now it is < {{post['" +ele_list[0] +"']}} > ")
        return err_mssg

    def get_info_mssg(self, path, ele_list):
        info_mssg = path.get('info', "Test PASSED: " + ele_list[0] +
                    " before was < {{pre['" +
                    ele_list[0] +
                    "']}} > now it is < {{post['" +
                    ele_list[0] +
                    "']}} > ")
        return info_mssg

    """
    function is used to extract values from either
    xml file or from database
    """
    def get_xml_reply(self, db, snap):
        if db.get('check_from_sqlite') is True:
            xml_value = etree.fromstring(snap)
        elif os.path.isfile(snap):
            xml_value = etree.parse(snap)
        else:
            self.logger_check.error(colorama.Fore.RED + "ERROR, Pre snapshot file: %s is not present in given path !!" %snap, extra = self.log_detail)
            return
        return xml_value

    # Extract xpath and other values for comparing two snapshots and
    # testop.Operator methods to perform tests
    def compare_reply(self, op, tests, teston, check, db, snap1, snap2=None, action= None):
        """
        call testop.Operator methods to compare snapshots based on given test cases
        :param op: testop.Operator object
        :param tests: test cases
        :param teston: command/rpc to perform test
        :param check: variable to check if --check is given
        :param db: database handler
        :param snap1: pre snapshot file name
        :param snap2: post snapshot file name
        :return:
        """
        tests = [t for t in tests if ('iterate' in t or 'item' in t)]
        if not len(tests) and (check is True or action is "check"):
            res = self.compare_xml(op, db, teston, snap1, snap2)
            if res is False:
                op.no_failed = op.no_failed + 1
            else:
                op.no_passed = op.no_passed + 1

        for test in tests:
            if 'iterate' in test:
                x_path = test.get('iterate').get('xpath', "no_xpath")
                if 'id' in test.get('iterate'):
                    id = test.get('iterate').get('id')
                    id_list = [val.strip() for val in id.split(',')]
                else:
                    id_list = []
                testcases = test.get('iterate').get(
                    'tests', [{'Define test operator': 'tests not defined'}])
                iter = True

            elif 'item' in test:
                x_path = test.get('item').get('xpath', "no_xpath")
                if 'id' in test.get('item'):
                    id = test.get('item').get('id')
                    id_list = [val.strip() for val in id.split(',')]
                else:
                    id_list = []
                testcases = test['item']['tests']
                iter = False

            for path in testcases:
                values = ['err', 'info']
                testvalues = path.keys()
                testop1 = [
                    tvalue for tvalue in testvalues if tvalue not in values]
                testop = testop1[0] if testop1 else "Define test operator"

                ele = path.get(testop)
                if ele is not None:
                    ele_list = [elements.strip()
                                for elements in ele.split(',')]
                else:
                    ele_list = ['no node']

                # set the default error and info message
                err_mssg = self.get_err_mssg(path, ele_list)
                info_mssg = self.get_info_mssg(path, ele_list)

                if testop in [
                        'no-diff', 'list-not-less', 'list-not-more', 'delta']:
                    if check is True or action is "check":
                        xml1 = self.get_xml_reply(db, snap1)
                        xml2= self.get_xml_reply(db, snap2)
                        op.define_operator(self.log_detail, testop, x_path, ele_list, err_mssg, info_mssg, teston, iter, id_list, xml1, xml2)
                    else:
                        self.logger_check.error(
                            colorama.Fore.RED +
                            "Test Operator %s is allowed only with --check" %testop, extra = self.log_detail)

            # if test operators are other than above mentioned four operators
                else:
                    # if check is used with uni operand test operator then use
                    # second snapshot file
                    if check is True or action is "check":
                        pre_snap = self.get_xml_reply(db, snap1)
                        post_snap = self.get_xml_reply(db, snap2)
                    else:
                        pre_snap = None
                        post_snap = self.get_xml_reply(db, snap1)

                    op.define_operator(
                        self.log_detail,
                        testop,
                        x_path,
                        ele_list,
                        err_mssg,
                        info_mssg,
                        teston,
                        iter,
                        id_list,
                        pre_snap,
                        post_snap)

    def compare_diff(self, pre_snap_file, post_snap_file, check_from_sqlite):
        diff_obj = jnpr.jsnapy.snap_diff.Diff()
        if check_from_sqlite:
            diff_obj.diff_strings(
                pre_snap_file,
                post_snap_file,
                ("Snap_1",
                 "Snap_2"))
        else:
            if os.path.isfile(pre_snap_file) and os.path.isfile(
                    post_snap_file):
                diff_obj.diff_files(pre_snap_file, post_snap_file)
            else:
                self.logger_check.info(
                    colorama.Fore.RED +
                    "ERROR!!! Files are not present in given path", extra = self.log_detail)

    """
    this function is called when no testoperator is given and --check is used
    """

    def compare_xml(self, op, db, teston, pre_snap_value, post_snap_value):
        """
        Compare two snapshots node by node without any pre defined criteria
        :param pre_snap_file: pre snapshots
        :param post_snap_file: post snapshots
        :return: True if no difference in files, false if there is difference
        """
        pre_snap = self.get_xml_reply(db, pre_snap_value)
        post_snap = self.get_xml_reply(db, post_snap_value)
        if db.get('check_from_sqlite') is True:
            pre_root = pre_snap
            post_root = post_snap
        else:
            pre_root = pre_snap.getroot()
            post_root = post_snap.getroot()
        result = []
        xml_comp = XmlComparator()
        tres= xml_comp.xml_compare(pre_root, post_root, result.append)
        self.logger_check.info(colorama.Fore.BLUE + (20) * '-' + "Performing --diff without test Operation " +  (20) * '-', extra = self.log_detail)
        self.logger_check.info(
            colorama.Fore.BLUE +
            "Difference in pre and post snap file", extra = self.log_detail)
        if len(result) == 0:
            self.logger_check.info(colorama.Fore.BLUE + "    No difference   ", extra = self.log_detail)
            self.logger_check.info(colorama.Fore.GREEN + "Final result of --diff without test operator: PASSED", extra = self.log_detail)
        else:
            for index, res in enumerate(result):
                self.logger_check.info(colorama.Fore.RED + str(index) + "] " + res, extra = self.log_detail)
        op.test_details[teston].append(tres)
        return tres['result']

# generate names of snap files from hostname and out files given by user,
# tests are performed on values stored in these snap filesin which test is
# to be performed

    def generate_test_files(
            self, main_file, device, check, diff, db, snap_del, pre=None, action= None, post=None):
        """
        generate pre and post snapshot file name to store snapshots and call compare_reply function
        :param main_file: main config file, to extract test files user wants to run
        :param device: device name
        :param check: variable to check if --check option is given or not
        :param diff: variable to check if --diff option is given or not
        :param db: database object
        :param pre: file name of pre snapshot
        :param post: file name of post snapshot
        :return:
        """
        op = Operator()
        op.device = device
        tests_files = []
        tests_included = []
        self.log_detail['hostname']= device
        # get the test files from config.yml
        if main_file.get('tests') is None:
            self.logger_check.info(
                colorama.Fore.BLUE +
                "\nNo test file, Please mention test files !!", extra = self.log_detail)
        else:
            for tfiles in main_file.get('tests'):
                filename = os.path.join(get_path('DEFAULT', 'test_file_path'), tfiles)
                if os.path.isfile(filename):
                    testfile = open(filename, 'r')
                    tfiles = yaml.load(testfile)
                    tests_files.append(tfiles)
                else:
                    self.logger_check.error("File %s not found" % filename, extra = self.log_detail)

            for tests in tests_files:
                if 'tests_include' in tests:
                    tests_included = tests.get('tests_include')
                else:
                    for t in tests:
                        tests_included.append(t)

                self.logger_check.info(colorama.Fore.BLUE + (25) * '*' + "Performing test on Device: " +
                                       device + (25) * '*', extra = self.log_detail)

                for val in tests_included:
                    self.logger_check.info(colorama.Fore.BLUE + "Tests Included: %s " % (val), extra = self.log_detail)
                    try:
                        if tests[val][0].keys()[0] == 'command':
                            command = tests[val][0].get('command')
                            reply_format = tests[val][0].get('format', 'xml')
                            self.logger_check.info(colorama.Fore.BLUE + (25)* "*" + "Command is " + command  + (25) * '*', extra = self.log_detail)
                            name = '_'.join(command.split())
                            teston = command
                        else:
                            rpc = tests[val][0]['rpc']
                            reply_format = tests[val][0].get('format', 'xml')
                            self.logger_check.info(colorama.Fore.BLUE + (25)* "*" + "RPC is " +
                                                   rpc + (25) * '*', extra = self.log_detail)
                            name = rpc
                            teston = rpc
                    except KeyError:
                        self.logger_check.error(
                            colorama.Fore.RED +
                            "ERROR occurred, test keys 'command' or 'rpc' not defined properly", extra = self.log_detail)
                    except Exception as ex:
                        self.logger_check.error(
                            colorama.Fore.RED +
                            "ERROR Occurred: %s" % str(ex), extra = self.log_detail)
                    else:
                        if db.get(
                                'check_from_sqlite') is True and (check is True or diff is True or action in ["check", "diff"]):
                            a = SqliteExtractXml(db.get('db_name'))

                            if (db['first_snap_id'] is not None) and (
                                    db['second_snap_id'] is not None):
                                snapfile1, data_format1 = a.get_xml_using_snap_id(str(device), name, db['first_snap_id'])
                                snapfile2, data_format2 = a.get_xml_using_snap_id(str(device), name, db['second_snap_id'])
                            else:
                                snapfile1, data_format1 = a.get_xml_using_snapname(str(device),name,pre)
                                snapfile2, data_format2 = a.get_xml_using_snapname(str(device),name,post)
                            if reply_format != data_format1 or reply_format != data_format2:
                                self.logger_check.error(colorama.Fore.RED + "ERROR!! Data stored in database is not in %s format."
                                                        % reply_format, extra = self.log_detail)
                                sys.exit(1)
                        elif db.get('check_from_sqlite') is True:
                            a = SqliteExtractXml(db.get('db_name'))
                            snapfile1, data_format1 = a.get_xml_using_snapname(str(device), name, pre)
                            if reply_format != data_format1:
                                self.logger_check.error(colorama.Fore.RED + "ERROR!! Data stored in database is not in %s format." % reply_format, extra = self.log_detail)
                                sys.exit(1)

                        else:
                            snapfile1= self.generate_snap_file(device, pre, name, reply_format)

                        if (check is True or action is "check") and reply_format == 'xml':
                            if db.get('check_from_sqlite') is False:
                                snapfile2 = self.generate_snap_file(device, post, name, reply_format)
                            self.compare_reply(
                                op,
                                tests[val],
                                teston,
                                check,
                                db,
                                snapfile1,
                                snapfile2,
                                action)

                        # as of now diff is not implemented for diff
                        elif(diff is True):
                            if db.get('check_from_sqlite') is False:
                                snapfile2 = self.generate_snap_file(device, post, name, reply_format)
                            self.compare_diff(
                                snapfile1,
                                snapfile2,
                                db.get('check_from_sqlite'))
                        elif (reply_format == 'xml'):
                            self.compare_reply(
                                op,
                                tests[val],
                                teston,
                                check,
                                db,
                                snapfile1,
                                action)
                            if snap_del is True:
                                snapfile1 = snapfile1 if os.path.isfile(snapfile1) else self.generate_snap_file(device, pre, name, reply_format)
                                os.remove(snapfile1)
                        else:
                            self.logger_check.error(
                                colorama.Fore.RED +
                                "ERROR!! for checking snapshots in text format use '--diff' option ", extra = self.log_detail)

            if (diff is not True):
                op.final_result(self.log_detail)

        return op
