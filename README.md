![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/some00/comics_viewer/.github%2Fworkflows%2Fci.yml)
![Codecov](https://img.shields.io/codecov/c/github/some00/comics_viewer)

# Comics Viewer2

A comic book reader written in Python supporting `.cbz` and `.cbr` formats, optimized for touch screens.

## Marking panels/tiles

There is a feature that lets you mark panels using a stylus pen. My goal was to generate enough data to train a model to automatically detect panels. This was the main idea behind starting development of my own comics reader.

## Installation

Tested on Arch Linux. Other distributions may work but are unverified. Feel free to open a PR or drop me an email if you manage to run it on Windows.

### CPython

```
pacman -S python-gobject python-pillow python-shapely python-humanize \
          python-sqlalchemy python-rarfile python-opengl python-numpy \
          python-transforms3d
```

### PyPy3

```
virtualenv -p pypy3 .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

Start the application with the following command:

```
PYTHONPATH=`pwd`/src python -m comics_viewer \
    --cache <path-to-thumb-and-cover-cache> \
    --library <path-to-your-comic-books> \
    --database <path-to-sqlite-database-of-metadata>
```

The `cache` and `database` paths default to the current working directory and can be omitted, but `library` must be set.

## Panels

### View

Here you can view the currently opened comic book. Tapping left or right (relative to the current page orientation) changes pages; swiping left/right does the same. Swiping up or down enters or exits fullscreen mode.

### Library

The library panel lets you browse your comics. The plus button adds a new category, while the minus button removes the currently opened category.

### Manage

In the Manage screen, comic metadata can be edited. This page won’t let you exit if you have pending changes until you press either **Save** or **Discard**.

The autoindex, copy title, and paste title features are useful for bulk editing:

- **Autoindex** uses the index of the first selected comic and increments it for each subsequent selected comic.
- **Copy title** copies the title of the currently selected comic to the application clipboard.
- **Paste title** pastes it to all currently selected comics.
