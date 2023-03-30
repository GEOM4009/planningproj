# -*- coding: utf-8 -*-
"""
planning.py
Authors: Mitch, Lucas, Ethan, Nata, Winaa

This file contains the main script for the GEOM4009 planning project.
It contains the main menu and all the functions for the different the
different steps of the data and planning process.

NOTE: This script must be run in the geom4009 environment, but will require
      the installation of the following additional packages:

    conda install -c anaconda flask  --> this will be removed in the future
    conda install -c conda-forge tk  --> provides the tkinter GUI

TODO: Get user input to set CRS for the project
TODO: Confirm with client if there will be any use case for an argument parser
TODO: Add additional error handling for the different functions

"""
# Import modules
from util import *
from defs import *
import os

os.environ["USE_PYGEOS"] = "0"
import app
from time import time

from shapely.geometry import Polygon
import shapely
from math import pi, cos, sqrt
import math

import geopandas as gpd
import pandas as pd
import matplotlib.pyplot as plt

from tqdm import tqdm
from multiprocessing import Pool

import numpy as np
import psutil
from functools import partial


# Global Variables
run_tests = False
verbose = True
CORES = psutil.cpu_count(logical=False)
target_crs = ""
rectangular_grid = False


# %% create a planning unit grid
def create_hexagon(l, x, y):
    """
    Author:Kadir Şahbaz
    Create a hexagon centered on (x, y)
    :param l: length of the hexagon's edge
    :param x: x-coordinate of the hexagon's center
    :param y: y-coordinate of the hexagon's center
    :return: The polygon containing the hexagon's coordinates
    Source:https://gis.stackexchange.com/questions/341218/creating-a-hexagonal-grid-of-regular-hexagons-of-definite-area-anywhere-on-the-g
    """
    c = [
        [x + math.cos(math.radians(angle)) * l, y + math.sin(math.radians(angle)) * l]
        for angle in range(0, 360, 60)
    ]
    return Polygon(c)


def create_hexgrid(bbx, side):
    """
    Author:Kadir Şahbaz
    returns an array of Points describing hexagons centers that are inside the given bounding_box
    :param bbx: The containing bounding box. The bbox coordinate should be in Webmercator.
    :param side: The size of the hexagons'
    :return: The hexagon grid
    Source:https://gis.stackexchange.com/questions/341218/creating-a-hexagonal-grid-of-regular-hexagons-of-definite-area-anywhere-on-the-g
    """
    grid = []
    v_step = math.sqrt(3) * side
    h_step = 1.5 * side

    x_min = min(bbx[0], bbx[2])
    x_max = max(bbx[0], bbx[2])
    y_min = min(bbx[1], bbx[3])
    y_max = max(bbx[1], bbx[3])

    h_skip = math.ceil(x_min / h_step) - 1
    h_start = h_skip * h_step

    v_skip = math.ceil(y_min / v_step) - 1
    v_start = v_skip * v_step

    h_end = x_max + h_step
    v_end = y_max + v_step

    if v_start - (v_step / 2.0) < y_min:
        v_start_array = [v_start + (v_step / 2.0), v_start]
    else:
        v_start_array = [v_start - (v_step / 2.0), v_start]

    v_start_idx = int(abs(h_skip) % 2)

    c_x = h_start
    c_y = v_start_array[v_start_idx]
    v_start_idx = (v_start_idx + 1) % 2
    while c_x < h_end:
        while c_y < v_end:
            grid.append((c_x, c_y))
            c_y += v_step
        c_x += h_step
        c_y = v_start_array[v_start_idx]
        v_start_idx = (v_start_idx + 1) % 2

    return grid


