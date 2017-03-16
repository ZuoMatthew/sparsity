import numpy as np
from distutils.core import setup, Extension

from Cython.Build import cythonize

ext = Extension("sparsity._traildb",
                        ['sparsity/_traildb.pyx',
                         'sparsity/src/traildb_coo.c',
                         'sparsity/src/hashtable.c',
                         'sparsity/src/linklist.c'],
                include_dirs=['/usr/local/include/', np.get_include()],
                libraries=["traildb"])

setup(
    name='sparsity',
    version='0.1',
    ext_modules = cythonize([ext]),
    author='Alan Hoeng',
    author_email='alan.f.hoeng@gmail.com',
    packages=['sparsity'],
    install_requires=[
                        'pandas>=0.19.2',
                        'scipy>=0.18.1',
                        'numpy>=1.12.0'
                    ],
    zip_safe=False
)