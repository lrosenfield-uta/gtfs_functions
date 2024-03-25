import pandas as pd
import geopandas as geopd
import shapely
import logging as log
import sys
import jenkspy
import numpy as np
import folium
from branca.colormap import LinearColormap
CSV_PATH = '2024_January_Stops.csv'
#import gtfs_functions
#import gtfs_plots as gt_plt

sys.path.insert(0, './gtfs_functions')

import gtfs_functions
import gtfs_plots

if not sys.warnoptions:
    import warnings
    warnings.simplefilter("ignore")

log.basicConfig(level=log.INFO)

def route_id_from_route_num(feed, route_num):
    """
    Gets GTFS route ID given a feed and a route number
    
    There cannot be any more than 1 instance of route_num
     in trip_short_name or the tool will fail
    """
    route_num = str(route_num)
    route_df = pd_filter(feed.routes, "route_short_name", route_num)
    if len(route_df) < 1:
        raise ValueError(f'Route number {route_num} not found in GTFS')
    if len(route_df) > 1:
        raise ValueError(f'Route number {route_num} refers to multiple route IDs!')
    final = route_df.route_id.iloc[0]
    log.info(f'Route ID is {final}')
    return(final)

def pd_filter(df, col, val):
    """
    Returns a pandas dataframe maintaining only rows that have val in col

    Parameter df: The dataframe filter
    Condition: Must be a valid Pandas Dataframe

    Parameter col: the column to filter on
    Condition: must be the name of a column within df

    Parameter val: the value to look for in the column
    Condition: none
    """
    return(df[df[col] == val])

def pd_checkfilter(df, col, val):
    """
    If val is found in col of datafram df, return df, filtered for val in col
        Otherwise, raise an error
    """
    df = pd_filter(df, col, val)
    #log.info(f'checkfiltering got \n {df}')
    if len(df) == 0:
        raise ValueError(f'Value {val} was not found '
                         f'in column {col} of the dataframe')
    return df

def get_route_speed_segments(feed, route_id):
    #route_id = route_id_from_route_num(feed, route_num)
    return pd_filter(feed.avg_speeds,'route_id', route_id)

def agg_rider_data(csvfile, route_num, dir, stype = None):
    """
    Filters & aggregate the rider data found in 'csvfile' containing cleaned
        APC data
    
    Filters on route 'route_num', direction 'dir' 
        and optionally service type 'stype' (like "Weekday") 
    
    Afterwards, aggregates by sum all trips to the same stop
    """
    df = pd.read_csv(csvfile)
    df = df[['LineAbbr', 'Direction', 'Service', 'StopId', 'AverageOn', 
             'AverageOff', 'Sequence', 'AverageLoad', 'StopName']]
    #return df
    if stype:
        log.info(f'Filtering ridership by service type {stype}')
        df = pd_checkfilter(df, 'Service', stype)
    
    df['LineAbbr'] = df['LineAbbr'].astype(str)
    df = pd_checkfilter(df, 'LineAbbr', str(route_num))
    
    df['Direction'] = df['Direction'].astype(str)
    df = pd_checkfilter(df, 'Direction', str(dir))

    df = df.groupby(['StopId']).agg({'AverageOn':'sum', 
                                      'AverageOff':'sum', 
                                      'AverageLoad':'sum',
                                      'Sequence':'max',
                                      'StopName':'max'})

    #df = df[['AverageOn', 'AverageOff', 'AverageLoad']]
    return df

def create_eol_row(df):
    """
    Returns a 1 x 18 dataframe representing the EOL for a route

    To be appended to a segmented speed dataframe from gtfs_functions
    """
    final_row = df[-1:].copy()
    #print(df[-1:])
    final_row['stop_sequence'] += 1
    #print(final_row)
    #print(df[-1:])
    final_row['segment_name'] = 'EOL'
    final_row['start_stop_id'] = final_row['end_stop_id']
    final_row['end_stop_id'] = 0
    final_row['start_stop_name'] = final_row['end_stop_name']
    final_row['end_stop_name'] = 'EOL'
    final_row['speed_kmh'] = 0
    final_row['distance_m'] = 0
    final_row['geometry'] = shapely.LineString()
    final_row['shape_id'] = ''
    final_row['runtime_sec'] = 0
    #final_row['segment_max_speed_kmh'] = 0
    return final_row

