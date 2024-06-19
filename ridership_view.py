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
# import folium
from nicegui import run, ui, context, app, events
import pandas
import gtfs_functions
import datetime as dt

session = None # I have no memory of what this does

# Classes
class AppClass:
    def __init__(self):
        self.is_feed_loading = False
        self.mapLayers = {}
        self.edgesDict = {}
        self.mapItem = None
        self.feedURI = None
        self._csvURI = None
        self._isFeedLoaded = False
        self._feed = None
        # self.get_route_dirs()

    @property
    def feed(self):
        return self._feed
    
    @feed.setter
    def feed(self, other):
        assert isinstance(other, gtfs_functions.Feed)
        self._feed = other
        self.is_feed_loading = False
        self._isFeedLoaded = True

    @property
    def isFeedLoaded(self):
        return self._isFeedLoaded

    @property
    def isAppReady(self):
        ready = self.isFeedLoaded and (self.csvURI is not None)
        return ready

    def load_feed(self):
        # TODO: refactor to enable weekends
        sid = gtfs_functions.Feed(self.feedURI).busiest_service_id
        self._feed = gtfs_functions.Feed(
                                            self.feedURI, 
                                            service_ids=[sid],
                                            time_windows=[0,24]
                                        )
        logging.info("Loading GTFS Feed")
        self.is_feed_loading = True
        self.feed.avg_speeds
        logging.info("GTFS Feed Loaded")
        return self.feed

    def clearMapLayers(self):
        self.mapLayers = {}
        activate_map_function.refresh()
        self.dialogCleanup()

    def dialogCleanup(self):
        self.dialog.close()
        self.dialog.clear()

    def openDialog(self):
        logging.info('Confirming user wants to clear')
        with ui.dialog() as self.dialog:
            with ui.card():
                ui.label('Do you really want to clear all lines from the map?')
                with ui.row().classes('self-center'):
                    ui.button('Yes', on_click=self.clearMapLayers)
                    ui.button('No', on_click=self.dialogCleanup)
        self.dialog.open()

        

class Item:
    def __init__(self):
        self.value = None
        self._valuesList = [] # Thank g-d for non-static typing
        self._visibility = False
        self.columns = []
        self._valuesMap = None
        self._valuesMapIsSet = False

    @property
    def valuesList(self):
        if self._valuesMapIsSet:
            return list(self._valuesMap)
        else: 
            return self._valuesList
    
    def setValuesDF(self, values):
        """
        Gets a list of dicts, converts to a PD dataframe, and sets as values
        """
        assert isinstance(values, list)
        self.valuesList = pandas.DataFrame(values)
        

    @valuesList.setter
    def valuesList(self, values):
        """
        Toggles visibility on for an item and loads the values list
        """
        if self._valuesMapIsSet:
            raise AttributeError(
                "Cannot set valuesList directly when valuesMap is set"
                )
        else:
            self.visibility = True
            self._valuesList = values

    
    @property
    def visibility(self):
        return self._visibility
    
    @visibility.setter
    def visibility(self, other):
        assert isinstance(other, bool)
        self._visibility = other

    @property
    def valuesMap(self):
        return self._valuesMap
    
    @valuesMap.setter
    def valuesMap(self, other):
        assert isinstance(other, dict)
        self._valuesMap = other
        self._valuesMapIsSet = True

# Set up objects
appObject = AppClass()
routes = Item()
dirs = Item()
prodToggle = Item()
stops = Item()
buttonObject = Item()

buttonObject.visibility = False
prodToggle.valuesMap = {
    'Productivity': 'productivity_activity',
    'Speed': 'speed'
    }

# Refreshable UI Elements
@ui.refreshable 
def routes_dropdown_function():
    routesel = ui.select(routes.valuesList, 
                            with_input=True,
                            on_change=update_dirs)
    routesel.bind_visibility_from(routes, 'visibility')
    routesel.bind_value(routes, 'value')
    routesel.classes('w-full')

@ui.refreshable
def list_dirs_function():
    with ui.row():
        dirs_label = ui.label("Direction:")
        dirs_label.classes('self-center')
        dirs_label.bind_visibility_from(dirs, 'visibility')
        dirs_toggle = ui.toggle(dirs.valuesList, on_change=update_stops)
        dirs_toggle.bind_value(dirs, 'value')
        dirs_toggle.bind_visibility_from(dirs, 'visibility')
        prod_toggle = ui.toggle(prodToggle.valuesList)
        prod_toggle.bind_visibility(dirs, 'visibility')
        prod_toggle.bind_value(prodToggle.value)

