from pythonnet import set_runtime
set_runtime('netfx')

import os
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)

runtime = Path.cwd() / 'python312.dll'
if runtime.exists():
    logging.info('Detected operating in package mode!')
    logging.info('Attempting to set up envs')
    os.environ["PYTHONNET_PYDLL"] = str(runtime.resolve())
    os.environ["BASE_DIR"] = str(Path.cwd().resolve())

import ridership_functions as rfx
import ridership_plots as rplt
import pickle
import json
from ridershipViewObjects import InteractableModelItem as Item
from ridershipViewObjects import AppClass
# import folium
from nicegui import run, ui, context, app, events
import pandas
#import gtfs_functions
import datetime as dt

session = None # I have no memory of what this does

# Classes


# Set up objects
appObject = AppClass()
routes = Item()
dirs = Item()
prodToggle = Item()
stopsTable = Item()
buttonObject = Item()

buttonObject.visibility = False
prodToggle.valuesMap = {
    'Productivity': 'productivity_activity',
    'Speed': 'speed'
    }
prodToggle.userValue = 'Productivity'

# Refreshable UI Elements
@ui.refreshable 
def routes_dropdown_function():
    routesel = ui.select(routes.valuesList, 
                            with_input=True,
                            on_change=update_dirs)
    routesel.bind_visibility_from(routes, 'visibility')
    routesel.bind_value(routes, 'userValue')
    routesel.classes('w-full')

@ui.refreshable
def list_dirs_function():
    with ui.row():
        dirs_label = ui.label("Direction:")
        dirs_label.classes('self-center')
        dirs_label.bind_visibility_from(dirs, 'visibility')
        dirs_toggle = ui.toggle(dirs.valuesList, on_change=update_stops)
        dirs_toggle.bind_value(dirs, 'userValue')
        dirs_toggle.bind_visibility_from(dirs, 'visibility')
        

@ui.refreshable
def list_stops_function():
    stops_table = ui.table(
            columns=stopsTable.columns, 
            rows = stopsTable.valuesList,
            selection='multiple'
            )
    stops_table.classes('w-full flex-grow')
    stops_table.props('virtual-scroll')
    stops_table.style("max-height: 70vh")
    # Take note, button visibility is bound to stops visibility
    stops_table.bind_visibility_from(stopsTable, 'visibility')
    route_dir = (routes.userValue, dirs.userValue)
    if route_dir in appObject.edgesDict:
        stops_table.selected = appObject.edgesDict[route_dir]

    # And we store the selected values
    stops_table.on_select(lambda: stoplist_sel(stops_table.selected))

@ui.refreshable
def activate_button_function():
    activate_button = ui.button(on_click=update_map)
    activate_button.classes('self-center')
    activate_button.bind_visibility_from(stopsTable, 'visibility')

    # The button object's visibility property is used to determine
    # if the button is activated
    activate_button.bind_enabled_from(buttonObject, 'visibility')
    activate_button.bind_text_from(buttonObject, 'userValue')

@ui.refreshable
def activate_map_function():
    if appObject.isFeedLoaded:
        appObject.mapItem = rplt.initialized_map(feed=appObject.feed, 
                                                lyrs=appObject.mapLayers)
        html = appObject.mapItem.get_root()._repr_html_()
        html = html.replace('">', 'height:100%;">',1)
        html = html.replace('height:0','height:100%',1)
        ui.html(html).classes('w-full h-full').style('height: 100%')
        logging.info('Map activation refreshed')
    else: pass

# UI Element Setters (I know I know)
def set_routes():
    """
    Sets the list of routes as the value of values in the provided GTFS Feed
    """
    route_list = appObject.feed.routes['route_short_name'].tolist()
    routes.valuesList = route_list

async def start_feedload():
    """
    Asynchronously loads a feed (defined by appObject.feedURI) from either
        a Zipped GTFS or a pickle
    """
    appObject.isFeedLoading = True
    routes.visibility = False
    logging.info("Beginning to load feed")
    if os.path.splitext(appObject.feedURI)[1] == '.pkl':
        logging.info('Detected pickled feed, loading!')
        with open(appObject.feedURI, 'rb') as thePickle:
            brineless = pickle.load(thePickle)
            appObject.feed = brineless
        routes.visibility = True
    elif os.path.splitext(appObject.feedURI)[1] == '.zip':
        logging.info('Detected zipped feed, loading!')
        appObject.feed = await run.cpu_bound(appObject.load_feed)
        appObject.needsPickling = True
        routes.visibility = True   
    
    else:
        appObject.isFeedLoading = False
        raise ValueError(f'File {appObject.feedURI} has wrong extension')