def create_planning_unit_grid(planning_unit_grid) -> gpd.GeoDataFrame:
    """
    Author: Lucas
    This function will take user input to create a hexagonal planning
    grid that is defined by a central coordinate, cell resolution,
    and grid height and width. A unique Planning unit ID is then given
    to each hexagon and the final grid can be output to a shapefile.
    It can also create this grid using other methods, such as taking a
    shapefile as input, the CRS and the bounds of that file will be
    determined and used to create the planning grid. Additionally a
    previously created grid can be input by the user
    Parameters
    ----------
    planning_unit_grid : gpd.geodataframe
        if a previuos hexagonal grid has been created it can be input
        to skip the creation of a new grid
    Area: float
        Size of grid cell that the user will use, the units will be
        the same units as the CRS that the user specifies
    grid_size_x: float
        width of the grid
    grid_size_y: float
        height of the grid
    grid_lat: float
        y coordinate for center of grid
    grid_lon: float
        x coordinate for center of grid
    Prj: float
        CRS the grid will be output with
    Returns
    -------
    TYPE
        Description

    """

    while True:
        try:
            selection = int(
                input(
                    """
    Create Planning Unit Grid
        1 Create Grid from Shape File extents
        2 Load existing Grid from File
        3 Create Grid from User Input
        9 Return to Main Menu
    >>> """
                )
            )
        except ValueError:
            print_warning_msg(msg_value_error)
            continue

        # 1 Create Grid from Shape File extents
        if selection == 1:
            file = get_file(title="Select a file to load the extents from")
            Area = get_user_float("Grid Cell Area (Meters Squared):")
            Prj = file.crs
            box = file.total_bounds

            edge = math.sqrt(Area**2 / (3 / 2 * math.sqrt(3)))
            hex_centers = create_hexgrid(box, edge)
            hex_centers
            hexagons = []
            for center in hex_centers:
                hexagons.append(create_hexagon(edge, center[0], center[1]))
            planning_unit_grid = gpd.GeoDataFrame(geometry=hexagons, crs=Prj)

            planning_unit_grid["PUID"] = planning_unit_grid.index + 1
            planning_unit_grid.to_file("planning_unit_grid.shp")
            break

        # 2 Load existing Grid from File
        elif selection == 2:
            file = get_file(title="Select a file to load the grid from")
            if file:
                planning_unit_grid = load_files(file, verbose)
                # TODO: This is a hack to get the global target_crs, should enable
                #      an option to do it this way or ask the user which crs to use.
                #      This crs should checked to see if it is projected or not.
                global target_crs
                target_crs = planning_unit_grid.crs
                if verbose:
                    print_info(
                        f"Hex area: {round(planning_unit_grid.geometry.area[0])}"
                    )
            else:
                print_warning_msg("No file loaded, please try again.")
                continue
            break

        # 3 Create Grid from User Input
        elif selection == 3:
            # The inputs below will get the information needed to
            # create a boundary that will be filled with the hexagons as
            # well as define the hexagon cell size
            Area = get_user_float("Grid Cell Area (Meters Squared):")
            grid_size_x = get_user_float("Grid Size X (m): ")
            grid_size_y = get_user_float("Grid Size Y (m): ")
            grid_lat = get_user_float("Latitude of grid anchor point (dd): ")
            grid_lon = get_user_float("Longitude of grid anchor point (dd): ")
            Prj = get_user_float("Enter CRS code: ")
            # Half of the grid width and height can be added to the central
            # coordinate to create a study area that meets the criteria
            xdiff = grid_size_x / 2
            ydiff = grid_size_y / 2

            xmax = grid_lon + (180 / pi) * (xdiff / 6378137) / cos(grid_lat)
            xmin = grid_lon - (180 / pi) * (xdiff / 6378137) / cos(grid_lat)
            ymax = grid_lat + (180 / pi) * (ydiff / 6378137)
            ymin = grid_lat - (180 / pi) * (ydiff / 6378137)
            area = "POLYGON(({0} {1}, {0} {3}, {2} {3}, {2} {1}, {0} {1}))".format(
                xmin, ymin, xmax, ymax
            )
            area_shply = shapely.wkt.loads(area)
            area_geos = gpd.GeoSeries(area_shply)
            box = area_geos.total_bounds
            edge = math.sqrt(Area**2 / (3 / 2 * math.sqrt(3)))
            hex_centers = create_hexgrid(box, edge)
            hex_centers
            hexagons = []
            for center in hex_centers:
                hexagons.append(create_hexagon(edge, center[0], center[1]))

            planning_unit_grid = gpd.GeoDataFrame(geometry=hexagons, crs=Prj)
            # unique PUID is assigned to each hexagon
            planning_unit_grid["PUID"] = planning_unit_grid.index + 1
            planning_unit_grid.to_file("planning_unit_grid.shp")
            break

        # 9 Return to Main Menu
        elif selection == 9:
            break
        else:
            print_warning_msg(msg_value_error)
            continue
    return planning_unit_grid


