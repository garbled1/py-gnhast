from setuptools import setup

# read the contents of your README file
from os import path
this_directory = path.abspath(path.dirname(__file__))
with open(path.join(this_directory, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='gnhast',
    version='0.1.3',
    description='Minimal code to create a gnhast collector',
    license='GPL',
    packages=['gnhast'],
    author='Tim Rightnour',
    author_email='thegarbledone@gmail.com',
    keywords=['homeautomation', 'ha', 'domotic', 'ghnast'],
    url='https://github.com/garbled1/py-gnhast',
    project_urls={
        'Gnhast API Documentation': 'https://garbled1.github.io/gnhast/',
        'Gnhast Code Documentation': 'https://codedocs.xyz/garbled1/gnhast/',
        'Gnhast Blog': 'http://gnhast.blogspot.com/',
        'Gnhast Main Repo': 'https://github.com/garbled1/gnhast',
        'Gnhast Python Collectors': 'https://github.com/garbled1/gnhast-python-collectors',
    },
    install_requires=[
        'pint',
        'ply',
        'py-flags'
    ],
    python_requires='>=3.5',
    long_description=long_description,
    long_description_content_type='text/markdown'
)
