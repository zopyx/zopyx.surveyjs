# zopyx.surveyjs

## What is zopyx.surveyjs

`zopyx.surveyjs` integrates the Javascript framework
[SurveyJS](https://surveyjs.io) into Plone. A survey in SurveyJS is represented
through a JSON datastructure, the polls are also represented as JSON.

SurveyJS consistent of serveral components:

- the SurveyJS `Library` which is open-source and rendered a poll given through
  its JSON representation within the browser

- the SurveyJS `Creator` is a visual survey designer/form builder for SurveyJS.
  The source code of the `Creator` is freely available. The `Creator` is not available
  for *free commercial usage*. Commercial usage requires a developer license.

- there is also a `PDF Export` and `Analytics Pack` available.

In any case, check the [SurveyJS license](https://surveyjs.io/Licenses).

## Background

This implementation is funded through a customer project from the educational
sector.  With a very small number of persons (1-2) using this tool. The costs
for one or two developer license are in this case neglectable compared to the
benefits. The decision for using SurveyJS for a poll functionality in Plone
followed a after an in-depth evaluation of various options. Unfortunately,
we could not find any other suitable solution as free/open-source software.
A mixture of commercial and free components are acceptable for us, if there is a
certain value added to the project compared to less powerfull free/open-source tools.


## Installation

Add `zopyx.surveyjs` to your buildout, re-run buildout and install it within Plone.

For Typesense installation, please check the installation docs of Typesense
(either for installation through Docker or through the standalone binary).

There is no public release at this time. You need to install `zopyx.surveyjs`
using `mr.developer` as source checkout from Github.
  

- [SurveyJS website](https://surveyjs.io)

## Author

Andreas Jung | info@zopyx.com | www.zopyx.com

Paid service for `zopyx.surveyjs` is available on request.