# %% Select planning units

# def select_planning_units(planning_unit_grid: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
#     """
#     Author: Ethan

#     Parameters
#     ----------
#     planning_unit_grid : gpd.GeoDataFrame
#         DESCRIPTION.

#     Returns
#     -------
#     TYPE
#         DESCRIPTION.

#     """

#     filtered_planning_unit_grid = planning_unit_grid.copy(deep=True)

#     if planning_unit_grid.empty:
#         print_warning_msg("No planning unit grid loaded.")
#         return planning_unit_grid

#     while True:
#         try:
#             selection = int(
#                 input(
#                     """
#     Select Planning Units
#         1 Manual Input
#         2 Interactive
#         3 Extents from File
#         9 Return to Main Menu
#     >>> """
#                 )
#             )
#         except ValueError:
#             print_warning_msg(msg_value_error)

#         if selection == 1:
#             # 1 Manual Input
#             while True:
#                 try:
#                     selection = int(
#                         input(
#                             """
#     Select Planning Units Manual Input Menu
#         1 Extents
#         2 PUIDS
#         3 Extents from File
#         9 Return to Select Planning Units Menu
#     >>> """
#                         )
#                     )
#                 except ValueError:
#                     print_warning_msg(msg_value_error)

#                 if selection == 1:
#                     # 1 Extents
#                     extent_str = input("Enter extents as xmin ymin xmax ymax: ")
#                     extent = list(map(float, extent_str.split()))

#                     poly = gpd.GeoSeries([{
#                         'type': 'Polygon',
#                         'coordinates': [[
#                             [extent[0], extent[1]],
#                             [extent[2], extent[1]],
#                             [extent[2], extent[3]],
#                             [extent[0], extent[3]],
#                             [extent[0], extent[1]]
#                         ]]
#                     }], crs='epsg:4326')
#                     selected_hexagons = filtered_planning_unit_grid[hexagons.intersects(poly[0])]
#                     break
#                 elif selection == 2:
#                     # 2 PUIDS
#                     userPUID = input("What is the PUID? Type the PUID's and put a space between each one':")
#                     selected_hexagons = hexagons[hexagons.PUID.isin(puids.split(','))]
#                     break
#                 elif selection == 3:
#                     # 3 Extents from File
#                     userShapefile = input("What is the path to the Shapefile?:")
#                     # Find intersecting hexagons
#                     selected_poly = gpd.read_file(userShapefile)
#                     selected_hexagons = hexagons[hexagons.intersects(selected_poly.geometry.unary_union)]
#                     break

#                 elif selection == 9:
#                     # 9 Return to Main Menu
#                     break
#                 else:
#                     print_warning_msg(msg_value_error)
#                     continue

#         elif selection == 2:
#             # 2 Interactive
#             continue
#         elif selection == 3:
#             # 3 Grid from File
#             continue
#         elif selection == 9:
#             # 9 Return to Main Menu
#             break
#         else:
#             print_warning_msg(msg_value_error)
#             continue

#     return filtered_planning_unit_grid


# %% Load planning layers from file


