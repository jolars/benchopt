import os
import stat
import warnings
import configparser
import yaml
from pathlib import Path
from collections.abc import Iterable
from benchopt.constants import PLOT_KINDS


BOOLEAN_STATES = configparser.ConfigParser.BOOLEAN_STATES
CONFIG_FILE_NAME = 'benchopt.yml'

# Global config file should be only accessible to current user as it stores
# sensitive information such as the Github token.
GLOBAL_CONFIG_FILE_MODE = stat.S_IFREG | stat.S_IRUSR | stat.S_IWUSR

DEFAULT_GLOBAL_CONFIG = {
    'debug': False,
    'raise_install_error': False,
    'github_token': None,
    'data_dir': './data/',
    'conda_cmd': 'conda',
    'shell': os.environ.get('SHELL', 'bash'),
    'cache': None,
}
"""
* ``debug``: If set to true, enable debug logs.
* ``raise_install_error``, *boolean*: If set to true, raise error when
  install fails.
* ``github_token``, *str*: token to publish results on ``benchopt/results``
  via github.
* ``conda_cmd``, *str*: can be used to give the path to ``conda`` if it is
  not directly installed on ``$PATH``. This can also be used to use ``mamba``
  to install benchmarks instead of conda. See :ref:`config_mamba`.
* ``shell``, *str*: can be used to specify the shell to use. Default to
  `SHELL` from env if it exists and ``'bash'`` otherwise.
* ``cache``, *str*: can be used to specify where the cache for the benchmarks
  should be stored. By default, the cache files are stored in the benchmark
  directory, under the folder __cache__. Setting this configuration would
  results in having the cache for benchmark `B1` stored in `${cache}/B1/`.
"""

DEFAULT_BENCHMARK_CONFIG = {
    "plots": list(PLOT_KINDS), "plot_configs": {}
}

"""
* ``plots``, *list*: Select the plots to display for the benchmark. Should be
  valid plot kinds. The list can simply be one item by line, with each item
  indented, as:

  .. code-block:: yaml

    plots:
    - objective_curve
    - suboptimality_curve
    - relative_suboptimality_curve
    - bar_chart

* ``plot_configs``, *list*: list of saved views that can be easily display for
  the plot. Each view corresponds to a name, with specified values to select
  either:

    ``dataset``,  ``objective``, ``objective_column``, ``kind``, ``scale``,
    ``with_quantiles``, ``xaxis_type``, ``xlim``, ``ylim``

  Values that are not specified by the view are left as is when setting the
  view in the interface. An example of views is:

  .. code-block:: yaml

    plot_configs:
      linear_objective:
          kind: objective_curve
          ylim: [0.0, 1.0]
          scale: linear
      view2:
          objective_column: objective_score_train
          kind: suboptimality_curve
          ylim: [1e-10, 1.0]
          scale: loglog

  These views can be easily created from the interactive HTML page, by hitting
  the ``Save as view`` button in the plot controls and downloading eiher the
  new HTML file to save them or the config file in th erepo of the benchmark,
  so that these saved views are embeded in the next plot results automatically.
"""


def get_global_config_file():
    "Return the global config file."

    config_file = os.environ.get('BENCHOPT_CONFIG', None)
    if config_file is not None:
        config_file = Path(config_file)
        assert config_file.exists(), (
            f"BENCHOPT_CONFIG is set but file {config_file} does not exists.\n"
            f"It can be created with `touch {config_file.resolve()}`."
        )
    else:

        def check_ini(path):
            # If a path does not exist but exist with suffix .ini, returns it.
            if not path.exists() and path.with_suffix('.ini').exists():
                return path.with_suffix('.ini')
            return path

        config_file = check_ini(Path('.') / CONFIG_FILE_NAME)
        if not config_file.exists():
            config_file = check_ini(Path.home() / '.config' / CONFIG_FILE_NAME)

    # check that the global config file is only accessible to current user as
    # it stores critical information such as the github token.
    if (config_file.exists()
            and config_file.stat().st_mode != GLOBAL_CONFIG_FILE_MODE):
        mode = oct(config_file.stat().st_mode)[5:]
        expected_mode = oct(GLOBAL_CONFIG_FILE_MODE)[5:]
        warnings.warn(
            f"BenchOpt config file {config_file} is with mode {mode}.\n"
            "As it stores sensitive information such as the github token,\n"
            f"it is advised to use mode {expected_mode} (user rw only)."
        )

    return config_file


def convert_ini_to_yml(config_file):
    warnings.warn(
        f"'.ini' config files are deprecated. Existing file {config_file} "
        "will be converted to `.yml` file. You can delete it."
    )
    config_ini = configparser.ConfigParser()
    config_ini.read(config_file)
    config = {}
    for sec in config_ini.sections():
        default = (
            DEFAULT_GLOBAL_CONFIG if sec == "benchopt"
            else DEFAULT_BENCHMARK_CONFIG
        )
        options = list(config_ini[sec].keys())
        values = {
            key: parse_value(config_ini.get(sec, key), default[key])
            for key in options
        }
        if sec == "benchopt":
            config.update(**values)
        else:
            config[sec] = values
    config_file = config_file.with_suffix('.yml')
    config_file.touch(mode=GLOBAL_CONFIG_FILE_MODE)
    with config_file.open('w') as f:
        yaml.safe_dump(config, f)


