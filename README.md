# TUI for yunetas

> This is the TUI (Terminal User Interface) for [Yuneta Simplified](https://yuneta.io)

<a href="https://yuneta.io/">
    <img src="https://github.com/artgins/yunetas/blob/main/docs/doc.yuneta.io/_static/yuneta-image.svg?raw=true" alt="Icon" width="200" /> <!-- Adjust the width as needed -->
</a>

[Yuneta Simplified](https://yuneta.io) is a development framework about messages and services, based on 
[Event-driven](https://en.wikipedia.org/wiki/Event-driven_programming), 
[Automata-based](https://en.wikipedia.org/wiki/Automata-based_programming) 
and [Object-oriented](https://en.wikipedia.org/wiki/Object-oriented_programming) 
programming.

Yuneta is based in functions, but it manages a system of virtual classes 
defined by programmatically and schematically.  

All his philosophy is based on that virtual classes (namely GClass or class G).

All architecture done by configuration, based in schema,
easy to see by human eye. 
Of course, you have an API functions to change configuration and data in real time. 

For [Linux](https://en.wikipedia.org/wiki/Linux) and [RTOS/ESP32](https://www.espressif.com/en/products/sdks/esp-idf). 

Versions in C, Javascript and (TODO) Python.

For more details, see [doc.yuneta.io](https://doc.yuneta.io) 



[pypi-badge]: https://img.shields.io/pypi/v/yunetas


# How build this package


## Install pdm

This package use `pdm` to build and publish.

```shell
    pip install pdm
    pip install cement
    pip install plumbum
    pip install fastapi
    pip install "uvicorn[standard]"
    pip install "typer[all]"
```

## Build and publish
```shell
  # Firstly change the version (explained below)
  # Next go to source root folder
  pdm build
  pdm publish --username __token__ --password <your-api-token> # (me: the full command is saved in publish-tui_yunetas.sh)
```

## Install the package in editable mode using pip from the source root folder:

```shell
  pip install -e .
```

## Change the version

> Edit the `__version__.py` file and change the variable `__version__`.
Then [build and publish](build-and-publish)
