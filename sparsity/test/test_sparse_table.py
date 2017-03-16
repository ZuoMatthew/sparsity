# coding=utf-8
import unittest
import os
import datetime as dt

import pandas as pd
import numpy as np
import pytest

#from dask.async import get_sync
#import dask.dataframe as dd
from sparsity import SparseFrame, csr_one_hot_series #, sparse_aggregate_cs

# 2017 starts with a sunday
@pytest.fixture()
def sampledata():
    def gendata(n):
        sampledata = pd.DataFrame(dict(date=pd.date_range("2017-01-01", periods=n)))
        sampledata["weekday"] = sampledata.date.dt.weekday_name
        sampledata["id"] = np.tile(np.arange(7), len(sampledata)//7+6)[:len(sampledata)]
        return sampledata
    return gendata


def test_groupby():
    shuffle_idx = np.random.permutation(np.arange(100))
    index = np.tile(np.arange(10), 10)
    data = np.vstack([np.identity(10) for i in range(10)])
    t = SparseFrame(data[shuffle_idx, :], index=index[shuffle_idx])
    res = t.groupby().data.todense()
    assert np.all(res == (np.identity(10)*10))


def test_simple_join():
    t = SparseFrame(np.identity(10))

    res1 = t.join(t, axis=0).data.todense()
    correct = np.vstack([np.identity(10), np.identity(10)])
    assert np.all(res1 == correct)

    res2 = t.join(t, axis=1).data.todense()
    correct = np.hstack([np.identity(10), np.identity(10)])
    assert np.all(res2 == correct)


def test_complex_join(complex_example):
    first, second, third = complex_example
    correct = pd.DataFrame(first.data.todense(),
                           index=first.index)\
                .join(pd.DataFrame(second.data.todense(),
                                   index=second.index), how='left',
                                   rsuffix='_second')\
                .join(pd.DataFrame(third.data.todense(),
                                   index=third.index), how='left',
                                   rsuffix = '_third')\
                .sort_index().fillna(0)

    res = first.join(second, axis=1).join(third, axis=1)\
        .sort_index().data.todense()
    assert np.all(correct.values == res)

    # res = right.join(left, axis=1).data.todense()
    # assert np.all(correct == res)


def test_mutually_exclusive_join():
    left = SparseFrame(np.identity(5), index=np.arange(5))
    right = SparseFrame(np.identity(5), index=np.arange(5,10))
    correct = np.vstack([np.hstack([np.identity(5), np.zeros((5,5))]),
                         np.hstack([np.zeros((5, 5)), np.identity(5)])])
    res = left.join(right, axis=1)
    assert np.all(res.data.todense() == correct)

def test_iloc():
    sf = SparseFrame(np.identity(5))

    assert np.all(sf.iloc[:2].data.todense() == np.identity(5)[:2])
    assert np.all(sf.iloc[[3,4]].data.todense() == np.identity(5)[[3,4]])
    assert np.all(sf.iloc[3].data.todense() == np.identity(5)[3])

def test_loc():
    sf = SparseFrame(np.identity(5), index=list("ABCDE"))

    assert np.all(sf.loc[:'B'].data.todense() == np.identity(5)[:2])

    sf = SparseFrame(np.identity(5), pd.date_range("2016-10-01", periods=5))
    assert np.all(sf.loc['2016-10-01':"2016-10-03"].data.todense() ==
                  np.identity(5)[:3])
    #assert np.all(sf.loc[['D', 'E']].data.todense() == np.identity(5)[[3,
    # 4]])
    # assert np.all(sf.loc['D'].data.todense() == np.identity(5)[3])

def test_column_assign():
    sf = SparseFrame(np.identity(5))
    sf[6] = np.ones(5)
    correct = np.hstack([np.identity(5), np.ones(5).reshape(-1,1)])
    assert np.all(correct == sf.data.todense())

@pytest.fixture()
def complex_example():
    first = np.identity(10)
    second = np.zeros((4, 10))
    third = np.zeros((4, 10))
    np.fill_diagonal(second, 10)
    np.fill_diagonal(third, 20)
    # place diagonals at correct start index
    second = second[:, [4, 5, 0, 1, 2, 3, 6, 7, 8, 9]]
    third = third[:, np.asarray([4, 5, 6, 7, 8, 9, 0, 1, 2, 3])]

    shuffle_idx = np.arange(10)
    np.random.shuffle(shuffle_idx)

    first = SparseFrame(first[shuffle_idx], index=np.arange(10)[
        shuffle_idx])

    shuffle_idx = np.arange(4)
    np.random.shuffle(shuffle_idx)

    second = SparseFrame(second[shuffle_idx], index=np.arange(2,
                                                              6)[shuffle_idx])

    shuffle_idx = np.arange(4)
    np.random.shuffle(shuffle_idx)

    third = SparseFrame(third[shuffle_idx], index=np.arange(6,
                                                            10)[shuffle_idx])
    return first, second, third

def test_add_total_overlap(complex_example):
    first, second, third = complex_example
    correct = first.sort_index().data.todense()
    correct[2:6, :] += second.sort_index().data.todense()
    correct[6:, :] += third.sort_index().data.todense()

    res = first.add(second).add(third).sort_index()

    assert np.all(res.data.todense() == correct)


def test_csr_one_hot_series(sampledata):
    categories= ['Sunday', 'Monday', 'Tuesday', 'Wednesday',
                 'Thursday', 'Friday', 'Saturday']
    one_hot = csr_one_hot_series(sampledata(49)["weekday"], categories)
    res = SparseFrame(one_hot).groupby(np.tile(np.arange(7),
                                            7)).data.todense()
    assert np.all(res == np.identity(7) * 7)


def test_read_traildb(testdb):
    res = SparseFrame.read_traildb(testdb, 'action')
    assert res.shape == (9,3)


def test_groupby_traildb(testdb):
    pass


def test_add_traildb(testdb):
    simple = SparseFrame.read_traildb(testdb, 'action')
    doubled = simple.add(simple)##
    # = simple.data.todense()*2)


def test_subtract_traildb(testdb):
    pass


# def test_aggregate(testdata):
#     categories = ['Sunday', 'Monday', 'Tuesday', 'Wednesday',
#                   'Thursday', 'Friday', 'Saturday']
#     df = testdata.set_index("date")
#     raw_cs = dd.from_pandas(df, chunksize=50)
#     os.makedirs("/tmp/drtools/sparse-test/", exist_ok=1)
#     raw_cs.to_hdf("/tmp/drtools/sparse-test/*.h5", "/df", lock=False, mode="w", get=get_sync)
#     raw_cs = dd.read_hdf("/tmp/drtools/sparse-test/*.h5", "/df", sorted_index="index", lock=False)
#     result = sparse_aggregate_cs(raw_cs, categories=categories,
#                                  slice_date=dt.date(2017,12,30),
#                                  agg_bin=(0,356),
#                                  categorical_col="weekday", get=get_sync)
#     assert np.all(np.identity(7) * 51 == result.data.todense())