def update_dirs():
    logging.info(f"Updating direction for route number {routes.userValue}")
    
    # Note: adds previously undefined object rid to Item 'routes'
    if routes.userValue is not None:
        rid = rfx.route_id_from_route_num(appObject.feed, routes.userValue)
        routes.speed_segs = rfx.pd_checkfilter(
            appObject.feed.avg_speeds,'route_id', rid)
        trips = rfx.pd_checkfilter(appObject.feed.trips, 'route_id', rid)
        dirs_list = list(set(trips['direction_id']))
        dirs.valuesList = dirs_list
    else:
        logging.info("No route provided, holding")
    list_dirs_function.refresh()

def stoplist_sel(ls):
    stopsTable.userValue = ls
    buttonObject.visibility = True

def update_stops():
    """
    Based on the route & direction identified by respective model objects,
        loads a table of stops into the stopsTable object
        refreshes the list view and the map update button
    """
    # Filters the GTFS speed segments
    route_in_dir = rfx.pd_checkfilter(
        routes.speed_segs, 'direction_id', dirs.userValue)
    stop_only = route_in_dir[['stop_sequence', 'start_stop_name']]
    
    # Prettifies and creates the columns
    stopsTable.valuesList = stop_only.rename(
        columns={'stop_sequence':'id'}).to_dict('records')
    buttonObject.visibility = False
    
    # This is currently the only use of Item.columns()
    stopsTable.columns = [
        {'name':'start_stop', 'label':'Stop', 'field':'start_stop_name'}
        ]
    routes_dirs = (routes.userValue, dirs.userValue)

    # Adjusts the text of the button if the user has already selected segments
    if routes_dirs in appObject.mapLayers:
        # print("It is!")
        buttonObject.userValue = "Update Segments"
    else:
        buttonObject.userValue = "Calculate Productivity"
    
    # Refreshes
    list_stops_function.refresh()
    activate_button_function.refresh()

def update_map():
    """
    Updates the map with a given route, direction, & edges found in the 
    relevant Item() model objects 
    """
    buttonObject.visibility = False
    ui.notify(f'Calculating {prodToggle.userValue}')

    # Setting up the edges from the checked values
    edges = set(pandas.DataFrame(stopsTable.userValue)['id'].tolist())
    edges = {v - 1 for v in edges}
    edges.add(0)
    edges_lst = list(edges)
    edges_lst.sort()
    
    # Create the layer for the routes
    newlyr = rplt.build_lyr_for_route(
        appObject.feed, routes.userValue, edges_lst, dirs.userValue,
        highlight=prodToggle.valuesMap[prodToggle.userValue],
        csv=appObject.csvURI)
    route_dir = (routes.userValue, dirs.userValue)
    
    # Places the layer and the edges into dictionaries
    appObject.mapLayers[route_dir] = newlyr
    appObject.edgesDict[route_dir] = stopsTable.userValue
    buttonObject.userValue = "Update Segments"
    activate_map_function.refresh()

def download_map():
    """
    Saves a raw Leaflet map to the folder Saved Maps with a title defined by
        the time marker
    """
    html_doc= appObject.mapItem.get_root()._repr_html_()
    dirmk('Saved Maps')
    time_marker = str(
        dt.datetime.today().replace(microsecond=0)
        ).replace(":","")
    with open(f'Saved Maps\\Export {time_marker}.html', 'w') as o:
        logging.info("Exporting map")
        o.write(html_doc)
    #ui.download(bytes(html_doc, encoding='utf-8'), 'productivity.html')

def save_seg_def():
    """
    Saves a JSON containing the segment information to the folder Exports
        with a title defined by the time marker
    """
    dirmk('Saved Segments')
    time_marker = str(
        dt.datetime.today().replace(microsecond=0)
        ).replace(":","")
    
    # IGNOREME
    # edges_cleaned = {}
    # for e in appObject.edgesDict:
    #     for 
    #     e_str = f'Route {e[0]} Direction {e[1]}'
    #     logging.info(f'cleaning {e_str}')
    #     edges_cleaned[e_str] = pandas.DataFrame(appObject.edgesDict[e])
    # logging.info(f'edges cleaned looks like {edges_cleaned}')
    # e_df = pandas.concat(edges_cleaned)
    # logging.info(f'e_df looks like{e_df} and is of type {type(e_df)}')
    
    dump = rearrange_and_convert_to_json(appObject.edgesDict)
    with open(f'Saved Segments\\Export {time_marker}.json', 'w') as o:
        logging.info("Exporting segments info")
        o.write(dump)