def fix_unmatched_ridership(df, unmatched_ridership):
    """
    Does a second matching process on unmatched_ridership, merging it
    into DF via sequence number

    Currently unused because it causes problems with the matching process

    Warns if it doesn't work.
    """

    log.info('Attempting sequence-based matching \n')

    df.sort_index().to_clipboard()

    # Prep and combine based on stop sequence 
    # (we warn 'cause this may give bad data)
    unmatched_ridership['stop_sequence'] = unmatched_ridership['Sequence']
    unmatched_ridership = unmatched_ridership.set_index('stop_sequence')
    df = df.combine_first(unmatched_ridership)
    
    # Then we check to see if that got rid of 
    # The last of our unmatched stop ridership
    unmatched_ridership = unmatched_ridership.drop('_merge', axis=1)
    df = df.drop('_merge', axis=1)
    unmatched_ridership = pd.merge(
        unmatched_ridership, df, how = 'left',
        left_on = 'AverageLoad', right_on = 'AverageLoad', 
        indicator=True)
    unmatched_ridership = unmatched_ridership[
        unmatched_ridership['_merge']=='left_only'
        ]
    # With some slight assistance by ChatGPT

    # Then we warn and pass
    if not unmatched_ridership.empty:
        log.info('Unmatched ridership remains. Are your data sources'
                    'up-to-date? \n'
                    f'{unmatched_ridership["StopName_x"]}\n')
    print(df)    
    return df


def combine_ridership_route(segments, rider_df):
    """
    Combines route segments with ridership
        
    GTFS segments should be from the a gtfs_functions Feed object
    Ridership should be from a csv file

    We do some error checking, but ideally we don't need to do any.
    """
    log.info('Combining GTFS Data and Ridership Info\n')
    

    df = segments.sort_values(by = ['stop_sequence'])
    
    # Check for out-of-order (duplicated) stops
    # This is obnoxious, but I don't know of a better way to do it

    # CONSIDER uncommenting
    dup_check = df.duplicated(subset = ['stop_sequence'])
    if not dup_check[dup_check].index.empty:
        log.info('removing duplicates \n')
        log.info(df[dup_check])
    df = df.drop_duplicates(subset = ['stop_sequence'])

    # Plug in the EOL Row
    df = pd.concat([df, create_eol_row(df)]) # Why even is Pylance
    df = df.set_index('start_stop_id')
    
    # Gets the ridership data and preps to merge it
    df.index = df.index.astype(int)
    rider_df.index = rider_df.index.astype(int)
    df = pd.merge(
                  df, rider_df, 
                  how = 'outer', 
                  indicator = True, 
                  left_index=True, 
                  right_index=True
                  )
    log.info(f'merged rider info with segment info\n')
    
    # Fixes any unmatched stops
    unmatched_ridership = df[(df._merge == 'right_only')]
    df = df[~(df._merge == 'right_only')]

    df = df.set_index('stop_sequence')
    
    # Check to see if there are stops that failed to merge
    if not unmatched_ridership.empty:
        unmatched_printable = unmatched_ridership[['StopName', 
                                                   'AverageOn', 
                                                   'AverageOff',
                                                   'Sequence'
                                                   ]]
        log.info(f'the following stops were unmatched on first pass \n'
                 f'{unmatched_printable}\n')
        
        # More of a headache than it's worth
        #df = fix_unmatched_ridership(df, unmatched_ridership)

    else:
        # Klunk
        df = df.drop(['_merge'], axis=1)
    
    # Cleans up the dataframe
    df.index = df.index - 1
    df.index = df.index.astype(int)
    df = df.drop(['Sequence','direction_id',
                  'route_id','route_name','segment_id',
                  'shape_id', 'window',
                  'segment_max_speed_kmh', 'avg_route_speed_kmh',
                  'speed_kmh'],
                   axis=1)
    df['distance_mi'] = df['distance_m'] / 1609
    df = df.sort_index()
    #df.to_clipboard()
    return df

