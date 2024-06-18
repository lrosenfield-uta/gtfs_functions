import sys
from importlib import reload as rl
import ridership_functions as rfx
F_URL = r'Feeds\Dec_23.zip'
CSV_PATH = '2024_January_Stops.csv'
SVC_ID = ['292.0.4']
sys.path.insert(0, './gtfs_functions')
import gtfs_functions
feed_test = gtfs_functions.Feed(F_URL)
feed = gtfs_functions.Feed(F_URL, service_ids=SVC_ID, time_windows=[0,24])

def trl():
    """
    Reloads feed_test and feed
    """
    rl(rfx)
    rl(gtfs_functions)
    global feed_test 
    global feed
    feed_test = gtfs_functions.Feed(F_URL)
    feed = gtfs_functions.Feed(F_URL, service_ids=SVC_ID, time_windows=[0,24])
