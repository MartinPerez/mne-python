"""Base class copy from sklearn.base."""
# Authors: Gael Varoquaux <gael.varoquaux@normalesup.org>
#          Romain Trachel <trachelr@gmail.com>
#          Alexandre Gramfort <alexandre.gramfort@telecom-paristech.fr>
#
# License: BSD (3-clause)

import warnings
import numpy as np

from ..externals.six import iteritems
from ..fixes import _get_args
from ..utils import check_version


class BaseEstimator(object):
    """Base class for all estimators in scikit-learn.

    Notes
    -----
    All estimators should specify all the parameters that can be set
    at the class level in their ``__init__`` as explicit keyword
    arguments (no ``*args`` or ``**kwargs``).
    """

    @classmethod
    def _get_param_names(cls):
        """Get parameter names for the estimator."""
        # fetch the constructor or the original constructor before
        # deprecation wrapping if any
        init = getattr(cls.__init__, 'deprecated_original', cls.__init__)
        if init is object.__init__:
            # No explicit constructor to introspect
            return []

        # introspect the constructor arguments to find the model parameters
        # to represent
        args, varargs = _get_args(init, varargs=True)
        if varargs is not None:
            raise RuntimeError("scikit-learn estimators should always "
                               "specify their parameters in the signature"
                               " of their __init__ (no varargs)."
                               " %s doesn't follow this convention."
                               % (cls, ))
        # Remove 'self'
        # XXX: This is going to fail if the init is a staticmethod, but
        # who would do this?
        args.pop(0)
        args.sort()
        return args

    def get_params(self, deep=True):
        """Get parameters for this estimator.

        Parameters
        ----------
        deep : boolean, optional
            If True, will return the parameters for this estimator and
            contained subobjects that are estimators.

        Returns
        -------
        params : mapping of string to any
            Parameter names mapped to their values.
        """
        out = dict()
        for key in self._get_param_names():
            # We need deprecation warnings to always be on in order to
            # catch deprecated param values.
            # This is set in utils/__init__.py but it gets overwritten
            # when running under python3 somehow.
            warnings.simplefilter("always", DeprecationWarning)
            try:
                with warnings.catch_warnings(record=True) as w:
                    value = getattr(self, key, None)
                if len(w) and w[0].category == DeprecationWarning:
                    # if the parameter is deprecated, don't show it
                    continue
            finally:
                warnings.filters.pop(0)

            # XXX: should we rather test if instance of estimator?
            if deep and hasattr(value, 'get_params'):
                deep_items = value.get_params().items()
                out.update((key + '__' + k, val) for k, val in deep_items)
            out[key] = value
        return out

    def set_params(self, **params):
        """Set the parameters of this estimator.

        The method works on simple estimators as well as on nested objects
        (such as pipelines). The former have parameters of the form
        ``<component>__<parameter>`` so that it's possible to update each
        component of a nested object.
        Returns
        -------
        self
        """
        if not params:
            # Simple optimisation to gain speed (inspect is slow)
            return self
        valid_params = self.get_params(deep=True)
        for key, value in iteritems(params):
            split = key.split('__', 1)
            if len(split) > 1:
                # nested objects case
                name, sub_name = split
                if name not in valid_params:
                    raise ValueError('Invalid parameter %s for estimator %s. '
                                     'Check the list of available parameters '
                                     'with `estimator.get_params().keys()`.' %
                                     (name, self))
                sub_object = valid_params[name]
                sub_object.set_params(**{sub_name: value})
            else:
                # simple objects case
                if key not in valid_params:
                    raise ValueError('Invalid parameter %s for estimator %s. '
                                     'Check the list of available parameters '
                                     'with `estimator.get_params().keys()`.' %
                                     (key, self.__class__.__name__))
                setattr(self, key, value)
        return self

    def __repr__(self):  # noqa: D105
        class_name = self.__class__.__name__
        return '%s(%s)' % (class_name, _pprint(self.get_params(deep=False),
                                               offset=len(class_name),),)