def get_ntrips(feed, route_id, dir):
    """
    Gets the number of trips operated on 'route' in direction 'dir' from 'feed'

    Will fail if there's more than one route with the same name or route ID
        going in the same direction
    
    """
    freq = feed.lines_freq
    #route_id = route_id_from_route_num(feed, route)
    freq = pd_filter(freq, 'route_id', route_id)
    freq = pd_filter(freq, 'direction_id', dir)
    log.info(f'the following is the number of filtered trips')
    print(freq)
    return sum(freq['ntrips'])


def get_segment_productivity(route_df, ntrips):
    """
    Adds a columns 'productivity_on', vehicle_hours' and 'speed' to route_df

    Productivity is based on the number of trips 'ntrips'

    Productivity is calculated from columns 'AverageOn' and 'runtime_sec'

    'speed' is calculated from from 'runtime_sec' and 'distance_mi'
    """
    route_df['speed'] = (
        route_df['distance_mi'] / (route_df['runtime_sec'] / 3600)
        )
    
    route_df['avg_activity'] = route_df['AverageOn'] + route_df['AverageOff']
 
    route_df['vehicle_hours'] = (
        (route_df['runtime_sec'] / 3600) * ntrips
        )
    
    route_df['productivity_on'] = (
        route_df['AverageOn'] / route_df['vehicle_hours']
        )
    
    route_df['productivity_activity'] = (
        (route_df['avg_activity'] / route_df['vehicle_hours']) / 2
    )

    # This result will be weird, and should not be compared to 'normal'
        # productivity
    route_df['productivity_load'] = (
        route_df['AverageLoad'] / route_df['vehicle_hours']
    )

    route_df = route_df.replace(np.inf, np.nan)
    #route_df = route_df.replace(np.nan, 0)

    #route_df.to_clipboard()
    return route_df

def bin_stops(df, edges):
    """
    Groups ridership & stop according to edges, and aggregates

    Edges are left-closed. 
    
    This function created with some help by a large pile of linear algebra
    """
    edges.append(len(df)+1)
    #df['geometry'] = geopd.GeoSeries.from_wkt(df['geometry'])
    #print(type(df['geometry'][1]))
    gdf = geopd.GeoDataFrame(df, geometry='geometry')
    groups = pd.cut(
        gdf.index, bins = edges, right=False, labels=False
        )
    #print(type(gdf))
    #print(type(groups))
    gdf['groups'] = groups
    #grouped_df = gdf.groupby(gdf['groups'])
    #print(type(grouped_df))
    agg_df = aggregate_stops(gdf)
    return agg_df

def aggregate_stops(grouped_df):
    """
    Helper to bin_stops; Aggregates a grouped set of stops sensibly

    For each group: 
        start_stop_name is first
        end_stop_name is last
        segment_name is First / Last
        Distances, AverageOn and AverageOff are sums
        AverageLoad is Average
    """
    #print(type(grouped_df))
    agg_df = grouped_df.dissolve(
        by = 'groups',
        aggfunc = {
            'runtime_sec':'sum',
            'start_stop_name':'first',
            'end_stop_name':'last',
            'end_stop_id':'last',
            'distance_m':'sum',
            'AverageOn':'sum',
            'AverageOff':'sum',
            'AverageLoad':'median', # Not sure if this is the 'correct' 
                                    # way to aggregate
            #'geometry':'union',
            'distance_mi':'sum'
        }
    )
    agg_df['segment_name'] = (
        agg_df['start_stop_name'] + "/" + agg_df['end_stop_name'])
    #agg_df.to_clipboard()
    return agg_df

