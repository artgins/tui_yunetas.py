# TUI for yunetas


## Building and publishing the TUI package
```shell
  pip install pdm
  
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