def set_setting(name, value, config_file=None, benchmark_name=None):
    if config_file is None:
        config_file = get_global_config_file()

    # Get default value
    default_config = DEFAULT_BENCHMARK_CONFIG
    if benchmark_name is None:
        benchmark_name = 'benchopt'
        default_config = DEFAULT_GLOBAL_CONFIG

    if name not in default_config:
        print(
            f'ERROR: {name} is not a setting for {benchmark_name}. Possible '
            'settings are:\n  - ' + '\n  - '.join(default_config)
        )
        raise SystemExit(1)
    default_value = default_config[name]

    # Get global config file
    config = configparser.ConfigParser()
    config.read(config_file)

    if benchmark_name not in config:
        config[benchmark_name] = {}

    config[benchmark_name][name] = reverse_parse(default_value, value)

    # Create config file with the correct permission.
    if not config_file.exists():
        config_file.touch(mode=GLOBAL_CONFIG_FILE_MODE)

    with config_file.open('w') as f:
        config.write(f)


def get_setting(name, config_file=None, benchmark_name=None,
                default_config=None):
    """Get setting in order:
        1. env var
        2. config file
        3. default value

    Parameters
    ----------
    name : str
        Name of the config parameter to retrieve.
    config_file : str | Path
        Path to a config file from which the setting can be retreives. When
        it is not provided, default to the global benchopt config file.
    benchmark_name : str
        Name of the benchmark for which the setting are retrieved.
    default_config : dict
        Extra default values, typically used to pass configs saved in the
        results parquet files.
    """

    if config_file is None:
        config_file = get_global_config_file()

    # Get default value
    default_config_ = DEFAULT_BENCHMARK_CONFIG
    if benchmark_name is None:
        default_config_ = DEFAULT_GLOBAL_CONFIG
    assert name in default_config_, (
        f"Unknown config key {name}. Valid key are {list(default_config_)}"
    )
    default_config = {} if default_config is None else default_config
    default_value = default_config.get(name, default_config_[name])

    # Handle deprecated .ini config file by automatically
    # converting them to .yml.
    if config_file.suffix == ".ini":
        convert_ini_to_yml(config_file)
        config_file = config_file.with_suffix('.yml')

    # Load the config from the yaml file if the file exists.
    if config_file.exists():
        with open(config_file, "r") as f:
            config = yaml.safe_load(f)
    else:
        config = {}

    # Get value from config file or keep the default value.
    if benchmark_name in config.keys():
        value = config[benchmark_name].get(name, default_value)
    else:
        value = config.get(name, default_value)

    # Get the value for the environment variable or keep the value from config
    # file or default.
    env_var_name = f"BENCHOPT_{name.upper()}"
    value = os.environ.get(env_var_name, value)

    # Parse the value to the correct type
    value = parse_value(value, default_value)

    return value


def parse_value(value, default_value):
    if isinstance(default_value, bool):
        # convert string 0/1/true/false/yes/no/on/off to boolean
        if isinstance(value, str):
            value = value.lower()
            try:
                value = BOOLEAN_STATES[value]
            except KeyError:
                warnings.warn(
                    f'setting {value} could not be parsed as a '
                    'boolean. Should be one of '
                    f'{list(BOOLEAN_STATES.keys())}'
                )
                value = default_value
        assert isinstance(value, bool)
    elif isinstance(default_value, list):
        # parse multiline statements as list with separators '\n' and ','
        if isinstance(value, str):
            values = value.split()
            values = [v.strip() for value in values
                      for v in value.split(',') if v != '']
            value = values
        assert isinstance(value, list), value

    return value


def reverse_parse(default_value, value):
    if isinstance(value, bool) or isinstance(default_value, bool):
        if isinstance(value, bool):
            assert isinstance(default_value, bool)
            value = 'true' if value else 'false'
        else:
            assert value.lower() in BOOLEAN_STATES, (
                "boolean setting should have value in "
                f"{list(BOOLEAN_STATES.keys())}"
            )
    elif isinstance(value, Iterable) and not isinstance(value, str):
        assert isinstance(default_value, list)
        value = '\n' + '\n'.join(value)

    return value


# Make sure we load the lattest value of the config parameter, even if it is
# changed. This should only be useful for testing purposes.
class BooleanFlag(object):
    def __init__(self, name):
        self.name = name

    def __bool__(self):
        return get_setting(self.name)


DEBUG = BooleanFlag('debug')
RAISE_INSTALL_ERROR = BooleanFlag('raise_install_error')
