"""
Module for checking southwest prices automatically.
"""


import argparse
import itertools
import json
import os
import time

import numpy as np
import pandas as pd

from selenium import webdriver
from selenium.webdriver.chrome import options as chrome_options

LOG_FILE = 'log.csv'
SW_WEB = 'https://southwest.com'
DEPART_TIME = 'depart_time'
ARRIVE_TIME = 'arrive_time'
BEST_PRICE = 'best_price'
DEPART_CITY = 'depart_city'
ARRIVE_CITY = 'arrive_city'
DATE = 'date'
DURATION = 'duration'

RUN_HEADLESS = True

COLUMNS_ORDERED = [
    DATE,
    DEPART_CITY,
    ARRIVE_CITY,
    DEPART_TIME,
    ARRIVE_TIME,
    DURATION,
    BEST_PRICE,
]

def main():
    parser = argparse.ArgumentParser()

    parser.add_argument('configs', help="The config that specifies a trip",
                        type=str, nargs='+')

    args = parser.parse_args()

    for config in args.configs:

        with open(config) as f_stream:
            config = json.load(f_stream)

        working_dir = maybe_make_dir_and_return_it(config)

        current_flights_df = check_flights(config)

        update_log_and_maybe_email(config, working_dir, current_flights_df)


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
            # if two identical, just keep min price
            df = df.groupby(COLUMNS_ORDERED[:-1], as_index=False, sort=False).min()
            dfs.append(df)

    return pd.concat(dfs)

def get_single_df(date, departure, arrival):

    option = None

    if RUN_HEADLESS:
        option = chrome_options.Options()
        option.add_argument('--headless')

    browser = webdriver.Chrome(chrome_options=option)

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
    def normalize_duration(duration):
        hours = int(duration.split('h')[0])
        mins = int(duration.split(' ')[1].split('m')[0])
        return '%dh %02dm' % (hours, mins)

    if rows:
        #print('Type 1: Found %d rows' % len(rows))
        for r in rows:
            r_by_class = r.find_elements_by_class_name
            times = r_by_class('time')
            am_pm = r_by_class('indicator')[:2]
            depart, arrive = [t.text + ' ' + i.text for t, i in zip(times, am_pm)]
            prices = [int(s.text.strip('$')) for s in r_by_class('product_price')]
            duration = normalize_duration(r_by_class('duration')[0].text)

            if prices:
                best_price = min(prices)
                for str_description, value in zip([DEPART_TIME, ARRIVE_TIME, DURATION, BEST_PRICE],
                                                  [depart, arrive, duration, best_price]):
                    flight_dict[str_description] = flight_dict.get(str_description, []) + [value]
    else:
        time.sleep(3)
        rows = many_by_class('air-booking-select-detail')
        #print('Type 2: Found %d rows' % len(rows))
        if not rows:
            print('Nothing found!!!')
        for r in rows:
            r_by_class = r.find_elements_by_class_name
            times = r_by_class('time--value')
            depart, arrive = [t.text.replace('P', ' P').replace('A', ' A') for t in times]
            prices = [int(s.text.strip('$').split('\n')[0]) for s in r_by_class('fare-button--value-total')]
            duration = r_by_class('flight-stops--duration-time')
            if duration:
                #print('\tRegular')
                duration = duration[0].text
            else:
                #print('\tHybrid')
                duration = r_by_class('flight-stops--hybrid-duration')[0].text

            duration = normalize_duration(duration)
            if prices:
                best_price = min(prices)
                for str_description, value in zip([DEPART_TIME, ARRIVE_TIME, DURATION, BEST_PRICE],
                                                  [depart, arrive, duration, best_price]):
                    flight_dict[str_description] = flight_dict.get(str_description, []) + [value]

    browser.close()

    if flight_dict:

        return pd.DataFrame(flight_dict)

    else:
        return None

def update_log_and_maybe_email(config, working_dir, df):

    log_file = os.path.join(working_dir, LOG_FILE)

    if not os.path.exists(log_file):
        with open(log_file, 'w') as f_stream:
            df.to_csv(f_stream, index=False)
        return

    with open(log_file) as f_stream:
        log_df = pd.read_csv(f_stream)

    last_df = log_df.groupby(COLUMNS_ORDERED[:-2], as_index=False, sort=False).last()
    min_df = log_df.groupby(COLUMNS_ORDERED[:-2], as_index=False, sort=False).min()

    both_prices = min_df.merge(df, on=COLUMNS_ORDERED[:-2], suffixes=('_old', ''))

    new_mins = both_prices[both_prices[BEST_PRICE] < both_prices[BEST_PRICE + '_old']][COLUMNS_ORDERED]


    print('For %s:' % config['name'])

    if not new_mins.empty:
        print('New Low Prices!!!')
        print(new_mins)

    updates = last_df.merge(df, on=COLUMNS_ORDERED, how='right', indicator=True)
    updates = updates[updates['_merge'] == 'right_only'][COLUMNS_ORDERED]
    updates[BEST_PRICE] = updates[BEST_PRICE].astype(int)

    if not updates.empty:
        print('New updates')
        print(updates)

    full_log = pd.concat([log_df, updates])

    full_log.to_csv(log_file, index=False)

    return

def email_updates():
    pass

if __name__ == '__main__':
    main()