def get_aggregate_productivity(
        feed, csvfile, route_num, dir, edges=None, stype = 'Weekday'
        ):
    """
    Makes a dataframe with speed, productivity and ridership for segments
        of a route

    This function pulls information about route number 'route' for feed 'feed' 
        in direction 'dir' (1)
    
    it then aggregates the feed information to ridership data found in csvfile
    
    from there it (optionally) groups the stop-stop segments according to a a
        list of edges (2)

    These aggregated segments are then appended with productivity data, which
        per UTA Standards is defined as people per vehicle hour. 

    (1) The feed must be initialized with A SINGLE TIME WINDOW & for a single
        day
        Due to the potential for unexpected results, the former requirement is
        enforced

    (2) The edge list is based on the stop sequence. The highest number in the
        edge list must be no greater than the highest stop.
        The particulars here are a little complicated, and probably best
            understood through example
        if there's a route with 20 stops then passing an edge list
        of stops [0, 4, 10, 18] will aggregate segments containing
        ridership for stops 0-3, 4-9, 10-17 and 18-20. Meanwhile distance and
        ride time will be based on route segments *trailing* the stops of 
        interest , so seconds and miles will be based on the distance from stop
        0-4, 4-10, 10-18, 18-20

    (3) A note on days of week: For the data I'm currently working with
        I have only weekday data. Eventually, there may also be weekend data
        If this is the case, you'll be specifying stype to filter the *rider*
        data. 

        Note that this does not apply to feed data. 
        In order to get weekend data from the feed you need to initiate the feed
        that is passed to this function with the appropriate service_ids 

        There's no easy way to check for this atm, so be warned that if you
        do not pass the correct service_ids you will end up with garbage data
        
    """
    assert len(feed.time_windows) == 2
    route_id = route_id_from_route_num(feed, route_num)
    ntrips = get_ntrips(feed, route_id, dir)
    segments_df = get_route_speed_segments(feed, route_id)
    #print(type(segments_df))
    segments_df = pd_filter(segments_df, 'direction_id', dir)
    rider_df = agg_rider_data(csvfile, route_num, dir, stype)
    combined_df = combine_ridership_route(segments_df, rider_df)
    if edges:
        log.info(f'Segment bins provided: {edges}')
        assert type(edges) == list
        combined_df = bin_stops(combined_df,edges)
    productivity_df = get_segment_productivity(combined_df, ntrips)
    return productivity_df

def plot_agg_productivity(gdf, savepoint='bad.html'):
    """
    Plots the aggregate productivity based on a single-route ridermap
    """
    
    # Original Values
    colors = ["#470000", "#ce0e2d" ,'#dc7237', '#f6d32a', '#d7f62a', '#6abf4b','#45842e', '#007dbb', '#004a98']    
    breaks = [0, 2.5, 5, 10, 15, 20, 25, 30, 40]

    #colors = ["#00000", "#470000" ,'#ce0e2d', '#dc7237', '#f6d32a','#6abf4b','#007dbb','#004a98','#c028b9']
    
    classer = 'productivity_on'
    # n_classes = len(colors)
    gdf[classer] = gdf[classer].replace(np.nan, 0)
    eol = gdf.iloc[-1:]['segment_name'].item()    
    #print(eol)
    if eol == 'EOL':
        log.info('Last row is an EOL, dropping')
        gdf = gdf.iloc[:-1]
    #log.info(f'Jenks for classes is {n_classes}, classer will be {gdf[classer]}')
    #breaks = jenkspy.jenks_breaks(gdf[classer], n_classes = n_classes)
    #breaks = [2.4, 5, 10, 15, 20, 25, 30]
        
    gdf['seq'] = gdf.index

    log.info(f'Breaks at {breaks}')
    p = gtfs_plots.map_gdf(
        gdf = gdf,
        variable = 'productivity_activity',
        colors = colors,
        tooltip_var = ['start_stop_name','AverageOn','AverageOff','speed','productivity_activity', 'seq'] , 
        tooltip_labels = ['Segment Start: ','Boardings: ', 'Alightings: ', 'Speed (mph): ', 'Productivity: ', 'Stop Sequence'], 
        breaks=breaks
    )
    p.save(savepoint)

