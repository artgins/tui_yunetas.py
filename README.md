# TUI for yunetas

## Install pdm

This package use `pdm` to build and publish.

```shell
  pip install pdm
```

## Build and publish
```shell
  # Firstly go to source root folder
  pdm build
  pdm publish --username __token__ --password <your-api-token> # (me: the full command is saved in publish-tui_yunetas.sh)
```

## Install the package in editable mode using pip from the source root folder:

```shell
  pip install -e .
```

## Change the version

> Edit the `__version__.py` file and change the variable `__version__`.
Then [build and publish](#build-and-publish)
