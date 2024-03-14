import sys
from importlib import reload as rl
F_URL = 'http://gtfsfeed.rideuta.com/GTFS.zip'
sys.path.insert(0, './gtfs_functions')
import gtfs_functions
feed = gtfs_functions.Feed(F_URL)