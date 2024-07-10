import gtfs_functions
import logging
import os
import pathlib
from nicegui import run, ui, context, app, events
import pickle


class AppClass:
    def __init__(self):
        self._isFeedLoading = False
        self.mapLayers = {}
        self.edgesDict = {}
        self.mapItem = None
        self.feedURI = None
        self._csvURI = None
        self._isFeedLoaded = False
        self._feed = None
        self._needsPickling = False
        self._dialog = None
        # self.get_route_dirs()

    @property
    def feed(self):
        return self._feed
    
    @feed.setter
    def feed(self, other):
        assert isinstance(other, gtfs_functions.Feed)
        self._feed = other
        self._isFeedLoading = False
        self._isFeedLoaded = True
        logging.info("Installing feed in object")
        if self._needsPickling is True:
            logging.info("Asking if user wants to Pickle")
            self.pickleDialog

    @property
    def isFeedLoaded(self):
        return self._isFeedLoaded
    
    @property
    def isFeedLoading(self):
        return self._isFeedLoading
    
    @isFeedLoading.setter
    def isFeedLoading(self, other):
        assert isinstance(other, bool)
        self._isFeedLoading = other

    @property
    def isAppReady(self):
        ready = self.isFeedLoaded and (self.csvURI is not None)
        return ready
   
    @property
    def needsPickling(self):
        return self._needsPickling

    @needsPickling.setter
    def needsPickling(self, other):
        assert isinstance(other, bool)
        self._needsPickling = other
        logging.info(f'Set needsPickling to {self._needsPickling}')

    @property
    def dialog(self):
        return self._dialog
    
    @dialog.setter
    def dialog(self, other):
        assert isinstance(other, ui.dialog)
        self._dialog = other

    def load_feed(self):
        """
        Loads the feed. Designed to be run asynchronously by NiceGUI

        For this reason, it returns the feed to be loaded into the main thread
        of the object.
        """
        # TODO: refactor to enable weekends
        sid = gtfs_functions.Feed(self.feedURI).busiest_service_id
        self._feed = gtfs_functions.Feed(
                                            self.feedURI, 
                                            service_ids=[sid],
                                            time_windows=[0,24]
                                        )
        logging.info("Loading GTFS Feed")
        self.isFeedLoading = True
        self.feed.avg_speeds
        logging.info("GTFS Feed Loaded")
        return self.feed
    
    def clearMapLayers(self):
        self.mapLayers = {}
        self.edgesDict = {}

    def pickleFeed(self):
        file_name = os.path.basename(self.feedURI)
        file_n2 = os.path.splitext(file_name)[0]
        with open(
                f'Feeds\\{file_n2}.pkl', 'wb'
            ) as o:
            logging.info('Saving pickle')
            pickle.dump(self.feed, o, pickle.HIGHEST_PROTOCOL)


    

    # def pickleDialog(self):
    #     """
    #     Opens a dialog confirming user wants to clear the map

    #     Encapsulated in appObject because we need to control the dialog box
    #     from helper functions
    #     """
    #     logging.info('Asking if user wants to pickle')
    #     with ui.dialog() as self.dialog:
    #         with ui.card():
    #             ui.label(
    #                 'Do you want to pickle the GTFS Feed (speeds loading time)'
    #                 )
    #             with ui.row().classes('self-center'):
    #                 ui.button('Yes', on_click=self.pickleFeed)
    #                 ui.button('No', on_click=self.dialogCleanup)
    #     self.dialog.open()

        

class InteractableModelItem:
    """
    A class defining for global values associated with view items.

    Initialized empty, but has a series of values with meanings relevant to the
        relevant UI Function via setter or method

    Parameter visibility (Bool): if the UI element should be visible.
        Automatically switches to 'True' when valuesList is updated.

    Parameter valuesList: the list of all values which are associated 
        with a given UI Element. Typically list or DF
    
    Parameter userValue: value(s) selected or identified by the user.

    Parameter columns: the columns used for a table with list valuesList

    Parameter valuesMap: a mapping dictionary containing values to be included
        in valuesList. 
        valuesList cannot be set directly when valuesMap is set.
    """
    def __init__(self):
        self._userValue = None
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

    @property
    def userValue(self):
        return self._userValue
    
    @userValue.setter
    def userValue(self, other):
        self.setUserValue(other)

    # def setUserValueDF(self, other):
    #     """
    #     Gets a list of dicts, converts to a PD dataframe, and sets as value
    #     """
    #     assert isinstance(other, list)
    #     self._userValue = pandas.DataFrame(other)
        
    def setUserValue(self, other):
        # logging.info(f"Updating value of object to {other}")
        self._userValue = other

    def visibilityOn(self):
        self.visibility = True