def load_convservation_layers(conserv_layers: list) -> list[gpd.GeoDataFrame]:
    """
    Author: Nata

    Takes user selection to load planning/ conservation layers of interest

    Parameters
    ----------
    conserv_layers : list
        Takes a list of planning layers to load.

    Returns
    -------
    conserv_layers : list[gpd.GeoDataFrame]
        returns a geodataframe of the selected planning layers.

    """
    # get list of files to load
    while True:
        try:
            selection = int(
                input(
                    """
    Load Planning Layers
        1 Select Files
        2 All from Directory
        9 Return to Main Menu
    >>> """
                )
            )
        except ValueError:
            print_warning_msg(msg_value_error)
            continue

        # 1 Select Files
        if selection == 1:
            files = get_files(title="Select planning layer files")
            if files:
                conserv_layers = load_files(files, verbose)
            else:
                print_warning_msg(
                    "No files loaded from directory, please verify files and try again."
                )
                continue
            break

        # 2 All from Directory
        elif selection == 2:
            files = get_files_from_dir()
            if files:
                conserv_layers = load_files(files, verbose)
            else:
                print_warning_msg(
                    "No files loaded from directory, try selecting files manually."
                )
                continue
            break

        # 9 Return to Main Menu
        elif selection == 9:
            break
        else:
            print_warning_msg(msg_value_error)
            continue
    # TODO - add projection to target CRS once target CRS is setup properly
    # projected_layers = []
    # for layer in conserv_layers:
    #     projected_layers.append(layer.to_crs(target_crs))
    return conserv_layers


# %% Filter for specific conservation features


def query_conservation_layers(
    conserv_layers: list[gpd.GeoDataFrame],
) -> list[gpd.GeoDataFrame]:
    """
        Author: Nata

        Takes planning layers and user input on conservation features of interest to select by attribute and save new file

    NOTE this is not fully functional yet, it keeps returning empty files, but is close to solving!

        Parameters
        ----------
        conserv_layers : list[gpd.GeoDataFrame]
            Takes the pre-loaded planning layers file.

        Returns
        -------
        TYPE
            Returns a geodataframe of only the selected conservation features.

    """

    filtered_conserv_layers = []

    if not len(conserv_layers):
        print_warning_msg("No planning layers loaded.")
        return []

    filtered_conserv_layers = []
    for layer in conserv_layers:
        filtered_conserv_layers.append(layer.copy(deep=True))

    while True:
        try:
            selection = int(
                input(
                    """
    Query Planning Layers
        1 ID
        2 CLASS_TYPE
        3 GROUP_
        4 NAME
        9 Return to Main Menu
    >>> """
                )
            )
        # 5 By Area --> Not sure about this one, could produce another menu
        # to get extents from intput, file, or interactive on map, but that
        # may be redundant if we just limits to the bounds of the selected
        # planning units to start with.

        except ValueError:
            print_warning_msg(msg_value_error)
            continue

        if selection == 1:
            # 1 ID
            # then filter by ID
            # make empty list to fill with the unique values in planning layers ID field, to show user
            filter = []
            # loop through the geodataframes to find and save every unique ID value, save to the filter list
            for gdf in conserv_layers:
                filter.extend(gdf["ID"].unique())
            # get user to select ID of interest
            # NOTE this is currently for selection of single features, but will be expanded to multi later
            # filterValues is essentially a list with one value for now
            chosenFeature = get_user_selection(filter)
            # do the filtering - loop through planning layers, keeping rows that match chosenFeature
            for i in range(len(filtered_conserv_layers)):
                # filter by checking if the ID value is in the chosenFeature list
                filtered_conserv_layers[i] = filtered_conserv_layers[i][
                    filtered_conserv_layers[i]["ID"].isin(chosenFeature)
                ]
                # this does not fully work, it keeps returning an empty list of geodataframes, will solve for the next report

            continue
        elif selection == 2:
            # 2 CLASS_TYPE
            # then filter by class type
            # make empty list to fill with the unique values in planning layers CLASS_TYPE field, to show user
            filter = []
            # loop through the geodataframes to find and save every unique CLASS_TYPE value, save to the filter list
            for gdf in conserv_layers:
                filter.extend(gdf["CLASS_TYPE"].unique())
            # get user to select class of interest
            # NOTE this is currently for selection of single features, but will be expanded to multi later
            # filterValues is essentially a list with one value for now
            chosenFeature = get_user_selection(filter)
            # do the filtering - loop through planning layers, keeping rows that match chosenFeature
            for i in range(len(filtered_conserv_layers)):
                # filter by checking if the CLASS_TYPE value is in the chosenFeature list
                filtered_conserv_layers[i] = filtered_conserv_layers[i][
                    filtered_conserv_layers[i]["CLASS_TYPE"].isin(chosenFeature)
                ]
                # this does not fully work, it keeps returning an empty list of geodataframes, will solve for the next report

            continue
        elif selection == 3:
            # 3 GROUP_
            # Then filter by group
            # make empty list to fill with the unique values in planning layers GROUP_ field, to show user
            filter = []
            # loop through the geodataframes to find and save every unique GROUP_ value, save to the filter list
            for gdf in conserv_layers:
                filter.extend(gdf["GROUP_"].unique())
            # get user to select GROUP_ of interest
            # NOTE this is currently for selection of single features, but will be expanded to multi later
            # filterValues is essentially a list with one value for now
            chosenFeature = get_user_selection(filter)
            # do the filtering - loop through planning layers, keeping rows that match chosenFeature
            for i in range(len(filtered_conserv_layers)):
                # filter by checking if the group value is in the chosenFeature list
                filtered_conserv_layers[i] = filtered_conserv_layers[i][
                    filtered_conserv_layers[i]["GROUP_"].isin(chosenFeature)
                ]
                # this does not fully work, it keeps returning an empty list of geodataframes, will solve for the next report
            continue

        elif selection == 4:
            # 3 NAME
            # Then filter by name
            # make empty list to fill with the unique values in planning layers NAME field, to show user
            filter = []
            # loop through the geodataframes to find and save every unique NAME value, save to the filter list
            for gdf in conserv_layers:
                filter.extend(gdf["NAME"].unique())
            # get user to select ID of interest
            # NOTE this is currently for selection of single features, but will be expanded to multi later
            # filterValues is essentially a list with one value for now
            chosenFeature = get_user_selection(filter)
            # do the filtering - loop through planning layers, keeping rows that match chosenFeature
            for i in range(len(filtered_conserv_layers)):
                # filter by checking if the name value is in the chosenFeature list
                filtered_conserv_layers[i] = filtered_conserv_layers[i][
                    filtered_conserv_layers[i]["NAME"].isin(chosenFeature)
                ]
                # this does not fully work, it keeps returning an empty list of geodataframes, will solve for the next report
            continue

        elif selection == 9:
            # 9 Return to Main Menu
            break
        else:
            print_warning_msg(msg_value_error)
            continue

    return filtered_conserv_layers