###############################################################################
def _pprint(params, offset=0, printer=repr):
    """Pretty print the dictionary 'params'.

    Parameters
    ----------
    params: dict
        The dictionary to pretty print
    offset: int
        The offset in characters to add at the beginning of each line.
    printer:
        The function to convert entries to strings, typically
        the builtin str or repr

    Returns
    -------
    out : str
        The string.
    """
    # Do a multi-line justified repr:
    options = np.get_printoptions()
    np.set_printoptions(precision=5, threshold=64, edgeitems=2)
    params_list = list()
    this_line_length = offset
    line_sep = ',\n' + (1 + offset // 2) * ' '
    for i, (k, v) in enumerate(sorted(iteritems(params))):
        if type(v) is float:
            # use str for representing floating point numbers
            # this way we get consistent representation across
            # architectures and versions.
            this_repr = '%s=%s' % (k, str(v))
        else:
            # use repr of the rest
            this_repr = '%s=%s' % (k, printer(v))
        if len(this_repr) > 500:
            this_repr = this_repr[:300] + '...' + this_repr[-100:]
        if i > 0:
            if (this_line_length + len(this_repr) >= 75 or '\n' in this_repr):
                params_list.append(line_sep)
                this_line_length = len(line_sep)
            else:
                params_list.append(', ')
                this_line_length += 2
        params_list.append(this_repr)
        this_line_length += len(this_repr)

    np.set_printoptions(**options)
    lines = ''.join(params_list)
    # Strip trailing space to avoid nightmare in doctests
    lines = '\n'.join(l.rstrip(' ') for l in lines.split('\n'))
    return lines


class LinearModel(BaseEstimator):
    """Clone a Linear Model from sklearn and update attributes for each fit.

    The linear model coefficients
    (filters) are used to extract discriminant neural sources from
    the measured data. This class implements the computation of patterns
    which provides neurophysiologically interpretable information [1]_,
    in the sense that significant nonzero weights are only observed at channels
    where activity is related to discriminant neural sources.

    Parameters
    ----------
    model : object | None
        A linear model from scikit-learn with a fit method
        that updates a ``coef_`` attribute.
        If None the model will be LogisticRegression.

    Attributes
    ----------
    ``filters_`` : ndarray
        If fit, the filters used to decompose the data, else None.
    ``patterns_`` : ndarray
        If fit, the patterns used to restore M/EEG signals, else None.

    Notes
    -----
    .. versionadded:: 0.10

    See Also
    --------
    CSP
    mne.preprocessing.ICA
    mne.preprocessing.Xdawn

    References
    ----------
    .. [1] Haufe, S., Meinecke, F., Gorgen, K., Dahne, S., Haynes, J.-D.,
           Blankertz, B., & Biebmann, F. (2014). On the interpretation of
           weight vectors of linear models in multivariate neuroimaging.
           NeuroImage, 87, 96-110.
    """

    def __init__(self, model=None):  # noqa: D102
        if model is None:
            from sklearn.linear_model import LogisticRegression
            model = LogisticRegression()

        self.model = model
        self.patterns_ = None
        self.filters_ = None

    def fit(self, X, y):
        """Estimate the coefficients of the linear model.

        Save the coefficients in the attribute ``filters_`` and
        computes the attribute ``patterns_``.

        Parameters
        ----------
        X : array, shape (n_epochs, n_features)
            The data to estimate the coeffiscient.
        y : array, shape (n_epochs,)
            The class for each epoch.

        Returns
        -------
        self : instance of LinearModel
            Returns the modified instance.
        """
        # fit the Model
        self.model.fit(X, y)
        # computes the patterns
        assert hasattr(self.model, 'coef_'), \
            "model needs a coef_ attribute to compute the patterns"
        self.patterns_ = np.dot(X.T, np.dot(X, self.model.coef_.T))
        self.filters_ = self.model.coef_

        return self

    def transform(self, X, y=None):
        """Transform the data using the linear model.

        Parameters
        ----------
        X : array, shape (n_epochs, n_features)
            The data to transform.
        y : array, shape (n_epochs,)
            The class for each epoch.

        Returns
        -------
        y_pred : array, shape (n_epochs,)
            Predicted class label per epoch.

        """
        return self.model.transform(X)

    def fit_transform(self, X, y):
        """Fit the data and transform it using the linear model.

        Parameters
        ----------
        X : array, shape (n_epochs, n_features)
            The data to transform.
        y : array, shape (n_epochs,)
            The class for each epoch.

        Returns
        -------
        y_pred : array, shape (n_epochs,)
            Predicted class label per epoch.

        """
        return self.fit(X, y).transform(X)

    def predict(self, X):
        """Compute predictions of y from X.

        Parameters
        ----------
        X : array, shape (n_epochs, n_features)
            The data used to compute the predictions.

        Returns
        -------
        y_pred : array, shape (n_epochs,)
            The predictions.
        """
        return self.model.predict(X)

    def score(self, X, y):
        """Score the linear model computed on the given test data.

        Parameters
        ----------
        X : array, shape (n_epochs, n_features)
            The data to transform.
        y : array, shape (n_epochs,)
            The class for each epoch.

        Returns
        -------
        score : float
            Score of the linear model
        """
        return self.model.score(X, y)

    def plot_patterns(self, info, times=None, ch_type=None, layout=None,
                      vmin=None, vmax=None, cmap='RdBu_r', sensors=True,
                      colorbar=True, scale=None, scale_time=1e3, unit='a.u.',
                      res=64, size=1, cbar_fmt='%3.1f',
                      name_format='%01d ms', proj=False, show=True,
                      show_names=False, title=None, mask=None,
                      mask_params=None, outlines='head', contours=6,
                      image_interp='bilinear', average=None, head_pos=None):
        """Plot topographic patterns of the linear model.

        The patterns explain how the measured data was generated
        from the neural sources (a.k.a. the forward model).

        Parameters
        ----------
        info : instance of Info
            Info dictionary of the epochs used to fit the linear model.
            If not possible, consider using ``create_info``.
        times : float | array of floats | None.
            The time point(s) to plot. If None, the number of ``axes``
            determines the amount of time point(s). If ``axes`` is also None,
            10 topographies will be shown with a regular time spacing between
            the first and last time instant.
        ch_type : 'mag' | 'grad' | 'planar1' | 'planar2' | 'eeg' | None
            The channel type to plot. For 'grad', the gradiometers are
            collected in pairs and the RMS for each pair is plotted.
            If None, then first available channel type from order given
            above is used. Defaults to None.
        layout : None | Layout
            Layout instance specifying sensor positions (does not need to be
            specified for Neuromag data). If possible, the correct layout file
            is inferred from the data; if no appropriate layout file was found
            the layout is automatically generated from the sensor locations.
        vmin : float | callable
            The value specfying the lower bound of the color range.
            If None, and vmax is None, -vmax is used. Else np.min(data).
            If callable, the output equals vmin(data).
        vmax : float | callable
            The value specfying the upper bound of the color range.
            If None, the maximum absolute value is used. If vmin is None,
            but vmax is not, defaults to np.min(data).
            If callable, the output equals vmax(data).
        cmap : matplotlib colormap | (colormap, bool) | 'interactive' | None
            Colormap to use. If tuple, the first value indicates the colormap
            to use and the second value is a boolean defining interactivity. In
            interactive mode the colors are adjustable by clicking and dragging
            the colorbar with left and right mouse button. Left mouse button
            moves the scale up and down and right mouse button adjusts the
            range. Hitting space bar resets the range. Up and down arrows can
            be used to change the colormap. If None, 'Reds' is used for all
            positive data, otherwise defaults to 'RdBu_r'. If 'interactive',
            translates to (None, True). Defaults to 'RdBu_r'.

            .. warning::  Interactive mode works smoothly only for a small
                amount of topomaps.

        sensors : bool | str
            Add markers for sensor locations to the plot. Accepts matplotlib
            plot format string (e.g., 'r+' for red plusses). If True,
            a circle will be used (via .add_artist). Defaults to True.
        colorbar : bool
            Plot a colorbar.
        scale : dict | float | None
            Scale the data for plotting. If None, defaults to 1e6 for eeg, 1e13
            for grad and 1e15 for mag.
        scale_time : float | None
            Scale the time labels. Defaults to 1e3.
        unit : dict | str | None
            The unit of the channel type used for colorbar label. If
            scale is None the unit is automatically determined.
        res : int
            The resolution of the topomap image (n pixels along each side).
        size : float
            Side length per topomap in inches.
        cbar_fmt : str
            String format for colorbar values.
        name_format : str
            String format for topomap values. Defaults to "%03f ms"
        proj : bool | 'interactive'
            If true SSP projections are applied before display.
            If 'interactive', a check box for reversible selection
            of SSP projection vectors will be show.
        show : bool
            Show figure if True.
        show_names : bool | callable
            If True, show channel names on top of the map. If a callable is
            passed, channel names will be formatted using the callable; e.g.,
            to delete the prefix 'MEG ' from all channel names, pass the
            function lambda x: x.replace('MEG ', ''). If `mask` is not None,
            only significant sensors will be shown.
        title : str | None
            Title. If None (default), no title is displayed.
        mask : ndarray of bool, shape (n_channels, n_times) | None
            The channels to be marked as significant at a given time point.
            Indices set to `True` will be considered. Defaults to None.
        mask_params : dict | None
            Additional plotting parameters for plotting significant sensors.
            Default (None) equals::

                dict(marker='o', markerfacecolor='w', markeredgecolor='k',
                     linewidth=0, markersize=4)

        outlines : 'head' | 'skirt' | dict | None
            The outlines to be drawn. If 'head', the default head scheme will
            be drawn. If 'skirt' the head scheme will be drawn, but sensors are
            allowed to be plotted outside of the head circle. If dict, each key
            refers to a tuple of x and y positions, the values in 'mask_pos'
            will serve as image mask, and the 'autoshrink' (bool) field will
            trigger automated shrinking of the positions due to points outside
            the outline. Alternatively, a matplotlib patch object can be passed
            for advanced masking options, either directly or as a function that
            returns patches (required for multi-axis plots). If None, nothing
            will be drawn. Defaults to 'head'.
        contours : int | False | None
            The number of contour lines to draw.
            If 0, no contours will be drawn.
        image_interp : str
            The image interpolation to be used.
            All matplotlib options are accepted.
        average : float | None
            The time window around a given time to be used for averaging
            (seconds). For example, 0.01 would translate into window that
            starts 5 ms before and ends 5 ms after a given time point.
            Defaults to None, which means no averaging.
        head_pos : dict | None
            If None (default), the sensors are positioned such that they span
            the head circle. If dict, can have entries 'center' (tuple) and
            'scale' (tuple) for what the center and scale of the head
            should be relative to the electrode locations.

        Returns
        -------
        fig : instance of matplotlib.figure.Figure
           The figure.
        """
        from .. import EvokedArray

        if times is None:
            tmin = 0
            times = 'auto'
        else:
            tmin = times[0]

        # create an evoked
        patterns = EvokedArray(self.patterns_.reshape(info['nchan'], -1),
                               info, tmin=tmin)
        # the call plot_topomap
        return patterns.plot_topomap(times=times, ch_type=ch_type,
                                     layout=layout, vmin=vmin, vmax=vmax,
                                     cmap=cmap, colorbar=colorbar, res=res,
                                     cbar_fmt=cbar_fmt, sensors=sensors,
                                     scale=scale, scale_time=scale_time,
                                     time_format=name_format, size=size,
                                     show_names=show_names, unit=unit,
                                     mask_params=mask_params,
                                     mask=mask, outlines=outlines,
                                     contours=contours, title=title,
                                     image_interp=image_interp, show=show,
                                     head_pos=head_pos, average=average)

    def plot_filters(self, info, times=None, ch_type=None, layout=None,
                     vmin=None, vmax=None, cmap='RdBu_r', sensors=True,
                     colorbar=True, scale=None, scale_time=1e3, unit='a.u.',
                     res=64, size=1, cbar_fmt='%3.1f',
                     name_format='%01d ms', proj=False, show=True,
                     show_names=False, title=None, mask=None,
                     mask_params=None, outlines='head', contours=6,
                     image_interp='bilinear', average=None, head_pos=None):
        """Plot topographic filters of the linear model.

        The filters are used to extract discriminant neural sources from
        the measured data (a.k.a. the backward model).

        Parameters
        ----------
        info : instance of Info
            Info dictionary of the epochs used to fit the linear model.
            If not possible, consider using ``create_info``.
        times : float | array of floats | None.
            The time point(s) to plot. If None, the number of ``axes``
            determines the amount of time point(s). If ``axes`` is also None,
            10 topographies will be shown with a regular time spacing between
            the first and last time instant.
        ch_type : 'mag' | 'grad' | 'planar1' | 'planar2' | 'eeg' | None
            The channel type to plot. For 'grad', the gradiometers are
            collected in pairs and the RMS for each pair is plotted.
            If None, then first available channel type from order given
            above is used. Defaults to None.
        layout : None | Layout
            Layout instance specifying sensor positions (does not need to be
            specified for Neuromag data). If possible, the correct layout file
            is inferred from the data; if no appropriate layout file was found
            the layout is automatically generated from the sensor locations.
        vmin : float | callable
            The value specfying the lower bound of the color range.
            If None, and vmax is None, -vmax is used. Else np.min(data).
            If callable, the output equals vmin(data).
        vmax : float | callable
            The value specfying the upper bound of the color range.
            If None, the maximum absolute value is used. If vmin is None,
            but vmax is not, defaults to np.min(data).
            If callable, the output equals vmax(data).
        cmap : matplotlib colormap | (colormap, bool) | 'interactive' | None
            Colormap to use. If tuple, the first value indicates the colormap
            to use and the second value is a boolean defining interactivity. In
            interactive mode the colors are adjustable by clicking and dragging
            the colorbar with left and right mouse button. Left mouse button
            moves the scale up and down and right mouse button adjusts the
            range. Hitting space bar resets the range. Up and down arrows can
            be used to change the colormap. If None, 'Reds' is used for all
            positive data, otherwise defaults to 'RdBu_r'. If 'interactive',
            translates to (None, True). Defaults to 'RdBu_r'.

            .. warning::  Interactive mode works smoothly only for a small
                amount of topomaps.

        sensors : bool | str
            Add markers for sensor locations to the plot. Accepts matplotlib
            plot format string (e.g., 'r+' for red plusses). If True,
            a circle will be used (via .add_artist). Defaults to True.
        colorbar : bool
            Plot a colorbar.
        scale : dict | float | None
            Scale the data for plotting. If None, defaults to 1e6 for eeg, 1e13
            for grad and 1e15 for mag.
        scale_time : float | None
            Scale the time labels. Defaults to 1e3.
        unit : dict | str | None
            The unit of the channel type used for colorbar label. If
            scale is None the unit is automatically determined.
        res : int
            The resolution of the topomap image (n pixels along each side).
        size : float
            Side length per topomap in inches.
        cbar_fmt : str
            String format for colorbar values.
        name_format : str
            String format for topomap values. Defaults to "%03f ms"
        proj : bool | 'interactive'
            If true SSP projections are applied before display.
            If 'interactive', a check box for reversible selection
            of SSP projection vectors will be show.
        show : bool
            Show figure if True.
        show_names : bool | callable
            If True, show channel names on top of the map. If a callable is
            passed, channel names will be formatted using the callable; e.g.,
            to delete the prefix 'MEG ' from all channel names, pass the
            function lambda x: x.replace('MEG ', ''). If `mask` is not None,
            only significant sensors will be shown.
        title : str | None
            Title. If None (default), no title is displayed.
        mask : ndarray of bool, shape (n_channels, n_times) | None
            The channels to be marked as significant at a given time point.
            Indices set to `True` will be considered. Defaults to None.
        mask_params : dict | None
            Additional plotting parameters for plotting significant sensors.
            Default (None) equals::

                dict(marker='o', markerfacecolor='w', markeredgecolor='k',
                     linewidth=0, markersize=4)

        outlines : 'head' | 'skirt' | dict | None
            The outlines to be drawn. If 'head', the default head scheme will
            be drawn. If 'skirt' the head scheme will be drawn, but sensors are
            allowed to be plotted outside of the head circle. If dict, each key
            refers to a tuple of x and y positions, the values in 'mask_pos'
            will serve as image mask, and the 'autoshrink' (bool) field will
            trigger automated shrinking of the positions due to points outside
            the outline. Alternatively, a matplotlib patch object can be passed
            for advanced masking options, either directly or as a function that
            returns patches (required for multi-axis plots). If None, nothing
            will be drawn. Defaults to 'head'.
        contours : int | False | None
            The number of contour lines to draw.
            If 0, no contours will be drawn.
        image_interp : str
            The image interpolation to be used.
            All matplotlib options are accepted.
        average : float | None
            The time window around a given time to be used for averaging
            (seconds). For example, 0.01 would translate into window that
            starts 5 ms before and ends 5 ms after a given time point.
            Defaults to None, which means no averaging.
        head_pos : dict | None
            If None (default), the sensors are positioned such that they span
            the head circle. If dict, can have entries 'center' (tuple) and
            'scale' (tuple) for what the center and scale of the head
            should be relative to the electrode locations.

        Returns
        -------
        fig : instance of matplotlib.figure.Figure
           The figure.
        """
        from .. import EvokedArray

        if times is None:
            tmin = 0
            times = 'auto'
        else:
            tmin = times[0]

        # create an evoked
        filters = EvokedArray(self.filters_.T.reshape(info['nchan'], -1),
                              info, tmin=tmin)
        # the call plot_topomap
        return filters.plot_topomap(times=times, ch_type=ch_type,
                                    layout=layout, vmin=vmin, vmax=vmax,
                                    cmap=cmap, colorbar=colorbar, res=res,
                                    cbar_fmt=cbar_fmt, sensors=sensors,
                                    scale=scale, scale_time=scale_time,
                                    time_format=name_format, size=size,
                                    show_names=show_names, unit=unit,
                                    mask_params=mask_params,
                                    mask=mask, outlines=outlines,
                                    contours=contours, title=title,
                                    image_interp=image_interp, show=show,
                                    head_pos=head_pos, average=average)


def _set_cv(cv, estimator=None, X=None, y=None):
    """Set the default CV depending on whether clf is classifier/regressor."""
    from sklearn.base import is_classifier

    # Detect whether classification or regression
    if estimator in ['classifier', 'regressor']:
        est_is_classifier = estimator == 'classifier'
    else:
        est_is_classifier = is_classifier(estimator)
    # Setup CV
    if check_version('sklearn', '0.18'):
        from sklearn import model_selection as models
        from sklearn.model_selection import (check_cv, StratifiedKFold, KFold)
        if isinstance(cv, (int, np.int)):
            XFold = StratifiedKFold if est_is_classifier else KFold
            cv = XFold(n_splits=cv)
        elif isinstance(cv, str):
            if not hasattr(models, cv):
                raise ValueError('Unknown cross-validation')
            cv = getattr(models, cv)
            cv = cv()
        cv = check_cv(cv=cv, y=y, classifier=est_is_classifier)
    else:
        from sklearn import cross_validation as models
        from sklearn.cross_validation import (check_cv, StratifiedKFold, KFold)
        if isinstance(cv, (int, np.int)):
            if est_is_classifier:
                cv = StratifiedKFold(y=y, n_folds=cv)
            else:
                cv = KFold(n=len(y), n_folds=cv)
        elif isinstance(cv, str):
            if not hasattr(models, cv):
                raise ValueError('Unknown cross-validation')
            cv = getattr(models, cv)
            if cv.__name__ not in ['KFold', 'LeaveOneOut']:
                raise NotImplementedError('CV cannot be defined with str for'
                                          ' sklearn < .017.')
            cv = cv(len(y))
        cv = check_cv(cv=cv, X=X, y=y, classifier=est_is_classifier)

    # Extract train and test set to retrieve them at predict time
    if hasattr(cv, 'split'):
        cv_splits = [(train, test) for train, test in
                     cv.split(X=np.zeros_like(y), y=y)]
    else:
        # XXX support sklearn.cross_validation cv
        cv_splits = [(train, test) for train, test in cv]

    if not np.all([len(train) for train, _ in cv_splits]):
        raise ValueError('Some folds do not have any train epochs.')

    return cv, cv_splits


def _check_estimator(estimator, get_params=True):
    """Check whether an object has the methods required by sklearn."""
    valid_methods = ('predict', 'transform', 'predict_proba',
                     'decision_function')
    if (
        (not hasattr(estimator, 'fit')) or
        (not any(hasattr(estimator, method) for method in valid_methods))
    ):
        raise ValueError('estimator must be a scikit-learn transformer or '
                         'an estimator with the fit and a predict-like (e.g. '
                         'predict_proba) or a transform method.')

    if get_params and not hasattr(estimator, 'get_params'):
        raise ValueError('estimator must be a scikit-learn transformer or an '
                         'estimator with the get_params method that allows '
                         'cloning.')


def _make_scorer(scoring):
    """Make scorer.

    Parameters
    ----------
    scoring : str | callable
        If str, must be compatible with sklearn sklearn's get_scorer.
        If callable, function with signature ``score_func(y, y_pred,
        **kwargs)``.
    Returns
    -------
    scorer : callable | None
        The scorer.
    """
    from sklearn.metrics import make_scorer, get_scorer
    # If scoring is None (default), the predictions are internally
    # generated by estimator.score(). Else, we must first get the
    # predictions based on the scorer.
    if scoring is None:
        return None
    elif isinstance(scoring, str):
        return get_scorer(scoring)
    else:
        return make_scorer(scoring)
