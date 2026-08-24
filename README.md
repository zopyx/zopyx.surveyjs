# zopyx.surveyjs

SurveyJS integration for Plone: create, publish, validate, store, export, and
embed surveys and forms.

## Documentation

The complete documentation is maintained in [`docs/`](docs/index.rst).

- [Online demo](https://demo.privacyforms.studio)
- [Privacy Forms Studio](https://www.privacyforms.studio)
- [Installation](docs/installation.rst)
- [Quick start](docs/quick-start.rst)
- [Configuration](docs/configuration.rst)
- [Endpoints](docs/endpoints.rst)
- [Security](docs/security.rst)
- [Development](docs/development.rst)

## Development

```shell
uv venv --clear
uv pip install -r requirements.txt
./bin/buildout
make test
make docs
```

See [Development](docs/development.rst) for the complete development setup.

## License

GPL-2.0-or-later. SurveyJS Creator licensing is documented by SurveyJS and may
require a commercial license.
