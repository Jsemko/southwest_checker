"""
Module for checking southwest prices automatically.
"""


import argparse
import itertools
import json
import os
from selenium import webdriver
import time

import numpy as np
import pandas as pd

LOG_FILE = 'log.csv'
SW_WEB = 'https://southwest.com'
DEPART_TIME = 'depart_time'
ARRIVE_TIME = 'arrive_time'
BEST_PRICE = 'best_price'
DEPART_CITY = 'depart_city'
ARRIVE_CITY = 'arrive_city'
DATE = 'date'

COLUMNS_ORDERED = [
    DATE,
    DEPART_CITY,
    ARRIVE_CITY,
    DEPART_TIME,
    ARRIVE_TIME,
    BEST_PRICE,
]

def main():
    parser = argparse.ArgumentParser()

    parser.add_argument('config', help="The config that specifies a trip",
                        type=str)

    args = parser.parse_args()

    with open(args.config) as f_stream:
        config = json.load(f_stream)

    working_dir = maybe_make_dir_and_return_it(config)

    current_flights_df = check_flights(config)

    print(current_flights_df)

    update_log_and_maybe_email(config, working_dir)


def maybe_make_dir_and_return_it(config):

    dir_name = config['name']

    cwd = os.getcwd()

    full_dir = os.path.join(cwd, dir_name)

    if not os.path.exists(full_dir):
        os.makedirs(full_dir)

    return full_dir

def check_flights(config):

    dfs = []
    for date, departure, arrival in itertools.product(config['dates'],
                                                      config['departure'],
                                                      config['arrival']):
        df = get_single_df(date, departure, arrival)
        if df is not None:
            df[DATE] = date
            df[DEPART_CITY] = departure
            df[ARRIVE_CITY] = arrival
            df = df[COLUMNS_ORDERED]
            dfs.append(df)

    return pd.concat(dfs)

def get_single_df(date, departure, arrival):

    browser = webdriver.Chrome()

    browser.get(SW_WEB)

    one_by_id = browser.find_element_by_id
    many_by_class = browser.find_elements_by_class_name

    def clear_then_send(identity, keys):
        one_by_id(identity).clear()
        one_by_id(identity).send_keys(keys + '\t')

    one_by_id('trip-type-one-way').click()

    clear_then_send('air-city-departure', departure)
    clear_then_send('air-city-arrival', arrival)
    clear_then_send('air-date-departure', date)

    one_by_id('jb-booking-form-submit-button').click()

    rows = many_by_class('bugTableRow')

    flight_dict = dict()

    for r in rows:
        r_by_class = r.find_elements_by_class_name
        times = r_by_class('time')
        am_pm = r_by_class('indicator')[:2]
        depart, arrive = [t.text + i.text for t, i in zip(times, am_pm)]
        prices = [int(s.text.strip('$')) for s in r_by_class('product_price')]

        if prices:
            best_price = min(prices)
            for str_description, value in zip([DEPART_TIME, ARRIVE_TIME, BEST_PRICE],
                                              [depart, arrive, best_price]):
                flight_dict[str_description] = flight_dict.get(str_description, []) + [value]

    browser.close()

    if flight_dict:

        return pd.DataFrame(flight_dict)

    else:
        return None

def update_log_and_maybe_email(config, working_dir):

    pass

if __name__ == '__main__':
    main()