@ui.refreshable
def list_stops_function():
    stops_table = ui.table(
        columns=stops.columns, rows = stops.valuesList, selection='multiple')
    stops_table.classes('w-full flex-grow')
    stops_table.props('virtual-scroll')
    stops_table.style("max-height: 70vh")
    # Take note, button visibility is bound to stops visibility
    stops_table.bind_visibility_from(stops, 'visibility')

    # And we store the selected values in the button
    stops_table.on_select(lambda: buttonObject.setValuesDF(stops_table.selected))

@ui.refreshable
def activate_button_function():
    activate_button = ui.button(on_click=update_map)
    activate_button.classes('self-center')
    activate_button.bind_visibility_from(stops, 'visibility')

    # The button object's visibility property is used to determine
    # if the button is activated
    activate_button.bind_enabled_from(buttonObject, 'visibility')
    activate_button.bind_text_from(buttonObject, 'value')

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
    appObject.is_feed_loading = True
    routes.visibility = False
    appObject.feed = await run.cpu_bound(appObject.load_feed)
    routes.visibility = True

def update_dirs():
    logging.info(f"Updating direction for route number {routes.value}")
    
    # Note: adds previously undefined object rid to Item 'routes'
    if routes.value is not None:
        rid = rfx.route_id_from_route_num(appObject.feed, routes.value)
        routes.speed_segs = rfx.pd_checkfilter(appObject.feed.avg_speeds,'route_id', rid)
        trips = rfx.pd_checkfilter(appObject.feed.trips, 'route_id', rid)
        dirs_list = list(set(trips['direction_id']))
        dirs.valuesList = dirs_list
    else:
        logging.info("No route provided, holding")
    list_dirs_function.refresh()

def update_stops():
    # print(f"Updating stops for route {routes.value} in direction {dirs.value}")
    route_in_dir = rfx.pd_checkfilter(
        routes.speed_segs, 'direction_id', dirs.value)
    stop_only = route_in_dir[['stop_sequence', 'start_stop_name']]
    stops.valuesList = stop_only.rename(
        columns={'stop_sequence':'id'}).to_dict('records')
    buttonObject.visibility = True
     # Note: adds previously undefined object columns to Item 'stops'
    stops.columns = [
        {'name':'start_stop', 'label':'Stop', 'field':'start_stop_name'}
        ]
    routes_dirs = (routes.value, dirs.value)
    # print(f"Checking if {routes_dirs} is in {appObject.mapLayers}")
    if routes_dirs in appObject.mapLayers:
        # print("It is!")
        buttonObject.value = "Update Segments"
    else:
        buttonObject.value = "Calculate Productivity"
    list_stops_function.refresh()
    activate_button_function.refresh()

def update_map():
    buttonObject.visibility = False
    ui.notify('calculating Productivity')
    edges = set(buttonObject.valuesList['id'].tolist())
    edges = {v - 1 for v in edges}
    edges.add(0)
    edges_lst = list(edges)
    edges_lst.sort()
    newlyr = rplt.build_lyr_for_route(
        appObject.feed, routes.value, edges_lst, dirs.value,
        highlight=prodToggle.valuesMap[buttonObject.value],
        csv=appObject.csvURI)
    route_dir = (routes.value, dirs.value)
    appObject.mapLayers[route_dir] = newlyr
    appObject.edgesDict[route_dir] = edges
    buttonObject.value = "Update Segments"
    activate_map_function.refresh()

def download_map():
    html_doc= appObject.mapItem.get_root()._repr_html_()
    dirmk('Saved Maps')
    time_marker = str(
        dt.datetime.today().replace(microsecond=0)
        ).replace(":","")
    with open(f'Saved Maps\\Export {time_marker}.html', 'w') as o:
        logging.info("Exporting map")
        o.write(html_doc)
    #ui.download(bytes(html_doc, encoding='utf-8'), 'productivity.html')

# def add_number() -> None:
#    numbers.appObjectend(random.randint(0, 100))
#    number_ui.refresh()

# Build the webpage

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
                with ui.row().classes('w-full justify-between'):
                    ui.label('Route Productivity Monitor').classes('self-center')
                    with ui.dropdown_button(
                        'Options'):
                            ui.item('Save Map', on_click=download_map)
                            ui.item('Clear Map', on_click=appObject.openDialog)
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
    spinner = ui.spinner().classes('self-center')
    spinner.bind_visibility_from(appObject, 'is_feed_loading')

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