# %% Calculate planning unit / conservation feature overlap


def calculate(
    planning_grid: gpd.GeoDataFrame, cons_layers: list[gpd.GeoDataFrame]
) -> list[gpd.GeoDataFrame]:
    """
    Author: Mitch Albert
    Target function for processor pool. Intersects planning grid with each conservation layer
    and calculates area of overlap.
    Parameters
    ----------
    planning_grid : gpd.GeoDataFrame
        The planning grid to intersect with conservation layers.
    cons_layers : list[gpd.GeoDataFrame]
        The conservation layers to intersect with the planning grid.

    Returns
    -------
    intersections : list[gpd.GeoDataFrame]
        The planning grid intersected with each conservation layer with an additional
        column containing the area of overlap.

    """
    intersections = []
    for layer in cons_layers:
        if not layer.empty:
            clipped_grid = gpd.clip(
                planning_grid, layer.geometry.convex_hull
            )  # this may not improve performance
            intersection = gpd.overlay(clipped_grid, layer, how="intersection")
            intersection[AMOUNT] = intersection.area
            intersection[AMOUNT] = intersection[AMOUNT].round().astype(int)
            intersections.append(intersection)
        else:
            print_warning_msg("Skipping empty conservation layer.")
    return intersections


def calculate_overlap(
    planning_grid: gpd.GeoDataFrame, cons_layers: list[gpd.GeoDataFrame]
) -> list[gpd.GeoDataFrame]:
    """
    Author: Mitch
    Intersects planning grid with conservation layers and calculates area of overlap.
    Parameters
    ----------
    planning_grid : gpd.GeoDataFrame
        The planning grid to intersect with conservation layers.
    cons_layers : list[gpd.GeoDataFrame]
        A list of conservation layers containing only the desired conservation features
        to intersect with the planning grid.

    Returns
    -------
    list[gpd.GeoDataFrame] | list[]
        The intersected gdfs, or an empty list if planning grid or conservation layers are not loaded,
        or if there are no intersecting features.

    """
    # TODO: check if planning grid and conservation layer are in same CRS

    # check if planning grid and conservation layers are loaded, otherwise return empty list
    if not len(cons_layers):
        print_warning_msg("No conservation feature layers loaded.")
        return []
    if planning_grid.empty:
        print_warning_msg("No planning unit grid loaded.")
        return []

    # split planning grid into chunks to be processed by each core
    planning_grid_divisions = np.array_split(planning_grid, CORES)

    # define partial function to pass to pool, this enables passing multiple arguments to calculate() from the pool
    # otherwise we would have to pass a tuple of arguments
    calc_overlap_partial = partial(calculate, cons_layers=cons_layers)

    # this will hold the results of the pool
    intersections = []

    if verbose:
        print_info(f"Starting intersection calculations with {CORES} cores")
        progress = print_progress_start("Calculating intersections", dots=10, time=1)
    # start timer
    start_time = time()
    # Create a Pool object with the number of cores specified in CORES
    with Pool(CORES) as pool:
        # Iterate through the planning_grid_divisions and apply the calc_overlap_partial function to each element
        for result in pool.imap_unordered(
            calc_overlap_partial, planning_grid_divisions
        ):
            intersections.extend(result)

    if verbose:
        print_progress_stop(progress)
        print_info_complete(
            f"Intersection calculations completed in: {(time() - start_time):.2f} seconds"
        )

    return intersections


