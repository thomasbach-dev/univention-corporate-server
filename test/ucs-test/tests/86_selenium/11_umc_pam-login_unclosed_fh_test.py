# This is an integration test, but the unittest framework is used to structure
# it. We are expecting to see a setUp method.
import unittest

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support.expected_conditions import presence_of_element_located
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from xvfbwrapper import Xvfb

import sys
import time
import subprocess

import univention.testing.udm as udm_test

class OpenFdTests(unittest.TestCase):

    def setUp(self):
        self.xvfb = Xvfb(width=1280, height=720)
        self.addCleanup(self.xvfb.stop)
        self.xvfb.start()
        self.browser = webdriver.Firefox()
        self.addCleanup(self.browser.quit)

        with ucr_test.UCSTestConfigRegistry() as ucr:
            self.domainname = ucr.get('domainname')

    def count_fhs():
        umc_pid = int(subprocess.check_output('pidof -x univention-management-console-server'.split(' ')))
        return int(subprocess.check_output(['bash', '-c', 'lsof -p ' + umc_pid + ' | grep 7389 | wc -l']))

    def restart_umc():
        subprocess.check_call(['systemctl', 'restart', 'univention-management-console-server'])
        """ HINT: check_call: Run command with arguments. Wait for command to complete.  """

    def test_self_service_change_password():
        """
        function to visit the self-service page 'passwordchange' and set a new
        password. The test fails, if the number of open file descriptors has
        changed after the password change.
        """

        self.restart_umc()

        password_before = "univention"
        password_after = "thisisatest"

        with udm_test.UCSTestUDM() as udm:
            userdn, username = udm.create_user(set={'password': password_before})


        before_fhs = count_fhs()
        try:
            self.browser.get("http://localhost/univention/self-service/#page=passwordchange")
            self.browser.find_element(By.ID, "selfservice_password_TextBox_5").send_keys(username)
            self.browser.find_element(By.ID, "selfservice_password_TextBox_6").send_keys(old_pass)
            self.browser.find_element(By.ID, "selfservice_password_PasswordBox_2").send_keys(new_pass)
            self.browser.find_element(By.ID, "selfservice_password_TextBox_7").send_keys(new_pass + Keys.RETURN)
            WebDriverWait(self.browser, 10).until(
                    expected_conditions.presence_of_element_located((By.ID, "umc_widgets_ConfirmDialog_0")))
        finally:
            self.browser.find_element(By.ID, "umc_widgets_Button_3").send_keys(Keys.RETURN) # ok button click
        after_fhs = count_fhs()

        self.assertEqual(before_fhs, after_fhs)


    def umc_logon(username, pw):
        """
        method to log into the ucs portal with a given username and password
        """

        try:
                self.browser.get('https://ucs-9720/univention/portal/')

                Webself.browserWait(self.browser, 20).until(
                        expected_conditions.element_to_be_clickable((By.XPATH, '//*[@id="umcLoginButton_label"]'))).click()
                Webself.browserWait(self.browser, 20).until(
                        expected_conditions.element_to_be_clickable((By.XPATH, '//*[@id="umcLoginUsername"]'))).send_keys(username)
                Webself.browserWait(self.browser, 20).until(
                        expected_conditions.element_to_be_clickable((By.XPATH, '//*[@id="umcLoginPassword"]'))).send_keys(pw)

                elem = self.browser.find_elements_by_id('umcLoginSubmit')[0]
                elem.click()

                Webself.browserWait(self.browser, 20).until(
                        expected_conditions.element_to_be_clickable((By.XPATH, '//*[@id="umcLoginButton_label"]'))).click()
        finally:
                print('UMC Logon with {} done'.format(username))


    def test_umc_logon():
        """
        count the number of open file handles in the CLOSE_WAIT state after
        several logins
        """

        self.restart_umc()

        password = "univention"

        with udm_test.UCSTestUDM() as udm:
            userdn, username = udm.create_user(set={'password': password})

        for i in range(0, 4):
            umc_logon(username, password)

        time.sleep(60)
        subprocess.check_call(['service', 'slapd', 'restart'])

        umc_logon(username, password)

        umc_pid = subprocess.check_output(['pidof', '-x', 'univention-management-console-server']).strip()
        umc_lsof = subprocess.check_output(['lsof', '-p', umc_pid])

        close_wait = 0
        for line in umc_lsof.split('\n'):
            if 'CLOSE_WAIT' in line:
                close_wait += 1

        assertEqual(close_wait, 0)


if __name__ == '__main__':
    unittest.main()

