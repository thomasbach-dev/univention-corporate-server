from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support.expected_conditions import presence_of_element_located
from selenium.webdriver.support import expected_conditions

import sys
import subprocess


def count_fhs():
    umc_pid = int(subprocess.check_output('pidof -x univention-management-console-server'.split(' ')))
    return int(subprocess.check_output(['bash', '-c', 'lsof -p ' + umc_pid + ' | grep 7389 | wc -l']))

#This example requires Selenium WebDriver 3.13 or newer
with webdriver.Firefox() as driver:
    # wait = WebDriverWait(driver, 10)
    before = count_fhs()
    driver.get("http://localhost/univention/self-service/#page=passwordchange")
    driver.find_element(By.ID, "selfservice_password_TextBox_5").send_keys("max")             # username
    driver.find_element(By.ID, "selfservice_password_TextBox_6").send_keys("a")               # old password
    driver.find_element(By.ID, "selfservice_password_PasswordBox_2").send_keys("b")           # new password
    driver.find_element(By.ID, "selfservice_password_TextBox_7").send_keys("b" + Keys.RETURN) # repeat
    try:
        element = WebDriverWait(driver, 10).until(expected_conditions.presence_of_element_located((By.ID, "umc_widgets_ConfirmDialog_0")))
    finally:
        driver.find_element(By.ID, "umc_widgets_Button_3").send_keys(Keys.RETURN) # ok button click
        driver.quit()
    after = count_fhs()
    print("before: %d, after:  %d", (before, after))
    sys.exit(before == after)
