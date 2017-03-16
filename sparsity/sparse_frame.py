# coding=utf-8
from functools import partial

import pandas as pd
import numpy as np
import datetime as dt
import uuid
from functools import reduce

from pandas.core.common import _default_index
from pandas.indexes.base import _ensure_index
from scipy import sparse

from sparsity.io import traildb_to_coo
from sparsity.indexing import _CsrILocationIndexer, _CsrLocIndexer

class SparseFrame(object):
    """
    Simple sparse table based on scipy.sparse.csr_matrix
    """

    __slots__ = ["_index", "_columns", "_data", "shape", "_multi_index",
                 'ndim', 'iloc', 'loc']

    def __init__(self, data, index=None, columns=None, **kwargs):
        if len(data.shape) != 2:
            raise ValueError("Only two dimensional data supported")
        N,K = data.shape

        if index is None:
            self._index = _default_index(N)
        else:
            #assert len(index) == N
            self._index = _ensure_index(index)


        if columns is None:
            self._columns = _default_index(K)
        else:
            #assert len(columns) == K
            self._columns = _ensure_index(columns)

        if not sparse.isspmatrix_csr(data):
            self._init_csr(sparse.csr_matrix(data, **kwargs))
        else:
            self._init_csr(data)

        self.shape = data.shape

        # register indexers
        self.ndim = 2
        self.iloc = _CsrILocationIndexer(self, 'iloc')
        self.loc = _CsrLocIndexer(self, 'loc')

    def _init_csr(self, csr):
        self._data = sparse.vstack(
            [csr,
             sparse.coo_matrix((1,csr.shape[1])).tocsr()
             ])

    def _get_axis(self, axis):
        if axis == 0:
            return self._index
        if axis == 1:
            return self._columns

    @property
    def index(self):
        return self._index

    @property
    def columns(self):
        return self._columns

    @property
    def data(self):
        return self._data[:-1,:]

    def groupby(self, by=None, level=0):
        """
        simple groupby operation using sparse matrix multiplication. Expects result to be sparse aswell
        :param by: (optional) alternative index
        :return:
        """
        if by is not None and by is not "index":
            assert len(by) == self.data.shape[0]
            by = np.array(by)
        else:
            if level and isinstance(self._index, pd.MultiIndex):
                by = self._multi_index.get_level_values(level).values
            elif level:
                raise ValueError("Connot use level in a non MultiIndex Frame")
            else:
                by = self.index.values
        group_idx = by.argsort()
        gm = _create_group_matrix(by[group_idx])
        grouped_data = self._data[group_idx, :].T.dot(gm).T
        return SparseFrame(grouped_data, index=np.unique(by), columns=self._columns)

    def join(self, other, axis=0, level=None):
        """
        Can be used to stack two tables with identical inidizes
        :param other: another CSRTable or compatible datatype
        :param axis:
        :return:
        """
        if isinstance(self._index, pd.MultiIndex)\
            or isinstance(other._index, pd.MultiIndex):
            raise NotImplementedError()
        if not isinstance(other, SparseFrame):
            other = SparseFrame(other)
        if axis not in set([0, 1]):
            raise ValueError("axis mut be either 0 or 1")
        if axis == 0:
            if np.all(other._columns.values == self._columns.values):
                # take short path if join axes are identical
                data = sparse.vstack([self.data, other.data])
                index = np.hstack([self.index, other.index])
                res = SparseFrame(data, index=index, columns=self._columns)
            else:
                data, new_index = _matrix_join(self._data.T.tocsr(), other._data.T.tocsr(),
                                               self._columns, other._columns)
                res = SparseFrame(data.T.to_csr(),
                                  index=np.concatenate([self.index, other.index]),
                                  columns=new_index)
        elif axis == 1:
            if np.all(self.index.values == other.index.values):
                # take short path if join axes are identical
                data = sparse.hstack([self.data, other.data])
                columns = np.hstack([self._columns, other._columns])
                res = SparseFrame(data, index=self.index, columns=columns)
            else:
                data, new_index= _matrix_join(self._data, other._data,
                                              self.index, other.index)
                res = SparseFrame(data,
                                  index=new_index,
                                  columns=np.concatenate([self._columns, other._columns]))
        return res

    def sort_index(self):
        passive_sort_idx = np.argsort(self._index)
        data = self._data[passive_sort_idx]
        index = self._index[passive_sort_idx]
        return SparseFrame(data, index=index)

    def add(self, other):
        assert np.all(self._columns == other.columns)
        data, new_idx = _aligned_csr_elop(self._data, other._data,
                                          self.index, other.index)
        # new_idx = self._index.join(other.index, how=how)
        res = SparseFrame(data, index=new_idx, columns = self._columns)
        return res


    def __sizeof__(self):
        return super().__sizeof__() + self.index.nbytes + \
               self._columns.nbytes + self._data.data.nbytes + \
               self._data.indptr.nbytes + self._data.indices.nbytes

    def _align_axis(self):
        raise NotImplementedError()

    def __repr__(self, *args, **kwargs):
        return self.head(5).to_string()

    def head(self, n=5):
        n = min(n, len(self._index))
        return pd.DataFrame(self._data[:n].todense(),
                            index=self._index[:n],
                            columns=self._columns)

    def _slice(self, sliceobj):
        return SparseFrame(self._data[sliceobj,:], index=self.index[sliceobj])

    @classmethod
    def concat(cls, tables, axis=0):
        func = partial(SparseFrame.join, axis=axis)
        return reduce(func, tables)

    def _ixs(self, key, axis=0):
        if axis != 0:
            raise NotImplementedError()
        new_idx = self.index[key]
        if not isinstance(new_idx, pd.Index):
            new_idx = [new_idx]
        return SparseFrame(self._data[key,:], index=new_idx)

    @classmethod
    def read_traildb(cls, file, field, ts_unit='s'):
        uuids, timestamps, cols, coo = traildb_to_coo(file, field)
        uuids = np.asarray([uuid.UUID(bytes=x.tobytes()) for x in
                            uuids])
        index = pd.MultiIndex.from_arrays \
            ([pd.CategoricalIndex(uuids),pd.to_datetime(timestamps, unit=ts_unit,)],
             names=('uuid', 'timestamp'))
        return cls(coo.tocsr(), index=index, columns=cols)

    def __setitem__(self, key, value):
        csc = self._data.tocsc()
        val = np.hstack([value, [0]]).reshape(-1,1)
        new_data = sparse.hstack([csc, sparse.csc_matrix(val)])
        self._columns.append(pd.Index([key]))
        self._data = new_data.tocsr()



