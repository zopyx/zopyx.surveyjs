# zopyx.surveyjs

SurveyJS integration for Plone: create, publish, validate, store, export, and
embed surveys and forms.

## Online resources

- **Documentation** — installation, configuration, usage, endpoints, security,
  and development reference: [docs.privacyforms.studio](https://docs.privacyforms.studio)
- **Online demo** — try Privacy Forms Studio in a running Plone instance:
  [demo.privacyforms.studio](https://demo.privacyforms.studio)
- **Website** — product information and services:
  [www.privacyforms.studio](https://www.privacyforms.studio)

### Documentation topics

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