def rearrange_and_convert_to_json(data):
    """
    Helper function, created with the support of a large pile of linear algebra
    """
    rearranged_data = {}

    for (rt, dir), records in data.items():
        if rt not in rearranged_data:
            rearranged_data[rt] = {}
        rearranged_data[rt][dir] = records

    # Convert the rearranged dictionary to a JSON string
    json_data = json.dumps(rearranged_data, indent=4)

    return json_data


# def add_number() -> None:
#    numbers.appObjectend(random.randint(0, 100))
#    number_ui.refresh()

# Build the webpage

def open_dialog():
        """
        Opens a dialog confirming user wants to clear the map

        Encapsulated in appObject because we need to control the dialog box
        from helper functions
        """
        logging.info('Confirming user wants to clear')
        with ui.dialog() as appObject.dialog:
            with ui.card():
                ui.label('Do you really want to clear all lines from the map?')
                with ui.row().classes('self-center'):
                    ui.button('Yes', on_click=clear_clean)
                    ui.button('No', on_click=dialog_cleanup)
        appObject.dialog.open()


    #activate_map_function.refresh()

def clear_clean():
    appObject.clearMapLayers()
    dialog_cleanup()


def dialog_cleanup():
    appObject.dialog.close()
    appObject.dialog.clear()
    activate_map_function.refresh()

@ui.page('/application')
def application():
    logging.info("Starting productivity monitor application")
    context.client.content.classes('h-[100vh]')
    ui.add_head_html(
    '<style>.q-textarea.flex-grow .q-field__control { height: 100% }</style>'
    ) 

    with ui.grid(columns='1fr 3fr').classes('w-full h-full gap-2'):
        for _ in range(1):
            with ui.column():
                ui.label('Route Productivity Monitor').classes('self-center')
                with ui.row().classes('w-full justify-right'):
                    with ui.dropdown_button('Options'):
                            ui.item('Save Segments', on_click=save_seg_def)
                            ui.item('Save Map', on_click=download_map)
                            ui.item('Clear Map', on_click=open_dialog)
                    with ui.dropdown_button(
                           prodToggle.valuesList
                        ) as prod_toggle:
                        #prod_toggle.bind_visibility(dirs, 'visibility')
                        prod_toggle.bind_text(prodToggle, 'userValue')
                        for i in prodToggle.valuesList:
                            ui.item(
                                i, 
                                on_click=lambda i=i: prodToggle.setUserValue(i)
                                )
                routes_dropdown_function()
                list_dirs_function()
                list_stops_function()
                activate_button_function()
            with ui.card().classes('no-shadow border-[1px] w-full'):
                activate_map_function()

def dirmk(dirname):
    if dirname not in os.listdir():
        logging.info(f"Directory {dirname} doesn't exist! Creating...")
        os.mkdir(dirname)
    else: pass

def activate_application():
    set_routes()
    ui.navigate.to('/application')
    routes_dropdown_function.refresh()

feed_uris = []

dirmk('Feeds')
dirmk('CSVs')

lsfeed = os.scandir('Feeds')
for e in lsfeed:
    feed_uris.append(e.path)
feed_uris.append('http://gtfsfeed.rideuta.com/GTFS.zip')
with ui.row().classes('self-center'):
    ui.label("Select GTFS Feed: ").classes('self-center')
    feed_selector = ui.select(feed_uris).classes('self-center w-96')
    feed_selector.bind_value(appObject, 'feedURI')

with ui.row().classes('self-center'):
    feed_button = ui.button('Load Feed', on_click=start_feedload)
    feed_button.classes('self-center')
    pickle_button = ui.button('Pickle Feed', on_click=appObject.pickleFeed)
    feed_button.classes('self-center')
    pickle_button.bind_visibility_from(appObject, 'needsPickling')
    spinner = ui.spinner().classes('self-center')
    spinner.bind_visibility_from(appObject, 'isFeedLoading')

csv_uris = []
lscsv = os.scandir('CSVs')
for e in lscsv:
    csv_uris.append(e.path)
with ui.row().classes('self-center'):
    ui.label("Select CSV File: ").classes('self-center')
    csv_selector = ui.select(csv_uris).classes('self-center w-96')
    csv_selector.bind_value(appObject, 'csvURI')
    # csv_button = ui.button('Load CSV')
    # csv_button.classes('self-center')


go = ui.button("Start Productivity Monitor", 
               on_click=activate_application)
go.classes('self-center')
go.bind_enabled_from(appObject, 'isAppReady')

ui.run(
    title="UTA Productivity Reporter", 
    favicon='🚏', window_size=(1024,768),
    reload=False
    )