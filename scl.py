"""Utility module to retrieve data from Seattle City Light."""

import csv
import datetime
from datetime import date
import glob
import logging
import os
import tempfile

from dateutil.parser import parse

from selenium import webdriver
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.common.by import By

import config


class SeattleCityLight:
    """A helper class to connect and download usage data from Seattle City Light."""

    def __init__(self):
        """Set up the necessary selenium components for accessing SCL."""
        logging.info("Setting up web driver")
        self._download_directory = tempfile.TemporaryDirectory()
        chrome_options = webdriver.ChromeOptions()
        chrome_options.experimental_options["prefs"] = {
            'profile.default_content_settings.popups': 0,
            'download.default_directory': self._download_directory.name
        }
        self._driver = webdriver.Chrome(options=chrome_options)

    def __del__(self):
        """Clean up driver and temporary files."""
        logging.info("Cleaning up")
        self._driver.quit()
        self._download_directory.cleanup()

    def get_usage(self, username: str, password: str):
        """Get the energy usage of the specified user over the past 30 days.

        Args:
            username (str): City of Seattle SSO username
            password (str): City of Seattle SSO password

        Returns:
            dict[date, float]: A dictionary with usage records.
        """
        logging.info("Logging in...")
        self._driver.get(config.COS_UTILITY_USAGE_SITE)
        WebDriverWait(self._driver, timeout=10).until(
            lambda driver: driver.execute_script("return document.title"))

        user_textbox = self._driver.find_element(by=By.NAME, value="userName")
        pass_textbox = self._driver.find_element(by=By.NAME, value="password")
        user_textbox.send_keys(username)
        pass_textbox.send_keys(password)
        submit_button = self._driver.find_element(
            by=By.CSS_SELECTOR, value="button")
        submit_button.click()

        # Form submits asynchronously so we need to wait.
        title = self._driver.title
        WebDriverWait(self._driver, timeout=10).until(
            lambda driver: title != driver.title)
        WebDriverWait(self._driver, timeout=10).until(
            lambda driver: driver.find_element(
                by=By.XPATH, value="//button[text() = 'Daily']"))
        self._driver.find_element(
            by=By.XPATH, value="//button[text() = 'Daily']").click()

        WebDriverWait(self._driver, timeout=10).until(
            lambda driver: driver.find_element(
                by=By.CLASS_NAME, value="fusioncharts-container"))
        end_date = self._driver.find_element(
            by=By.XPATH, value="//input[@placeholder = 'End Date']")
        start_date = self._driver.find_element(
            by=By.XPATH, value="//input[@placeholder = 'Start Date']")
        logging.info("Getting energy usage from the last 30 days")

        # The city only provides data on a daily basis except today.
        old_value = end_date.get_attribute("value")
        end_date.clear()
        end_date.send_keys((date.today() - datetime.timedelta(days=1)
                            ).strftime("%m-%d-%Y"))
        start_date.clear()
        start_date.send_keys((date.today() - datetime.timedelta(days=30)
                              ).strftime("%m-%d-%Y"))
        WebDriverWait(self._driver, timeout=10).until(
            lambda driver: end_date.get_attribute("value") != old_value)
        self._driver.find_element(
            by=By.XPATH, value="//button[text() = 'Update']").click()
        WebDriverWait(self._driver, timeout=10).until(
            lambda driver: driver.find_element(by=By.CLASS_NAME,
                                               value="fusioncharts-container"))

        logging.info("Downloading data")
        expected_file_glob = self._download_directory.name + os.path.sep \
            + "*.csv"
        self._driver.find_element(by=By.LINK_TEXT, value="Download").click()
        WebDriverWait(self._driver, timeout=10).until(
            lambda driver: glob.glob(expected_file_glob))

        logging.info("Data downloaded\n")
        usage: dict[date, float] = {}
        with open(
            glob.glob(expected_file_glob)[0], "r", encoding='ascii'
        ) as csvfile:
            reader = csv.DictReader(
                csvfile, delimiter=',', fieldnames=config.COS_CSV_SCHEMA)

            # Skip two lines because there are special headers.
            next(reader)
            next(reader)

            for row in reader:
                day = parse(row[config.COS_CSV_DATE_HEADER]).date()
                usage[day] = float(row[config.COS_CSV_CONSUMPTION_HEADER])
        os.remove(glob.glob(expected_file_glob)[0])

        return usage