# %% CRS helper function


def validate_crs(crs: any, target_crs: str) -> bool:
    """
    Author: Winaa

    Parameters
    ----------
    crs : any
        DESCRIPTION.
    target_crs : str
        DESCRIPTION.

    Returns
    -------
    bool
        DESCRIPTION.

    """
    return


def plot_layers(
    planning_unit_grid: gpd.GeoDataFrame,
    conserv_layers: list[gpd.GeoDataFrame],
    filtered_conserv_layers: list[gpd.GeoDataFrame],
):
    """
    Author: Mitch Albert
    Displays the view layers menu and allows the user to select which layers to plot.

    Parameters
    ----------
    planning_unit_grid : gpd.GeoDataFrame
        The planning unit grid.
    conserv_layers : list[gpd.GeoDataFrame]
        The conservation feature layers without filtering.
    filtered_conserv_layers : list[gpd.GeoDataFrame]
        The selected conservation features after filtering.

    Returns
    -------
    None.

    """

    def plot(layers: list[gpd.GeoDataFrame]):
        """
        Author: Mitch Albert
        Internal function to plot the layers. This is called by the view layers menu.
        Only acceps a list of geodataframes and loops through them plotting each one.

        Parameters
        ----------
        layers : list[gpd.GeoDataFrame]
            The list of geodataframes to plot.

        Returns
        -------
        None.

        """
        if len(layers):
            try:
                if verbose:
                    progress = print_progress_start("Plotting", dots=3)
                for layer in layers:
                    if layer.empty:
                        print_warning_msg("Nothing to plot.")
                        continue
                    layer.plot()
                    plt.show()
            except Exception as e:
                print_warning_msg(f"Error while plotting\n")
                print(e)
            finally:
                if verbose:
                    print_progress_stop(progress)
        else:
            print_warning_msg("Nothing plot.")
        return

    while True:
        try:
            selection = int(
                input(
                    """
    View Layers Menu:
        1 Planning Unit Grid
        2 Conservation Features Files
        3 Filtered Conservation Features
        9 Return to Main Menu
    >>> """
                )
            )
        except ValueError:
            print_warning_msg(msg_value_error)
            continue

        # 1 Planning Unit Grid
        if selection == 1:
            print_info("Plotting Planning Unit Grid...")
            plot([] if planning_unit_grid.empty else [planning_unit_grid])
            continue

        # 2 All Conservation Features Files
        elif selection == 2:
            print_info("Plotting Conservation Features...")
            plot(conserv_layers)
            continue

        # 3 Filtered Conservation Features
        elif selection == 3:
            print_info("Plotting Filtered Conservation Features...")
            plot(filtered_conserv_layers)
            continue

        # 9 Return to Main Menu
        elif selection == 9:
            break

        else:
            print_warning_msg(msg_value_error)
            continue
    return