def plot_2(gdf, colorscale, name, highlight = 'productivity_activity'):
    tooltip_var = ['start_stop_name','AverageOn','AverageOff','speed','productivity_activity', 'seq']
    tooltip_labels = ['Segment Start: ','Boardings: ', 'Alightings: ', 'Speed (mph): ', 'Productivity: ', 'Stop Sequence']

    gdf['fill_color'] = gdf[highlight].apply(lambda x: colorscale(x))

    gdf['seq'] = gdf.index

    def style_function(feature):
        return {
            'fillOpacity': 0.5,
            'weight': 3,  # math.log2(feature['properties']['speed'])*2,
            'color': feature['properties']['fill_color']}
    # my code for lines
    geo_data = gdf.__geo_interface__
    lyr = folium.GeoJson(
        geo_data,
        style_function=style_function,
        name = name,
        show=False,
        tooltip=folium.features.GeoJsonTooltip(
            fields=tooltip_var,
            aliases=tooltip_labels,
            labels=True,
            sticky=False)
        )
    
    return lyr
    #colorscale.caption = 'Productivity Legend'

    return m

def build_map(feed, csv = CSV_PATH, step = 4):
    #routes = [455]

    routes = ['1', '17', '2', '200', '201', '205', '209', '21', '213', '217', 
              '218', '220', '223', '227', '240', '248', '33', '35', '39', '4', 
              '45', '451', '455', '47', '470', '509', '513', '54', 
              '603X', '604', '612', '613', '62', '625', '626', '627', 
              '628', '630', '640', '645', '72', '805', 
              '806', '807', '821', '822', '830X', '831', 
              '834', '850', '862', '871',
              '9', 'F11', 'F202', 'F232', 'F453', 
              'F514', 'F556', 'F570', 'F578', 'F590', 
              'F618', 'F620', 'F94']

            # Removed routes are:
            # All Ski service
            # 472, 473, 551 601, 602, 606, F638, 667, 833
    #routes = list(feed.routes['route_short_name'])

    routegeom = geopd.GeoDataFrame(feed.avg_speeds, geometry='geometry')
    minx, miny, maxx, maxy = routegeom.geometry.total_bounds

    centroid_lat = miny + (maxy - miny)/2
    centroid_lon = minx + (maxx - minx)/2

    m = folium.Map(
        location=[centroid_lat, centroid_lon],
        tiles='cartodbpositron', zoom_start=12
        )

    colorscale = LinearColormap(
        colors=['#570600', '#ce0e2d', '#dc7237', '#f6d32a', '#6abf4b','#45842e','#2e847d'],
        index =[0, 2.5, 5, 10, 20, 25, 40],
        tick_labels=[10, 20, 30, 40],
        vmin = 0,
        vmax = 50,
        caption='productivity'
    )

    #ldf = {}
    directions = [1, 0]
    for direction in directions:
        for route in routes:
            glen = get_number_stops(feed, route, direction)
            name = "Route " + str(route) + " Direction " + str(direction)
            #try:
            log.info(f'Trying {name}')
            gdf = bin_for_map(
                feed, csv, route, direction, glen, step
                    )
            plot_2(gdf, colorscale, name).add_to(m)

            
            # Handle weird annoying cases where the number of stops is???
                # More than the number of stops (?????)

            # Update: should be fixed by modifying get_number_stops to drop duplicates

            # except ValueError:
            #     log.info('Route ' + str(route) + "threw an error")
            #     glen = glen - 5
            #     bin_for_map(
            #         feed, csv, route, direction, glen, step
            #         )
            #     plot_2(gdf, colorscale, name).add_to(m)
    

    colorscale.add_to(m)
    
    folium.LayerControl().add_to(m)

    m.save('index.html')