def _aligned_csr_elop(a, b, a_idx, b_idx, op='_plus_'):
    """Asumme data == 0 at loc[-1]"""
    join_idx, lidx, ridx = a_idx.join(b_idx, return_indexers=True)

    if lidx is None:
        a_new = a[:-1,:]
    else:
        a_new = sparse.csr_matrix(a[lidx])
    if ridx is None:
        b_new = b[:-1,:]
    else:
        b_new = sparse.csr_matrix(b[ridx])

    assert b_new.shape == a_new.shape
    added = a_new._binopt(b_new, op=op)
    return added, join_idx


def _matrix_join(a,b, a_idx, b_idx, how='outer'):
    """Asumme data == 0 at loc[-1]"""
    join_idx, lidx, ridx = a_idx.join(b_idx, return_indexers=True,
                                      how=how)
    if lidx is None:
        a_new = a[:-1,:]
    else:
        a_new = sparse.csr_matrix(a[lidx])
    if ridx is None:
        b_new = b[:-1,:]
    else:
        b_new = sparse.csr_matrix(b[ridx])

    data = sparse.hstack([a_new, b_new])

    return data, join_idx


def _create_group_matrix(group_idx, dtype='f8'):
    """create a matrix based on groupby index labels"""
    if not isinstance(group_idx, pd.Categorical):
        group_idx = pd.Categorical(group_idx, np.unique(group_idx))
    col_idx = group_idx.codes
    row_idx = np.arange(len(col_idx))
    data = np.ones(len(row_idx))
    return sparse.coo_matrix((data, (row_idx, col_idx)),
                             shape=(len(group_idx), len(group_idx.categories)),
                             dtype=dtype).tocsr()


def csr_one_hot_series(s, categories, dtype='f8'):
    """Transform a pandas.Series into a sparse matrix.
    Works by one-hot-encoding for the given categories
    """
    cat = pd.Categorical(s, np.asarray(categories))

    codes = cat.codes
    n_features = len(cat.categories)
    n_samples = codes.size
    mask = codes != -1
    if np.any(~mask):
        raise ValueError("unknown categorical features present %s "
                         "during transform." % np.unique(s[~mask]))
    row_indices = np.arange(n_samples, dtype=np.int32)
    col_indices = codes
    data = np.ones(row_indices.size)
    return sparse.coo_matrix((data, (row_indices, col_indices)),
                             shape=(n_samples, n_features),
                             dtype=dtype).tocsr()


def sparse_aggregate_cs(raw, slice_date, agg_bin, categories,
                        id_col="id", categorical_col="pageId", **kwargs):
    """aggregates clickstream data using sparse data structures"""
    start_date = slice_date - dt.timedelta(days=agg_bin[1])
    end_date = slice_date - dt.timedelta(days=agg_bin[0])

    sliced_cs = raw.loc[start_date:end_date]
    sparse_bagged= sliced_cs.map_partitions(_sparse_groupby_sum_cs,
                                            group_col=id_col,
                                            categorical_col=categorical_col,
                                            categories=categories, meta=SparseFrame).compute(**kwargs)
    data = SparseFrame.concat(sparse_bagged, axis=0)
    data = data.groupby()
    return data


def _sparse_groupby_sum_cs(cs, group_col, categorical_col, categories):
    """transform a dask partition into a bagged sparse matrix"""
    if isinstance(categories, str):
        categories = pd.read_hdf(categories, "/df")
    one_hot = csr_one_hot_series(cs[categorical_col], categories)
    table = SparseFrame(one_hot, columns=categories, index=cs[group_col])
    return table.groupby()


