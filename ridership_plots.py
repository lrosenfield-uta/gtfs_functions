"""
Functions for plotting ridership and productivity 
    based on GTFS and ridership data

Author: Lilah Rosenfield || Utah Transit Authority
11925@rideuta.com
"""

import pandas as pd
import geopandas as geopd
# import shapely
import logging as log
# import sys
# import jenkspy
import numpy as np
import folium
from branca.colormap import LinearColormap
import ridership_functions as rfx
import gtfs_functions
import gtfs_plots

DEFAULT_COLORSCALE = LinearColormap(
    colors=['#570600', '#ce0e2d', '#dc7237', '#f6d32a', '#6abf4b','#45842e','#2e847d'],
    index =[0, 2.5, 5, 10, 20, 25, 40],
    tick_labels=[10, 20, 30, 40],
    vmin = 0,
    vmax = 50,
    caption='productivity'
    )

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

def plot_2(gdf, 
           name, 
           colorscale=DEFAULT_COLORSCALE,
           highlight = 'productivity_activity'):
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

    # return m

def initialized_map(feed, lyrs, colorscale = DEFAULT_COLORSCALE):
    routegeom = geopd.GeoDataFrame(feed.stops, geometry='geometry')
    minx, miny, maxx, maxy = routegeom.geometry.total_bounds

    centroid_lat = miny + (maxy - miny)/2
    centroid_lon = minx + (maxx - minx)/2

    m = folium.Map(
        location=[centroid_lat, centroid_lon],
        tiles='cartodbpositron', zoom_start=12
        )
    
    for lyr in lyrs:
        lyrs[lyr].add_to(m)

    colorscale.add_to(m)
    folium.LayerControl().add_to(m)

    return m

def build_lyr_for_route(feed, route, edges, direction,
                         csv = rfx.CSV_PATH, colorscale = DEFAULT_COLORSCALE):
    name = "Route " + str(route) + " Direction " + str(direction)
        #try:
    log.info(f'Trying {name}')
    gdf = rfx.get_aggregate_productivity(
        feed, csv, route, direction, edges
                    )
    gdf = gdf.fillna(0)
    
    log.info('Getting Layer')
    lyr = plot_2(gdf, name, colorscale=colorscale)
    return lyr


def build_map_for_route(feed, route, edges, direction, map_in,
                         csv = rfx.CSV_PATH, colorscale = DEFAULT_COLORSCALE,
                         save_map = False):
    """
    Builds map for a single route

    Parameter feed: a gtfs feed object
    Parameter route: the route on which to calculate
    Parameter edges: a left-closed list of edges at which to calculate productivity
    csv: the path to the CSV 
    save: boolean switch to save map to html
    """
   
    build_lyr_for_route(feed, route, 
                        edges, direction,
                        map_in, csv, colorscale).add_to(map_in)

    if save_map == True:
        map_in.save('Route_' + route + '.html')

    log.info('Successfully added to map, returning')
    return map_in

def build_map(feed, csv = rfx.CSV_PATH,
              step = 4, colorscale = DEFAULT_COLORSCALE):
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
            plot_2(gdf, name).add_to(m)

            
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
    gd_route = rfx.get_route_speed_segments(
        feed, rfx.route_id_from_route_num(feed, route_num)
        )
    gd_route = rfx.pd_filter(gd_route, 'direction_id', direction)
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
    gdf = rfx.get_aggregate_productivity(
        feed, csv, route, direction, gdf_slist
    )
    gdf = gdf.fillna(0)
    #ldf[route] = gdf
    return gdf

def build_map_for_speed(feed, csv = rfx.CSV_PATH, step = 5):
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