# %% Main


def main():
    """
    Author: Mitch
    Main function. Calls main_menu() and runs until user enters 9 to exit.
    """

    def main_menu():
        """
        Author: Mitch
        Prints main menu and returns user selection. If user selection is not
        valid, will print error message and return to main menu. If user
        enters 9, the program will exit. Otherwise calls appropriate function based
        on user selection.

        Returns
        -------
        None.

        """
        # intialize variables
        planning_unit_grid = gpd.GeoDataFrame()  # planning unit grid
        filtered_planning_unit_grid = (
            gpd.GeoDataFrame()
        )  # this is the planning unit grid after filtering, now obsolete
        conserv_layers = (
            []
        )  # list of planning layers gdfs, name will change to conservation_features
        filtered_conserv_layers = (
            []
        )  # this is list of conservation_features gdfs after filtering
        intersections_gdf = (
            []
        )  # list of gdfs of planning unit / conservation feature intersections
        intersections_df = (
            pd.DataFrame()
        )  # dataframe of planning unit / conservation feature intersections, used to easy csv export

        # target_crs = get_crs()

        while True:
            try:
                selection = int(
                    input(
                        """
    Main Menu:
        1 Create Planning Unit Grid
        2 Select Planning Units
        3 Load Conservation Features Files
        4 Select Conservation Features
        5 View Layers
        6 Calculate Overlap
        7 Save Results
        9 Quit
    >>> """
                    )
                )
            except ValueError:
                print_warning_msg(msg_value_error)
                continue

            # 1 Create Planning Unit GridFeatures
            if selection == 1:
                planning_unit_grid = create_planning_unit_grid()
                continue

            # 2 Select Planning Units
            elif selection == 2:
                # NOTE: this is now obsolete, but only commenting out for now
                # filtered_planning_unit_grid = select_planning_units(planning_unit_grid)
                continue

            # 3 Load Conservation Features Files
            elif selection == 3:
                conserv_layers = load_convservation_layers(conserv_layers)
                continue

            # 4 Select conservation features
            elif selection == 4:
                filtered_conserv_layers = query_conservation_layers(conserv_layers)
                continue

            # 5 View Layers
            elif selection == 5:
                plot_layers(planning_unit_grid, conserv_layers, filtered_conserv_layers)
                continue

            # 6 Calculate Overlap
            elif selection == 6:
                # TODO: update to remove filtered_planning_unit_grid
                # intersections_gdf = calc_overlap(
                #     filtered_planning_unit_grid, filtered_conserv_layers
                # )
                intersections_gdf = calculate_overlap(
                    planning_unit_grid, conserv_layers
                )

                if len(intersections_gdf):
                    intersections_df = pd.DataFrame(
                        gpd.GeoDataFrame(
                            pd.concat(intersections_gdf, ignore_index=True)
                        )
                    )
                # intersections_df.sort_values(PUID, ascending=True, inplace=True)
                continue

            # 7 Save Results
            elif selection == 7:
                # TODO: add saving of planning unit grid
                if intersections_df.empty:
                    print_warning_msg("No results to save.")
                    continue
                file_name = get_save_file_name(
                    title="Save results to csv", f_types=ft_csv
                )
                # Columns names / order need to be updated to match sample file from client, waiting to receive
                intersections_df.to_csv(
                    file_name,
                    header=[SPECIES, PU, AMOUNT],
                    columns=[ID, PUID, AMOUNT],
                    index=False,
                )
                continue

            # 9 Quit
            elif selection == 9:
                # TODO: add confirmation prompt if user has not saved results
                break

            else:
                print_warning_msg(msg_value_error)
            continue
        return

    main_menu()

    print_info_complete("All done!")

    return


if __name__ == "__main__":
    if run_tests:
        input("\nTESTING COMPLETE")
    else:
        main()

# %%