def get_number_stops(feed, route_num, direction):
    gd_route = get_route_speed_segments(
        feed, route_id_from_route_num(feed, route_num)
        )
    gd_route = pd_filter(gd_route, 'direction_id', direction)
    log.info(f'Number of stops (preliminary) {len(gd_route)}')
    gd_route = gd_route.drop_duplicates(subset = ['stop_sequence'])
    rtn = len(gd_route)
    log.info(f'Number of stops (finalized) {len(gd_route)}')
    return rtn

def bin_for_map(feed, csv, route, direction, length, step):
    gdf_split = range(
        0, length, step
    )
    gdf_slist = list(gdf_split)
    gdf = get_aggregate_productivity(
        feed, csv, route, direction, gdf_slist
    )
    gdf = gdf.fillna(0)
    #ldf[route] = gdf
    return gdf

def build_map_for_speed(feed, csv = CSV_PATH, step = 5):
    """
    I Know, I Know,

    At some point I'll actually refactor
    
    But for now...
    """

    #routes = [455]

    routes = ['1', '17', '2', '200', '201', '205', '209', '21', '213', '217', 
              '218', '220', '223', '227', '240', '248', '33', '35', '39', '4', 
              '45', '451', '455', '47', '470', '509', '513', '54', 
              '603X', '604', '612', '613', '62', '625', '626', '627', 
              '628', '630', '640', '645', '72', '805', 
              '806', '807', '821', '822', '830X', '831', 
              '834', '850', '862', '871',
              '9', 'F11', 'F202', 'F232', 'F453', 
              'F514', 'F556', 'F570', 'F578', 'F590', 
              'F618', 'F620', 'F94']

            # Removed routes are:
            # All Ski service
            # 472, 473, 551 601, 602, 606, F638, 667, 833
    #routes = list(feed.routes['route_short_name'])

    routegeom = geopd.GeoDataFrame(feed.avg_speeds, geometry='geometry')
    minx, miny, maxx, maxy = routegeom.geometry.total_bounds

    centroid_lat = miny + (maxy - miny)/2
    centroid_lon = minx + (maxx - minx)/2

    m = folium.Map(
        location=[centroid_lat, centroid_lon],
        tiles='cartodbpositron', zoom_start=12
        )

    colorscale = LinearColormap(
        colors=['#570600', '#ce0e2d', '#dc7237', '#f6d32a', '#6abf4b','#45842e','#2e847d'],
        index =[0, 10, 15, 20, 25, 30, 40],
        tick_labels=[10, 20, 30, 40, 50],
        vmin = 0,
        vmax = 60,
        caption='Speed'
    )

    #ldf = {}
    directions = [1, 0]
    for direction in directions:
        for route in routes:
            glen = get_number_stops(feed, route, direction)
            name = "Route " + str(route) + " Direction " + str(direction)
            #try:
            log.info(f'Trying {name}')
            gdf = bin_for_map(
                feed, csv, route, direction, glen, step
                    )
            plot_2(gdf, colorscale, name, 'speed').add_to(m)

            
            # Handle weird annoying cases where the number of stops is???
                # More than the number of stops (?????)

            # Update: should be fixed by modifying get_number_stops to drop duplicates

            # except ValueError:
            #     log.info('Route ' + str(route) + "threw an error")
            #     glen = glen - 5
            #     bin_for_map(
            #         feed, csv, route, direction, glen, step
            #         )
            #     plot_2(gdf, colorscale, name).add_to(m)
    

    colorscale.add_to(m)
    
    folium.LayerControl().add_to(m)

    m.save('speed.html')