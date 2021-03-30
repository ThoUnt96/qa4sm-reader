from qa4sm_reader.img import QA4SMImg
from qa4sm_reader.plot_utils import diff_plot, mapplot, boxplot, plot_spatial_extent
from qa4sm_reader.handlers import QA4SMDatasets, QA4SMMetricVariable, QA4SMMetric
import qa4sm_reader.globals as glob

from shapely.geometry import Polygon
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy import stats

import warnings as warn


class QA4SMComparison():  #todo: optimize initialization (slow with large gridded files)
    """
    Class that provides comparison plots and table for a list of netCDF files. As initialising a QA4SMImage can
    take some time, the class can be updated keeping memory of what has already been initialized
    """
    def __init__(self, paths:list, extent:tuple=None, get_intersection:bool=True):
        """
        Initialise the QA4SMImages from the paths to netCDF files specified

        Parameters
        ----------
        paths : list
            list of paths to .nc validation results files to use for the comparison
        extent : tuple, optional (default: None)
            Area to subset the values for.
            (min_lon, max_lon, min_lat, max_lat)

        Attributes
        ----------
        comparison : dict
            dictionary with shape {path: (id, QA4SMImage)}
        ref : tuple
            QA4SMImage for the reference validation
        """
        self.paths = paths
        self.extent = extent

        self.comparison = self._init_imgs(extent=extent, get_intersection=get_intersection)
        self.ref = self._check_ref()

    def _init_imgs(self, extent=None, get_intersection=True) -> dict:
        """
        Initialize the QA4SMImages for the selected validation results files. If 'extent' is specified, this is used. If
        not, by default the intersection of results is taken and the images are initialized with it, unless 'get_union'
        is specified. In this case, only diff_table and diff_boxplots can be created (as only non-pairwise methods).

        Returns
        -------
        extent: tuple, optional. Default is None
            exent of stapial subset
        get_intersection : bool, optional. Default is True.
            if extent is not specified, we can either take the union or intersection of the original extents of the
            passed .nc files. This affects the diff_table and diff_boxplot methods, whereas the diff_corr, diff_mapplot
            and diff_plot ALWAYS consider the intersection.
        """
        comparison = {}
        imgs = []
        if extent:
            try:
                for n, path in enumerate(self.paths):
                    img = QA4SMImg(path, extent=extent)
                    imgs.append(img)
                    assert path not in comparison.keys(), "You are initializing the same validation twice"
                    comparison[path] = (n, img)

            except AssertionError as e:
                e.message = "One of the initialised validation result files has no points in the given spatial subset:" \
                            "{}. \nYou should change subset to a valid one, or not pass any.".format(extent)
                raise e
        else:
            self.union = True  # save the state 'union' or 'intersection' to a class attribute
            if get_intersection:
                extent = self.get_extent(get_intersection=get_intersection)
                self.extent = extent
                self.union = False

            for n, path in enumerate(self.paths):
                img = QA4SMImg(path, extent=extent)
                imgs.append(img)
                assert path not in comparison.keys(), "You are initializing the same validation twice"
                comparison[path] = (n, img)

        return comparison

    def init_union(self):
        """Re-initialize the images using the union of spatial extents"""
        self.comparison = self._init_imgs(extent=None, get_intersection=False)
        # make sure the new state is stored in the class attribute
        assert self.union

    def _check_ref(self) -> str:  # todo: should it work with different versions?
        """ Check that all initialized validation results have the same dataset as reference """
        for id, img in self.comparison.values():
            ref = img.datasets.ref
            if id != 0:
                assert ref == previous, "The initialized validation results have different reference datasets. " \
                                        "This is currently not supported"
            previous = ref

        return ref

    @property
    def overlapping(self) -> bool:
        """Return True if the initialised validation results have overlapping spatial extents, else False"""
        polys = {}
        for id, img in self.comparison.values():  # get names and extents for all images
            minlon, maxlon, minlat, maxlat = img.extent
            bounds = [(minlon,minlat), (maxlon, minlat),
                      (maxlon, maxlat), (minlon, maxlat)]
            Pol = Polygon(bounds)
            name = "{}: ".format(id) + img.name
            polys[name] = Pol

        for n, Pol in enumerate(polys.values()):
            if n == 0:
                output = Pol  # define starting point
            output = output.intersection(Pol)

        return output.bounds != ()

    def _check_initialized(self, paths:str or list):
        """
        Check that the given path has been initialized in the class

        Parameters
        ----------
        paths: str or list
            path(s) to be checked

        Raise
        -----
        KeyError : if path has not been initialized
        """
        hasnot = False
        if isinstance(paths, list):
            for path in paths:
                if not path in self.comparison.keys():
                    hasnot = True
                    break

        elif paths not in self.comparison.keys():
            path = paths
            hasnot = True

        if hasnot:
            raise KeyError ("The path {} has not been initialized in the QA4SMComparison class".format(path))

    def _check_pairwise(self):
        """
        Checks that the current initialized supports pairwise comparison methods

        Raise
        -----
        ComparisonException : if not
        """
        pairwise = True
        if len(list(self.comparison.keys())) > 2:
            pairwise = False

        else:
            for id, img in self.comparison.values():
                if img.datasets.n_datasets() > 2:
                    pairwise = False

        assert pairwise, "For pairwise comparison methods, only two validation " \
                         "results with two datasets each can be compared"

    @staticmethod
    def _combine_geometry(imgs:list, get_intersection:bool=True, visualize=False) -> tuple:
        """
        Return the union or the intersection of the spatial extents of the provided validations; in case of intersection,
        check that the validations are overlapping

        Parameters
        ----------
        imgs : list
            list with the QA4SMImg corresponding to the paths
        get_intersection : bool, optional. Default is True.
            if extent is not specified, we can either take the union or intersection of the original extents of the
            passed .nc files. This affects the diff_table and diff_boxplot methods, whereas the diff_corr, diff_mapplot
            and diff_plot ALWAYS consider the intersection.
        visualize: bool, optional. Default is False.
            If true, an image is produced to visualize the output

        Return
        ------
        extent: tuple
            spatial extent deriving from union or intersection of inputs
        """
        polys = {}
        for n, img in enumerate(imgs):  # get names and extents for all images
            minlon, maxlon, minlat, maxlat = img.extent
            bounds = [(minlon,minlat), (maxlon, minlat),
                      (maxlon, maxlat), (minlon, maxlat)]
            Pol = Polygon(bounds)
            name = "{}: ".format(n) + img.name
            polys[name] = Pol

        for n, Pol in enumerate(polys.values()):
            if n == 0:
                output = Pol  # define starting point
            if not get_intersection:  # get maximum extent
                output = output.union(Pol)
                where = "Union"
            else:  # get maximum common
                output = output.intersection(Pol)
                where = "Intersection"
                assert output, "The spatial extents of the chosen validation results do not overlap. " \
                               "Set 'get_intersection' to False to perform the comparison."
        name = '{} of the spatial subsets'.format(where)
        polys[name] = output

        minlon, minlat, maxlon, maxlat = output.bounds

        if visualize:
            title = "Spatial extent of the {} of the given validations".format(where)
            plot_spatial_extent(polys, output=name, title=title)

        return minlon, maxlon, minlat, maxlat

    def get_extent(self, get_intersection=True, visualize=False):
        """
        Method to get and visualize the output of 'union' or 'intersection' of the spatial extents.

        Parameters
        ----------
        get_intersection : bool, optional. Default is True.
            if extent is not specified, we can either take the union or intersection of the original extents of the
            passed .nc files. This affects the diff_table and diff_boxplot methods, whereas the diff_corr, diff_mapplot
            and diff_plot ALWAYS consider the intersection.
        visualize : bool, default is False
            create an image showing the output of this method
        """
        imgs = []
        for n, path in enumerate(self.paths):
            img = QA4SMImg(path, extent=None, load_data=False)
            imgs.append(img)

        return self._combine_geometry(imgs=imgs,
                                      get_intersection=get_intersection,
                                      visualize=visualize)

    def _get_pairwise(self, metric:str) -> (list, list):
        """
        Get the data and names for pairwise comparisons, meaning: two validations with one satellite dataset each

        Parameters
        ----------
        metric: str
            name of metric to get data on
        """
        to_plot, names, ids = [], [], []
        for id, img in self.comparison.values():
            ids.append(id)
            Var = img.group_vars(**{'metric':metric})[0]
            # below necessary to workaround identical variable names
            names.append("{}: ".format(id) + Var.pretty_name)
            df = Var.values
            to_plot.append(df)

        # if lon, lat in index are the same (e.g. multiple points in same ISMN station), needs workaround
        boxplot_df = to_plot[0].join(to_plot[1],
                                     how='outer',
                                     lsuffix='_caller',
                                     rsuffix='_other')
        boxplot_df.columns = names
        diff_name = 'Difference between {} and {}'.format(*ids[::-1])
        boxplot_df[diff_name] = boxplot_df.iloc[:,1] - boxplot_df.iloc[:,0]

        return boxplot_df

    def perform_checks(self, overlapping=False, union=False, pairwise=False):
        """Performs selected checks and throws error is they're not passed"""
        if overlapping:
            assert self.overlapping, "This method works only in case the initialized validations " \
                                     "have overlapping spatial extents."
        if not self.extent and union:
            assert not self.union, "If the comparison is based on the 'union' of spatial extents, this method " \
                                   "cannot be called, as it is based on a point-by-point comparison"
        if pairwise:
            self._check_pairwise() # todo: handle other cases

    def diff_table(self, **kwargs) -> pd.DataFrame:
        """
        Create a table where all the metrics for the different validation runs are compared
        """
        self.perform_checks(pairwise=True)

        medians, names, ids = [], [], []
        for id, img in self.comparison.values():
            ids.append(id)
            median = img.stats_df()['Median']
            medians.append(median)
            names.append("Medians for {}: {}".format(id, img.name))

        table = pd.concat(medians, axis=1)
        table.columns = names
        diff_name = 'Difference of medians ({} - {})'.format(*ids[::-1])
        table[diff_name] = table.iloc[:,1] - table.iloc[:,0]

        return table

    def diff_boxplot(self, metric:str, **kwargs):
        """
        Create a boxplot where two validations are compared. If the comparison is on the subsets union, then the
        difference is not shown.

        metric: str
            metric from the .nc result file attributes that the plot is based on
        """
        self.perform_checks(pairwise=True)
        # prepare data
        boxplot_df = self._get_pairwise(metric=metric)
        # prepare axis name
        Metric = QA4SMMetric(metric)
        ref_ds = self.ref['short_name']
        um = glob._metric_description[metric].format(glob._metric_units[ref_ds])

        # plot data
        palette = sns.color_palette(palette=['paleturquoise', 'paleturquoise', 'pink'], n_colors=3)
        if self.union:
            palette = sns.color_palette(palette=['paleturquoise', 'paleturquoise'], n_colors=2)
            boxplot_df = boxplot_df.drop(columns=boxplot_df.columns[-1])
        fig, axes = boxplot(boxplot_df,
                            label= "{} {}".format(Metric.pretty_name, um),
                            figsize=(16,10),
                            **{'palette':palette})
        title_plot = "Boxplot comparison of {} {}".format(Metric.pretty_name, um)
        axes.set_title(title_plot, pad=glob.title_pad)

    def diff_plot(self, metric:str, **kwargs):
        """
        Create a Bland Altman plot where two validations are compared

        Parameters
        ----------
        metric: str
            metric from the .nc result file attributes that the plot is based on
        **kwargs : kwargs
            plotting keyword arguments
        """
        self.perform_checks(overlapping=True, union=True, pairwise=True)

        # get data and names
        df = self._get_pairwise(metric=metric).dropna()

        fig, axes = diff_plot(df)
        # get unit measures
        ref_name = self.ref['short_name']
        um = glob._metric_description[metric].format(glob._metric_units[ref_name])
        # set figure title
        Metric = QA4SMMetric(metric)
        title_plot = "Difference plot of {} {}".format(Metric.pretty_name, um)
        axes.set_title(title_plot, pad=glob.title_pad)

    def corr_plot(self, metric:str, **sns_kwargs):  #todo: colouring based on metadata
        """
        Correlation plot between two validation results, for a metric

        Parameters
        ----------
        metric: str
            metric from the .nc result file attributes that the plot is based on
        **sns_kwargs : kwargs
            plotting keyword arguments
        """
        self.perform_checks(overlapping=True, union=True, pairwise=True)

        # get data and names
        corrplot_df = self._get_pairwise(metric=metric).dropna()
        # get names right
        Metric = QA4SMMetric(metric)
        ref_ds = self.ref['short_name']
        um = glob._metric_description[metric].format(glob._metric_units[ref_ds])
        # plot regression
        slope, int, r, p, sterr = stats.linregress(corrplot_df.iloc[:,0], corrplot_df.iloc[:,1])
        fig, axes = plt.subplots(figsize=(16,10))
        ax = sns.regplot(x=corrplot_df.iloc[:, 0],
                         y=corrplot_df.iloc[:, 1],
                         label="Validation point",
                         line_kws={'label':"x ={}*y + {}, r: {}, p: {}".format(
                             *[round(i,2) for i in [slope, int, r, p]])},
                         **sns_kwargs)
        title_plot = "Correlation plot of {} {}".format(Metric.pretty_name, um)
        axes.set_title(title_plot, pad=glob.title_pad)
        plt.legend()

    def diff_mapplot(self, metric:str, diff_range:str='adjusted', **kwargs):
        """
        Create a pairwise mapplot of the difference between the validations, for a metric. Difference is other - reference

        Parameters
        ----------
        metric: str
            metric from the .nc result file attributes that the plot is based on
        diff_range: str, default is 'adjusted'
            if 'adjusted', colorbar goues from minimum to maximum of difference; if 'fixed', the colorbar goes from the
            maximum to the minimum difference range, by metric
        **kwargs : kwargs
            plotting keyword arguments
        """
        self.perform_checks(overlapping=True, union=True, pairwise=True)

        df_diff = self._get_pairwise(metric=metric).dropna()
        Metric = QA4SMMetric(metric)
        um = glob._metric_description[metric].format(glob._metric_units[self.ref['short_name']])
        # make mapplot
        cbar_label = "Difference between {} and {}".format(*df_diff.columns)
        fig, axes = mapplot(df_diff.iloc[:,2],
                            metric,
                            self.ref['short_name'],
                            diff_range=diff_range,
                            label=cbar_label)
        title_plot = "Overview of the difference of {} {}".format(Metric.pretty_name, um)
        axes.set_title(title_plot, pad=glob.title_pad)

    def diff_methods(self, method:str):
        """
        Return the difference function from a lookup table

        Parameters
        ----------
        method: str
            method linked to function
        """
        try:
            diff_methods_lut = {'table': self.diff_table,
                                'boxplot': self.diff_boxplot,
                                'correlation': self.corr_plot,
                                'difference': self.diff_plot,
                                'mapplot': self.diff_mapplot}
        except IndexError as e:
            warn('Difference method not valid. Choose one of %s' % ', '.join(diff_methods_lut.keys()))
            raise e

        return diff_methods_lut[method]

    def wrapper(self, method:str, metric:str, **kwargs):
        """
        Call the method using a list of paths and the already initialised images

        Properties
        ----------
        method: str
            a method from the lookup table in diff_method
        metric: str
            metric from the .nc result file attributes that the plot is based on
        **kwargs : kwargs
            plotting keyword arguments
        """
        diff_funct = self.diff_methods(method)
        output = diff_funct(metric=metric, **kwargs)

        return output

paths = ['/home/pstradio/Projects/qa4sm-reader/docs/examples/example_data/validations_nc/0-C3S.sm_with_1-GLDAS.SoilMoi0_10cm_inst.nc',
         '/home/pstradio/Projects/qa4sm-reader/docs/examples/example_data/validations_nc/0-C3S.sm_with_1-GLDAS.SoilMoi40_100cm_inst.nc']

comp = QA4SMComparison(paths)
