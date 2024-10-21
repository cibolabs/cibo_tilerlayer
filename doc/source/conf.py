# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'CiboTiler'
copyright = '2024, Sam Gillingham and Neil Flood'
author = 'Sam Gillingham and Neil Flood'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    'sphinx.ext.autodoc', 'numpydoc', 'sphinx.ext.graphviz',
    'sphinx.ext.autosectionlabel', 'sphinx.ext.intersphinx']

templates_path = ['_templates']
exclude_patterns = []
autodoc_mock_imports = ['numpy', 'osgeo']
autodoc_member_order = 'bysource'
# Make sure section targets are unique
autosectionlabel_prefix_document=True



# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'pydata_sphinx_theme'
html_theme_options = {
    "icon_links": [
        {
            "name": "GitHub",
            "url": "https://github.com/cibolabs/cibo_tilerlayer",
            "icon": "fa-brands fa-square-github",
            "type": "fontawesome",
        }
    ]
}
html_static_path = []

numpydoc_show_class_members = False

html_logo = "logo-cibolabs.png"

# -- Options for intersphinx extension ---------------------------------------

intersphinx_mapping = {
    "numpy": ("https://numpy.org/doc/stable", None),
    "python": ("https://docs.python.org/3", None),
    "gdal": ("https://gdal.org/en/latest/api/python_bindings.html", None)
}

