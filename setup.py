from distutils.core import setup

setup(name='novacode', 
      version='1.0',
      description='An SQL like interface for .csv files.',
      author='Cathal Coffey',
      author_email='coffey.cathal@gmail.com',
      url='https://github.com/ccoffey/sql4csv',
      py_modules=['novacode'],
      requires=['pyparsing'],
     )
